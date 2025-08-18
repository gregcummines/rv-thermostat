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
