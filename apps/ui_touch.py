import os
import sys
import signal
import argparse
import time
import datetime as dt
import math

# Add the root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Then import from src
from src.ui.config import UIConfig
from src.ui.network import NetworkMonitor
from src.ui.weather import WeatherMonitor
from src.ui.screens import (
    FanScreen, 
    InfoScreen, 
    MainScreen, 
    ModeScreen, 
    ScheduleScreen, 
    SettingsScreen, 
    WeatherScreen
)
from src.ui.widgets import Router

# Then import from src
import tkinter as tk
from src.thermostat.runtime import load_config, build_runtime, apply_schedule_if_due
from src.thermostat.geolocate import resolve_location
from src.thermostat.weather import owm_current, fmt_temp

REFRESH_MS=1000; SCHED_MS=60000
WX_LIMIT_PER_DAY = 1000
# Add small buffer (+5s) and a floor of 90s
WX_MIN = max(90, math.ceil(86400 / WX_LIMIT_PER_DAY) + 5)

# === UI theme wiring (B2 for your branch) ================================
# Map existing globals to UIConfig so the rest of the file keeps working.
COL_BG    = UIConfig.bg
COL_TEXT  = UIConfig.fg
COL_FRAME = UIConfig.rail_tile_border

# New theme values we'll use for status strip / setpoint pills
COOL_PILL     = UIConfig.cool_pill
HEAT_PILL     = UIConfig.heat_pill
STATUS_ACCENT = UIConfig.status_accent
TEXT_MUTED    = UIConfig.text_muted

# Safe-margin default if not present in YAML config
SAFE_MARGIN_DEFAULT = getattr(UIConfig, "safe_margin_px", 24)

def c_to_f(c): return (c * 9.0 / 5.0) + 32.0

class TouchUI(tk.Tk):
    def __init__(self, fullscreen=True, hide_cursor=True):
        super().__init__()
        self.title('RV Thermostat')
        self.config(bg=COL_BG)
        try: 
            self.tk.call('tk', 'scaling', 1.0)
        except Exception: 
            pass
        self.attributes('-fullscreen', bool(fullscreen))
        if hide_cursor: 
            self.config(cursor='none')
        self.bind('<Escape>', lambda e: self.attributes('-fullscreen', False))

        # Load config and create runtime
        self.cfg = load_config()
        self.ctrl, self.act, self.gpio_cleanup = build_runtime(self.cfg)
        self.router = Router(self)

        # Create NetworkMonitor
        self.network = NetworkMonitor()
        # Create WeatherMonitor (same pattern)
        self.weather_monitor = WeatherMonitor(self.cfg, min_period_sec=WX_MIN)

        # Create screens
        self.main = MainScreen(self)
        self.router.register('home', self.main)
        self.mode = ModeScreen(self)
        self.router.register('mode', self.mode)
        self.fan = FanScreen(self)
        self.router.register('fan', self.fan)
        self.settings = SettingsScreen(self)
        self.router.register('settings', self.settings)
        self.weather = WeatherScreen(self)
        self.router.register('weather', self.weather)
        self.info = InfoScreen(self)
        self.router.register('info', self.info)
        self.schedule = ScheduleScreen(self)
        self.router.register('schedule', self.schedule)
        self.router.show('home')
        self._last_wx = 0

        # Start monitoring immediately (don't wait for first interval)
        self.network.start_monitoring(self)
        self.weather_monitor.start_monitoring(self)

        # Start other monitoring loops
        # self.after(REFRESH_MS, self.loop)
        # self.after(SCHED_MS, self.sched_loop)

    # loops
    # def loop(self):
    #     t=self.ctrl.s.last_temp_c
    #     temp = f'{c_to_f(t):.0f}' if (t is not None and self.cfg.weather.units=="imperial") else (f'{t:.0f}' if t is not None else '--')
    #     self.main.set_temp(temp)
    #     # Update setpoint pills if values available
    #     cool_c = getattr(self.ctrl.s, 'cool_setpoint_c', getattr(self.cfg.control, 'cool_setpoint_c', None))
    #     heat_c = getattr(self.ctrl.s, 'heat_setpoint_c', getattr(self.cfg.control, 'heat_setpoint_c', None))
    #     if self.cfg.weather.units == "imperial":
    #         cool = c_to_f(cool_c) if isinstance(cool_c, (int, float)) else None
    #         heat = c_to_f(heat_c) if isinstance(heat_c, (int, float)) else None
    #     else:
    #         cool = cool_c if isinstance(cool_c, (int, float)) else None
    #         heat = heat_c if isinstance(heat_c, (int, float)) else None
    #     self.main.set_setpoints(cool, heat)

    #     self.ctrl.tick()
    #     self.after(REFRESH_MS, self.loop)

    # def sched_loop(self):
    #     apply_schedule_if_due(self.ctrl, dt.datetime.now())
    #     self.after(SCHED_MS, self.sched_loop)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--windowed', action='store_true'); p.add_argument('--show-cursor', action='store_true'); a=p.parse_args()
    app=TouchUI(fullscreen=not a.windowed, hide_cursor=not a.show_cursor)
    app.protocol('WM_DELETE_WINDOW', lambda: app.destroy())
    signal.signal(signal.SIGTERM, lambda *x: sys.exit(0))
    app.mainloop()
if __name__=='__main__': main()
