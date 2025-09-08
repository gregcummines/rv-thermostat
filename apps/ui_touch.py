import os
import sys
import signal
import argparse
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
    WeatherScreen,
    LogScreen,     # NEW
)
from src.ui.widgets import Router
from src.ui.thermostat_monitor import ThermostatMonitor, ThermostatSnapshot

# Then import from src
import tkinter as tk
from src.thermostat.runtime import load_config, build_runtime
from src.thermostat.geolocate import GeoLocator
from src.thermostat.logging_config import setup_logging, resolve_logging_from_env_and_cfg

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

        # Load config first so logging can read optional cfg.logging
        self.cfg = load_config()

        # Initialize logging (env first, then cfg fallback)
        enabled, level, log_file = resolve_logging_from_env_and_cfg(self.cfg)
        # Default file path if requested but not set: logs/app.log under repo
        if log_file is None and os.getenv("RVT_LOG_FILE_DEFAULT", "0") in ("1", "true", "yes"):
            log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "app.log")
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
        setup_logging(enabled=enabled, level=level, log_file=log_file)

        import logging
        self._log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._log.info("TouchUI starting (fullscreen=%s hide_cursor=%s)", fullscreen, hide_cursor)

        # Runtime controller and router
        self.ctrl, self.act, self.gpio_cleanup = build_runtime(self.cfg)
        self.router = Router(self)

        # Shared GeoLocator
        self.locator = GeoLocator(
            interface="wlan0",
            ip_ttl_sec=20 * 60,
            wifi_ttl_sec=60 * 60,
            use_wifi=False,
            cache_file="/tmp/pi_loc_cache.json",
            http_timeout_sec=5,
        )

        # Monitors
        self.network = NetworkMonitor()
        self.weather_monitor = WeatherMonitor(self.cfg, locator=self.locator, min_period_sec=WX_MIN)
        self.thermo_monitor = ThermostatMonitor(self.ctrl, self.cfg, period_ms=REFRESH_MS)

        # Screens
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
        self.router.register('logs', LogScreen(self))   # NEW
        self.router.show('home')

        # Start monitors
        self.network.start_monitoring(self)
        self.weather_monitor.start_monitoring(self)
        self.thermo_monitor.add_listener(self._on_thermo_update)
        self.thermo_monitor.start_monitoring(self)

    def _on_thermo_update(self, snap: ThermostatSnapshot) -> None:
        self.main.set_temp(snap.temp_text)
        self.main.set_setpoints(snap.cool_disp, snap.heat_disp)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--windowed', action='store_true'); p.add_argument('--show-cursor', action='store_true'); a=p.parse_args()
    app=TouchUI(fullscreen=not a.windowed, hide_cursor=not a.show_cursor)
    app.protocol('WM_DELETE_WINDOW', lambda: app.destroy())
    signal.signal(signal.SIGTERM, lambda *x: sys.exit(0))
    app.mainloop()
if __name__=='__main__': main()
