import subprocess
import random
import time
from ..config import IS_MOCK

_base_temp = 45.0
_last_temp_update = 0

_last_cpu_idle = 0.0
_last_cpu_total = 0.0
_cached_cpu_pct = 15.0
_last_cpu_update = 0.0

_start_time = time.time()
BATTERY_CAPACITY_AH = 20.0 # 20Ah Battery Bank
BATTERY_NOMINAL_V = 3.7   # 3.7V Li-ion nominal cell voltage (74.0 Wh total)
BATTERY_TOTAL_WH = BATTERY_CAPACITY_AH * BATTERY_NOMINAL_V # 74.0 Wh
BATTERY_EFFICIENCY = 0.90 # 90% DC-DC boost conversion efficiency
BATTERY_USABLE_WH = BATTERY_TOTAL_WH * BATTERY_EFFICIENCY # ~66.6 Wh

def get_temp():
    global _base_temp, _last_temp_update
    now = time.time()
    
    if IS_MOCK:
        if now - _last_temp_update > 2:
            _base_temp += random.uniform(-0.5, 0.8)
            _base_temp = max(40.0, min(_base_temp, 65.0))
            _last_temp_update = now
        return round(_base_temp, 1)
    
    try:
        if now - _last_temp_update > 2:
            res = subprocess.check_output(['vcgencmd', 'measure_temp']).decode('utf-8')
            _base_temp = float(res.replace('temp=', '').replace('\'C\n', ''))
            _last_temp_update = now
        return round(_base_temp + random.uniform(-0.1, 0.1), 1)
    except Exception:
        return 48.0

def get_cpu_usage():
    """
    Computes real CPU utilization percentage from Linux /proc/stat.
    """
    global _last_cpu_idle, _last_cpu_total, _cached_cpu_pct, _last_cpu_update
    now = time.time()
    if now - _last_cpu_update < 0.5:
        return _cached_cpu_pct

    _last_cpu_update = now
    if IS_MOCK:
        _cached_cpu_pct = round(max(5.0, min(95.0, _cached_cpu_pct + random.uniform(-4.0, 4.5))), 1)
        return _cached_cpu_pct

    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        fields = [float(x) for x in line.split()[1:]]
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0.0) # idle + iowait
        total = sum(fields)

        idle_delta = idle - _last_cpu_idle
        total_delta = total - _last_cpu_total
        _last_cpu_idle = idle
        _last_cpu_total = total

        if total_delta > 0:
            usage = (1.0 - (idle_delta / total_delta)) * 100.0
            _cached_cpu_pct = round(max(0.0, min(100.0, usage)), 1)
        return _cached_cpu_pct
    except Exception:
        return _cached_cpu_pct

def get_ram_usage():
    """
    Reads real memory metrics from /proc/meminfo.
    Returns (used_mb, total_mb, percent).
    """
    if IS_MOCK:
        return (1420, 3900, 36)
    try:
        mem_total = 0
        mem_available = 0
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1]) // 1024
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1]) // 1024
        if mem_total > 0:
            used = mem_total - mem_available
            pct = int((used / mem_total) * 100)
            return (used, mem_total, pct)
        return (1200, 3800, 31)
    except Exception:
        return (1200, 3800, 31)

def get_wifi_status():
    if IS_MOCK:
        return "LINK: 85%"
    try:
        with open("/proc/net/wireless", "r") as f:
            lines = f.readlines()
            if len(lines) > 2:
                parts = lines[2].split()
                if len(parts) >= 3:
                    link_quality = parts[2].replace('.', '')
                    return f"LINK: {link_quality}%"
        return "OFFLINE"
    except Exception:
        return "OFFLINE"

def get_wifi_ip():
    if IS_MOCK:
        return "192.168.4.99"
    try:
        res = subprocess.check_output(['ip', '-4', 'addr', 'show', 'wlan0'], timeout=2).decode('utf-8', errors='ignore')
        for line in res.split('\n'):
            if 'inet ' in line:
                return line.split()[1].split('/')[0]
        return None
    except Exception:
        return None

def get_uptime():
    elapsed = int(time.time() - _start_time)
    hours = elapsed // 3600
    minutes = (elapsed % 3600) // 60
    seconds = elapsed % 60
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"

