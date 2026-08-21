import threading
import time

class OledDisplay(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        print("OLED control delegated to Arduino Nano. Dummy class initialized.")

    def run(self):
        while self.running:
            time.sleep(0.5) # Just idle to keep the thread alive
