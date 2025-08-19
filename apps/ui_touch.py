import os, sys, signal, argparse, time, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from thermostat.runtime import load_config, build_runtime, apply_schedule_if_due
from thermostat.geolocate import resolve_location
from thermostat.weather import owm_current, pick_emoji, fmt_temp
from thermostat.schedule import load_schedule, save_schedule, Schedule, DaySchedule, Event, DAYS

REFRESH_MS=1000; TICK_MS=2000; WX_MIN=180; SCHED_MS=30*1000
COL_BG='#0b0d10'; COL_TEXT='#ffffff'; COL_DIM='#9aa6b2'; COL_BLUE='#2ea7ff'; COL_RED='#ff4d4d'; COL_GREEN='#00c853'; COL_RED2='#ff1744'; COL_DB='#0d47a1'

def c_to_f(c): return (c*9.0/5.0)+32.0
def f_to_c(f): return (f-32.0)*5.0/9.0
def hm_str(now: dt.datetime, h24: bool): return now.strftime('%H:%M' if h24 else '%-I:%M %p')

class Router(tk.Frame):
    def __init__(self, root, **kw):
        super().__init__(root, **kw); self.config(bg=COL_BG); self.pack(fill='both', expand=True)
        self.screens={}; self.current=None
    def register(self, name, widget): self.screens[name]=widget
    def show(self, name):
        if self.current: self.screens[self.current].pack_forget()
        self.current=name; self.screens[name].pack(fill='both', expand=True)

class Screen(tk.Frame):
    def __init__(self, app, title:str):
        super().__init__(app.router, bg=COL_BG); self.app=app; self.title=title
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        top=tk.Frame(self, bg=COL_BG); top.grid(row=0,column=0,sticky='ew',padx=16,pady=(10,0))
        tk.Button(top, text='←', command=self.app.go_home, bg=COL_BG, fg=COL_TEXT, bd=0, font=app.f_mid, activebackground=COL_BG).pack(side='left')
        tk.Label(top, text=title, fg=COL_TEXT, bg=COL_BG, font=app.f_title).pack(side='left', padx=8)
        # Clock on right
        self.clock_var=tk.StringVar(value=hm_str(dt.datetime.now(), app.cfg.ui.time_24h))
        tk.Label(top, textvariable=self.clock_var, fg=COL_TEXT, bg=COL_BG, font=app.f_title).pack(side='right')
        self.body=tk.Frame(self, bg=COL_BG); self.body.grid(row=1,column=0,sticky='nsew',padx=20,pady=12)
    def tick_clock(self):
        self.clock_var.set(hm_str(dt.datetime.now(), self.app.cfg.ui.time_24h))

class IconButton(tk.Frame):
    def __init__(self, parent, text, fg, command, size=112):
        super().__init__(parent, bg=COL_BG, highlightthickness=0)
        self.btn=tk.Button(self, text=text, fg=fg, bg=COL_BG, bd=0, activebackground=COL_BG,
                           font=tkfont.Font(size=int(size*0.6), weight='bold'), command=command)
        # square look via fixed ipadding; relies on large font to fill area
        self.btn.pack(ipadx=int(size*0.35), ipady=int(size*0.25))

