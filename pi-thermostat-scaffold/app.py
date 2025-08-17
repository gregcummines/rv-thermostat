import yaml, time, signal, sys
from thermostat.config import AppConfig
from thermostat.sensors import MockSensor, DS18B20Sensor
from thermostat.gpioio import gpio_init, gpio_cleanup, RelayOut
from thermostat.actuators import Outputs, ActuatorController
from thermostat.controller import ThermostatController

RUN = True
def handle_sig(sig, frame):
    global RUN
    RUN = False

def load_config() -> AppConfig:
    with open("config.yaml", "r") as f:
        data = yaml.safe_load(f)
    return AppConfig.model_validate(data)

def build_sensor(cfg):
    if cfg.sensor.kind == "mock":
        return MockSensor()
    else:
        return DS18B20Sensor(cfg.sensor.ds18b20_id)

def main():
    cfg = load_config()
    gpio_init()

    heat = RelayOut(cfg.pins.heat_pin, cfg.pins.active_low, "heat")
    cool = RelayOut(cfg.pins.cool_pin, cfg.pins.active_low, "cool")
    fan  = RelayOut(cfg.pins.fan_pin,  cfg.pins.active_low, "fan")

    outputs = Outputs(heat=heat, cool=cool, fan=fan)
    actuators = ActuatorController(outputs, cfg.control.fan_lead_s, cfg.control.fan_lag_s)
    sensor = build_sensor(cfg)

    ctrl = ThermostatController(sensor, actuators, cfg.control, logger=print)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    print("[APP] Starting thermostat loop. Ctrl+C to exit.")
    try:
        while RUN:
            ctrl.tick()
            time.sleep(2.0)  # loop period
    finally:
        print("[APP] Shutting down, GPIO safe-off.")
        actuators.all_off()
        gpio_cleanup()

if __name__ == "__main__":
    sys.exit(main())
