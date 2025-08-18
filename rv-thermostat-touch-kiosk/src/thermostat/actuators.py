import time
from dataclasses import dataclass
from thermostat.gpioio import RelayOut

@dataclass
class Outputs: heat: RelayOut; cool: RelayOut; fan: RelayOut

class ActuatorController:
    def __init__(self, outputs: Outputs, fan_lead_s: int, fan_lag_s: int):
        self.o = outputs; self.fan_lead_s = fan_lead_s; self.fan_lag_s = fan_lag_s
    def all_off(self): self.o.heat.off(); self.o.cool.off(); self.o.fan.off()
    def heat_on(self): self.o.cool.off(); self.o.fan.on(); time.sleep(self.fan_lead_s); self.o.heat.on()
    def cool_on(self): self.o.heat.off(); self.o.fan.on(); time.sleep(self.fan_lead_s); self.o.cool.on()
    def hvac_off_with_fan_lag(self): self.o.heat.off(); self.o.cool.off(); time.sleep(self.fan_lag_s); self.o.fan.off()
