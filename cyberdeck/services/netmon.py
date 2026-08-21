import threading
import time

class NetMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.nodes_detected = 0

    def run(self):
        while self.running:
            # Fake iw scan
            self.nodes_detected += 1
            time.sleep(5)
