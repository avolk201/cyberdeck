import sys

# Detect if we are on a mock system (e.g. Mac)
IS_MOCK = sys.platform == "darwin" or sys.platform == "win32"

# Pins (BCM) — 3-button nav cluster. LEDs, matrix and OLEDs all live on the
# Arduino Nano node, so the Pi only needs the buttons.
PIN_BTN_LEFT = 27   # Physical 13
PIN_BTN_RIGHT = 22  # Physical 15
PIN_BTN_ACTION = 5  # Physical 29

# Device Specific Persistent States (prevents cross-device clobbering)
ACTIVE_VISOR_MODE = "GRAPHIC"          # "GRAPHIC", "TEXT", or "AUTO"
ACTIVE_VISOR_FX = "RADAR"             # Graphic preset name
ACTIVE_VISOR_TEXT = ("CYBER", "DECK")  # 2-word phrase for left and right eye
ACTIVE_SUIT_PRESET = "SANDEVISTAN_APEX" # Global deck preset coordinating all devices
ACTIVE_MATRIX_FX = "CYBER_SKULL"       # 8x8 LED Matrix preset
ACTIVE_MC_OLED_FX = "NETRUNNER_HUD"    # Chest Micro-OLED preset
ACTIVE_FX = "VISOR_OLED_RADAR"         # Backward compatibility alias
STEALTH_MODE = False                  # Power-saving stealth mode (disables LEDs/EL-wire, dims power)

# Serial link to the Arduino Nano accessory node
NANO_BAUD = 115200
NANO_HR = 0
NANO_SW = 0
NANO_LAST_SEEN = 0
NANO_MA = 0  # Real-time estimated mA draw reported by the Nano's enforceBudget()
ESP_MA = 0   # Real-time estimated mA draw reported by the ESP32 visor over UDP
ESP_LAST_SEEN = 0

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
# Power-saving mode halves the render rate and drops the visor stream + heavy
# overlays to cut CPU/GPU draw. The deck UI stays interactive throughout.
STEALTH_FPS = 15
RESOLUTION = (800, 480)  # 3.5" HDMI panel native res
