from __future__ import annotations

import time
import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, List, Optional, Any, Dict

from src.thermostat.geolocate import resolve_location
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
    def __init__(self, cfg, min_period_sec: int = 180):
        self._cfg = cfg
        self._min_period = max(30, int(min_period_sec))
        self._listeners = []
        self._app = None
        self._last_update = 0.0
        self._current = None

        weather_cfg = getattr(cfg, 'weather', None)
        self.units = getattr(weather_cfg, 'units', 'metric')
        self._api_key = os.getenv('OPENWEATHERMAP_API_KEY')
            
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
                    self._current = data
                    self._notify(data)
                self._last_update = now
        except Exception:
            # Swallow errors; try again later
            pass

        self._after(1000, self._tick)

    def _fetch(self) -> Optional[WeatherData]:
        if not self._api_key:
            return None
        loc = resolve_location(self._cfg)
        if not loc:
            return None

        raw: Dict[str, Any] = owm_current(
            loc['lat'],
            loc['lon'],
            self._api_key,
            self.units
        ) or {}

        # Expected shape (from your usage): {'temp': <float>, ...}
        temp = raw.get('temp')
        temp_c: Optional[float] = None
        temp_f: Optional[float] = None
        try:
            if temp is not None:
                t = float(temp)
                if self.units == 'imperial':
                    temp_f = t
                    temp_c = (t - 32.0) * 5.0 / 9.0
                else:
                    temp_c = t
                    temp_f = (t * 9.0 / 5.0) + 32.0
        except Exception:
            pass

        # Try to find a condition signal
        cond_main = raw.get('main') or raw.get('condition')
        if not cond_main:
            # Fallback to OWM "weather[0]" shape if your wrapper exposes it
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

        condition = _to_condition(cond_main)
        return WeatherData(
            temp_c=temp_c,
            temp_f=temp_f,
            condition=condition,
            description=description,
            icon=icon,
            last_updated=time.time(),
        )