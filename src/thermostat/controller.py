import time
from dataclasses import dataclass
from typing import Literal
from thermostat.config import Control
from thermostat.sensors import TemperatureSensor
from thermostat.actuators import ActuatorController
@dataclass
class State:
    last_cool_off_at: float | None = None
    last_cool_on_at: float | None = None
    current_mode: Literal['idle','heating','cooling','off'] = 'idle'
    last_temp_c: float | None = 22.0
    last_tick_at: float | None = None
    fan_mode: Literal['auto','cycled','manual','off'] = 'auto'
class ThermostatController:
    def __init__(self,sensor:TemperatureSensor,actuators:ActuatorController,control:Control,logger=print):
        self.sensor=sensor; self.act=actuators; self.cfg=control; self.s=State(); self.log=logger
    def _stop_hvac(self):
        if self.s.current_mode=='cooling': self.s.last_cool_off_at=time.time()
        self.act.hvac_off_with_fan_lag(); self.s.current_mode='idle'
    def tick(self):
        t_raw=self.sensor.read_c(); t=t_raw + float(getattr(self.cfg,'reading_offset_c',0.0))
        self.s.last_temp_c=t; self.s.last_tick_at=time.time()
        # basic hysteresis
        sp=self.cfg.setpoint_c; db=self.cfg.deadband_c
        if self.cfg.mode=='off':
            if self.s.current_mode!='off': self.act.all_off(); self.s.current_mode='off'
            return
        cool_call=(self.cfg.mode in ('cool','auto')) and (t>sp+db)
        heat_call=(self.cfg.mode in ('heat','auto')) and (t<sp-db)
        if cool_call and self.s.current_mode!='cooling':
            if self.s.current_mode=='heating': self._stop_hvac()
            self.act.cool_on(); self.s.current_mode='cooling'
        elif heat_call and self.s.current_mode!='heating':
            if self.s.current_mode=='cooling': self._stop_hvac()
            self.act.heat_on(); self.s.current_mode='heating'
        elif (not cool_call and not heat_call) and self.s.current_mode in ('heating','cooling'):
            self._stop_hvac()
        # fan manual override
        if self.s.fan_mode=='manual': self.act.o.fan.on()
        elif self.s.fan_mode=='off': self.act.o.fan.off()
