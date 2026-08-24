import os
from ..config import IS_MOCK

class PowerManager:
    def __init__(self):
        if not IS_MOCK:
            try:
                from gpiozero import Button
                self.device = Button(3, pull_up=True)
                # We trigger safe shutdown when it starts floating (is released)
                self.device.when_released = self.shutdown
            except ImportError:
                print("gpiozero not found, mock power manager")

    def shutdown(self):
        print("Power switch opened (floating). Initiating safe shutdown...")
        import os
        os.system("sudo shutdown -h now")
