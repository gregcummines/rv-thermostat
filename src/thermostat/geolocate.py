#!/usr/bin/env python3
"""
GeoLocator + OpenWeather helper

- No external hardware required.
- No ipinfo token required (uses https://ipinfo.io/json anonymously).
- Optional Wi-Fi scanning (no WPS call; just counts/sample for diagnostics).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None

if TYPE_CHECKING:
    from src.thermostat.gps_reader import GPSReader
else:
    GPSReader = None  # type: ignore


# =============================================================================
# GeoLocator
# -----------------------------------------------------------------------------
# PURPOSE
#   A lightweight, "configure once, call many times" helper for obtaining a
#   coarse-but-useful location (city, region/state, lat, lon) on a Raspberry Pi
#   without extra hardware. Optimized for frequent weather polling (e.g., 90s).
#
# WHAT IT DOES
#   • Uses IP-based geolocation via ipinfo.io (no key required)
#       - Returns: city, region (state), lat, lon (parsed from "loc")
#       - Notes: accuracy is city-level; good enough for weather; ~1000 req/day
#   • (Optional) Performs periodic Wi-Fi scans using `iw` to measure environment
#       - Gathers nearby BSSIDs (AP MACs) + sample; NO external WPS call
#       - Useful for diagnostics / future upgrade to Google Geolocation, etc.
#   • Caches results with independent TTLs for IP lookup and Wi-Fi scan
#       - Avoids blocking every call; keeps your 90-second loop snappy
#   • Optional on-disk cache for persistence across restarts
#
# HOW IT USES Wi-Fi (no external provider by default)
#   1) Runs `iw dev <iface> scan` (typically iface = "wlan0").
#   2) Parses BSSID lines (and may sample a few for logging/inspection).
#   3) Stores only counts/sample/timestamp; does NOT resolve to coordinates.
#      (If you later add a Wi-Fi Positioning Service, you can plug it in.)
#
# HOW IT USES ipinfo.io
#   1) Calls https://ipinfo.io/json (no token required).
#   2) Reads "city", "region", and "loc" (e.g., "44.98,-93.27") → lat/lon.
#   3) Caches result with timestamp; subsequent calls reuse until TTL expires.
#
# ALGORITHM (get_location):
#   • If cached IP geolocation is younger than ip_ttl_sec → return cached.
#   • Else fetch fresh ipinfo result → update cache → return fresh.
#   • Independently, if use_wifi=True and Wi-Fi scan is older than wifi_ttl_sec,
#     run a scan and update Wi-Fi cache (does not affect coordinates by itself).
#
# DESIGN GOALS
#   • Synchronous, small, dependency-light.
#   • Predictable latency for tight polling loops (e.g., every 90 seconds).
#   • Encapsulated state (no module-level globals), clear configuration in __init__.
#
# RETURN SHAPE (get_location):
#   {
#     "city": str | None,
#     "region": str | None,
#     "lat": float | None,
#     "lon": float | None,
#     "method": "ipinfo" | "cache" | None,   # how the coords were obtained
#     "provider": "ipinfo" | None,
#     "ip_checked_at": int,                  # epoch seconds (last IP lookup)
#     "ip_age_sec": int,                      # age of IP result
#     "wifi_checked_at": int,                # epoch seconds (last Wi-Fi scan)
#     "wifi_age_sec": int,                    # age of Wi-Fi scan
#     "wifi_count": int,                      # APs seen last scan
#     "wifi_sample": List[str],               # up to 5 BSSIDs
#     "source": "fresh" | "cache"             # freshness of THIS return
#   }
#
# CONFIGURATION (constructor kwargs):
#   • interface: str               - Wi-Fi interface name (default "wlan0")
#   • ip_ttl_sec: int              - how long to cache IP geolocation (default 20m)
#   • wifi_ttl_sec: int            - how long to cache Wi-Fi scan (default 60m)
#   • use_wifi: bool               - enable periodic Wi-Fi scanning (default False)
#   • cache_file: Optional[str]    - JSON path to persist cache (e.g. "/tmp/loc.json")
#
# PERFORMANCE / LATENCY
#   • ipinfo lookup: ~50–300 ms typical; timeout set small (e.g., 5 s)
#   • iw Wi-Fi scan: ~1–3 s in most environments; done on its own TTL cadence
#   • get_location calls are O(1) when cache is fresh (fast path).
#
# ERROR HANDLING
#   • Network failures return the last cached values when available.
#   • If nothing is cached and lookups fail, fields are None and you can retry.
#
# THREAD SAFETY
#   • Designed for single-process polling. If multiple processes share cache_file,
#     add external locking as needed.
# =============================================================================
class GeoLocator:
    def __init__(
        self,
        *,
        interface: str = "wlan0",
        ip_ttl_sec: int = 20 * 60,
        wifi_ttl_sec: int = 60 * 60,
        use_wifi: bool = False,
        cache_file: Optional[str] = None,
        http_timeout_sec: int = 5,
        gps_reader: Optional['GPSReader'] = None,
    ) -> None:
        self.interface = interface
        self.ip_ttl_sec = max(1, int(ip_ttl_sec))
        self.wifi_ttl_sec = max(1, int(wifi_ttl_sec))
        self.use_wifi = bool(use_wifi)
        self.cache_file = cache_file
        self.http_timeout_sec = max(1, int(http_timeout_sec))

        self._ip: Optional[Dict[str, Any]] = None
        self._ip_checked_at: int = 0
        self._wifi: Optional[Dict[str, Any]] = None
        self._wifi_checked_at: int = 0

        # Pre-resolve `iw` path once (best-effort)
        self._iw_cmd = self._resolve_iw()

        # Load persisted cache if provided
        self._load_cache_file()

        # Prefer GPS if provided and enabled
        gr = gps_reader
        self._gps_reader = gr if (gr and getattr(gr, "is_enabled", lambda: False)()) else None

        self._log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._log.info("GeoLocator init iface=%s ip_ttl=%s wifi_ttl=%s use_wifi=%s cache=%s (gps_reader=%s)",
                       interface, ip_ttl_sec, wifi_ttl_sec, use_wifi, cache_file, bool(self._gps_reader))

    # ---------- Public API ----------

    def get_location(self) -> dict | None:
        """
        Returns dict with at least lat/lon.
        Prefers GPSReader (if injected/enabled), then falls back to existing Wi‑Fi/IP logic.
        """
        # 1) Prefer GPS
        if self._gps_reader is not None:
            gps_loc = None
            try:
                gps_loc = self._gps_reader.get_location_if_ready()
            except Exception as e:
                self._log.debug("GPSReader error: %s", e)
            if gps_loc:
                self._log.debug("GeoLocator: using GPS location %s", gps_loc)
                return gps_loc

        # 2) Fallbacks (use your existing Wi‑Fi/IP code below)
        now = int(time.time())

        # Periodic Wi-Fi scan (diagnostic only; no WPS resolution here)
        if self.use_wifi and self._is_stale(self._wifi_checked_at, self.wifi_ttl_sec):
            self._wifi = self._scan_wifi()
            self._wifi_checked_at = now
            self._save_cache_file()

        # IP geolocation refresh (authoritative for coords)
        source = "cache"
        if self._is_stale(self._ip_checked_at, self.ip_ttl_sec) or not self._ip:
            fresh = self._ipinfo_lookup()
            if fresh:
                self._ip = fresh
                self._ip_checked_at = now
                self._save_cache_file()
                source = "fresh"

        ip_age = max(0, now - self._ip_checked_at) if self._ip_checked_at else 0
        wifi_age = max(0, now - self._wifi_checked_at) if self._wifi_checked_at else 0
        ip = self._ip or {}
        wifi = self._wifi or {"wifi_count": 0, "sample": []}

        loc = {
            "city": ip.get("city"),
            "region": ip.get("region"),
            "lat": ip.get("lat"),
            "lon": ip.get("lon"),
            "method": ip.get("method"),
            "provider": ip.get("provider"),
            "ip_checked_at": self._ip_checked_at,
            "ip_age_sec": ip_age,
            "wifi_checked_at": self._wifi_checked_at,
            "wifi_age_sec": wifi_age,
            "wifi_count": int(wifi.get("wifi_count", 0)),
            "wifi_sample": wifi.get("sample", []),
            "source": source,
        }
        self._log.debug("Location: %s", {k: loc.get(k) for k in ("city", "region", "lat", "lon")})
        return loc

    # ---------- Internal helpers ----------

    @staticmethod
    def _is_stale(last_ts: int, ttl_sec: int) -> bool:
        if last_ts <= 0:
            return True
        return (time.time() - last_ts) >= ttl_sec

    def _load_cache_file(self) -> None:
        if not self.cache_file:
            return
        if not os.path.exists(self.cache_file):
            return
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._ip = data.get("ip") if isinstance(data.get("ip"), dict) else None
                self._ip_checked_at = int(data.get("ip_checked_at") or 0)
                self._wifi = data.get("wifi") if isinstance(data.get("wifi"), dict) else None
                self._wifi_checked_at = int(data.get("wifi_checked_at") or 0)
        except Exception:
            # Corrupt or unreadable cache; start clean
            self._ip = None
            self._ip_checked_at = 0
            self._wifi = None
            self._wifi_checked_at = 0

    def _save_cache_file(self) -> None:
        if not self.cache_file:
            return
        tmp_path = f"{self.cache_file}.tmp"
        payload = {
            "ip": self._ip,
            "ip_checked_at": self._ip_checked_at,
            "wifi": self._wifi,
            "wifi_checked_at": self._wifi_checked_at,
        }
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, self.cache_file)  # atomic on POSIX
        except Exception:
            # Best-effort; ignore cache write failures
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _ipinfo_lookup(self) -> Optional[Dict[str, Any]]:
        """Query ipinfo.io/json and parse city/region/loc → dict or None."""
        if requests is None:
            return None
        url = "https://ipinfo.io/json"
        try:
            r = requests.get(url, timeout=self.http_timeout_sec)
            if not r.ok:
                return None
            # Defensive: ensure JSON
            try:
                data = r.json()
            except ValueError:
                return None
            if not isinstance(data, dict):
                return None

            city = data.get("city")
            region = data.get("region")
            loc = data.get("loc")  # "lat,lon"
            lat, lon = None, None
            if isinstance(loc, str) and "," in loc:
                parts = loc.split(",")
                try:
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                except (ValueError, IndexError):
                    lat, lon = None, None

            return {
                "city": city if isinstance(city, str) else None,
                "region": region if isinstance(region, str) else None,
                "lat": lat,
                "lon": lon,
                "method": "ipinfo" if lat is not None and lon is not None else None,
                "provider": "ipinfo",
            }
        except requests.exceptions.RequestException:
            return None

    def _resolve_iw(self) -> Optional[str]:
        """Find an 'iw' binary path (returns None if not found)."""
        # Common locations, plus PATH lookup
        candidates = ["/sbin/iw", "/usr/sbin/iw", "/usr/bin/iw", "/bin/iw"]
        for c in candidates:
            if os.path.exists(c) and os.access(c, os.X_OK):
                return c
        found = shutil.which("iw")
        return found

    def _scan_wifi(self) -> Dict[str, Any]:
        """
        Run 'iw dev <interface> scan' and return {"wifi_count": int, "sample": [bssids...]}.
        Best-effort; returns zero count on any error (no exceptions leak out).
        """
        if not self._iw_cmd:
            return {"wifi_count": 0, "sample": []}
        # Build command safely
        cmd = [self._iw_cmd, "dev", self.interface, "scan"]
        try:
            out = subprocess.check_output(
                cmd,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=6,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return {"wifi_count": 0, "sample": []}

        bssid_re = re.compile(r"^BSS\s+([0-9a-f:]{17})", re.IGNORECASE)
        sample: List[str] = []
        count = 0
        # Parse line-by-line to avoid big regexes on large outputs
        for line in out.splitlines():
            m = bssid_re.match(line)
            if m:
                count += 1
                if len(sample) < 5:
                    sample.append(m.group(1).lower())
        return {"wifi_count": count, "sample": sample}

# ---------------- Example usage ----------------
if __name__ == "__main__":
    # Configure once
    locator = GeoLocator(
        interface="wlan0",
        ip_ttl_sec=20 * 60,              # refresh IP-based location every 20 minutes
        wifi_ttl_sec=60 * 60,            # scan Wi-Fi every 60 minutes
        use_wifi=False,                  # set True if you want periodic Wi-Fi stats
        cache_file="/tmp/pi_loc_cache.json",
        http_timeout_sec=5,
    )

    # Example: 90-second polling loop
    OWM_KEY = os.environ.get("OWM_KEY", "").strip()
    UNITS = "imperial"

    try:
        while True:
            loc = locator.get_location()
            lat, lon = loc.get("lat"), loc.get("lon")
            city, region = loc.get("city"), loc.get("region")

            # if lat is None or lon is None:
            #     print("[loc] Unavailable; will retry next tick.")
            # else:
            #     wx = owm_current(lat, lon, api_key=OWM_KEY, units=UNITS)
            #     if wx:
            #         print(f"[{time.strftime('%H:%M:%S')}] "
            #               f"{city}, {region} | {wx['desc']} | {fmt_temp(wx['temp'], UNITS)}")
            #     else:
            #         print(f"[{time.strftime('%H:%M:%S')}] Weather fetch failed.")

            time.sleep(90)
    except KeyboardInterrupt:
        print("\nExiting.")
