# RV Thermostat

A Raspberry Pi thermostat with a headless core and optional desktop UI.

## Layout
```
rv-thermostat/
├─ requirements.txt
├─ config/
│  └─ config.yaml
├─ src/
│  └─ thermostat/
│     ├─ config.py
│     ├─ sensors.py
│     ├─ gpioio.py
│     ├─ actuators.py
│     ├─ controller.py
│     └─ runtime.py
├─ apps/
│  ├─ app.py      # headless loop
│  └─ ui_tk.py    # simulated desktop UI (Tkinter)
└─ system/
   └─ rv-thermostat.service
```

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip -r requirements.txt
PYTHONPATH=src python apps/app.py         # headless
# or
sudo apt-get install -y python3-tk        # if needed
PYTHONPATH=src python apps/ui_tk.py       # desktop UI
```

## Service
```bash
sudo cp system/rv-thermostat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rv-thermostat.service
sudo systemctl start rv-thermostat.service
```
