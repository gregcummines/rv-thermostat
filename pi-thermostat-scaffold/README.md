# Pi Thermostat Scaffold

## Quick start
```bash
cd ~/pi-thermostat
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Edit `config.yaml` to change mode/setpoint. Use `sensor.kind: mock` until you attach a DS18B20.

## Autostart (optional)
Copy `pi-thermostat.service` to `/etc/systemd/system/` and enable as described in the main chat.
