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
PIN_BTN_LEFT = 27   # Physical 13
PIN_BTN_RIGHT = 22  # Physical 15
PIN_BTN_ACTION = 5  # Physical 29

# I2C
OLED_ADDR = 0x3C

# Serial
NANO_BAUD = 115200
NANO_HR = 0
NANO_SW = 0
NANO_LAST_SEEN = 0

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
RES_HDMI = (800, 480)
RESOLUTION = RES_HDMI # Default to HDMI/DSI res
