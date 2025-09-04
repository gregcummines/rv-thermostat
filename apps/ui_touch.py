import os, sys, signal, argparse, time, datetime as dt, socket
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

class UIConfig:
    # Layout
    safe_margin_px = 24

    # Colors
    bg = "#000000"
    fg = "#FFFFFF"
    rail_tile_border = "#FFFFFF"
    cool_pill = "#1E90FF"
    heat_pill = "#E74C3C"
    status_accent = "#7CFC00"
    text_muted = "#A0A0A0"

    # Fonts (optional defaults)
    temp_font = ("Helvetica", 160, "bold")
    temp_unit_font = ("Helvetica", 36, "bold")
    tile_glyph_font = ("Helvetica", 44, "bold")
    tile_label_font = ("Helvetica", 12)

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

class Pill(tk.Canvas):
    def __init__(self, parent, label_text, bg_hex, command=None):
        super().__init__(parent, bg=COL_BG, bd=0, highlightthickness=0, height=64, cursor='hand2')
        self._bg = bg_hex
        self._label_item = self.create_text(0, 0, text=label_text, fill='#FFFFFF',
                                            font=('DejaVu Sans', 14, 'normal'), tags=('pill_label',))
        self._value_item = self.create_text(0, 0, text='--° F', fill='#FFFFFF',
                                            font=('DejaVu Sans', 24, 'bold'), tags=('pill_value',))
        if command:
            self.bind('<Button-1>', lambda e: command())

    def set_value(self, value_text):
        self.itemconfigure(self._value_item, text=value_text)

    def resize(self, w, h):
        self.config(width=w, height=h)
        self.delete('pill_bg')
        r = max(18, h // 2)
        self.create_rectangle(r, 0, w - r, h, outline='', fill=self._bg, tags='pill_bg')
        self.create_oval(0, 0, 2*r, h, outline='', fill=self._bg, tags='pill_bg')
        self.create_oval(w - 2*r, 0, w, h, outline='', fill=self._bg, tags='pill_bg')

        # layout: small label on top, big value below
        label_fs = max(12, int(h * 0.28))
        value_fs = max(18, int(h * 0.46))
        self.itemconfigure(self._label_item, font=('DejaVu Sans', label_fs, 'normal'))
        self.itemconfigure(self._value_item,  font=('DejaVu Sans', value_fs, 'bold'))
        # vertical positions
        self.coords(self._label_item, w//2, int(h*0.35))
        self.coords(self._value_item,  w//2, int(h*0.72))
        # ensure text on top
        self.tag_raise(self._label_item); self.tag_raise(self._value_item)

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
        # Better Python style would be:
        self.after(REFRESH_MS, self.loop)
        self.after(SCHED_MS, self.sched_loop) 
        self.after(1000, self.network_status_loop)  # Add network status check
        self.after(1500, self.weather_loop)

    # loops
    def loop(self):
        t=self.ctrl.s.last_temp_c
        temp = f'{c_to_f(t):.0f}' if (t is not None and self.cfg.weather.units=="imperial") else (f'{t:.0f}' if t is not None else '--')
        self.main.set_temp(temp)
        # Update setpoint pills if values available
        cool_c = getattr(self.ctrl.s, 'cool_setpoint_c', getattr(self.cfg.control, 'cool_setpoint_c', None))
        heat_c = getattr(self.ctrl.s, 'heat_setpoint_c', getattr(self.cfg.control, 'heat_setpoint_c', None))
        if self.cfg.weather.units == "imperial":
            cool = c_to_f(cool_c) if isinstance(cool_c, (int, float)) else None
            heat = c_to_f(heat_c) if isinstance(heat_c, (int, float)) else None
        else:
            cool = cool_c if isinstance(cool_c, (int, float)) else None
            heat = heat_c if isinstance(heat_c, (int, float)) else None
        self.main.set_setpoints(cool, heat)

        self.ctrl.tick()
        self.after(REFRESH_MS, self.loop)

    def sched_loop(self):
        apply_schedule_if_due(self.ctrl, dt.datetime.now())
        self.after(SCHED_MS, self.sched_loop)

    def check_network_status(self):
        """Check network connectivity status. Returns 'ok', 'no_internet', or 'disconnected'"""
        try:
            # Check if we have a Wi-Fi connection
            import subprocess
            result = subprocess.run(['iwconfig'], capture_output=True, text=True)
            if "ESSID:" not in result.stdout:
                return 'disconnected'  # No Wi-Fi connection
            
            # If we have Wi-Fi, check internet by trying to reach Google's DNS
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=1)
                return 'ok'  # Connected with internet
            except OSError:
                return 'no_internet'  # Wi-Fi but no internet
                
        except Exception as e:
            print(f"Network check error: {e}")  # Debug
            return 'disconnected'  # Assume disconnected on any error

    def network_status_loop(self):
        """Update network status every second"""
        try:
            status = self.check_network_status()
            print(f"Got status: {status}")  # Debug
            if status in ('ok', 'no_internet', 'disconnected'):
                self.main.set_status(status)
        except Exception as e:
            print(f"Error in network_status_loop: {e}")  # Debug
            pass
        self.after(1000, self.network_status_loop)

    def weather_loop(self):
        """Get weather data every WX_MIN seconds"""
        now = time.time()
        if now - self._last_wx >= WX_MIN:
            loc = resolve_location(self.cfg)
            if loc and self.cfg.weather.api_key:
                try:
                    data = owm_current(loc['lat'], loc['lon'],
                                    self.cfg.weather.api_key, self.cfg.weather.units)
                    if data and (data.get('temp') is not None):
                        outside = fmt_temp(data.get('temp'), self.cfg.weather.units)
                except Exception:
                    pass
            self._last_wx = now
        self.after(1000, self.weather_loop)

class MainScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.router, bg=COL_BG); self.app=app
        # Columns: left rail, center, right rail
        self.left  = tk.Frame(self, bg=COL_BG); self.left.pack(side='left',  fill='y')
        self.right = tk.Frame(self, bg=COL_BG); self.right.pack(side='right', fill='y')   # <-- changed
        self.center= tk.Frame(self, bg=COL_BG); self.center.pack(side='left', fill='both', expand=True)

        AS = os.path.join(os.path.dirname(__file__), '..', 'assets')
        self.left_tiles = [
            WifiTile(self.left, 100, os.path.join(AS, 'weather.png'), lambda: app.router.show('weather')),
            ImageTile(self.left, 100, os.path.join(AS, 'info.png'),     lambda: app.router.show('info')),
            ImageTile(self.left, 100, os.path.join(AS, 'settings.png'), lambda: app.router.show('settings')),
            ImageTile(self.left, 100, os.path.join(AS, 'schedule.png'), lambda: app.router.show('schedule')),
        ]
        self.right_tiles = [
            ImageTile(self.right, 100, os.path.join(AS, 'snow.png'),  lambda: app.router.show('mode')),
            ImageTile(self.right, 100, os.path.join(AS, 'flame.png'), lambda: app.router.show('mode')),
            ImageTile(self.right, 100, os.path.join(AS, 'fan.png'),   lambda: app.router.show('fan')),
            ImageTile(self.right, 100, os.path.join(AS, 'power.png'), self._power_off),
        ]

        # Center big temp (with degree symbol)
        self.lbl = tk.Label(self.center, text='--°', fg=COL_TEXT, bg=COL_BG)
        self.lbl.pack(expand=True)

        # Setpoint pills at bottom
        self.pills = tk.Frame(self.center, bg=COL_BG)
        self.pills.pack(side='bottom', fill='x', padx=16, pady=(0,16))
        self.cool_pill = Pill(self.pills, 'Cool to', COOL_PILL, command=lambda: app.router.show('mode'))
        self.heat_pill = Pill(self.pills, 'Heat to', HEAT_PILL, command=lambda: app.router.show('mode'))
        self.cool_pill.pack(side='left', expand=True, fill='x', padx=(0,10))
        self.heat_pill.pack(side='left', expand=True, fill='x', padx=(10,0))

        # reflow guarantee: 4 rows always fit
        self.bind('<Configure>', self._layout)

    def _layout(self, e=None):
        W=self.winfo_width() or self.winfo_screenwidth()
        H=self.winfo_height() or self.winfo_screenheight()
        m = int(getattr(self.app.cfg.ui, 'safe_margin_px', SAFE_MARGIN_DEFAULT))
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
        self.lbl.config(font=tkfont.Font(family='DejaVu Sans', size=font_px, weight='normal'))

        # Resize the setpoint pills based on center size
        self.update_idletasks()
        cw = self.center.winfo_width() or (W - 2*(square + 2*m))
        ch = self.center.winfo_height() or (H - 2*m)
        pill_h = max(56, int(ch * 0.12))
        inner_gap = 20
        pill_w = max(160, int((cw - 16*2 - inner_gap) / 2))
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

    def set_status(self, status: str):
        self.left_tiles[0].set_status(status)

class ImageTile(SquareTile):
    def __init__(self, parent, size, image_path, command):
        self._img_path = image_path
        self._photo = None
        super().__init__(parent, size, glyph='', fg='#FFFFFF', command=command)

    def draw(self, size):
        self.delete('all')
        pad=max(4,int(size*0.04)); border=max(2,int(size*0.02))
        self.config(width=size, height=size)
        self.create_rectangle(pad,pad,size-pad,size-pad, outline=COL_FRAME, width=border)
        # load/scale image
        if self._img_path and os.path.exists(self._img_path):
            # Tk PhotoImage only does nearest scaling; for crispness, provide multiple icon sizes if needed.
            self._photo = tk.PhotoImage(file=self._img_path).subsample(max(1, int(self._photo_width()/size)))
            # simpler approach: center the raw image and accept nearest scaling
            self._photo = tk.PhotoImage(file=self._img_path)
            iw = int(size * 0.58); ih = iw
            try:
                self._photo = self._photo.subsample(max(1, self._photo.width() // iw))
            except Exception:
                pass
            self.create_image(size//2, size//2, image=self._photo)

class WifiTile(ImageTile):
    def __init__(self, parent, size, image_path, command):
        self._status = None
        self._size = size
        super().__init__(parent, size, image_path, command)
        
    def draw(self, size):
        # Don't call parent's draw to avoid the border rectangle
        self.delete('all')
        self.config(width=size, height=size)
        self._size = size
        # Redraw status if we have one
        if self._status:
            self.set_status(self._status)
        
    def set_status(self, status: str):
        if status != self._status:  # Only update if status changed
            color = {
                'ok': '#00C853',          # green
                'no_internet': '#2196F3',  # blue
                'disconnected': '#E53935', # red
            }.get(status)
            
            if color:
                # Calculate icon size to fill tile
                w = self._size
                icon_size = int(w * 0.8)  # 80% of tile size
                x = w/2  # center x
                y = w/2  # center y
                
                # Clear previous icon
                self.delete('wifi_icon')
                
                # Draw all elements in the same color
                # Draw three Wi-Fi arcs centered in tile, from largest to smallest
                r = icon_size/2  # Outer arc radius
                self.create_arc(x-r, y-r, x+r, y+r, 
                    start=45, extent=90, style='arc', width=4, 
                    outline=color, tags='wifi_icon')
                
                r = icon_size/3  # Middle arc radius
                self.create_arc(x-r, y-r, x+r, y+r, 
                    start=45, extent=90, style='arc', width=4, 
                    outline=color, tags='wifi_icon')
                
                r = icon_size/6  # Inner arc radius
                self.create_arc(x-r, y-r, x+r, y+r, 
                    start=45, extent=90, style='arc', width=4, 
                    outline=color, tags='wifi_icon')
                
                # Center dot in same color as arcs
                dot_size = icon_size * 0.1
                self.create_oval(x-dot_size/2, y-dot_size/2, 
                    x+dot_size/2, y+dot_size/2, 
                    fill=color, outline=color, tags='wifi_icon')
                
                self._status = status
            else:
                self.delete('wifi_icon')
                self._status = None
                
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
