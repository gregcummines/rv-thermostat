from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

def c_to_f(c: float) -> float:
    return (c * 9.0 / 5.0) + 32.0

@dataclass
class ThermostatSnapshot:
    ts: float
    # Raw values (C)
    temp_c: Optional[float]
    heat_setpoint_c: Optional[float]
    cool_setpoint_c: Optional[float]
    # Display values (unit-selected)
    temp_text: str           # e.g., "72" or "--"
    heat_disp: Optional[float]
    cool_disp: Optional[float]

class ThermostatMonitor:
    """
    Periodically runs controller.tick() and publishes snapshot to listeners.
    Mirrors NetworkMonitor/WeatherMonitor API.
    """
    def __init__(self, ctrl, cfg, period_ms: int = 1000):
        self._ctrl = ctrl
        self._cfg = cfg
        self._period_ms = max(250, int(period_ms))
        self._listeners: List[Callable[[ThermostatSnapshot], None]] = []
        self._app = None

    def add_listener(self, cb: Callable[[ThermostatSnapshot], None]) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[ThermostatSnapshot], None]) -> None:
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def start_monitoring(self, app) -> None:
        self._app = app
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

    def _notify(self, snap: ThermostatSnapshot) -> None:
        for cb in list(self._listeners):
            try:
                cb(snap)
            except Exception:
                pass

    def _tick(self) -> None:
        # 1) Run control loop
        try:
            self._ctrl.tick()
        except Exception:
            # keep UI alive on controller errors
            pass

        # 2) Build snapshot
        units = getattr(getattr(self._cfg, 'weather', None), 'units', 'metric')
        t_c = getattr(self._ctrl.s, 'last_temp_c', None)

        heat_c = getattr(self._ctrl.s, 'heat_setpoint_c', getattr(self._cfg.control, 'heat_setpoint_c', None))
        cool_c = getattr(self._ctrl.s, 'cool_setpoint_c', getattr(self._cfg.control, 'cool_setpoint_c', None))

        if units == 'imperial':
            temp_text = f'{c_to_f(t_c):.0f}' if isinstance(t_c, (int, float)) else '--'
            heat_disp = c_to_f(heat_c) if isinstance(heat_c, (int, float)) else None
            cool_disp = c_to_f(cool_c) if isinstance(cool_c, (int, float)) else None
        else:
            temp_text = f'{t_c:.0f}' if isinstance(t_c, (int, float)) else '--'
            heat_disp = heat_c if isinstance(heat_c, (int, float)) else None
            cool_disp = cool_c if isinstance(cool_c, (int, float)) else None

        snap = ThermostatSnapshot(
            ts=time.time(),
            temp_c=t_c,
            heat_setpoint_c=heat_c,
            cool_setpoint_c=cool_c,
            temp_text=temp_text,
            heat_disp=heat_disp,
            cool_disp=cool_disp,
        )

        # 3) Notify listeners and reschedule
        self._notify(snap)
        self._after(self._period_ms, self._tick)

class ScheduleMonitor:
    def __init__(self, ctrl, period_ms: int = 60000):
        self._ctrl = ctrl
        self._period_ms = max(10000, int(period_ms))
        self._app = None

    def start_monitoring(self, app) -> None:
        self._app = app
        self._after(0, self._tick)

    def stop(self) -> None:
        self._app = None

    def _after(self, ms: int, fn) -> None:
        if self._app is not None:
            try:
                self._app.after(ms, fn)
            except Exception:
                pass

    def _tick(self) -> None:
        try:
            from src.thermostat.runtime import apply_schedule_if_due
            import datetime as dt
            apply_schedule_if_due(self._ctrl, dt.datetime.now())
        finally:
            self._after(self._period_ms, self._tick)