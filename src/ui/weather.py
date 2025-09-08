from __future__ import annotations
import os
import time
import logging
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
    if 'fog' in k: return WeatherCondition.FOG
    if 'haze' in k: return WeatherCondition.HAZE
    return WeatherCondition.UNKNOWN

class WeatherMonitor:
    """
    Periodically polls weather and notifies listeners with WeatherData.
    Mirrors NetworkMonitor pattern (add_listener/start_monitoring).
    """
    def __init__(self, cfg, locator: GeoLocator | None = None, min_period_sec: int = 180):
        self._cfg = cfg
        self._min_period = max(30, int(min_period_sec))
        self._listeners: List[Callable[[WeatherData], None]] = []
        self._app = None
        self._last_update = 0.0
        self._current: Optional[WeatherData] = None

        # Use the provided GeoLocator or create a default one
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
        self._log.info("Init WeatherMonitor units=%s min_period=%ss", self.units, self._min_period)

    def add_listener(self, cb: Callable[[WeatherData], None]) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)
            # Immediately push last value if we have one
            if self._current is not None:
                try:
                    cb(self._current)
                except Exception:
                    pass

    def remove_listener(self, cb: Callable[[WeatherData], None]) -> None:
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def start_monitoring(self, app) -> None:
        """Begin periodic polling using Tk's app.after (same shape as NetworkMonitor)."""
        self._app = app
        self._log.info("Starting monitor")
        # Kick off immediately; subsequent polls respect min_period
        self._after(0, self._tick)

    def stop(self) -> None:
        self._app = None

    # internals
    def _after(self, ms: int, fn) -> None:
        if self._app is not None:
            try:
                self._app.after(ms, fn)
            except Exception:
                pass

    def _notify(self, data: WeatherData) -> None:
        for cb in list(self._listeners):
            try:
                cb(data)
            except Exception:
                # Keep others firing even if one listener explodes
                pass

    def _tick(self) -> None:
        now = time.time()
        if (now - self._last_update) < self._min_period:
            self._after(1000, self._tick)
            return

        try:
            data = self._fetch()
            if data is not None:
                # Only notify if changed or first value
                if (self._current is None) or (
                    (data.temp_c != self._current.temp_c) or
                    (data.condition is not self._current.condition)
                ):
                    self._log.info("Weather updated: %s, %s temp=%.1fC/%.1fF cond=%s",
                                   data.city, data.region,
                                   (data.temp_c if data.temp_c is not None else float('nan')),
                                   (data.temp_f if data.temp_f is not None else float('nan')),
                                   data.condition.name)
                    self._current = data
                    self._notify(data)
                self._last_update = now
        except Exception as e:
            self._log.exception("Tick failed: %s", e)

        self._after(1000, self._tick)

    def _fetch(self) -> Optional[WeatherData]:
        # Always re-check env before use
        self._api_key = self._api_key or os.getenv('OPENWEATHERMAP_API_KEY')
        if not self._api_key:
            self._log.warning("Missing OPENWEATHERMAP_API_KEY; skipping fetch")
            return None

        loc = self._locator.get_location() or {}
        lat = loc.get('lat'); lon = loc.get('lon'); city = loc.get('city'); region = loc.get('region')
        if lat is None or lon is None:
            self._log.warning("No lat/lon from GeoLocator; loc=%s", loc)
            return None

        self._log.debug("Fetching OWM lat=%.5f lon=%.5f city=%s region=%s units=%s", float(lat), float(lon), city, region, self.units)

        raw: Dict[str, Any] = owm_current(float(lat), float(lon), self._api_key, self.units) or {}

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
            last_updated=time.time(),
        )