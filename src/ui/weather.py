from __future__ import annotations
import os, time, logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, List, Optional, Any, Dict

from src.thermostat.geolocate import GeoLocator
from src.thermostat.weather import owm_current

class WeatherCondition(Enum):
    CLEAR = auto()
    CLOUDS = auto()
    RAIN = auto()
    DRIZZLE = auto()
    THUNDERSTORM = auto()
    SNOW = auto()
    MIST = auto()
    FOG = auto()
    HAZE = auto()
    UNKNOWN = auto()

@dataclass
class WeatherData:
    temp_c: Optional[float]
    temp_f: Optional[float]
    condition: WeatherCondition
    description: Optional[str]
    icon: Optional[str]
    city: Optional[str]
    region: Optional[str]
    last_updated: float

def _to_condition(s: Optional[str]) -> WeatherCondition:
    if not s:
        return WeatherCondition.UNKNOWN
    k = s.lower()
    if 'clear' in k: return WeatherCondition.CLEAR
    if 'cloud' in k: return WeatherCondition.CLOUDS
    if 'thunder' in k: return WeatherCondition.THUNDERSTORM
    if 'drizzle' in k: return WeatherCondition.DRIZZLE
    if 'rain' in k: return WeatherCondition.RAIN
    if 'snow' in k: return WeatherCondition.SNOW
    if 'mist' in k: return WeatherCondition.MIST
    if 'fog'  in k: return WeatherCondition.FOG
    if 'haze' in k: return WeatherCondition.HAZE
    return WeatherCondition.UNKNOWN

class WeatherMonitor:
    """
    Fetches weather no more often than min_period_sec.
    Internal loop wakes every loop_ms (default 5000 ms) to check if due.
    """
    def __init__(self, cfg, locator: GeoLocator | None = None,
                 min_period_sec: int = 180,
                 loop_ms: int = 5000):
        self._cfg = cfg
        self._min_period = max(30, int(min_period_sec))  # enforce sensible floor
        self._loop_ms = max(1000, int(loop_ms))
        self._listeners: List[Callable[[WeatherData], None]] = []
        self._app = None
        self._current: Optional[WeatherData] = None

        # Separate timestamps
        self._last_fetch: float = 0.0
        self._last_notify: float = 0.0

        # Behavior: set to True if you want rapid retry on failure
        self._retry_on_fail = False

        self._locator = locator or GeoLocator(
            interface="wlan0",
            ip_ttl_sec=20 * 60,
            wifi_ttl_sec=60 * 60,
            use_wifi=False,
            cache_file="/tmp/pi_loc_cache.json",
            http_timeout_sec=5,
        )
        weather_cfg = getattr(cfg, 'weather', None)
        self.units = getattr(weather_cfg, 'units', 'metric')
        self._api_key = os.getenv('OPENWEATHERMAP_API_KEY')
        self._log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._log.info("Init units=%s min_period=%ss loop_ms=%d", self.units, self._min_period, self._loop_ms)

    def add_listener(self, fn: Callable[[WeatherData], None]) -> None:
        if fn not in self._listeners:
            self._listeners.append(fn)
            if self._current:
                try: fn(self._current)
                except Exception: pass

    def remove_listener(self, fn: Callable[[WeatherData], None]) -> None:
        try: self._listeners.remove(fn)
        except ValueError: pass

    def start_monitoring(self, app) -> None:
        if self._app is not None:
            return
        self._app = app
        self._log.info("Starting monitor loop")
        # Immediate first attempt
        self._schedule(0, self._tick)

    def stop(self) -> None:
        self._app = None
        self._log.info("Stopped monitor")

    def _schedule(self, ms: int, fn) -> None:
        if self._app:
            try: self._app.after(ms, fn)
            except Exception: pass

    def _tick(self) -> None:
        now = time.time()
        due_in = self._min_period - (now - self._last_fetch)
        if self._last_fetch == 0 or due_in <= 0:
            self._do_fetch_cycle(now)
        # Schedule next loop wake
        self._schedule(self._loop_ms, self._tick)

    def _do_fetch_cycle(self, now: float) -> None:
        self._api_key = self._api_key or os.getenv('OPENWEATHERMAP_API_KEY')
        if not self._api_key:
            self._log.debug("Fetch skipped: no API key")
            if not self._retry_on_fail:
                self._last_fetch = now  # avoid hammering every loop
            return

        loc = self._locator.get_location() or {}
        lat = loc.get('lat'); lon = loc.get('lon')
        city = loc.get('city'); region = loc.get('region')
        if lat is None or lon is None:
            self._log.debug("Fetch skipped: location unavailable %s", loc)
            if not self._retry_on_fail:
                self._last_fetch = now
            return

        try:
            raw: Dict[str, Any] = owm_current(float(lat), float(lon), self._api_key, self.units) or {}
        except Exception as e:
            self._log.warning("Fetch error: %s", e)
            if not self._retry_on_fail:
                self._last_fetch = now
            return

        data = self._normalize(raw, city, region)
        self._last_fetch = now  # ALWAYS advance fetch timestamp
        if data is None:
            self._log.debug("Normalization returned None")
            return

        changed = (
            self._current is None or
            data.temp_c != self._current.temp_c or
            data.condition is not self._current.condition
        )

        if changed:
            self._current = data
            self._last_notify = now
            self._log.info("Weather updated: %s, %s temp=%.1fC/%.1fF cond=%s",
                           data.city, data.region,
                           (data.temp_c if data.temp_c is not None else float('nan')),
                           (data.temp_f if data.temp_f is not None else float('nan')),
                           data.condition.name)
            for fn in list(self._listeners):
                try: fn(data)
                except Exception: pass
        else:
            self._log.debug("No change (%.1fs since last notify)", now - self._last_notify)

    def _normalize(self, raw: Dict[str, Any], city: Optional[str], region: Optional[str]) -> Optional[WeatherData]:
        if not raw:
            return None
        temp = raw.get('temp')
        temp_c: Optional[float] = None
        temp_f: Optional[float] = None
        if isinstance(temp, (int, float)):
            if self.units == 'imperial':
                temp_f = float(temp)
                temp_c = (temp_f - 32.0) * 5.0 / 9.0
            else:
                temp_c = float(temp)
                temp_f = (temp_c * 9.0 / 5.0) + 32.0

        cond_main = raw.get('main') or raw.get('condition')
        if not cond_main:
            wx_list = raw.get('weather') or []
            if wx_list:
                cond_main = (wx_list[0] or {}).get('main')

        description = raw.get('description')
        if not description:
            wx_list = raw.get('weather') or []
            if wx_list:
                description = (wx_list[0] or {}).get('description')

        icon = raw.get('icon')
        if not icon:
            wx_list = raw.get('weather') or []
            if wx_list:
                icon = (wx_list[0] or {}).get('icon')

        return WeatherData(
            temp_c=temp_c,
            temp_f=temp_f,
            condition=_to_condition(cond_main),
            description=description,
            icon=icon,
            city=city,
            region=region,
            last_updated=time.time()
        )