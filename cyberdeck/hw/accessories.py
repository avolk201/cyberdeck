import serial
import serial.tools.list_ports
import threading
from ..config import IS_MOCK, NANO_BAUD

class NanoAccessories:
    def __init__(self, callback=None):
        self.nodes = []
        self.lock = threading.Lock()
        self.callback = callback
        self.running = True
        if not IS_MOCK:
            t = threading.Thread(target=self._monitor_ports, daemon=True)
            t.start()

    def _monitor_ports(self):
        import time
        while self.running:
            ports = serial.tools.list_ports.comports()
            available_devices = [p.device for p in ports if "Arduino" in p.description or "Nano" in p.description or "USB" in p.description]
            
            with self.lock:
                dead_nodes = [n for n in self.nodes if n.port not in available_devices or not n.is_open]
                for node in dead_nodes:
                    self.nodes.remove(node)
                    try: node.close()
                    except: pass
                    print(f"Nano node disconnected: {node.port}")
                    
                connected_ports = [n.port for n in self.nodes]
                for dev in available_devices:
                    if dev not in connected_ports:
                        try:
                            s = serial.Serial(dev, NANO_BAUD, timeout=1)
                            self.nodes.append(s)
                            print(f"Found new Nano node on {dev}")
                            t = threading.Thread(target=self._listen, args=(s,), daemon=True)
                            t.start()
                        except serial.SerialException as e:
                            pass
            time.sleep(2.0)
            
    def _listen(self, node):
        while self.running:
            try:
                line = node.readline()
                if line:
                    data = line.decode('ascii', errors='ignore').strip()
                    if data:
                        if self.callback:
                            self.callback(data)
                        else:
                            print(f"Nano: {data}")
            except Exception as e:
                print(f"Nano listen error: {e}")
                try: node.close()
                except: pass
                break

    def broadcast(self, state):
        msg = f"S {state}\n".encode('ascii')
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error broadcasting to node: {e}")
