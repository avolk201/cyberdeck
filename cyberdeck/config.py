import sys

# Detect if we are on a mock system (e.g. Mac)
IS_MOCK = sys.platform == "darwin" or sys.platform == "win32"

# Power Limits
BUDGET_MA = 2800  # Tier 1 fallback as per doc (Bank B plain 5V/3A)
EST_MA_PER_PX = 60

# Pixels
MATRIX_LEDS = 64
STRIP_LEDS = 120 # 2m at 60/m
TOTAL_LEDS = MATRIX_LEDS + STRIP_LEDS

# Pins (BCM)
PIN_PIXELS = 18
PIN_ENCODER_A = 17
PIN_ENCODER_B = 27
PIN_BUTTON = 22

# I2C
OLED_ADDR = 0x3C

# Serial
NANO_BAUD = 115200

# States
class State:
    BOOT = "BOOT"
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    RUNNING = "RUNNING"
    ALERT = "ALERT"
    COOLDOWN = "COOLDOWN"
    BLACKOUT = "BLACKOUT"
    TARGET_LOCK = "TARGET_LOCK"

# UI Settings
FPS = 30
RES_SPI = (480, 320)
RES_HDMI = (854, 480)
RESOLUTION = RES_HDMI # Default to HDMI/DSI res
