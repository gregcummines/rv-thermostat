# RV Thermostat

A Raspberry Pi thermostat with a headless control loop and touch-friendly UI. The controller is the single source of truth for temperature and exposes `state.last_temp_c` for the UIs.

## Repo layout
```text
rv-thermostat/
├── requirements.txt
├── requirements-ui.txt
├── .gitignore
├── README.md
├── config/
│   └── config.yaml
├── src/
│   └── thermostat/
│       ├── __init__.py
│       ├── config.py
│       ├── sensors.py
│       ├── gpioio.py
│       ├── actuators.py
│       ├── controller.py
│       └── runtime.py
├── apps/
│   ├── app.py
│   ├── ui_tk.py
│   └── ui_touch.py
└── system/
    └── rv-thermostat.service
```
## Quick start
```bash
cd ~/rv-thermostat
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip -r requirements.txt
PYTHONPATH=src python apps/ui_touch.py     # kiosk UI (fullscreen)
# or:
PYTHONPATH=src python apps/ui_tk.py        # desktop UI
```
