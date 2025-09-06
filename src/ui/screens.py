import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from src.ui.widgets import Pill

# Colors and constants
COL_BG = "#222"         # Background color
COL_TEXT = "#fff"       # Text color
COOL_PILL = "#00cfff"   # Cool pill color
HEAT_PILL = "#ff6600"   # Heat pill color
SAFE_MARGIN_DEFAULT = 24

# Local imports (relative to this module)
from src.ui.tiles import (
    WifiTile, 
    WeatherIndicationTile, 
    OutsideTempTile, 
    InformationTile, 
    ReservedTile, 
    ModeSelectionTile, 
    FanSpeedSelectionTile, 
    SettingsTile
)

# Thermostat imports (these should be imported from main app)
from src.thermostat.geolocate import resolve_location
from src.thermostat.weather import owm_current, fmt_temp

class Screen(tk.Frame):
    def __init__(self, app, title):
        super().__init__(app.router, bg=COL_BG); self.app=app
        top=tk.Frame(self, bg=COL_BG); top.pack(fill='x', padx=16, pady=12)
        tk.Button(top, text='←', command=lambda: app.router.show('home'), bg=COL_BG, fg=COL_TEXT, bd=0, font=('DejaVu Sans', 28, 'bold'), activebackground=COL_BG).pack(side='left')
        tk.Label(top, text=title, fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 28, 'bold')).pack(side='left', padx=10)
        self.body=tk.Frame(self, bg=COL_BG); self.body.pack(fill='both', expand=True, padx=24, pady=12)

class MainScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.router, bg=COL_BG)
        self.app = app
        
        # Configure grid columns with weights
        self.grid_columnconfigure(0, weight=0)  # Left column - fixed width
        self.grid_columnconfigure(1, weight=1)  # Center column - expands
        self.grid_columnconfigure(2, weight=0)  # Right column - fixed width
        
        # Create frames for each column
        self.left = tk.Frame(self, bg=COL_BG)
        self.left.grid(row=0, column=0, sticky='ns')
        
        self.center = tk.Frame(self, bg=COL_BG)
        self.center.grid(row=0, column=1, sticky='nsew')
        
        self.right = tk.Frame(self, bg=COL_BG)
        self.right.grid(row=0, column=2, sticky='ns')

        # Create and grid the tiles
        self.left_tiles = [
            WifiTile(self.left, 100, self.app),
            WeatherIndicationTile(self.left, 100, lambda: app.router.show('weather')),
            OutsideTempTile(self.left, 100),
            InformationTile(self.left, 100, lambda: app.router.show('info'))
        ]
        
        self.right_tiles = [
            ReservedTile(self.right, 100),
            ModeSelectionTile(self.right, 100, lambda: app.router.show('mode')),
            FanSpeedSelectionTile(self.right, 100, lambda: app.router.show('fan-speed-selection')),
            SettingsTile(self.right, 100, lambda: app.router.show('settings'))
        ]

        # Configure center area
        self.center.grid_rowconfigure(0, weight=1)  # Temperature expands
        self.center.grid_rowconfigure(1, weight=0)  # Pills fixed height
        
        # Center temperature display
        self.lbl = tk.Label(self.center, text='--°', fg=COL_TEXT, bg=COL_BG)
        self.lbl.grid(row=0, column=0, sticky='nsew')
        
        # Bottom pills
        self.pills = tk.Frame(self.center, bg=COL_BG)
        self.pills.grid(row=1, column=0, sticky='ew', padx=16, pady=(0,16))
        self.pills.grid_columnconfigure(0, weight=1)
        self.pills.grid_columnconfigure(1, weight=1)
        
        self.cool_pill = Pill(self.pills, 'Cool to', COOL_PILL, 
                            command=lambda: app.router.show('mode'))
        self.heat_pill = Pill(self.pills, 'Heat to', HEAT_PILL, 
                            command=lambda: app.router.show('mode'))
        
        self.cool_pill.grid(row=0, column=0, sticky='ew', padx=(0,10))
        self.heat_pill.grid(row=0, column=1, sticky='ew', padx=(10,0))

        # Bind layout handler
        self.bind('<Configure>', self._layout)

    def _layout(self, e=None):
        W = self.winfo_width() or self.winfo_screenwidth()
        H = self.winfo_height() or self.winfo_screenheight()
        m = int(getattr(self.app.cfg.ui, 'safe_margin_px', SAFE_MARGIN_DEFAULT))
        gap = max(8, int(min(W,H)*0.02))
        square = (H - 2*m - 3*gap) // 4
        square = max(72, square)

        # Resize tiles
        for i, t in enumerate(self.left_tiles):
            t.resize(square)
            t.grid(row=i, column=0, pady=(m if i==0 else gap//2), padx=m)

        for i, t in enumerate(self.right_tiles):
            t.resize(square)
            t.grid(row=i, column=0, pady=(m if i==0 else gap//2), padx=m)

        # Center font sizing
        center_h = H - 2*m
        font_px = max(80, int(center_h * 0.50))
        self.lbl.config(font=tkfont.Font(family='DejaVu Sans', 
                                       size=font_px, 
                                       weight='normal'))

        # Pill sizing
        pill_h = max(56, int(center_h * 0.12))
        inner_gap = 20
        pill_w = max(160, int((W - 2*(square + 2*m) - inner_gap) / 2))
        self.cool_pill.resize(pill_w, pill_h)
        self.heat_pill.resize(pill_w, pill_h)


    def set_temp(self, s):
        if isinstance(s, str) and s.replace('.','',1).isdigit():
            self.lbl.config(text=s)  # no degree symbol on the big number
        elif isinstance(s, (int, float)):
            self.lbl.config(text=f'{s:.0f}')
        else:
            self.lbl.config(text='--')

    def set_outside(self, s):
        # now updates the status strip
        self.status.set_outside(s)

    def set_setpoints(self, cool_f=None, heat_f=None):
        if isinstance(cool_f, (int, float)):
            self.cool_pill.set_value(f'{cool_f:.0f}° F')
        if isinstance(heat_f, (int, float)):
            self.heat_pill.set_value(f'{heat_f:.0f}° F')

    def _power_off(self):
        self.app.cfg.control.mode='off'
        # immediate tick so relays follow
        self.app.ctrl.tick()

class ModeScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Mode')
        for m in ('OFF','HEAT','COOL','AUTO'):
            tk.Button(self.body, text=m, bg=COL_BG, fg=COL_TEXT, bd=2, highlightthickness=2,
                      font=('DejaVu Sans', 28, 'bold'),
                      command=lambda x=m.lower(): self._set(x)).pack(pady=12, ipadx=20, ipady=10)
    def _set(self, m): self.app.cfg.control.mode=m; self.app.ctrl.tick()

class FanScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Fan')
        for m in ('AUTO','CYCLED','MANUAL','OFF'):
            tk.Button(self.body, text=m, bg=COL_BG, fg=COL_TEXT, bd=2, highlightthickness=2,
                      font=('DejaVu Sans', 28, 'bold'),
                      command=lambda x=m.lower(): self._set(x)).pack(pady=12, ipadx=20, ipady=10)
    def _set(self, f): self.app.ctrl.s.fan_mode=f; self.app.ctrl.tick()

class SettingsScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Settings')
        wrap=tk.Frame(self.body, bg=COL_BG); wrap.pack(fill='both', expand=True)
        # Units
        frm=tk.LabelFrame(wrap, text='Units & Display', fg=COL_TEXT, bg=COL_BG, bd=2, labelanchor='n')
        frm.pack(fill='x', padx=8, pady=8)
        self.units=tk.StringVar(value='F' if app.cfg.weather.units=='imperial' else 'C')
        tk.Radiobutton(frm, text='Fahrenheit (°F)', value='F', variable=self.units, command=self._units).pack(anchor='w', padx=10, pady=4)
        tk.Radiobutton(frm, text='Celsius (°C)',    value='C', variable=self.units, command=self._units).pack(anchor='w', padx=10, pady=4)
        self.t24=tk.BooleanVar(value=app.cfg.ui.time_24h)
        tk.Checkbutton(frm, text='24‑hour time', variable=self.t24, command=self._timefmt).pack(anchor='w', padx=10, pady=4)
        # Deadband/offset
        frm2=tk.LabelFrame(wrap, text='Calibration & Hysteresis', fg=COL_TEXT, bg=COL_BG, bd=2, labelanchor='n'); frm2.pack(fill='x', padx=8, pady=8)
        tk.Label(frm2, text='Reading Offset (°C)', fg=COL_TEXT, bg=COL_BG).grid(row=0,column=0,sticky='w',padx=10,pady=4)
        self.offset=tk.DoubleVar(value=getattr(app.cfg.control,'reading_offset_c',0.0))
        tk.Spinbox(frm2, from_=-5.0, to=5.0, increment=0.1, textvariable=self.offset, width=6).grid(row=0,column=1,sticky='w',padx=10,pady=4)
        tk.Button(frm2, text='Apply', command=lambda: setattr(app.cfg.control,'reading_offset_c', float(self.offset.get()))).grid(row=0,column=2, padx=10)
        tk.Label(frm2, text='Deadband (°C)', fg=COL_TEXT, bg=COL_BG).grid(row=1,column=0,sticky='w',padx=10,pady=4)
        self.db=tk.DoubleVar(value=app.cfg.control.deadband_c)
        tk.Spinbox(frm2, from_=0.2, to=3.0, increment=0.1, textvariable=self.db, width=6).grid(row=1,column=1,sticky='w',padx=10,pady=4)
        tk.Button(frm2, text='Apply', command=lambda: setattr(app.cfg.control,'deadband_c', float(self.db.get()))).grid(row=1,column=2, padx=10)
    def _units(self): self.app.cfg.weather.units='imperial' if self.units.get()=='F' else 'metric'
    def _timefmt(self): self.app.cfg.ui.time_24h=bool(self.t24.get())

class WeatherScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Weather')
        self.lbl=tk.Label(self.body, text='--', fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 64, 'bold')); self.lbl.pack(pady=8)
        self.desc=tk.Label(self.body, text='', fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 24)); self.desc.pack(pady=4)
        tk.Button(self.body, text='Refresh', command=self._refresh).pack(pady=8)
    def _refresh(self):
        loc=resolve_location(self.app.cfg)
        if loc and self.app.cfg.weather.api_key:
            data=owm_current(loc['lat'], loc['lon'], self.app.cfg.weather.api_key, self.app.cfg.weather.units)
            self.lbl.config(text=fmt_temp(data.get('temp') if data else None, self.app.cfg.weather.units))
            self.desc.config(text=(data.get('desc') if data else '') or '')

class InfoScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Info')
        tk.Label(self.body, text='Thermostat Info', fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 22, 'bold')).pack(anchor='w', pady=6)
        tk.Label(self.body, text='Mode/Setpoint reflect active controller state.', fg=COL_TEXT, bg=COL_BG).pack(anchor='w')

class ScheduleScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Schedule')
        from src.thermostat.schedule import load_schedule, save_schedule, DAYS, DaySchedule, Event
        self.path='config/schedule.yaml'; self.sch=load_schedule(self.path); self.DAYS=DAYS; self.DaySchedule=DaySchedule; self.Event=Event
        self.day_idx=0
        tab=tk.Frame(self.body, bg=COL_BG); tab.pack(fill='x', pady=(0,6))
        for i,d in enumerate(self.DAYS):
            tk.Button(tab, text=d.title(), bg=COL_BG, fg=COL_TEXT, bd=0, font=('DejaVu Sans', 16), command=lambda k=i: self._pick_day(k)).pack(side='left', padx=6)
        grid=tk.Frame(self.body, bg=COL_BG); grid.pack(fill='both', expand=True, padx=4, pady=6)
        hdr=('Time (24h HH:MM)','Mode','Setpoint (°C)')
        for j,h in enumerate(hdr):
            tk.Label(grid, text=h, fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 14, 'bold')).grid(row=0,column=j, sticky='w', pady=4, padx=6)
        self.rows=[]
        for r in range(6):
            tvar=tk.StringVar(value=''); mvar=tk.StringVar(value='off'); svar=tk.DoubleVar(value=22.0)
            tk.Entry(grid, textvariable=tvar, width=8).grid(row=r+1, column=0, sticky='w', padx=6, pady=4)
            ttk.Combobox(grid, textvariable=mvar, values=['off','heat','cool','auto'], width=8, state='readonly').grid(row=r+1, column=1, sticky='w', padx=6, pady=4)
            tk.Spinbox(grid, from_=5.0, to=35.0, increment=0.5, textvariable=svar, width=6).grid(row=r+1, column=2, sticky='w', padx=6, pady=4)
            self.rows.append((tvar,mvar,svar))
        btns=tk.Frame(self.body, bg=COL_BG); btns.pack(fill='x', pady=6)
        tk.Button(btns, text='Load', command=self._load_day).pack(side='left', padx=4)
        tk.Button(btns, text='Save', command=self._save_day).pack(side='left', padx=4)
        tk.Button(btns, text='Save All Days', command=self._save_all).pack(side='left', padx=4)
        self._load_day()
    def _pick_day(self, i): self.day_idx=i; self._load_day()
    def _load_day(self):
        day=self.DAYS[self.day_idx]; evs=self.sch.days[day].events
        for i,(tvar,mvar,svar) in enumerate(self.rows):
            if i<len(evs): tvar.set(evs[i].time); mvar.set(evs[i].mode); svar.set(evs[i].setpoint_c)
            else: tvar.set(''); mvar.set('off'); svar.set(22.0)
    def _read_rows(self):
        evs=[]; used=set()
        for (tvar,mvar,svar) in self.rows:
            t=tvar.get().strip()
            if not t: continue
            if len(t)!=5 or t[2] != ':' or not t[:2].isdigit() or not t[3:].isdigit(): continue
            if t in used: continue
            used.add(t)
            try: evs.append(self.Event(time=t, mode=mvar.get().strip() or 'off', setpoint_c=float(svar.get())))
            except Exception: continue
        evs.sort(key=lambda e:e.time)
        return evs[:6]
    def _save_day(self):
        day=self.DAYS[self.day_idx]
        self.sch.days[day]=self.DaySchedule(events=self._read_rows())
        from src.thermostat.schedule import save_schedule
        save_schedule(self.path, self.sch)
    def _save_all(self): self._save_day()