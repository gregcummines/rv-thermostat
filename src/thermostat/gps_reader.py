from __future__ import annotations
import logging, socket, time
from typing import Optional, Dict

try:
    import gps as gpslib  # python3-gps
except Exception:
    gpslib = None

class GPSReader:
    """
    Hot‑plug aware reader for GPS coordinates via gpsd.

    What it returns
    - get_location_if_ready() returns a dict on success:
      {'lat': float, 'lon': float, 'accuracy_m': Optional[float], 'city': None, 'region': None, 'source': 'gps'}
      or None if gpsd/device/no-fix conditions prevent a quick result.
    - A valid fix requires TPV mode >= 2 (2D or 3D).

    Integration with GeoLocator
    - Construct once and inject into GeoLocator, then prefer it before other methods:
        from src.thermostat.gps_reader import GPSReader
        gps = GPSReader(enabled=True)
        locator = GeoLocator(..., gps_reader=gps)
      GeoLocator should call gps.get_location_if_ready() first and fall back to Wi‑Fi/IP if it returns None.
    - Call get_location_if_ready() from your periodic loop; it only blocks for small timeouts you configure.
    - On shutdown, call gps.close().

    Hot‑plug behavior
    - Listens for DEVICE reports from gpsd; if a USB receiver is unplugged/plugged, the session is reset and retried.
    - Uses adaptive backoff:
        - gpsd socket down -> longer backoff (service not running).
        - Device absent or no fix yet -> short backoff (retry soon).
        - Session errors -> short backoff.

    Linux setup (gpsd)
    - sudo apt install gpsd gpsd-clients python3-gps
    - sudo systemctl enable --now gpsd
    - Edit /etc/default/gpsd:
        USBAUTO="true"
        DEVICES=""     # let udev add/remove /dev/ttyACM0 or /dev/ttyUSB0
    - Add user to dialout and re-login: sudo usermod -aG dialout "$USER"
    - Test hardware/fix independently: cgps -s

    Tuning
    - probe_timeout: TCP connect timeout to gpsd socket (fast failure if service down).
    - fix_timeout: how long to wait for a TPV fix per call.
    - backoff_*: how long to defer the next probe after failures.

    Notes
    - Requires python3-gps; if not importable, GPSReader disables itself and always returns None.
    - Designed to be safe to call frequently from a scheduler without hammering gpsd/USB.
    """

    def __init__(self,
                 enabled: bool = True,
                 host: str = "127.0.0.1",
                 port: str = "2947",
                 probe_timeout: float = 0.5,
                 fix_timeout: float = 2.0,
                 backoff_no_socket: float = 60.0,
                 backoff_no_device: float = 10.0,
                 backoff_error: float = 5.0):
        self._log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._enabled = bool(enabled and gpslib is not None)
        self._host = host
        self._port = port
        self._probe_timeout = float(probe_timeout)
        self._fix_timeout = float(fix_timeout)
        self._backoff_no_socket = float(backoff_no_socket)
        self._backoff_no_device = float(backoff_no_device)
        self._backoff_error = float(backoff_error)
        self._next_probe = 0.0
        self._session = None

        if gpslib is None and enabled:
            self._log.warning("python3-gps not importable; GPSReader disabled")
        else:
            self._log.info("GPSReader enabled=%s host=%s port=%s probe_timeout=%.1fs fix_timeout=%.1fs",
                           self._enabled, self._host, self._port, self._probe_timeout, self._fix_timeout)

    def is_enabled(self) -> bool:
        return self._enabled

    def get_location_if_ready(self) -> Optional[Dict]:
        """
        Returns {'lat','lon','accuracy_m','city','region','source'} or None.
        Hot-plug aware: reacts to DEVICE events and session errors, with adaptive backoff.
        """
        if not self._enabled:
            self._log.debug("GPS disabled; skipping.")
            return None

        now = time.time()
        if now < self._next_probe:
            delay = self._next_probe - now
            self._log.debug("GPS backoff active; next probe in %.1fs", delay)
            return None

        self._log.debug("GPS attempt: probing gpsd and seeking fix (timeout %.1fs)", self._fix_timeout)

        # 1) Probe gpsd socket (handles gpsd/service down)
        if not self._probe_gpsd_socket():
            self._set_backoff(self._backoff_no_socket, "gpsd socket unreachable")
            return None

        # 2) Ensure session
        if not self._ensure_session():
            self._set_backoff(self._backoff_error, "gps session open failed")
            return None

        # 3) Consume reports briefly to find a 2D+ fix
        deadline = now + self._fix_timeout
        poll_s = 0.25  # non-blocking poll interval
        try:
            while time.time() < deadline:
                # Avoid blocking indefinitely if gpsd has no data yet
                try:
                    if hasattr(self._session, "waiting"):
                        if not self._session.waiting(timeout=poll_s):
                            continue
                except Exception as e:
                    self._log.debug("gps waiting() error: %s", e)
                    # Fall through and try a next(); loop deadline still bounds us

                try:
                    report = self._session.next()
                except StopIteration:
                    # gpsd closed our stream (service restart or device gone)
                    self._log.debug("gpsd stream closed (StopIteration).")
                    self._close_session()
                    self._set_backoff(self._backoff_error, "gpsd stream closed")
                    return None
                except Exception as e:
                    self._log.warning("gps session error: %s", e)
                    self._close_session()
                    self._set_backoff(self._backoff_error, "session error")
                    return None

                # Normalize class
                try:
                    rclass = report['class']
                except Exception:
                    rclass = getattr(report, 'class', None)

                if rclass == 'DEVICE':
                    # Device add/remove events
                    activated = getattr(report, 'activated', None)
                    if activated:
                        self._log.info("GPS device activated at %s", getattr(report, 'path', 'unknown'))
                        continue  # device came up; keep looking for TPV
                    else:
                        self._log.info("GPS device removed (path=%s)", getattr(report, 'path', 'unknown'))
                        self._close_session()
                        self._set_backoff(self._backoff_no_device, "device removed")
                        return None

                if rclass == 'SKY':
                    # Satellites info (debug aid)
                    sats = getattr(report, 'satellites', []) or []
                    seen = len(sats)
                    used = sum(1 for s in sats if getattr(s, 'used', False))
                    self._log.debug("GPS SKY: satellites seen=%d used=%d", seen, used)
                    continue

                if rclass != 'TPV':
                    continue

                mode = getattr(report, 'mode', 1)  # 1=no fix, 2=2D, 3=3D
                lat = getattr(report, 'lat', None)
                lon = getattr(report, 'lon', None)
                eph = getattr(report, 'eph', None)  # horizontal error (m), if present

                if mode >= 2 and lat is not None and lon is not None:
                    self._next_probe = time.time()  # allow immediate next call
                    self._log.debug("GPS fix: mode=%s lat=%.6f lon=%.6f eph=%s",
                                    mode, float(lat), float(lon), f"{float(eph):.1f}m" if eph is not None else "n/a")
                    return {
                        'lat': float(lat),
                        'lon': float(lon),
                        'accuracy_m': float(eph) if eph is not None else None,
                        'city': None,
                        'region': None,
                        'source': 'gps',
                    }
                else:
                    self._log.debug("GPS TPV but no fix yet: mode=%s lat=%s lon=%s", mode, lat, lon)

            # Timed out waiting for a fix while device/gpsd are up -> short backoff
            self._log.debug("No GPS fix within %.1fs.", self._fix_timeout)
            self._set_backoff(self._backoff_no_device, "no fix within timeout")
            return None

        except Exception as e:
            self._log.warning("Unexpected GPS error: %s", e)
            self._close_session()
            self._set_backoff(self._backoff_error, "unexpected error")
            return None

    def close(self) -> None:
        self._log.debug("Closing GPSReader session.")
        self._close_session()

    # Internals

    def _probe_gpsd_socket(self) -> bool:
        try:
            with socket.create_connection((self._host, int(self._port)), timeout=self._probe_timeout):
                self._log.debug("gpsd reachable at %s:%s", self._host, self._port)
                return True
        except Exception:
            self._log.debug("gpsd not reachable at %s:%s", self._host, self._port)
            self._close_session()
            return False

    def _ensure_session(self) -> bool:
        try:
            if self._session is None:
                self._session = gpslib.gps(host=self._host, port=self._port)
                self._session.stream(gpslib.WATCH_ENABLE | gpslib.WATCH_NEWSTYLE)
                self._log.info("Opened gpsd session to %s:%s", self._host, self._port)
            return True
        except Exception as e:
            self._log.debug("gps session open failed: %s", e)
            self._close_session()
            return False

    def _close_session(self) -> None:
        try:
            if self._session:
                self._log.debug("Closing gpsd session.")
                self._session.close()
        except Exception:
            pass
        self._session = None

    def _set_backoff(self, seconds: float, reason: str = "") -> None:
        seconds = max(0.5, float(seconds))
        self._next_probe = time.time() + seconds
        if reason:
            self._log.debug("GPS backoff %.1fs (%s)", seconds, reason)
        else:
            self._log.debug("GPS backoff %.1fs", seconds)