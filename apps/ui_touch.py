import os, sys, signal, argparse, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from thermostat.runtime import load_config, build_runtime

REFRESH_MS = 1000
TICK_MS = 2000

class TouchUI(tk.Tk):
    def __init__(self, fullscreen=True):
        super().__init__()
        self.title("RV Thermostat")
        self.configure(bg="#111")
        self.attributes("-fullscreen", bool(fullscreen))
        self.bind("<Escape>", lambda e: self.exit_kiosk())
        self.bind("<F11>", lambda e: self.toggle_fullscreen())

        # runtime
        self.cfg = load_config()
        self.ctrl, self.actuators, self.gpio_cleanup = build_runtime(self.cfg)

        # fonts (big & touch-friendly)
        self.f_title  = tkfont.Font(size=22, weight="bold")
        self.f_big    = tkfont.Font(size=56, weight="bold")
        self.f_mid    = tkfont.Font(size=28, weight="bold")
        self.f_small  = tkfont.Font(size=18)

        # ttk theme tweaks
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=12, font=self.f_mid)
        style.configure("Mode.TRadiobutton", padding=8, font=self.f_small)
        style.configure("TLabel", background="#111", foreground="#eee")
        style.configure("Header.TLabel", font=self.f_title, background="#111", foreground="#eee")

        self.temp_c_var   = tk.StringVar(value="--.- °C")
        self.temp_f_var   = tk.StringVar(value="--.- °F")
        self.mode_var     = tk.StringVar(value=self.cfg.control.mode)
        self.state_var    = tk.StringVar(value=self.ctrl.s.current_mode)
        self.setpoint_var = tk.DoubleVar(value=self.cfg.control.setpoint_c)

        self.build_layout()

        # timers
        self.refresh_job = self.after(REFRESH_MS, self.refresh_readings)
        self.tick_job    = self.after(TICK_MS, self.control_tick)

    # -------- Layout --------
    def build_layout(self):
        root = self
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        # Top bar
        top = ttk.Frame(root, padding=16)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ttk.Label(top, text="RV Thermostat", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        self.clock_var = tk.StringVar(value=time.strftime("%-I:%M %p"))
        ttk.Label(top, textvariable=self.clock_var, style="Header.TLabel").grid(row=0, column=1, sticky="e")
        self.after(1000, self._tick_clock)

        # Main panel
        main = ttk.Frame(root, padding=16)
        main.grid(row=1, column=0, sticky="nsew")
        for c in range(3):
            main.grid_columnconfigure(c, weight=1)
        for r in range(4):
            main.grid_rowconfigure(r, weight=1)

        # Big temperature display
        self.lbl_temp = ttk.Label(main, textvariable=self.temp_f_var, anchor="center")
        self.lbl_temp.configure(font=self.f_big)
        self.lbl_temp.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0,8))

        # Mode buttons (radio)
        mode_frame = ttk.Frame(main)
        mode_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=8)
        for m,label in [("off","OFF"),("heat","HEAT"),("cool","COOL"),("auto","AUTO")]:
            rb = ttk.Radiobutton(mode_frame, text=label, variable=self.mode_var,
                                 value=m, style="Mode.TRadiobutton",
                                 command=self.apply_mode)
            rb.pack(side="left", expand=True, fill="x", padx=6, pady=4)

        # Setpoint controls
        sp_frame = ttk.Frame(main)
        sp_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=8)
        btn_minus = ttk.Button(sp_frame, text="−", command=lambda: self.bump_setpoint(-0.5))
        btn_plus  = ttk.Button(sp_frame, text="+", command=lambda: self.bump_setpoint(+0.5))
        for i in range(3):
            sp_frame.grid_columnconfigure(i, weight=1)
        btn_minus.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        ttk.Label(sp_frame, textvariable=self.setpoint_var, anchor="center",
                  font=self.f_mid).grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        btn_plus.grid(row=0, column=2, sticky="nsew", padx=8, pady=8)

        # Status + quick actions
        status = ttk.Frame(main)
        status.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8,0))
        ttk.Label(status, text="STATE:", font=self.f_small).pack(side="left")
        ttk.Label(status, textvariable=self.state_var, font=self.f_small).pack(side="left", padx=(8,24))
        ttk.Button(status, text="Fan 5s", command=self.fan_test).pack(side="right", padx=6)
        ttk.Button(status, text="Power Off", command=self.power_off).pack(side="right", padx=6)

        # Gestures: double-tap top-left to exit kiosk
        root.bind("<Double-Button-1>", self._maybe_exit_area)

    # -------- Behavior --------
    def _tick_clock(self):
        self.clock_var.set(time.strftime("%-I:%M %p"))
        self.after(1000, self._tick_clock)

    def c_to_f(self, c): return (c * 9.0 / 5.0) + 32.0

    def bump_setpoint(self, delta):
        val = round((self.setpoint_var.get() + delta) * 2) / 2.0
        self.setpoint_var.set(val)
        self.cfg.control.setpoint_c = float(val)

    def apply_mode(self):
        self.cfg.control.mode = self.mode_var.get()
        # force a control cycle so state updates promptly
        self.ctrl.tick()

    def refresh_readings(self):
        t = self.ctrl.s.last_temp_c
        if t is None:
            self.temp_c_var = "--.- °C"
            self.temp_f_var.set("--.- °F")
            self.lbl_temp.configure(text="--.- °F")
        else:
            self.lbl_temp.configure(text=f"{self.c_to_f(t):.0f} °F")
        self.state_var.set(self.ctrl.s.current_mode)
        self.refresh_job = self.after(REFRESH_MS, self.refresh_readings)

    def control_tick(self):
        self.ctrl.tick()
        self.tick_job = self.after(TICK_MS, self.control_tick)

    def power_off(self):
        self.mode_var.set("off")
        self.apply_mode()

    def fan_test(self):
        try:
            self.ctrl.act.o.fan.on()
            self.after(5000, self.ctrl.act.o.fan.off)
        except Exception as ex:
            messagebox.showerror("Fan Test", f"Error: {ex}")

    # kiosk helpers
    def toggle_fullscreen(self):
        fs = not bool(self.attributes("-fullscreen"))
        self.attributes("-fullscreen", fs)

    def exit_kiosk(self):
        self.attributes("-fullscreen", False)

    def _maybe_exit_area(self, e):
        # Allow double-tap near top-left corner to toggle fullscreen
        if e.x < 60 and e.y < 60:
            self.toggle_fullscreen()

    def on_close(self):
        for job in (getattr(self, "refresh_job", None), getattr(self, "tick_job", None)):
            if job is not None:
                try: self.after_cancel(job)
                except Exception: pass
        try:
            self.ctrl.act.all_off()
            self.gpio_cleanup()
        except Exception:
            pass
        self.destroy()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--windowed", action="store_true", help="Run windowed (not fullscreen).")
    args = parser.parse_args()
    app = TouchUI(fullscreen=not args.windowed)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    main()
