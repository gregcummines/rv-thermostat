from pydantic import BaseModel, Field
from typing import Literal, Optional
class Pins(BaseModel): heat_pin:int=17; cool_pin:int=27; fan_pin:int=22; active_low:bool=True
class Control(BaseModel):
    mode:Literal['off','heat','cool','auto']='auto'; setpoint_c:float=22.0; deadband_c:float=0.5
    compressor_min_off_s:int=300; fan_lead_s:int=5; fan_lag_s:int=15; reading_offset_c:float=0.0
class Sensor(BaseModel): kind:Literal['mock','ds18b20']='mock'; ds18b20_id:Optional[str]=None
class LocationEnable(BaseModel): gpsd:bool=False; wifi:bool=False; ip:bool=True
class LocationWifi(BaseModel): iface:str='wlan0'; provider:Literal['mls']='mls'; mls_api_key:Optional[str]=None
class LocationIP(BaseModel): provider:Literal['ip-api','ipinfo']='ip-api'
class LocationManual(BaseModel): lat:Optional[float]=None; lon:Optional[float]=None
class Location(BaseModel):
    manual:LocationManual=Field(default_factory=LocationManual); enable:LocationEnable=Field(default_factory=LocationEnable)
    wifi:LocationWifi=Field(default_factory=LocationWifi); ip:LocationIP=Field(default_factory=LocationIP)
class Weather(BaseModel): provider:Literal['openweathermap']='openweathermap'; api_key:str=''; units:Literal['imperial','metric']='imperial'; refresh_minutes:int=10
class UISettings(BaseModel): time_24h: bool=False; safe_margin_px:int=24
class AppConfig(BaseModel):
    pins:Pins=Field(default_factory=Pins); control:Control=Field(default_factory=Control); sensor:Sensor=Field(default_factory=Sensor)
    location:Location=Field(default_factory=Location); weather:Weather=Field(default_factory=Weather); ui:UISettings=Field(default_factory=UISettings)
