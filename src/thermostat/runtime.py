import os, yaml, datetime as dt
from src.thermostat.config import AppConfig
from src.thermostat.sensors import MockSensor, DS18B20Sensor
from src.thermostat.gpioio import gpio_cleanup, gpio_init, RelayOut
from src.thermostat.actuators import Outputs, ActuatorController
from src.thermostat.controller import ThermostatController
from src.thermostat.schedule import load_schedule, evaluate
SCHEDULE_PATH='config/schedule.yaml'
def load_config(path: str | None = None) -> AppConfig:
    for p in ([path] if path else []) + ['config/config.yaml','config.yaml']:
        if p and os.path.exists(p):
            return AppConfig.model_validate(yaml.safe_load(open(p,'r')))
    return AppConfig()
def build_runtime(cfg: AppConfig):
    gpio_init()
    heat=RelayOut(cfg.pins.heat_pin,cfg.pins.active_low,'heat'); cool=RelayOut(cfg.pins.cool_pin,cfg.pins.active_low,'cool'); fan=RelayOut(cfg.pins.fan_pin,cfg.pins.active_low,'fan')
    outputs=Outputs(heat=heat,cool=cool,fan=fan)
    actuators=ActuatorController(outputs,cfg.control.fan_lead_s,cfg.control.fan_lag_s)
    sensor=MockSensor() if cfg.sensor.kind=='mock' else DS18B20Sensor(cfg.sensor.ds18b20_id)
    ctrl=ThermostatController(sensor, actuators, cfg.control, logger=print)
    ctrl._schedule=load_schedule(SCHEDULE_PATH); ctrl._last_applied=None
    return ctrl, actuators, gpio_cleanup
def apply_schedule_if_due(ctrl: ThermostatController, now: dt.datetime):
    sch=getattr(ctrl,'_schedule',None)
    if not sch: return
    key=now.strftime('%w-%H:%M')
    if getattr(ctrl,'_last_applied',None)==key: return
    res=evaluate(sch, now)
    if res:
        m,sp=res; ctrl.cfg.mode=m; ctrl.cfg.setpoint_c=float(sp); ctrl._last_applied=key
