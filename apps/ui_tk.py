import os, sys, signal
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import tkinter as tk
from tkinter import ttk, messagebox
from thermostat.runtime import load_config, build_runtime

REFRESH_MS = 1000
TICK_MS = 2000

class ThermostatUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RV Thermostat (Simulated UI)")
        self.geometry("380x260")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Build runtime
        self.cfg = load_config()
        self.ctrl, self.actuators, self.gpio_cleanup = build_runtime(self.cfg)

        # UI state vars
        self.temp_c_var = tk.StringVar(value="--.- °C")
        self.temp_f_var = tk.StringVar(value="--.- °F")
        self.mode_var = tk.StringVar(value=self.cfg.control.mode)
        self.state_var = tk.StringVar(value=self.ctrl.s.current_mode)
        self.setpoint_var = tk.DoubleVar(value=self.cfg.control.setpoint_c)

        self.build_widgets()

        # Schedule AFTER widgets/vars exist, and keep job IDs
        self.refresh_job = self.after(REFRESH_MS, self.refresh_readings)
        self.tick_job    = self.after(TICK_MS, self.control_tick)

    def build_widgets(self):
        pad = {'padx': 8, 'pady': 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, **pad)

        row = 0
        ttk.Label(frm, text="Current Temperature", font=("TkDefaultFont", 10, "bold"))\
            .grid(column=0, row=row, sticky="w", **pad)
        ttk.Label(frm, textvariable=self.temp_c_var)\
            .grid(column=1, row=row, sticky="e", **pad)

        row += 2
        ttk.Label(frm, text="Current Temperature (°F)")\
            .grid(column=0, row=row, sticky="w", **pad)
        ttk.Label(frm, textvariable=self.temp_f_var)\
            .grid(column=1, row=row, sticky="e", **pad)

        row += 1
        ttk.Separator(frm, orient="horizontal")\
            .grid(columnspan=3, row=row, sticky="ew", **pad)

        row += 1
        ttk.Label(frm, text="Setpoint (°C)", font=("TkDefaultFont", 10, "bold"))\
            .grid(column=0, row=row, sticky="w", **pad)
        sp_frame = ttk.Frame(frm)
        sp_frame.grid(column=1, row=row, sticky="e", **pad)
        ttk.Button(sp_frame, text="−", width=3,
                   command=lambda: self.bump_setpoint(-0.5)).pack(side="left", padx=3)
        ttk.Label(sp_frame, textvariable=self.setpoint_var, width=6, anchor="center")\
            .pack(side="left")
        ttk.Button(sp_frame, text="+", width=3,
                   command=lambda: self.bump_setpoint(+0.5)).pack(side="left", padx=3)

        row += 1
        ttk.Label(frm, text="Mode", font=("TkDefaultFont", 10, "bold"))\
            .grid(column=0, row=row, sticky="w", **pad)
        mode_combo = ttk.Combobox(
            frm,
            textvariable=self.mode_var,
            values=["off", "heat", "cool", "auto"],
            state="readonly",
            width=8,
        )
        mode_combo.grid(column=1, row=row, sticky="e", **pad)
        mode_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_mode())

        row += 1
        ttk.Label(frm, text="System State")\
            .grid(column=0, row=row, sticky="w", **pad)
        ttk.Label(frm, textvariable=self.state_var)\
            .grid(column=1, row=row, sticky="e", **pad)

        row += 1
        ttk.Separator(frm, orient="horizontal")\
            .grid(columnspan=3, row=row, sticky="ew", **pad)

        row += 1
        btn_row = ttk.Frame(frm)
        btn_row.grid(column=0, row=row, columnspan=2, sticky="ew")
        ttk.Button(btn_row, text="Power Off", command=self.power_off)\
            .pack(side="left", padx=5)
        ttk.Button(btn_row, text="Fan Test (5s)", command=self.fan_test)\
            .pack(side="left", padx=5)

    def c_to_f(self, c: float) -> float:
        return (c * 9.0 / 5.0) + 32.0

    def bump_setpoint(self, delta: float):
        val = round((self.setpoint_var.get() + delta) * 2) / 2.0
        self.setpoint_var.set(val)
        self.cfg.control.setpoint_c = float(val)

    def apply_mode(self):
        self.cfg.control.mode = self.mode_var.get()

    def refresh_readings(self):
        # Show exactly what the controller used last tick
        t = self.ctrl.s.last_temp_c
        if t is None:
            self.temp_c_var.set("--.- °C")
            self.temp_f_var.set("--.- °F")
        else:
            self.temp_c_var.set(f"{t:.2f} °C")
            self.temp_f_var.set(f"{self.c_to_f(t):.1f} °F")
        self.state_var.set(self.ctrl.s.current_mode)

        self.refresh_job = self.after(REFRESH_MS, self.refresh_readings)

    def control_tick(self):
        self.ctrl.tick()
        self.tick_job = self.after(TICK_MS, self.control_tick)

    def power_off(self):
        self.mode_var.set("off")
        self.apply_mode()
        self.ctrl.tick()

    def fan_test(self):
        try:
            self.ctrl.act.o.fan.on()
            self.after(5000, self.ctrl.act.o.fan.off)
        except Exception as ex:
            messagebox.showerror("Fan Test", f"Error: {ex}")

    def on_close(self):
        # cancel scheduled callbacks to avoid "called after destroy" errors
        for job in (getattr(self, "refresh_job", None), getattr(self, "tick_job", None)):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        try:
            self.ctrl.act.all_off()   # safe state
            self.gpio_cleanup()       # from build_runtime(...)
        except Exception:
            pass
        self.destroy()

def main():
    app = ThermostatUI()
    app.mainloop()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    main()
