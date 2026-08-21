import serial
import serial.tools.list_ports
import threading
from ..config import IS_MOCK, NANO_BAUD

class NanoAccessories:
    def __init__(self):
        self.nodes = []
        self.lock = threading.Lock()
        if not IS_MOCK:
            self._find_nodes()

    def _find_nodes(self):
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if "Arduino" in p.description or "Nano" in p.description or "USB" in p.description:
                try:
                    s = serial.Serial(p.device, NANO_BAUD, timeout=1)
                    self.nodes.append(s)
                    print(f"Found Nano node on {p.device}")
                except serial.SerialException as e:
                    print(f"Failed to open {p.device}: {e}")
        if not self.nodes:
            print("No Nano nodes found.")

    def broadcast(self, state):
        msg = f"S {state}\n".encode('ascii')
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error broadcasting to node: {e}")
