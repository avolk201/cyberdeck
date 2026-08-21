from ..config import IS_MOCK, PIN_BUTTON

class MasterButton:
    def __init__(self, on_short, on_long, on_double):
        self.on_short = on_short
        self.on_long = on_long
        self.on_double = on_double
        
        if not IS_MOCK:
            try:
                from gpiozero import Button
                self.device = Button(PIN_BUTTON, hold_time=1.5)
                self.device.when_held = self.on_long
                self.device.when_released = self.on_short 
            except ImportError:
                print("gpiozero not found, mock button")
