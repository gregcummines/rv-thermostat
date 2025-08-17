# Pi Thermostat

A simple Raspberry Pi–based thermostat project that controls heating, cooling, and fan relays using GPIO.  
It reads from a temperature sensor (DS18B20 or a mock sensor for testing) and runs a control loop with interlocks (no heat + cool overlap, compressor min-off-time, fan lead/lag).  

This repo is designed to be extended with a Kivy touchscreen UI, scheduling, and optional remote control via REST.

---

## 🚀 Features
- **Relay control** for heat, cool, and fan (active-low friendly).
- **Configurable** via `config.yaml`:
  - mode (`off`, `heat`, `cool`, `auto`)
  - setpoint & deadband
  - compressor safety delay
  - fan lead/lag times
- **Mock sensor mode** for development without hardware.
- **Safe shutdown** — ensures relays are off when exiting.
- **Systemd service** for autostart on boot.

---

## 📂 Project Structure

    pi-thermostat/
    ├── app.py                # Main entry point
    ├── config.yaml           # Runtime configuration
    ├── requirements.txt      # Python dependencies
    ├── thermostat/           # Core package
    │   ├── config.py         # Config models (Pydantic)
    │   ├── gpioio.py         # GPIO relay wrapper
    │   ├── sensors.py        # Mock + DS18B20 sensor drivers
    │   ├── actuators.py      # Relay sequencing logic
    │   └── controller.py     # Main thermostat controller
    └── pi-thermostat.service # Example systemd service file

---

## ⚙️ Quick Start

    # Clone the repo
    git clone git@github.com:gregcummines/thermostat.git
    cd thermostat

    # Set up a virtual environment
    python3 -m venv .venv
    source .venv/bin/activate

    # Install dependencies
    pip install --upgrade pip
    pip install -r requirements.txt

    # Run the app
    python app.py

---

## 🧪 Configuration
Edit `config.yaml` to adjust pins, setpoint, mode, and sensor type.  
Example:

    control:
      mode: auto
      setpoint_c: 22.0
      deadband_c: 0.5

---

## 🔌 Hardware
- Raspberry Pi (tested on Pi 4/5)
- Relay module (3 channels: heat, cool, fan)
- DS18B20 temperature sensor (optional, enable 1-Wire in raspi-config)

---

## 📦 Autostart (systemd)
Copy the included service file and enable it:

    sudo cp pi-thermostat.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable pi-thermostat.service
    sudo systemctl start pi-thermostat.service

---

## 🛠️ Roadmap
- [ ] Add Kivy touchscreen UI  
- [ ] Add schedule/program support  
- [ ] Optional FastAPI REST API for remote control  
- [ ] Data logging & visualization  
- [ ] Additional sensor support (e.g., DHT22, BME280)  

---

## 📜 License
MIT License — see `LICENSE` for details.

