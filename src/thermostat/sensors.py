import random, time
from pathlib import Path
class TemperatureSensor: 
    def read_c(self)->float: raise NotImplementedError
class MockSensor(TemperatureSensor):
    def __init__(self,start_c:float=22.0): self.t=start_c
    def read_c(self)->float:
        self.t+=random.uniform(-0.05,0.05); return round(self.t,2)
class DS18B20Sensor(TemperatureSensor):
    def __init__(self,sensor_id:str):
        self.path=Path(f'/sys/bus/w1/devices/{sensor_id}/w1_slave')
        if not self.path.exists(): raise FileNotFoundError(self.path)
    def read_c(self)->float:
        text=self.path.read_text()
        if 'YES' not in text.splitlines()[0]: time.sleep(0.2); text=self.path.read_text()
        temp_line=[l for l in text.splitlines() if 't=' in l][-1]
        return round(int(temp_line.split('t=')[-1])/1000.0,2)
