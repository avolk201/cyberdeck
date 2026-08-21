import threading
import time
from ..config import IS_MOCK, OLED_ADDR

class OledDisplay(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        
        if not IS_MOCK:
            try:
                from luma.core.interface.serial import i2c
                from luma.oled.device import ssd1306
                self.serial = i2c(port=1, address=OLED_ADDR)
                self.device = ssd1306(self.serial)
            except ImportError:
                print("luma.oled not found, mock oled")
                self.device = None
        else:
            self.device = None

    def run(self):
        while self.running:
            if self.device:
                # render telemetry
                pass
            time.sleep(0.5) # 2 Hz refresh
