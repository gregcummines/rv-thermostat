import os, yaml
from thermostat.config import AppConfig
from thermostat.sensors import MockSensor, DS18B20Sensor
from thermostat.gpioio import gpio_init, gpio_cleanup, RelayOut
from thermostat.actuators import Outputs, ActuatorController
from thermostat.controller import ThermostatController

def load_config(path: str | None = None) -> AppConfig:
    candidates = [path] if path else []
    candidates += ['config/config.yaml','config.yaml']
    for p in candidates:
        if p and os.path.exists(p):
            with open(p,'r') as f:
                return AppConfig.model_validate(yaml.safe_load(f))
    return AppConfig()

def build_runtime(cfg: AppConfig):
    gpio_init(); heat=RelayOut(cfg.pins.heat_pin,cfg.pins.active_low,'heat'); cool=RelayOut(cfg.pins.cool_pin,cfg.pins.active_low,'cool'); fan=RelayOut(cfg.pins.fan_pin,cfg.pins.active_low,'fan')
    outputs=Outputs(heat=heat,cool=cool,fan=fan)
    actuators=ActuatorController(outputs,cfg.control.fan_lead_s,cfg.control.fan_lag_s)
    sensor=MockSensor() if cfg.sensor.kind=='mock' else DS18B20Sensor(cfg.sensor.ds18b20_id)
    ctrl=ThermostatController(sensor,actuators,cfg.control,logger=print)
    return ctrl, actuators, gpio_cleanup
