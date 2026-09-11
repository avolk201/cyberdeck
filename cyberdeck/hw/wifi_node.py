import fcntl
import socket
import struct
import threading
import time
from .. import config

VISOR_SUBNET = "192.168.4."
VISOR_HOST = "192.168.4.1"
SIOCGIFADDR = 0x8915

def pack_surface(surface):
    """
    Converts a 128x64 pygame Surface into 1024 bytes of XBM data
    (each 128px row packed into 16 bytes, LSB = leftmost pixel).
    """
    import pygame
    w, h = surface.get_size()
    if w != 128 or h != 64:
        surface = pygame.transform.scale(surface, (128, 64))
    import numpy as np
    # pixels3d is (x, y, rgb); threshold to mono rows, then pack LSB-first
    # (XBM order, matches U8g2 drawXBM / drawTile).
    pixels = pygame.surfarray.pixels3d(surface)
    mono = (pixels.max(axis=2) > 127).transpose()
    return np.packbits(mono, axis=1, bitorder='little').tobytes()

class WifiNode:
    def __init__(self, port=1337):
        self.port = port
        self.running = False
        self.thread = None

        # UDP socket for visor traffic; SO_BROADCAST keeps the fallback path
        # working when we are not on the visor subnet.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.settimeout(0.05)
        try:
            self.sock.bind(('', port))
        except Exception:
            pass

        self.last_fx = None
        self._last_state = None
        self._target = ('<broadcast>', port)
        self._last_sent = {"L": None, "R": None}
        self._last_sent_at = {"L": 0.0, "R": 0.0}

    def _handle_incoming(self, data, addr=None):
        """Parses telemetry reports from the ESP32 visor (e.g. PWR <mA>)."""
        try:
            msg = data.decode('ascii', errors='ignore').strip()
            if msg.startswith("PWR ") or msg.startswith("MA ") or msg.startswith("ESP_MA "):
                val = int(msg.split()[1])
                config.ESP_MA = val
                config.ESP_LAST_SEEN = time.time()
        except Exception:
            pass

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print(f"WiFi Node broadcaster started on UDP port {self.port}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.sock.close()

    @staticmethod
    def _wlan_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                info = fcntl.ioctl(s.fileno(), SIOCGIFADDR, struct.pack('256s', b'wlan0'))
                return socket.inet_ntoa(info[20:24])
            finally:
                s.close()
        except Exception:
            return None

    def _refresh_target(self):
        # Broadcast UDP gets no WiFi-layer ACKs and is sent at the lowest
        # PHY rate, so frames drop constantly. When we are on the visor
        # subnet, unicast straight to the ESP32 instead: retransmissions,
        # rate adaptation and no wasted airtime.
        ip = self._wlan_ip()
        if ip and ip.startswith(VISOR_SUBNET):
            self._target = (VISOR_HOST, self.port)
        else:
            self._target = ('<broadcast>', self.port)

    def _send(self, msg):
        try:
            self.sock.sendto(msg.encode('ascii'), self._target)
        except Exception:
            pass

    def send_state(self, state):
        """Sends the active OS state to the ESP32 visor (deduped)."""
        if state == self._last_state:
            return
        self._last_state = state
        self._send(f"S {state}\n")

    def _run(self):
        last_heartbeat = 0.0
        last_target_check = 0.0
        last_watchdog = 0.0

        while self.running:
            now = time.time()

            if now - last_target_check > 5.0:
                last_target_check = now
                self._refresh_target()

            # Send state immediately if it changes
            current_fx = getattr(config, "ACTIVE_FX", None)
            if current_fx != self.last_fx:
                self.last_fx = current_fx
                if current_fx:
                    self._send(f"S {current_fx}\n")

            # Send heartbeat every 1 second
            if now - last_heartbeat > 1.0:
                last_heartbeat = now
                self._send("H 1\n")

            # Check for incoming UDP telemetry packets (e.g. PWR <mA>)
            try:
                data, addr = self.sock.recvfrom(512)
                if data:
                    self._handle_incoming(data, addr)
            except (socket.timeout, BlockingIOError, OSError):
                pass
            except Exception:
                pass

            time.sleep(0.1)

    def stream_image(self, surface, eye="L"):
        """
        Converts a 128x64 pygame Surface into a 1024-byte XBM array
        and streams it over UDP to the ESP32.
        """
        if not self.running: return

        try:
            out_bytes = pack_surface(surface)
        except Exception:
            return

        # Skip unchanged frames to save airtime, but force a full resend
        # every 2 s so a rebooted/blanked ESP32 recovers its picture.
        now = time.time()
        if self._last_sent.get(eye) == out_bytes and now - self._last_sent_at.get(eye, 0) < 2.0:
            return

        # Header: V, space, L/R, space
        header = f"V {eye} ".encode('ascii')

        try:
            self.sock.sendto(header + out_bytes, self._target)
            self._last_sent[eye] = out_bytes
            self._last_sent_at[eye] = now
        except:
            pass

    def send_text(self, left_word, right_word=None):
        """
        Sends a large bold text command to the ESP32 visor (one word per eye).
        Example: wifi_node.send_text("TARGET", "LOCKED")
        """
        if right_word is None:
            parts = left_word.strip().split(maxsplit=1)
            if len(parts) == 2:
                left_word, right_word = parts[0], parts[1]
            else:
                right_word = left_word
        msg = f"TXT {left_word.upper()} {right_word.upper()}\n"
        self._send(msg)

# Singleton instance
wifi_node = WifiNode()

