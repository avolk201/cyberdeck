import os
import time
from ..config import IS_MOCK

# GPIO the latching master power switch is wired to. While the switch is closed
# it pulls the line low ("pressed"); when the wearer flips the master switch
# off the line floats and the pull-up releases it, which is our cue to shut
# down. GPIO3 (SCL) is free because the OLEDs live on the Nano/visor now.
POWER_GPIO = 3


class PowerManager:
    """
    Watches the master power switch and performs a graceful shutdown.

    On release (switch opened) it first darkens every light on the suit so the
    wearer is not left glowing while the Pi powers down, then halts the system.
    """
    def __init__(self, gpio=POWER_GPIO):
        self.device = None
        if IS_MOCK:
            return
        try:
            from gpiozero import Button
            # bounce_time guards against a brief spurious release at power-on.
            self.device = Button(gpio, pull_up=True, bounce_time=0.15)
            self.device.when_released = self.shutdown
        except Exception as e:
            print(f"[POWER] Power switch monitor unavailable: {e}")

    def shutdown(self):
        print("[POWER] Master switch opened. Initiating graceful shutdown...")
        # Darken the suit immediately. Without this the Nanos keep their last
        # pattern lit for ~30 s (their autonomous-fallback timeout) while the
        # Pi goes down, which looks broken at a convention.
        try:
            from ..hw.accessories import nano_accessories
            nano_accessories.send_brightness(0)
            nano_accessories.broadcast("BLACKOUT")
        except Exception:
            pass
        try:
            from ..hw.wifi_node import wifi_node
            wifi_node.send_text("SYS", "OFFLINE")
        except Exception:
            pass
        time.sleep(0.5)  # let the blackout commands flush over serial/UDP
        os.system("sudo shutdown -h now")
