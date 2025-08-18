# RV Thermostat — Touch Kiosk Build

This bundle includes the **new touchscreen UI** and the core control loop.

## What’s in this version
- **Fullscreen, touch-friendly layout** with bold colors (blue/red action buttons, dark card, teal/cyan accents).
- **Hidden cursor** inside the Tk window by default (toggle with `--show-cursor`).
- **Big central °F readout** that mirrors the controller’s `last_temp_c` (single source of truth).
- Quick actions: **Cool to 76°F** / **Heat to 68°F** (updates mode + setpoint immediately).
- Mode selectors (**OFF / HEAT / COOL / AUTO**) and **setpoint nudgers** (+/−).
- **Status indicators** for **COOL / HEAT / FAN** change color based on state.
- **Right-side vertical action bar** (WiFi / Bluetooth / Scheduling / Alarm) as placeholders.
- **Top bar** with title, **zone badge**, and decorative **Wi‑Fi** indicator.
- **Clean shutdown**: cancels timers, sets outputs safe, calls `gpio_cleanup()`.

## Run
```bash
cd rv-thermostat
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip -r requirements.txt
PYTHONPATH=src python apps/ui_touch.py
# windowed / show mouse for debugging:
PYTHONPATH=src python apps/ui_touch.py --windowed --show-cursor
```
