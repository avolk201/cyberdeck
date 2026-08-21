import threading
import time
from ..config import State

class PixelController(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.state = State.BOOT
        print("LED control delegated to Arduino Nano. Dummy class initialized.")

    def run(self):
        while self.running:
            time.sleep(0.5) # Just idle to keep the thread alive

    def set_state(self, new_state):
        self.state = new_state
