# Touchscreen kiosk UI for RV Thermostat (Option A)
import os, sys, signal, argparse, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from thermostat.runtime import load_config, build_runtime

REFRESH_MS = 1000
TICK_MS = 2000

# ---- Color palette ----
COL_BG      = "#0f1218"   # deep slate
COL_PANEL   = "#151a22"   # card
COL_TEXT    = "#eef2f6"   # primary text
COL_MUTED   = "#98a2b3"   # secondary text
COL_BLUE    = "#2ea7ff"   # cool action
COL_RED     = "#ff4d4d"   # heat action
COL_TEAL    = "#1ac6a9"   # fan/ok
COL_AMBER   = "#f59e0b"   # outside label
COL_CYAN    = "#22d3ee"   # accents
COL_GRAYBTN = "#1f2630"   # neutral buttons

def c_to_f(c: float) -> float: return (c * 9.0 / 5.0) + 32.0
def f_to_c(f: float) -> float: return (f - 32.0) * 5.0 / 9.0

class TouchUI(tk.Tk):
    def __init__(self, fullscreen=True, hide_cursor=True):
        super().__init__()
        self.title("RV Thermostat")
        self.configure(bg=COL_BG)
        self.attributes("-fullscreen", bool(fullscreen))
        if hide_cursor:
            # Hide mouse cursor inside the Tk window
            self.config(cursor="none")

        # shortcuts
        self.bind("<Escape>", lambda e: self.exit_kiosk())
        self.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.bind("<Double-Button-1>", self._maybe_exit_area)  # double-tap top-left to toggle fullscreen

        # runtime
        self.cfg = load_config()
        self.ctrl, self.actuators, self.gpio_cleanup = build_runtime(self.cfg)

        # fonts
        self.f_title  = tkfont.Font(size=20, weight="bold")
        self.f_big    = tkfont.Font(size=84, weight="bold")
        self.f_mid    = tkfont.Font(size=30, weight="bold")
        self.f_small  = tkfont.Font(size=18)
        self.f_caps   = tkfont.Font(size=14, weight="bold")

        # UI state
        self.mode_var     = tk.StringVar(value=self.cfg.control.mode)
        self.state_var    = tk.StringVar(value=self.ctrl.s.current_mode)
        self.setpoint_var = tk.DoubleVar(value=self.cfg.control.setpoint_c)
        self.outside_var  = tk.StringVar(value="-- °F")  # placeholder

        # quick targets
        self.cool_target_f = 76.0
        self.heat_target_f = 68.0

        self._build_layout()

        # timers
        self.refresh_job = self.after(REFRESH_MS, self.refresh_readings)
        self.tick_job    = self.after(TICK_MS, self.control_tick)

    # ---------------- Layout ----------------
    def _zone_badge(self, parent, text="1"):
        c = tk.Canvas(parent, width=46, height=40, bg=COL_PANEL, highlightthickness=0)
        c.create_oval(6, 6, 40, 34, fill=COL_GRAYBTN, outline="")
        c.create_text(23, 20, text=str(text), fill=COL_TEXT, font=self.f_mid)
        return c

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top bar: title, zone badge, Wi-Fi indicator
        top = tk.Frame(self, bg=COL_PANEL)
        top.grid(row=0, column=0, sticky="ew")
        for i in range(3): top.grid_columnconfigure(i, weight=1)
        tk.Label(top, text="RV THERMOSTAT", fg=COL_TEXT, bg=COL_PANEL, font=self.f_title)            .grid(row=0, column=0, sticky="w", padx=18, pady=12)
        self._zone_badge(top, "1").grid(row=0, column=1)
        tk.Label(top, text="Wi-Fi ●●●", fg=COL_CYAN, bg=COL_PANEL, font=self.f_caps)            .grid(row=0, column=2, sticky="e", padx=18)

        # Main area with card
        main = tk.Frame(self, bg=COL_BG)
        main.grid(row=1, column=0, sticky="nsew", padx=16, pady=(10,16))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        card = tk.Frame(main, bg=COL_PANEL)
        card.grid(row=0, column=0, sticky="nsew")
        for r in range(6): card.grid_rowconfigure(r, weight=1)
        for c in range(3): card.grid_columnconfigure(c, weight=1)

        # Left rail: Outside + Indicators
        left = tk.Frame(card, bg=COL_PANEL)
        left.grid(row=0, column=0, rowspan=6, sticky="nsw", padx=(14,0), pady=14)
        tk.Label(left, text="Outside", fg=COL_AMBER, bg=COL_PANEL, font=self.f_caps).pack(anchor="w")
        tk.Label(left, textvariable=self.outside_var, fg=COL_TEXT, bg=COL_PANEL, font=self.f_mid)            .pack(anchor="w", pady=(0,10))
        ind = tk.Frame(left, bg=COL_PANEL); ind.pack(anchor="w", pady=(10,0))
        self.ind_cool = tk.Label(ind, text="❄ COOL", fg=COL_MUTED, bg=COL_PANEL, font=self.f_small)
        self.ind_heat = tk.Label(ind, text="🔥 HEAT", fg=COL_MUTED, bg=COL_PANEL, font=self.f_small)
        self.ind_fan  = tk.Label(ind, text="🌀 FAN",  fg=COL_MUTED, bg=COL_PANEL, font=self.f_small)
        self.ind_cool.grid(row=0, column=0, padx=(0,14))
        self.ind_heat.grid(row=0, column=1, padx=(0,14))
        self.ind_fan.grid(row=0, column=2)

        # Center: big °F + state
        center = tk.Frame(card, bg=COL_PANEL)
        center.grid(row=0, column=1, rowspan=4, sticky="nsew")
        center.grid_columnconfigure(0, weight=1); center.grid_rowconfigure(0, weight=1)
        self.lbl_bigtemp = tk.Label(center, text="--", fg=COL_CYAN, bg=COL_PANEL, font=self.f_big)
        self.lbl_bigtemp.grid(row=0, column=0, sticky="n", pady=(10,0))
        tk.Label(center, textvariable=self.state_var, fg=COL_MUTED, bg=COL_PANEL, font=self.f_small)            .grid(row=1, column=0, pady=(0,8))

        # Right action bar (placeholders)
        right = tk.Frame(card, bg=COL_PANEL)
        right.grid(row=0, column=2, rowspan=6, sticky="nse", padx=(0,14), pady=14)
        for txt in ("WiFi", "Bluetooth", "Scheduling", "Alarm"):
            tk.Button(right, text=txt, fg=COL_TEXT, bg="#1b2230", bd=0, relief="flat",
                      activebackground="#243043", activeforeground=COL_TEXT, font=self.f_small, width=12)                .pack(pady=6, fill="x")

        # Mode selectors
        modes = tk.Frame(card, bg=COL_PANEL)
        modes.grid(row=4, column=1, sticky="n", pady=(0,6))
        for m,label in (("off","OFF"),("heat","HEAT"),("cool","COOL"),("auto","AUTO")):
            ttk.Radiobutton(modes, text=label, value=m, variable=self.mode_var, command=self.apply_mode)                .pack(side="left", padx=8, pady=6)

        # Setpoint nudgers
        nudges = tk.Frame(card, bg=COL_PANEL)
        nudges.grid(row=4, column=0, sticky="w", padx=12)
        tk.Label(nudges, text="Setpoint", fg=COL_TEXT, bg=COL_PANEL, font=self.f_small)            .pack(side="left", padx=(0,8))
        tk.Button(nudges, text="−", fg=COL_TEXT, bg=COL_GRAYBTN, bd=0, relief="flat",
                  font=self.f_mid, width=2, command=lambda: self.bump_setpoint(-0.5))            .pack(side="left", padx=4)
        self.lbl_setpoint = tk.Label(nudges, text=self._format_sp_f(), fg=COL_TEXT, bg=COL_PANEL, font=self.f_mid)
        self.lbl_setpoint.pack(side="left", padx=8)
        tk.Button(nudges, text="+", fg=COL_TEXT, bg=COL_GRAYBTN, bd=0, relief="flat",
                  font=self.f_mid, width=2, command=lambda: self.bump_setpoint(+0.5))            .pack(side="left", padx=4)

        # Bottom action buttons
        bottom = tk.Frame(card, bg=COL_PANEL)
        bottom.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0,12), padx=12)
        bottom.grid_columnconfigure(0, weight=1); bottom.grid_columnconfigure(1, weight=1)
        self.btn_cool = tk.Button(
            bottom, text="Cool to 76°F", command=self.cool_to_target,
            fg=COL_TEXT, bg=COL_BLUE, activebackground="#1f8fd6",
            activeforeground=COL_TEXT, bd=0, relief="flat", font=self.f_mid, height=1
        )
        self.btn_cool.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        self.btn_heat = tk.Button(
            bottom, text="Heat to 68°F", command=self.heat_to_target,
            fg=COL_TEXT, bg=COL_RED, activebackground="#d63c3c",
            activeforeground=COL_TEXT, bd=0, relief="flat", font=self.f_mid, height=1
        )
        self.btn_heat.grid(row=0, column=1, sticky="nsew", padx=(8,0))

    # ---------------- Behavior ----------------
    def _format_sp_f(self) -> str:
        return f"{round(c_to_f(self.setpoint_var.get())):.0f}°F"

    def bump_setpoint(self, delta: float):
        val = round((self.setpoint_var.get() + delta) * 2) / 2.0
        self.setpoint_var.set(val)
        self.cfg.control.setpoint_c = float(val)
        self.lbl_setpoint.configure(text=self._format_sp_f())

    def apply_mode(self):
        self.cfg.control.mode = self.mode_var.get()
        self.ctrl.tick()  # immediate feedback

    def cool_to_target(self):
        self.mode_var.set("cool")
        self.cfg.control.mode = "cool"
        self.cfg.control.setpoint_c = f_to_c(76.0)
        self.setpoint_var.set(self.cfg.control.setpoint_c)
        self.lbl_setpoint.configure(text=self._format_sp_f())
        self.ctrl.tick()

    def heat_to_target(self):
        self.mode_var.set("heat")
        self.cfg.control.mode = "heat"
        self.cfg.control.setpoint_c = f_to_c(68.0)
        self.setpoint_var.set(self.cfg.control.setpoint_c)
        self.lbl_setpoint.configure(text=self._format_sp_f())
        self.ctrl.tick()

    def refresh_readings(self):
        t = self.ctrl.s.last_temp_c
        self.lbl_bigtemp.configure(text="--" if t is None else f"{c_to_f(t):.0f}")
        self.state_var.set(self.ctrl.s.current_mode)
        # Indicators coloring
        mode = self.ctrl.s.current_mode
        self.ind_cool.configure(fg=(COL_BLUE if mode == "cooling" else COL_MUTED))
        self.ind_heat.configure(fg=(COL_RED  if mode == "heating" else COL_MUTED))
        self.ind_fan.configure (fg=(COL_TEAL if mode in ("heating","cooling") else COL_MUTED))
        # Outside placeholder
        self.outside_var.set("-- °F")
        self.refresh_job = self.after(REFRESH_MS, self.refresh_readings)

    def control_tick(self):
        self.ctrl.tick()
        self.tick_job = self.after(TICK_MS, self.control_tick)

    # kiosk helpers
    def toggle_fullscreen(self): self.attributes("-fullscreen", not bool(self.attributes("-fullscreen")))
    def exit_kiosk(self): self.attributes("-fullscreen", False)
    def _maybe_exit_area(self, e):
        if e.x < 60 and e.y < 60: self.toggle_fullscreen()

    def on_close(self):
        # Clean shutdown: cancel timers, outputs safe, GPIO cleanup
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
    parser.add_argument("--show-cursor", action="store_true", help="Show mouse cursor (debug).")
    args = parser.parse_args()
    app = TouchUI(fullscreen=not args.windowed, hide_cursor=not args.show_cursor)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    app.mainloop()

if __name__ == "__main__":
    main()
