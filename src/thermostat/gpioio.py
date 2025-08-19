try:
    import RPi.GPIO as GPIO
except Exception:
    class _Dummy:
        BCM=OUT=HIGH=LOW=None
        def setmode(*a,**k): pass
        def setwarnings(*a,**k): pass
        def setup(*a,**k): pass
        def output(*a,**k): pass
        def cleanup(*a,**k): pass
    GPIO=_Dummy()

class RelayOut:
    def __init__(self, pin: int, active_low: bool = True, name: str = "relay"):
        self.pin = pin; self.active_low = active_low; self.name = name
        GPIO.setup(self.pin, GPIO.OUT, initial=self._level(False))
        self.state = False
    def _level(self, on: bool):
        if on:  return GPIO.LOW if self.active_low else GPIO.HIGH
        else:   return GPIO.HIGH if self.active_low else GPIO.LOW
    def set(self, on: bool):
        if on != self.state:
            GPIO.output(self.pin, self._level(on)); self.state = on
    def on(self): self.set(True)
    def off(self): self.set(False)

def gpio_init(): GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
def gpio_cleanup():
    try: GPIO.cleanup()
    except Exception: pass