class TouchUI(tk.Tk):
    def __init__(self, fullscreen=True, hide_cursor=True):
        super().__init__(); self.title('RV Thermostat'); self.config(bg=COL_BG)
        self.attributes('-fullscreen', bool(fullscreen))
        if hide_cursor: self.config(cursor='none')
        self.bind('<Escape>', lambda e: self.attributes('-fullscreen', False))
        self.bind('<F11>', lambda e: self.attributes('-fullscreen', not bool(self.attributes('-fullscreen'))))
        self.cfg=load_config(); self.ctrl,self.act,self.gpio_cleanup=build_runtime(self.cfg)
        # fonts
        self.f_title=tkfont.Font(size=26, weight='bold'); self.f_big=tkfont.Font(size=160, weight='bold'); self.f_mid=tkfont.Font(size=28, weight='bold'); self.f_small=tkfont.Font(size=16)
        # vars
        self.mode_var=tk.StringVar(value=self.cfg.control.mode); self.fan_var=tk.StringVar(value=self.ctrl.s.fan_mode)
        self.wifi_state=tk.StringVar(value='disconnected'); self.outside_var=tk.StringVar(value='--'); self.out_desc_var=tk.StringVar(value=''); self._last_wx_ts=0
        # router + screens
        self.router=Router(self, bg=COL_BG)
        self.main=MainScreen(self); self.router.register('home', self.main)
        self.mode=ModeScreen(self); self.router.register('mode', self.mode)
        self.fan=FanScreen(self); self.router.register('fan', self.fan)
        self.settings=SettingsScreen(self); self.router.register('settings', self.settings)
        self.weather=WeatherScreen(self); self.router.register('weather', self.weather)
        self.info=InfoScreen(self); self.router.register('info', self.info)
        self.schedule=ScheduleScreen(self); self.router.register('schedule', self.schedule)
        self.router.show('home')
        # timers
        self.refresh_job=self.after(REFRESH_MS, self.refresh_loop); self.tick_job=self.after(TICK_MS, self.control_tick); self.wx_job=self.after(200, self.weather_poll)
        self.clock_job=self.after(1000, self.clock_tick); self.sched_job=self.after(1000, self.schedule_tick)
    def go_home(self): self.router.show('home')
    def refresh_loop(self):
        t=self.ctrl.s.last_temp_c
        self.main.set_inside('--' if t is None else (f'{c_to_f(t):.0f}' if self.cfg.weather.units=='imperial' else f'{t:.0f}'))
        mode=self.ctrl.s.current_mode; self.main.set_state(mode); self.main.set_wifi(self.wifi_state.get())
        self.refresh_job=self.after(REFRESH_MS, self.refresh_loop)
    def control_tick(self): self.ctrl.tick(); self.tick_job=self.after(TICK_MS, self.control_tick)
    def weather_poll(self):
        now=time.time()
        if now - self._last_wx_ts >= WX_MIN: self._fetch_weather()
        self.wx_job=self.after(1000, self.weather_poll)
    def _fetch_weather(self):
        loc=resolve_location(self.cfg)
        if not loc: self.wifi_state.set('disconnected'); self.outside_var.set('--'); return
        data=owm_current(loc['lat'], loc['lon'], self.cfg.weather.api_key, units=self.cfg.weather.units)
        if not data: self.wifi_state.set('no-internet'); self.outside_var.set('--'); return
        self.wifi_state.set('ok'); self.outside_var.set(fmt_temp(data.get('temp'), self.cfg.weather.units)); self.out_desc_var.set(data.get('desc') or ''); self._last_wx_ts=time.time()
        self.main.set_weather_icon(self.out_desc_var.get())
    def clock_tick(self):
        # Update top bar clocks on every screen
        for name,screen in self.router.screens.items():
            if hasattr(screen, 'tick_clock'): screen.tick_clock()
        self.clock_job=self.after(1000, self.clock_tick)
    def schedule_tick(self):
        apply_schedule_if_due(self.ctrl, dt.datetime.now())
        self.sched_job=self.after(SCHED_MS, self.schedule_tick)

class MainScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.router, bg=COL_BG); self.app=app
        # grid scaffolding
        for r in range(6): self.grid_rowconfigure(r, weight=1)
        for c in range(5): self.grid_columnconfigure(c, weight=1)
        # Top row: title + clock
        top=tk.Frame(self, bg=COL_BG); top.grid(row=0,column=0,columnspan=5,sticky='ew',padx=16,pady=(10,0))
        self.clock_var=tk.StringVar(value=hm_str(dt.datetime.now(), app.cfg.ui.time_24h))
        tk.Label(top, text='Easy RV', fg=COL_TEXT, bg=COL_BG, font=app.f_title).pack(side='left')
        tk.Label(top, textvariable=self.clock_var, fg=COL_TEXT, bg=COL_BG, font=app.f_title).pack(side='right')
        # Left rail (equal-size icon buttons)
        left=tk.Frame(self, bg=COL_BG); left.grid(row=1,column=0,rowspan=4,sticky='nsw',padx=8)
        self.btn_weather=IconButton(left, text='☀', fg='#ffe680', command=lambda: app.router.show('weather'), size=128); self.btn_weather.pack(pady=12)
        IconButton(left, text='ℹ', fg='#20d16b', command=lambda: app.router.show('info'), size=128).pack(pady=12)
        IconButton(left, text='⚙', fg='#cfe3ff', command=lambda: app.router.show('settings'), size=128).pack(pady=12)
        IconButton(left, text='🗓', fg='#c1ffd7', command=lambda: app.router.show('schedule'), size=128).pack(pady=12)
        # Center big temp (white & larger)
        center=tk.Frame(self, bg=COL_BG); center.grid(row=1,column=1,columnspan=3,rowspan=4,sticky='nsew')
        center.grid_columnconfigure(0, weight=1); center.grid_rowconfigure(0, weight=1)
        self.lbl_big=tk.Label(center, text='--', fg=COL_TEXT, bg=COL_BG, font=app.f_big); self.lbl_big.grid(row=0,column=0,sticky='n', pady=(10,0))
        # Right rail (equal-size icon buttons)
        right=tk.Frame(self, bg=COL_BG); right.grid(row=1,column=4,rowspan=4,sticky='nse',padx=8)
        IconButton(right, text='❄', fg='#9cd9ff', command=lambda: app.router.show('mode'), size=128).pack(pady=12)
        IconButton(right, text='🔥', fg='#ffb07c', command=lambda: app.router.show('mode'), size=128).pack(pady=12)
        IconButton(right, text='🌀', fg=COL_GREEN, command=lambda: app.router.show('fan'), size=128).pack(pady=12)
        IconButton(right, text='⏻', fg='#ff6666', command=self.power_off, size=128).pack(pady=12)
        # Bottom row: quick actions & wifi dot
        bottom=tk.Frame(self, bg=COL_BG); bottom.grid(row=5,column=0,columnspan=5,sticky='sew',pady=(0,10),padx=16)
        for i in range(5): bottom.grid_columnconfigure(i, weight=1)
        self.lbl_wifi=tk.Label(bottom, text='●', fg=COL_DB, bg=COL_BG, font=self.app.f_mid); self.lbl_wifi.grid(row=0,column=0,sticky='w')
        tk.Button(bottom, text='Cool to\n76 F', fg='white', bg=COL_BLUE, bd=0, activebackground='#218fd6', font=self.app.f_mid, height=2, command=self.cool_to_target).grid(row=0,column=1,sticky='nsew',padx=8)
        tk.Button(bottom, text='Heat to\n68 F', fg='white', bg=COL_RED,  bd=0, activebackground='#d63c3c', font=self.app.f_mid, height=2, command=self.heat_to_target).grid(row=0,column=3,sticky='nsew',padx=8)
    def set_inside(self, txt): self.lbl_big.config(text=txt)
    def set_state(self, mode): pass  # color state is communicated by side icons/states; can be extended
    def set_wifi(self, state):
        color={'ok':COL_GREEN,'no-internet':COL_RED2,'disconnected':COL_DB}.get(state,COL_DB)
        self.lbl_wifi.config(fg=color)
    def power_off(self):
        self.app.cfg.control.mode='off'; self.app.ctrl.tick()
    def cool_to_target(self): self.app.cfg.control.mode='cool'; self.app.cfg.control.setpoint_c=f_to_c(76.0); self.app.mode_var.set('cool'); self.app.ctrl.tick()
    def heat_to_target(self): self.app.cfg.control.mode='heat'; self.app.cfg.control.setpoint_c=f_to_c(68.0); self.app.mode_var.set('heat'); self.app.ctrl.tick()
    def set_weather_icon(self, desc): pass  # future: vary left sun icon based on desc

class ModeScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Mode')
        bl=tk.Frame(self.body, bg=COL_BG); bl.pack(expand=True)
        def set_mode(m): app.cfg.control.mode=m; app.mode_var.set(m); app.ctrl.tick()
        for m,label in (('off','OFF'),('heat','HEAT'),('cool','COOL'),('auto','AUTO')):
            tk.Button(bl, text=label, width=16, height=2, font=app.f_mid, command=lambda x=m: set_mode(x)).pack(pady=10)

class FanScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Fan')
        bl=tk.Frame(self.body, bg=COL_BG); bl.pack(expand=True)
        def set_fan(f): app.ctrl.s.fan_mode=f
        for f,label in (('auto','AUTO'),('cycled','CYCLED'),('manual','MANUAL'),('off','OFF')):
            tk.Button(bl, text=label, width=16, height=2, font=app.f_mid, command=lambda x=f: set_fan(x)).pack(pady=10)

class SettingsScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Settings')
        wrap=tk.Frame(self.body, bg=COL_BG); wrap.pack(fill='both', expand=True)
        # Units
        frm=tk.LabelFrame(wrap, text='Units & Display', fg=COL_TEXT, bg=COL_BG, bd=2, labelanchor='n')
        frm.pack(fill='x', padx=8, pady=8)
        self.units=tk.StringVar(value='F' if app.cfg.weather.units=='imperial' else 'C')
        ttk.Radiobutton(frm, text='Fahrenheit (°F)', value='F', variable=self.units, command=self._units).pack(anchor='w', padx=10, pady=4)
        ttk.Radiobutton(frm, text='Celsius (°C)',    value='C', variable=self.units, command=self._units).pack(anchor='w', padx=10, pady=4)
        self.t24=tk.BooleanVar(value=app.cfg.ui.time_24h)
        ttk.Checkbutton(frm, text='24‑hour time', variable=self.t24, command=self._timefmt).pack(anchor='w', padx=10, pady=4)
        # Offset & Deadband
        frm2=tk.LabelFrame(wrap, text='Calibration & Hysteresis', fg=COL_TEXT, bg=COL_BG, bd=2, labelanchor='n')
        frm2.pack(fill='x', padx=8, pady=8)
        tk.Label(frm2, text='Reading Offset (°C)', fg=COL_TEXT, bg=COL_BG).grid(row=0,column=0,sticky='w',padx=10,pady=4)
        self.offset=tk.DoubleVar(value=getattr(app.cfg.control,'reading_offset_c',0.0))
        tk.Spinbox(frm2, from_=-5.0, to=5.0, increment=0.1, textvariable=self.offset, width=6).grid(row=0,column=1,sticky='w',padx=10,pady=4)
        ttk.Button(frm2, text='Apply', command=lambda: setattr(app.cfg.control,'reading_offset_c', float(self.offset.get()))).grid(row=0,column=2, padx=10)
        tk.Label(frm2, text='Deadband (°C)', fg=COL_TEXT, bg=COL_BG).grid(row=1,column=0,sticky='w',padx=10,pady=4)
        self.db=tk.DoubleVar(value=app.cfg.control.deadband_c)
        tk.Spinbox(frm2, from_=0.2, to=3.0, increment=0.1, textvariable=self.db, width=6).grid(row=1,column=1,sticky='w',padx=10,pady=4)
        ttk.Button(frm2, text='Apply', command=lambda: setattr(app.cfg.control,'deadband_c', float(self.db.get()))).grid(row=1,column=2, padx=10)
        # Nav
        ttk.Button(wrap, text='Open Schedule', command=lambda: app.router.show('schedule')).pack(anchor='w', padx=10, pady=10)
    def _units(self): self.app.cfg.weather.units='imperial' if self.units.get()=='F' else 'metric'
    def _timefmt(self): self.app.cfg.ui.time_24h=bool(self.t24.get())

class WeatherScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Weather')
        self.icon=tk.Label(self.body, text='☀', fg='#ffe680', bg=COL_BG, font=tkfont.Font(size=80, weight='bold')); self.icon.pack(pady=(12,6))
        self.lbl=tk.Label(self.body, textvariable=app.out_desc_var, fg=COL_TEXT, bg=COL_BG, font=app.f_mid); self.lbl.pack(pady=6)
        self.temp=tk.Label(self.body, textvariable=app.outside_var, fg=COL_TEXT, bg=COL_BG, font=app.f_big); self.temp.pack()
        ttk.Button(self.body, text='Refresh Now', command=lambda: app._fetch_weather()).pack(pady=12)

class InfoScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Information')
        tk.Label(self.body, text='Sensor: Internal/Mock', fg=COL_TEXT, bg=COL_BG).pack(anchor='w', pady=6)
        tk.Label(self.body, textvariable=app.mode_var, fg=COL_TEXT, bg=COL_BG).pack(anchor='w', pady=6)

class ScheduleScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Schedule')
        self.path='config/schedule.yaml'
        self.sch = load_schedule(self.path)
        # Day tabs
        self.day_idx=0
        tab=tk.Frame(self.body, bg=COL_BG); tab.pack(fill='x', pady=(0,6))
        for i,d in enumerate(DAYS):
            tk.Button(tab, text=d.title(), bg=COL_BG, fg=COL_TEXT, bd=0, font=self.app.f_small, command=lambda k=i: self._pick_day(k)).pack(side='left', padx=6)
        # Editor
        self.rows=[]
        grid=tk.Frame(self.body, bg=COL_BG); grid.pack(fill='both', expand=True, padx=4, pady=6)
        hdr=('Time (24h HH:MM)','Mode','Setpoint (°C)')
        for j,h in enumerate(hdr):
            tk.Label(grid, text=h, fg=COL_TEXT, bg=COL_BG, font=self.app.f_small).grid(row=0,column=j, sticky='w', pady=4, padx=6)
        for r in range(6):
            tvar=tk.StringVar(value=''); mvar=tk.StringVar(value='off'); svar=tk.DoubleVar(value=22.0)
            e=tk.Entry(grid, textvariable=tvar, width=8); e.grid(row=r+1, column=0, sticky='w', padx=6, pady=4)
            opt=ttk.Combobox(grid, textvariable=mvar, values=['off','heat','cool','auto'], width=8, state='readonly'); opt.grid(row=r+1, column=1, sticky='w', padx=6, pady=4)
            sp=tk.Spinbox(grid, from_=5.0, to=35.0, increment=0.5, textvariable=svar, width=6); sp.grid(row=r+1, column=2, sticky='w', padx=6, pady=4)
            self.rows.append((tvar,mvar,svar))
        # Buttons
        btns=tk.Frame(self.body, bg=COL_BG); btns.pack(fill='x', pady=6)
        ttk.Button(btns, text='Load', command=self._load_day).pack(side='left', padx=4)
        ttk.Button(btns, text='Save', command=self._save_day).pack(side='left', padx=4)
        ttk.Button(btns, text='Save All Days', command=self._save_all).pack(side='left', padx=4)
        self._load_day()
    def _pick_day(self, i):
        self.day_idx=i; self._load_day()
    def _load_day(self):
        day=DAYS[self.day_idx]; evs=self.sch.days[day].events
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
            try:
                evs.append(Event(time=t, mode=mvar.get().strip() or 'off', setpoint_c=float(svar.get())))
            except Exception: continue
        evs.sort(key=lambda e:e.time)
        return evs[:6]
    def _save_day(self):
        day=DAYS[self.day_idx]
        self.sch.days[day]=DaySchedule(events=self._read_rows())
        save_schedule(self.path, self.sch)
    def _save_all(self):
        # just write current day; others unchanged
        self._save_day()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--windowed', action='store_true'); p.add_argument('--show-cursor', action='store_true'); a=p.parse_args()
    app=TouchUI(fullscreen=not a.windowed, hide_cursor=not a.show_cursor)
    app.protocol('WM_DELETE_WINDOW', lambda: app.destroy())
    signal.signal(signal.SIGTERM, lambda *x: sys.exit(0))
    app.mainloop()
if __name__=='__main__': main()
