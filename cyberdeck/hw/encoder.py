from ..config import IS_MOCK, PIN_ENCODER_A, PIN_ENCODER_B

class Encoder:
    def __init__(self, callback):
        self.callback = callback
        if not IS_MOCK:
            try:
                from gpiozero import RotaryEncoder
                self.device = RotaryEncoder(PIN_ENCODER_A, PIN_ENCODER_B, max_steps=0)
                self.device.when_rotated_clockwise = lambda: self.callback(1)
                self.device.when_rotated_counter_clockwise = lambda: self.callback(-1)
            except ImportError:
                print("gpiozero not found, mock encoder")
