import threading
import time
import math
import random
from ..config import IS_MOCK, MATRIX_LEDS, STRIP_LEDS, TOTAL_LEDS, BUDGET_MA, EST_MA_PER_PX, State, PIN_PIXELS

class PixelController(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.state = State.BOOT
        self.pixels = [(0, 0, 0)] * TOTAL_LEDS
        
        if not IS_MOCK:
            try:
                from rpi_ws281x import Adafruit_NeoPixel, Color
                self.strip = Adafruit_NeoPixel(TOTAL_LEDS, PIN_PIXELS, 800000, 10, False, 255, 0)
                self.strip.begin()
            except ImportError:
                print("Warning: rpi_ws281x not found, falling back to mock")
                self.strip = None
        else:
            self.strip = None

    def enforce_budget(self):
        total_ma = 0
        for r, g, b in self.pixels:
            brightness_pct = (r + g + b) / 765.0
            total_ma += brightness_pct * EST_MA_PER_PX
        
        if total_ma > BUDGET_MA:
            scale = BUDGET_MA / total_ma
            for i in range(TOTAL_LEDS):
                r, g, b = self.pixels[i]
                self.pixels[i] = (int(r * scale), int(g * scale), int(b * scale))

    def show(self):
        self.enforce_budget()
        if self.strip and not IS_MOCK:
            from rpi_ws281x import Color
            for i, (r, g, b) in enumerate(self.pixels):
                self.strip.setPixelColor(i, Color(r, g, b))
            self.strip.show()

    def run(self):
        while self.running:
            if self.state == State.BOOT:
                self.fill((0, 50, 0))
            elif self.state == State.IDLE:
                from .. import config
                fx = getattr(config, 'ACTIVE_FX', 'PULSE')
                
                if fx == "PULSE":
                    val = int((math.sin(time.time() * 3) + 1) * 20)
                    self.fill((0, val, 0))
                elif fx == "CHASE":
                    self.fill((0, 0, 0))
                    idx = int(time.time() * 10) % TOTAL_LEDS
                    self.pixels[idx] = (0, 255, 0)
                elif fx == "STROBE":
                    if int(time.time() * 10) % 2 == 0:
                        self.fill((255, 255, 255))
                    else:
                        self.fill((0, 0, 0))
                elif fx.startswith("MATRIX_"):
                    self.fill((0, 5, 0))
                    pattern = fx.split("_")[1]
                    if pattern == "SKULL":
                        for _ in range(10):
                            self.pixels[random.randint(0, min(63, TOTAL_LEDS-1))] = (255, 0, 0)
                    elif pattern == "SMILE":
                        for _ in range(10):
                            self.pixels[random.randint(0, min(63, TOTAL_LEDS-1))] = (0, 255, 0)
                    elif pattern == "RADAR":
                        sweep = int(time.time() * 20) % min(64, TOTAL_LEDS)
                        self.pixels[sweep] = (0, 255, 0)
                else:
                    self.fill((0, 10, 0))
            elif self.state == State.ALERT:
                if int(time.time() * 10) % 2 == 0:
                    self.fill((255, 0, 0))
                else:
                    self.fill((0, 0, 0))
            elif self.state == State.BLACKOUT:
                self.fill((0, 0, 0))
            elif self.state == State.RUNNING:
                if int(time.time() * 20) % 2 == 0:
                    colors = [(0, 255, 255), (150, 0, 255), (0, 255, 0)]
                    self.fill(random.choice(colors))
                else:
                    self.fill((0, 0, 0))
            else:
                self.fill((0, 20, 20))
                
            self.show()
            time.sleep(0.033)

    def fill(self, color):
        self.pixels = [color] * TOTAL_LEDS

    def set_state(self, new_state):
        self.state = new_state