def get_power_telemetry(active_fx=""):
    """
    Computes real-time system power draw and estimated 20Ah battery runtime:
      - Raspberry Pi: ~3.2W idle up to ~6.2W under load (proportional to CPU load)
      - NeoPixel Strip (120 LEDs on vest/Sandy): ~0.6W idle up to ~4.5W depending on active pattern
      - 8x8 LED Matrix (64 LEDs): ~1.1W
      - EL Wire (5 meters): +4.0W when Arduino Nano switch is ON (0W when OFF or in Stealth mode)
      - OLED Displays (Visor dual + Chest OLED): ~0.4W
      - 20Ah Battery: 74.0Wh nominal capacity, calculates remaining runtime and discharge %.
      - STEALTH MODE: Powers down EL wire, NeoPixels, and matrix to stretch battery life to 20+ hours!
    """
    from .. import config
    is_stealth = getattr(config, 'STEALTH_MODE', False)
    nano_sw_on = (getattr(config, 'NANO_SW', 1) != 0)
    cpu_pct = get_cpu_usage()
    
    if is_stealth:
        # STEALTH / POWER SAVING MODE: Digitally dimmed/unpowered components
        pi_watts = 3.0 + (cpu_pct / 100.0) * 1.8
        led_strip_watts = 0.05
        matrix_watts = 0.05
        oled_watts = 0.15
    else:
        # 1. Pi Draw (Dynamic 3.2W - 6.2W)
        pi_watts = 3.2 + (cpu_pct / 100.0) * 3.0

        # 2-3. LED Strip (120 LEDs) + 8x8 Matrix (64 LEDs)
        # Use real mA telemetry from the Nano's enforceBudget() when available;
        # fall back to pattern-based heuristic otherwise.
        nano_ma = getattr(config, 'NANO_MA', 0)
        if nano_ma > 0:
            # Nano reports combined strip + matrix draw after budget clamping.
            # Convert mA @ 5V to watts.
            led_strip_watts = round((nano_ma / 1000.0) * 5.0, 2)
            matrix_watts = 0.0  # already included in nano_ma
        else:
            fx_upper = (active_fx or "").upper()
            if "OVERCLOCK" in fx_upper or "STROBE" in fx_upper or "FRENZY" in fx_upper:
                led_strip_watts = 4.2
            elif "STEALTH" in fx_upper or "OFFLINE" in fx_upper or "BLACKOUT" in fx_upper:
                led_strip_watts = 0.8
            elif "SANDEVISTAN" in fx_upper or "SURGE" in fx_upper:
                led_strip_watts = 3.2
            else:
                led_strip_watts = 2.2
            matrix_watts = 1.1

        # 5. Visor (ESP32 + dual SSD1306 + NeoPixels) & Chest Micro-OLED
        esp_ma = getattr(config, 'ESP_MA', 0)
        if esp_ma > 0:
            # Real telemetry from ESP32 visor over UDP: mA @ 5.0V converted to Watts
            # +0.1W for chest Micro-OLED connected to Nano
            oled_watts = round(((esp_ma / 1000.0) * 5.0) + 0.1, 2)
        else:
            oled_watts = 0.4  # heuristic fallback

    # 4. EL Wire (5 Meters) - Hardwired physical toggle switch monitored by Nano
    if nano_sw_on:
        el_wire_watts = 4.0
        el_status_str = "NANO SW: ON"
    else:
        el_wire_watts = 0.0
        el_status_str = "NANO SW: OFF"

    # Total System Power (Watts) & Current @ 5.0V (Amps)
    total_watts = round(pi_watts + led_strip_watts + matrix_watts + el_wire_watts + oled_watts, 2)
    current_amps = round(total_watts / 5.0, 2)

    # 20Ah Battery Runtime Estimation
    est_total_mins = int((BATTERY_USABLE_WH / max(1.0, total_watts)) * 60)
    est_hours = est_total_mins // 60
    est_mins = est_total_mins % 60

    # Battery Discharge / Consumed % based on session elapsed time
    elapsed_hours = (time.time() - _start_time) / 3600.0
    consumed_wh = elapsed_hours * total_watts
    remaining_wh = max(0.0, BATTERY_USABLE_WH - consumed_wh)
    battery_pct = max(1, min(100, int((remaining_wh / BATTERY_USABLE_WH) * 100)))

    return {
        "cpu_pct": cpu_pct,
        "is_stealth": is_stealth,
        "nano_sw_on": nano_sw_on,
        "el_status_str": el_status_str,
        "pi_watts": round(pi_watts, 1),
        "led_strip_watts": round(led_strip_watts, 1),
        "matrix_watts": round(matrix_watts, 1),
        "el_wire_watts": round(el_wire_watts, 1),
        "oled_watts": round(oled_watts, 1),
        "total_watts": total_watts,
        "current_amps": current_amps,
        "battery_pct": battery_pct,
        "est_hours": est_hours,
        "est_mins": est_mins,
        "runtime_str": f"{est_hours:02d}h {est_mins:02d}m",
        "nano_ma": getattr(config, 'NANO_MA', 0),
        "esp_ma": getattr(config, 'ESP_MA', 0),
    }
