import os, sys, signal, argparse, time, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from thermostat.runtime import load_config, build_runtime, apply_schedule_if_due
from thermostat.geolocate import resolve_location
from thermostat.weather import owm_current, fmt_temp

COL_BG='#000000'; COL_TEXT='#FFFFFF'; COL_FRAME='#FFFFFF'
REFRESH_MS=1000; SCHED_MS=60000; WX_MIN=180

def c_to_f(c): return (c*9.0/5.0)+32.0
def f_to_c(f): return (f-32.0)*5.0/9.0

class SquareTile(tk.Canvas):
    def __init__(self, parent, size, glyph, fg, command):
        super().__init__(parent, width=size, height=size, bg=COL_BG, bd=0, highlightthickness=0)
        self._glyph=glyph; self._fg=fg; self._cmd=command
        if command: self.bind('<Button-1>', lambda e: command())
        self.draw(size)
    def draw(self, size):
        self.delete('all'); pad=max(4,int(size*0.04)); border=max(2,int(size*0.02))
        self.config(width=size, height=size)
        self.create_rectangle(pad,pad,size-pad,size-pad, outline=COL_FRAME, width=border)
        self.create_text(size/2, size/2, text=self._glyph, fill=self._fg, font=('DejaVu Sans', int(size*0.6), 'bold'))
    def resize(self, size): self.draw(size)

class Router(tk.Frame):
    def __init__(self, root):
        super().__init__(root, bg=COL_BG); self.pack(fill='both', expand=True); self.screens={}; self.current=None
    def register(self,n,w): self.screens[n]=w
    def show(self,n):
        if self.current: self.screens[self.current].pack_forget()
        self.current=n; self.screens[n].pack(fill='both', expand=True)

class Screen(tk.Frame):
    def __init__(self, app, title):
        super().__init__(app.router, bg=COL_BG); self.app=app
        top=tk.Frame(self, bg=COL_BG); top.pack(fill='x', padx=16, pady=12)
        tk.Button(top, text='←', command=lambda: app.router.show('home'), bg=COL_BG, fg=COL_TEXT, bd=0, font=('DejaVu Sans', 28, 'bold'), activebackground=COL_BG).pack(side='left')
        tk.Label(top, text=title, fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 28, 'bold')).pack(side='left', padx=10)
        self.body=tk.Frame(self, bg=COL_BG); self.body.pack(fill='both', expand=True, padx=24, pady=12)

class TouchUI(tk.Tk):
    def __init__(self, fullscreen=True, hide_cursor=True):
        super().__init__(); self.title('RV Thermostat'); self.config(bg=COL_BG)
        try: self.tk.call('tk', 'scaling', 1.0)
        except Exception: pass
        self.attributes('-fullscreen', bool(fullscreen))
        if hide_cursor: self.config(cursor='none')
        self.bind('<Escape>', lambda e: self.attributes('-fullscreen', False))

        self.cfg=load_config(); self.ctrl,self.act,self.gpio_cleanup=build_runtime(self.cfg)
        self.router=Router(self)

        # Screens
        self.main=MainScreen(self); self.router.register('home', self.main)
        self.mode=ModeScreen(self); self.router.register('mode', self.mode)
        self.fan=FanScreen(self); self.router.register('fan', self.fan)
        self.settings=SettingsScreen(self); self.router.register('settings', self.settings)
        self.weather=WeatherScreen(self); self.router.register('weather', self.weather)
        self.info=InfoScreen(self); self.router.register('info', self.info)
        self.schedule=ScheduleScreen(self); self.router.register('schedule', self.schedule)
        self.router.show('home')

        self._last_wx=0
        self.after(REFRESH_MS, self.loop); self.after(SCHED_MS, self.sched_loop); self.after(1500, self.weather_loop)

    # loops
    def loop(self):
        t=self.ctrl.s.last_temp_c
        temp = f'{c_to_f(t):.0f}' if (t is not None and self.cfg.weather.units=="imperial") else (f'{t:.0f}' if t is not None else '--')
        self.main.set_temp(temp)
        self.ctrl.tick()
        self.after(REFRESH_MS, self.loop)

    def sched_loop(self):
        apply_schedule_if_due(self.ctrl, dt.datetime.now())
        self.after(SCHED_MS, self.sched_loop)

    def weather_loop(self):
        now=time.time()
        if now-self._last_wx >= WX_MIN:
            loc=resolve_location(self.cfg)
            if loc and self.cfg.weather.api_key:
                data=owm_current(loc['lat'], loc['lon'], self.cfg.weather.api_key, self.cfg.weather.units)
                self.main.set_outside(fmt_temp(data.get('temp') if data else None, self.cfg.weather.units))
            self._last_wx=now
        self.after(1000, self.weather_loop)

class MainScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.router, bg=COL_BG); self.app=app
        # Columns: left rail, center, right rail
        self.left=tk.Frame(self, bg=COL_BG); self.left.pack(side='left', fill='y')
        self.center=tk.Frame(self, bg=COL_BG); self.center.pack(side='left', fill='both', expand=True)
        self.right=tk.Frame(self, bg=COL_BG); self.right.pack(side='left', fill='y')

        # Tiles (callbacks route to screens)
        self.left_tiles=[
            SquareTile(self.left, 100, '☀', '#ffe680', lambda: app.router.show('weather')),
            SquareTile(self.left, 100, 'ℹ', '#20d16b', lambda: app.router.show('info')),
            SquareTile(self.left, 100, '⚙', '#cfe3ff', lambda: app.router.show('settings')),
            SquareTile(self.left, 100, '🗓', '#c1ffd7', lambda: app.router.show('schedule')),
        ]
        for t in self.left_tiles: t.pack()
        self.right_tiles=[
            SquareTile(self.right, 100, '❄', '#9cd9ff', lambda: app.router.show('mode')),
            SquareTile(self.right, 100, '🔥', '#ffb07c', lambda: app.router.show('mode')),
            SquareTile(self.right, 100, '🌀', '#00c853', lambda: app.router.show('fan')),
            SquareTile(self.right, 100, '⏻', '#ff6666', self._power_off),
        ]
        for t in self.right_tiles: t.pack()

        # Center big temp
        self.lbl=tk.Label(self.center, text='--', fg=COL_TEXT, bg=COL_BG)
        self.lbl.pack(expand=True)

        # outside temp under top-left
        self.out_lbl=tk.Label(self.left, text='', fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 16))
        self.out_lbl.pack(pady=(4,0))

        # reflow guarantee: 4 rows always fit
        self.bind('<Configure>', self._layout)

    def _layout(self, e=None):
        W=self.winfo_width() or self.winfo_screenwidth()
        H=self.winfo_height() or self.winfo_screenheight()
        m=int(getattr(self.app.cfg.ui,'safe_margin_px',24))
        gap=max(8,int(min(W,H)*0.02))
        square = (H - 2*m - 3*gap) // 4
        square = max(72, square)
        # apply to rails
        for i,t in enumerate(self.left_tiles):
            t.resize(square); t.pack_configure(pady=(m if i==0 else gap//2, m if i==3 else gap//2), padx=m)
        for i,t in enumerate(self.right_tiles):
            t.resize(square); t.pack_configure(pady=(m if i==0 else gap//2, m if i==3 else gap//2), padx=m)
        # center font
        center_h = H - 2*m
        font_px = max(80, int(center_h * 0.50))
        self.lbl.config(font=tkfont.Font(size=font_px, weight='bold'))

    def set_temp(self, s): self.lbl.config(text=s)
    def set_outside(self, s): self.out_lbl.config(text=s or '')

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
        ttk.Radiobutton(frm, text='Fahrenheit (°F)', value='F', variable=self.units, command=self._units).pack(anchor='w', padx=10, pady=4)
        ttk.Radiobutton(frm, text='Celsius (°C)',    value='C', variable=self.units, command=self._units).pack(anchor='w', padx=10, pady=4)
        self.t24=tk.BooleanVar(value=app.cfg.ui.time_24h)
        ttk.Checkbutton(frm, text='24‑hour time', variable=self.t24, command=self._timefmt).pack(anchor='w', padx=10, pady=4)
        # Deadband/offset
        frm2=tk.LabelFrame(wrap, text='Calibration & Hysteresis', fg=COL_TEXT, bg=COL_BG, bd=2, labelanchor='n'); frm2.pack(fill='x', padx=8, pady=8)
        tk.Label(frm2, text='Reading Offset (°C)', fg=COL_TEXT, bg=COL_BG).grid(row=0,column=0,sticky='w',padx=10,pady=4)
        self.offset=tk.DoubleVar(value=getattr(app.cfg.control,'reading_offset_c',0.0))
        tk.Spinbox(frm2, from_=-5.0, to=5.0, increment=0.1, textvariable=self.offset, width=6).grid(row=0,column=1,sticky='w',padx=10,pady=4)
        ttk.Button(frm2, text='Apply', command=lambda: setattr(app.cfg.control,'reading_offset_c', float(self.offset.get()))).grid(row=0,column=2, padx=10)
        tk.Label(frm2, text='Deadband (°C)', fg=COL_TEXT, bg=COL_BG).grid(row=1,column=0,sticky='w',padx=10,pady=4)
        self.db=tk.DoubleVar(value=app.cfg.control.deadband_c)
        tk.Spinbox(frm2, from_=0.2, to=3.0, increment=0.1, textvariable=self.db, width=6).grid(row=1,column=1,sticky='w',padx=10,pady=4)
        ttk.Button(frm2, text='Apply', command=lambda: setattr(app.cfg.control,'deadband_c', float(self.db.get()))).grid(row=1,column=2, padx=10)
    def _units(self): self.app.cfg.weather.units='imperial' if self.units.get()=='F' else 'metric'
    def _timefmt(self): self.app.cfg.ui.time_24h=bool(self.t24.get())

class WeatherScreen(Screen):
    def __init__(self, app):
        super().__init__(app, 'Weather')
        self.lbl=tk.Label(self.body, text='--', fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 64, 'bold')); self.lbl.pack(pady=8)
        self.desc=tk.Label(self.body, text='', fg=COL_TEXT, bg=COL_BG, font=('DejaVu Sans', 24)); self.desc.pack(pady=4)
        ttk.Button(self.body, text='Refresh', command=self._refresh).pack(pady=8)
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
        from thermostat.schedule import load_schedule, save_schedule, DAYS, DaySchedule, Event
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
        ttk.Button(btns, text='Load', command=self._load_day).pack(side='left', padx=4)
        ttk.Button(btns, text='Save', command=self._save_day).pack(side='left', padx=4)
        ttk.Button(btns, text='Save All Days', command=self._save_all).pack(side='left', padx=4)
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
        from thermostat.schedule import save_schedule
        save_schedule(self.path, self.sch)
    def _save_all(self): self._save_day()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--windowed', action='store_true'); p.add_argument('--show-cursor', action='store_true'); a=p.parse_args()
    app=TouchUI(fullscreen=not a.windowed, hide_cursor=not a.show_cursor)
    app.protocol('WM_DELETE_WINDOW', lambda: app.destroy())
    signal.signal(signal.SIGTERM, lambda *x: sys.exit(0))
    app.mainloop()
if __name__=='__main__': main()
