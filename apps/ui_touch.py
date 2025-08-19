import os, sys, signal, argparse, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from thermostat.runtime import load_config, build_runtime
from thermostat.geolocate import resolve_location
from thermostat.weather import owm_current, pick_emoji, fmt_temp

REFRESH_MS=1000; TICK_MS=2000; IDLE_S=30; ALPHA_ACTIVE=1.0; ALPHA_SLEEP=0.25
COL_BG='#0b0d10'; COL_TEXT='#e9eef5'; COL_DIM='#9aa6b2'; COL_BLUE='#2ea7ff'; COL_RED='#ff4d4d'; COL_GREEN='#00c853'; COL_RED2='#ff1744'; COL_DB='#0d47a1'

def c_to_f(c): return (c*9.0/5.0)+32.0

def f_to_c(f): return (f-32.0)*5.0/9.0

class TouchUI(tk.Tk):
    def __init__(self, fullscreen=True, hide_cursor=True):
        super().__init__(); self.title('RV Thermostat'); self.config(bg=COL_BG); self.attributes('-fullscreen', bool(fullscreen))
        if hide_cursor: self.config(cursor='none')
        self.last_input_ts=time.time(); self._sleeping=False
        for ev in ('<Button-1>','<Button-2>','<Button-3>','<Key>','<Motion>'): self.bind_all(ev, self._on_user_input, add='+')
        self.cfg=load_config(); self.ctrl,self.act,self.gpio_cleanup=build_runtime(self.cfg)
        self.f_big=tkfont.Font(size=100, weight='bold'); self.f_mid=tkfont.Font(size=30, weight='bold'); self.f_small=tkfont.Font(size=16)
        self.mode_var=tk.StringVar(value=self.cfg.control.mode); self.state_var=tk.StringVar(value=self.ctrl.s.current_mode)
        self.fan_var=tk.StringVar(value=self.ctrl.s.fan_mode); self.setpoint_var=tk.DoubleVar(value=self.cfg.control.setpoint_c)
        self.outside_var=tk.StringVar(value='--'); self.out_desc_var=tk.StringVar(value=''); self.wifi_state=tk.StringVar(value='disconnected')
        self._build_layout()
        self.refresh_job=self.after(REFRESH_MS, self.refresh_readings); self.tick_job=self.after(TICK_MS, self.control_tick)
        self.saver_job=self.after(1000, self._screensaver_tick); self.wx_job=self.after(1000, self._weather_tick)
        self.bind('<Escape>', lambda e: self.exit_kiosk()); self.bind('<F11>', lambda e: self.toggle_fullscreen())
    def _wifi_color(self): return {'ok':COL_GREEN, 'no-internet':COL_RED2, 'disconnected':COL_DB}.get(self.wifi_state.get(), COL_DB)
    def _build_layout(self):
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(0, weight=1)
        root=tk.Frame(self,bg=COL_BG); root.grid(row=0,column=0,sticky='nsew',padx=16,pady=16)
        for r in range(5): root.grid_rowconfigure(r, weight=1)
        for c in range(5): root.grid_columnconfigure(c, weight=1)
        top_left=tk.Frame(root,bg=COL_BG); top_left.grid(row=0,column=0,sticky='nw',padx=4,pady=2)
        self.lbl_wifi=tk.Label(top_left,text='●',fg=self._wifi_color(),bg=COL_BG,font=self.f_mid); self.lbl_wifi.bind('<Button-1>', lambda e: self._open_wifi_info()); self.lbl_wifi.pack(anchor='w')
        left=tk.Frame(root,bg=COL_BG); left.grid(row=1,column=0,rowspan=3,sticky='w',padx=4)
        self.lbl_out_icon=tk.Label(left,text='☀',fg='#f7d04a',bg=COL_BG,font=self.f_mid); self.lbl_out_icon.grid(row=0,column=0,sticky='w')
        tk.Label(left,text='Outside',fg=COL_TEXT,bg=COL_BG,font=self.f_small).grid(row=1,column=0,sticky='w')
        self.lbl_out=tk.Label(left,textvariable=self.outside_var,fg=COL_TEXT,bg=COL_BG,font=self.f_mid); self.lbl_out.grid(row=2,column=0,sticky='w'); self.lbl_out.bind('<Button-1>', lambda e: self._open_weather())
        center=tk.Frame(root,bg=COL_BG); center.grid(row=1,column=1,columnspan=3,rowspan=3,sticky='nsew')
        center.grid_columnconfigure(0,weight=1); center.grid_rowconfigure(0,weight=1)
        self.lbl_big=tk.Label(center,text='--',fg='#19d3ea',bg=COL_BG,font=self.f_big); self.lbl_big.grid(row=0,column=0,sticky='n')
        rail=tk.Frame(root,bg=COL_BG); rail.grid(row=1,column=4,rowspan=3,sticky='ne')
        self.ic_cool=tk.Label(rail,text='❄',fg=COL_DIM,bg=COL_BG,font=self.f_mid); self.ic_cool.pack(pady=8)
        self.ic_heat=tk.Label(rail,text='🔥',fg=COL_DIM,bg=COL_BG,font=self.f_mid); self.ic_heat.pack(pady=8)
        self.ic_fan=tk.Label(rail,text='🌀',fg=COL_DIM,bg=COL_BG,font=self.f_mid); self.ic_fan.pack(pady=8)
        for w in (self.ic_cool,self.ic_heat): w.bind('<Button-1>', lambda e: self._open_mode())
        self.ic_fan.bind('<Button-1>', lambda e: self._open_fan())
        bottom=tk.Frame(root,bg=COL_BG); bottom.grid(row=4,column=0,columnspan=5,sticky='sew',pady=(0,2))
        for i in range(5): bottom.grid_columnconfigure(i, weight=1)
        tk.Button(bottom,text='ℹ',fg='#20d16b',bg=COL_BG,bd=0,relief='flat',font=self.f_mid,command=self._open_info).grid(row=0,column=0,sticky='w',padx=6)
        self.btn_cool=tk.Button(bottom,text='Cool to\n76 F',fg='white',bg=COL_BLUE,activebackground='#218fd6',activeforeground='white',bd=0,relief='flat',font=self.f_mid,height=2,command=self.cool_to_target)
        self.btn_heat=tk.Button(bottom,text='Heat to\n68 F',fg='white',bg=COL_RED,activebackground='#d63c3c',activeforeground='white',bd=0,relief='flat',font=self.f_mid,height=2,command=self.heat_to_target)
        self.btn_cool.grid(row=0,column=1,sticky='nsew',padx=8); self.btn_heat.grid(row=0,column=3,sticky='nsew',padx=8)
        tk.Button(bottom,text='⚙',fg='white',bg=COL_BG,bd=0,relief='flat',font=self.f_mid,command=self._open_settings).grid(row=0,column=4,sticky='e',padx=6)
    def _open_info(self):
        t=tk.Toplevel(self); t.title('Thermostat Info'); t.configure(bg=COL_BG)
        src='DS18B20' if self.cfg.sensor.kind=='ds18b20' else 'Internal/Mock'
        tk.Label(t,text=f'Sensor: {src}',fg=COL_TEXT,bg=COL_BG).pack(padx=16,pady=(16,4))
        tk.Label(t,text=f'Fan: {self.ctrl.s.fan_mode}  •  Mode: {self.cfg.control.mode}',fg=COL_TEXT,bg=COL_BG).pack(padx=16,pady=4)
        ttk.Button(t,text='Close',command=t.destroy).pack(pady=12)
    def _open_weather(self):
        if self.wifi_state.get()!='ok':
            messagebox.showinfo('Weather','Connect to Wi‑Fi to view weather.'); return
        w=tk.Toplevel(self); w.title('Weather'); w.configure(bg=COL_BG)
        tk.Label(w,text=f"{self.out_desc_var.get()}  {self.outside_var.get()}",fg=COL_TEXT,bg=COL_BG,font=self.f_mid).pack(padx=16,pady=(16,6))
        ttk.Button(w,text='Refresh now',command=lambda: self._fetch_weather(force=True)).pack(pady=6)
        ttk.Button(w,text='Close',command=w.destroy).pack(pady=6)
    def _open_wifi_info(self):
        wi=tk.Toplevel(self); wi.title('Wi‑Fi'); wi.configure(bg=COL_BG)
        tk.Label(wi,text='Wi‑Fi Status:',fg=COL_TEXT,bg=COL_BG).pack(anchor='w',padx=16,pady=(16,4))
        tk.Label(wi,text=f"State = {self.wifi_state.get()}  (●: green OK / red no‑internet / dark‑blue disconnected)",fg=COL_TEXT,bg=COL_BG).pack(anchor='w',padx=16)
        ttk.Button(wi,text='Close',command=wi.destroy).pack(pady=12)
    def _open_mode(self):
        s=tk.Toplevel(self); s.title('Mode'); s.configure(bg=COL_BG)
        for m,label in (('off','OFF'),('heat','HEAT'),('cool','COOL'),('auto','AUTO')):
            ttk.Radiobutton(s,text=label,value=m,variable=self.mode_var,command=self.apply_mode).pack(anchor='w',padx=10,pady=6)
        ttk.Button(s,text='Close',command=s.destroy).pack(pady=8)
    def _open_fan(self):
        s=tk.Toplevel(self); s.title('Fan'); s.configure(bg=COL_BG)
        for f,label in (('auto','AUTO (with cycles)'),('cycled','CYCLED'),('manual','MANUAL'),('off','OFF')):
            ttk.Radiobutton(s,text=label,value=f,variable=self.fan_var,command=self._apply_fan).pack(anchor='w',padx=10,pady=6)
        ttk.Button(s,text='Close',command=s.destroy).pack(pady=8)
    def _open_settings(self):
        s=tk.Toplevel(self); s.title('Settings'); s.configure(bg=COL_BG)
        nb=ttk.Notebook(s); nb.pack(fill='both', expand=True, padx=8, pady=8)
        frm_units=tk.Frame(nb,bg=COL_BG); nb.add(frm_units,text='Units')
        self.units_var=tk.StringVar(value='F' if self.cfg.weather.units=='imperial' else 'C')
        ttk.Radiobutton(frm_units,text='Fahrenheit (°F)',value='F',variable=self.units_var,command=self._units_changed).pack(anchor='w',padx=10,pady=6)
        ttk.Radiobutton(frm_units,text='Celsius (°C)',value='C',variable=self.units_var,command=self._units_changed).pack(anchor='w',padx=10,pady=6)
        tk.Label(frm_units,text='Reading Offset (°C)',fg=COL_TEXT,bg=COL_BG).pack(anchor='w',padx=10,pady=(10,2))
        self.offset_var=tk.DoubleVar(value=getattr(self.cfg.control,'reading_offset_c',0.0))
        tk.Spinbox(frm_units,from_=-5.0,to=5.0,increment=0.1,textvariable=self.offset_var,width=6).pack(anchor='w',padx=10)
        ttk.Button(frm_units,text='Apply Offset',command=self._apply_offset).pack(anchor='w',padx=10,pady=6)
        frm_hyst=tk.Frame(nb,bg=COL_BG); nb.add(frm_hyst,text='Hysteresis')
        self.db_var=tk.DoubleVar(value=self.cfg.control.deadband_c)
        tk.Label(frm_hyst,text='Deadband (°C):',fg=COL_TEXT,bg=COL_BG).pack(anchor='w',padx=10,pady=(10,2))
        tk.Spinbox(frm_hyst,from_=0.2,to=3.0,increment=0.1,textvariable=self.db_var,width=6).pack(anchor='w',padx=10)
        ttk.Button(frm_hyst,text='Apply',command=self._apply_deadband).pack(anchor='w',padx=10,pady=6)
        frm_disp=tk.Frame(nb,bg=COL_BG); nb.add(frm_disp,text='Display')
        ttk.Button(frm_disp,text='Night Mode (dim now)',command=lambda: self._force_sleep(True)).pack(anchor='w',padx=10,pady=6)
        ttk.Button(frm_disp,text='Day Mode (wake)',command=lambda: self._force_sleep(False)).pack(anchor='w',padx=10,pady=6)
        frm_wx=tk.Frame(nb,bg=COL_BG); nb.add(frm_wx,text='Weather')
        tk.Label(frm_wx,text='Provider: OpenWeatherMap',fg=COL_TEXT,bg=COL_BG).pack(anchor='w',padx=10,pady=6)
        tk.Label(frm_wx,text='API key is read from config.yaml (weather.api_key).',fg=COL_DIM,bg=COL_BG).pack(anchor='w',padx=10,pady=(0,6))
        ttk.Button(frm_wx,text='Refresh Now',command=lambda: self._fetch_weather(force=True)).pack(anchor='w',padx=10,pady=6)
        ttk.Button(s,text='Close',command=s.destroy).pack(pady=8)
    def _apply_offset(self):
        try: self.cfg.control.reading_offset_c=float(self.offset_var.get())
        except Exception: pass
    def _apply_deadband(self):
        try: self.cfg.control.deadband_c=float(self.db_var.get())
        except Exception: pass
    def _apply_fan(self): self.ctrl.s.fan_mode=self.fan_var.get()
    def _units_changed(self):
        self.cfg.weather.units='imperial' if self.units_var.get()=='F' else 'metric'; self._refresh_outside_text()
    def _on_user_input(self,*_):
        self.last_input_ts=time.time()
        if self._sleeping: self.attributes('-alpha', ALPHA_ACTIVE); self._sleeping=False
    def _force_sleep(self, yes: bool):
        self.attributes('-alpha', ALPHA_SLEEP if yes else ALPHA_ACTIVE); self._sleeping=yes; self.last_input_ts=time.time()
    def apply_mode(self): self.cfg.control.mode=self.mode_var.get(); self.ctrl.tick()
    def cool_to_target(self): self.mode_var.set('cool'); self.cfg.control.mode='cool'; self.cfg.control.setpoint_c=f_to_c(76.0); self.setpoint_var.set(self.cfg.control.setpoint_c); self.ctrl.tick()
    def heat_to_target(self): self.mode_var.set('heat'); self.cfg.control.mode='heat'; self.cfg.control.setpoint_c=f_to_c(68.0); self.setpoint_var.set(self.cfg.control.setpoint_c); self.ctrl.tick()
    def _refresh_outside_text(self, temp=None, desc=None):
        if temp is not None: self._last_out_temp=temp
        if desc is not None: self._last_out_desc=desc
        units=self.cfg.weather.units
        s=fmt_temp(getattr(self,'_last_out_temp',None), units)
        self.outside_var.set(s); self.out_desc_var.set(getattr(self,'_last_out_desc',''))
        self.lbl_out_icon.config(text=pick_emoji(self.out_desc_var.get()))
    def _fetch_weather(self, force=False):
        loc=resolve_location(self.cfg)
        if not loc:
            self.wifi_state.set('disconnected'); self._refresh_outside_text(None,''); return
        data=owm_current(loc['lat'],loc['lon'], self.cfg.weather.api_key, units=self.cfg.weather.units)
        if not data:
            self.wifi_state.set('no-internet'); self._refresh_outside_text(None,''); return
        self.wifi_state.set('ok'); self._refresh_outside_text(data.get('temp'), data.get('desc'))
    def _weather_tick(self):
        try: self._fetch_weather(False)
        except Exception: pass
        mins=max(3, int(getattr(self.cfg.weather,'refresh_minutes',10) or 10)); self.wx_job=self.after(mins*60*1000, self._weather_tick)
    def refresh_readings(self):
        t=self.ctrl.s.last_temp_c
        if self.cfg.weather.units=='imperial': self.lbl_big.config(text='--' if t is None else f"{c_to_f(t):.0f}")
        else: self.lbl_big.config(text='--' if t is None else f"{t:.0f}")
        mode=self.ctrl.s.current_mode
        self.ic_cool.config(fg=(COL_BLUE if mode=='cooling' else COL_DIM))
        self.ic_heat.config(fg=('#ffb07c' if mode=='heating' else COL_DIM))
        self.ic_fan.config(fg=(COL_GREEN if mode in ('heating','cooling') else COL_DIM))
        self.lbl_wifi.config(fg=self._wifi_color())
        self.refresh_job=self.after(REFRESH_MS, self.refresh_readings)
    def control_tick(self): self.ctrl.tick(); self.tick_job=self.after(TICK_MS, self.control_tick)
    def toggle_fullscreen(self): self.attributes('-fullscreen', not bool(self.attributes('-fullscreen')))
    def exit_kiosk(self): self.attributes('-fullscreen', False)
    def _screensaver_tick(self):
        if time.time()-self.last_input_ts>=IDLE_S and not self._sleeping:
            self.attributes('-alpha', ALPHA_SLEEP); self._sleeping=True
        self.saver_job=self.after(1000, self._screensaver_tick)
    def on_close(self):
        for job in (getattr(self,'refresh_job',None),getattr(self,'tick_job',None),getattr(self,'saver_job',None),getattr(self,'wx_job',None)):
            if job is not None:
                try: self.after_cancel(job)
                except Exception: pass
        try: self.ctrl.act.all_off(); self.gpio_cleanup()
        except Exception: pass
        self.destroy()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--windowed',action='store_true'); p.add_argument('--show-cursor',action='store_true'); a=p.parse_args()
    app=TouchUI(fullscreen=not a.windowed, hide_cursor=not a.show_cursor)
    app.protocol('WM_DELETE_WINDOW', app.on_close); signal.signal(signal.SIGTERM, lambda *x: sys.exit(0)); app.mainloop()
if __name__=='__main__': main()
