from ..config import IS_MOCK, PIN_BTN_LEFT, PIN_BTN_RIGHT, PIN_BTN_ACTION

class NavButtons:
    def __init__(self, on_left, on_right, on_action_short, on_action_long, on_action_double):
        self.on_left = on_left
        self.on_right = on_right
        self.on_action_short = on_action_short
        self.on_action_long = on_action_long
        self.on_action_double = on_action_double
        
        if not IS_MOCK:
            try:
                from gpiozero import Button
                self.btn_left = Button(PIN_BTN_LEFT, bounce_time=0.05)
                self.btn_right = Button(PIN_BTN_RIGHT, bounce_time=0.05)
                self.btn_action = Button(PIN_BTN_ACTION, hold_time=1.5, bounce_time=0.05)
                
                self.btn_left.when_pressed = self.on_left
                self.btn_right.when_pressed = self.on_right
                self.btn_action.when_held = self.on_action_long
                self.btn_action.when_released = self.on_action_short 
                
                # Note: gpiozero Button doesn't natively support double-click out of the box in a simple callback,
                # For simplicity, we stick to short/long, or implement double click if really needed.
                # Since the original implementation passed on_double, we'll keep the param but it won't be fired automatically by gpiozero unless we add timing logic.
                
            except ImportError:
                print("gpiozero not found, mock buttons")
