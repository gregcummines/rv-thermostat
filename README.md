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
