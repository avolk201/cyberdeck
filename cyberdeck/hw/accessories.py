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
        self.last_synced_fx = None
        if not IS_MOCK:
            t = threading.Thread(target=self._monitor_ports, daemon=True)
            t.start()
            h = threading.Thread(target=self._hr_stream, daemon=True)
            h.start()
            s = threading.Thread(target=self._sync_loop, daemon=True)
            s.start()

    def _sync_loop(self):
        import time
        from .. import config
        while self.running:
            time.sleep(0.05)
            current_fx = getattr(config, "ACTIVE_FX", None)
            if current_fx != self.last_synced_fx:
                self.last_synced_fx = current_fx
                if current_fx:
                    if current_fx.startswith("MC_OLED_"):
                        mc_name = current_fx[8:]
                        self.broadcast(f"MC_{mc_name}")
                    elif current_fx.startswith("MC_"):
                        self.broadcast(current_fx)
                    elif current_fx.startswith("SUIT_") or current_fx.startswith("MATRIX_"):
                        self.broadcast(current_fx)

    def _handshake(self, node):
        import time
        from .. import config
        from ..ui.theme import theme_manager
        # Wait for Arduino bootloader to complete after DTR reset
        time.sleep(1.8)
        try:
            active_mc = getattr(config, "ACTIVE_MC_OLED_FX", "NETRUNNER_HUD").replace(" ", "_")
            if active_mc.startswith("MC_OLED_"):
                active_mc = active_mc[8:]
            elif active_mc.startswith("MC_"):
                active_mc = active_mc[3:]
            
            node.write(f"S MC_{active_mc}\n".encode('ascii'))
            if getattr(config, "STEALTH_MODE", False):
                node.write(b"B 0\n")
            else:
                node.write(b"B 255\n")
                
            cur_th = theme_manager.current
            node.write(f"C {cur_th.primary[0]} {cur_th.primary[1]} {cur_th.primary[2]}\n".encode('ascii'))
            print(f"[NANO] Handshake complete on {node.port}, synced MC_{active_mc}")
        except Exception as e:
            print(f"[NANO] Handshake error: {e}")

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
                            hs = threading.Thread(target=self._handshake, args=(s,), daemon=True)
                            hs.start()
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
        if state.startswith("MC_OLED_"):
            state = "MC_" + state[8:]
        msg = f"S {state}\n".encode('ascii')
        print(f"[NANO_DEBUG] Broadcasting: {state}")
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error broadcasting to node: {e}")

    def send_color(self, r, g, b):
        msg = f"C {r} {g} {b}\n".encode('ascii')
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error sending color to node: {e}")

    def send_brightness(self, brightness):
        msg = f"B {brightness}\n".encode('ascii')
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error sending brightness to node: {e}")

    def send_matrix(self, hex_data):
        msg = f"M {hex_data}\n".encode('ascii')
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error sending matrix to node: {e}")

    def send_hr(self, bpm):
        msg = f"W {bpm}\n".encode('ascii')
        with self.lock:
            for node in self.nodes:
                try:
                    node.write(msg)
                except Exception as e:
                    print(f"Error sending HR to node: {e}")

    def _hr_stream(self):
        import time
        from .hr import hr_monitor
        while self.running:
            time.sleep(0.1)
            with self.lock:
                has_nodes = bool(self.nodes)
            if not has_nodes:
                continue
            wave = hr_monitor.get_waveform(64)
            if wave is None:
                continue
            self.send_hr(hr_monitor.bpm)

def _default_nano_callback(data):
    from .. import config
    if data.startswith("SW "):
        try: config.NANO_SW = int(data.split()[1])
        except: pass
    elif data.startswith("HR "):
        try:
            val = int(data.split()[1])
            config.NANO_HR = val
            from .hr import hr_monitor
            hr_monitor.add_sample(val)
        except: pass
    elif data.startswith("MA "):
        try: config.NANO_MA = int(data.split()[1])
        except: pass
    import time
    config.NANO_LAST_SEEN = time.time()

nano_accessories = NanoAccessories(callback=_default_nano_callback)
