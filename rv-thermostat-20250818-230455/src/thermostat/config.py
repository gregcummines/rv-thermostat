from pydantic import BaseModel, Field
from typing import Literal

class Pins(BaseModel):
    heat_pin: int = 17
    cool_pin: int = 27
    fan_pin:  int = 22
    active_low: bool = True

class Control(BaseModel):
    mode: Literal["off", "heat", "cool", "auto"] = "auto"
    setpoint_c: float = 22.0
    deadband_c: float = 0.5
    compressor_min_off_s: int = 300
    fan_lead_s: int = 5
    fan_lag_s: int = 15

class Sensor(BaseModel):
    kind: Literal["mock", "ds18b20"] = "mock"
    ds18b20_id: str | None = None

class AppConfig(BaseModel):
    pins: Pins = Field(default_factory=Pins)
    control: Control = Field(default_factory=Control)
    sensor: Sensor = Field(default_factory=Sensor)
