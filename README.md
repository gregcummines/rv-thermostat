# RV Thermostat

A Raspberry Pi thermostat with a headless control loop and an optional desktop UI (Tkinter). The controller is the single source of truth for temperature: it reads the sensor once per cycle and exposes `state.last_temp_c` for the UI and logs.

## Features
- Deadband control, heat/cool interlock, compressor min-off time, fan lead/lag
- Sensors: `mock` and `ds18b20`
- GPIO relays with `active_low` support
- Tkinter desktop UI (`apps/ui_tk.py`)
- systemd unit (`system/rv-thermostat.service`)

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
│   └── ui_tk.py
└── system/
    └── rv-thermostat.service
```
## Quick start
```bash
cd ~/rv-thermostat
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip -r requirements.txt

# headless loop
PYTHONPATH=src python apps/app.py

# desktop UI (if needed: sudo apt-get install -y python3-tk)
PYTHONPATH=src python apps/ui_tk.py
```
**Tip:** If you enabled the service, stop it before running manually:
```bash
sudo systemctl stop rv-thermostat.service
```

## Configuration (`config/config.yaml`)
```yaml
pins:
  heat_pin: 17
  cool_pin: 27
  fan_pin: 22
  active_low: true

control:
  mode: auto            # off|heat|cool|auto
  setpoint_c: 22.0
  deadband_c: 0.5
  compressor_min_off_s: 300
  fan_lead_s: 5
  fan_lag_s: 15

sensor:
  kind: mock            # mock|ds18b20
  ds18b20_id: null
```
The app looks for `config/config.yaml` first, then `config.yaml` at the repo root.

## DS18B20 setup (optional)
1. `sudo raspi-config` → Interface Options → **1-Wire** → enable → reboot  
2. Find ID under `/sys/bus/w1/devices/28-*/w1_slave`  
3. Set `sensor.kind: ds18b20` and `sensor.ds18b20_id: "28-XXXXXXXXXXXX"`

## Run as a service (systemd)
```bash
sudo cp system/rv-thermostat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rv-thermostat.service
sudo systemctl start rv-thermostat.service
sudo systemctl status rv-thermostat.service
```
The unit uses:
- `WorkingDirectory=/home/pi/rv-thermostat`
- `Environment="PYTHONPATH=/home/pi/rv-thermostat/src"`
- `ExecStart=/home/pi/rv-thermostat/.venv/bin/python /home/pi/rv-thermostat/apps/app.py`

## VS Code (optional)
1) Select interpreter: **Python: Select Interpreter** → `.venv/bin/python`  
2) Add `.env` at repo root:
```
PYTHONPATH=src
```
3) Create `.vscode/launch.json`:
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "UI (Tkinter)",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/apps/ui_tk.py",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env",
      "justMyCode": true
    },
    {
      "name": "Headless app",
      "type": "python",
      "request": "launch",
      "program": "${workspaceFolder}/apps/app.py",
      "console": "integratedTerminal",
      "envFile": "${workspaceFolder}/.env",
      "justMyCode": true
    }
  ]
}
```

## Tests (optional)
```bash
pip install pytest
PYTHONPATH=src pytest -q
```
Example `tests/test_controller.py`:
```python
from thermostat.config import AppConfig
from thermostat.sensors import MockSensor
from thermostat.actuators import Outputs, ActuatorController
from thermostat.controller import ThermostatController

class DummyRelay:
    def on(self): pass
    def off(self): pass

def build():
    cfg = AppConfig()
    acts = ActuatorController(Outputs(DummyRelay(), DummyRelay(), DummyRelay()),
                              cfg.control.fan_lead_s, cfg.control.fan_lag_s)
    return ThermostatController(MockSensor(22.0), acts, cfg.control, logger=lambda *a, **k: None)

def test_last_temp_updates():
    ctrl = build()
    assert ctrl.s.last_temp_c is None
    ctrl.tick()
    assert isinstance(ctrl.s.last_temp_c, float)
```

## Troubleshooting
- `ModuleNotFoundError: thermostat` → run from repo root with `PYTHONPATH=src`, or set `.env`
- No Tk window → `sudo apt-get install -y python3-tk`
- GPIO perms → `sudo usermod -aG gpio $USER && newgrp gpio`
- DS18B20 missing → check ID/wiring and `/sys/bus/w1/devices/`

## Notes
- UI displays `controller.state.last_temp_c` (exact value used for decisions).
- Don’t run the UI and the service at the same time (both use GPIO).
