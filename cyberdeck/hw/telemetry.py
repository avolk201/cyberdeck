import subprocess
import random
import time
from ..config import IS_MOCK

_base_temp = 45.0
_last_temp_update = 0

def get_temp():
    global _base_temp, _last_temp_update
    now = time.time()
    
    if IS_MOCK:
        if now - _last_temp_update > 2:
            _base_temp += random.uniform(-1.0, 1.5)
            # clamp
            _base_temp = max(40.0, min(_base_temp, 65.0))
            _last_temp_update = now
        return round(_base_temp, 1)
    
    try:
        if now - _last_temp_update > 2:
            res = subprocess.check_output(['vcgencmd', 'measure_temp']).decode('utf-8')
            _base_temp = float(res.replace('temp=', '').replace('\'C\n', ''))
            _last_temp_update = now
        # Add tiny jitter even to real temp
        return round(_base_temp + random.uniform(-0.2, 0.2), 1)
    except Exception:
        return 0.0

def get_wifi_status():
    if IS_MOCK:
        return "WIFI: LINK 85%"
    try:
        with open("/proc/net/wireless", "r") as f:
            lines = f.readlines()
            if len(lines) > 2:
                parts = lines[2].split()
                if len(parts) >= 3:
                    link_quality = parts[2].replace('.', '')
                    return f"WIFI: LINK {link_quality}%"
        return "WIFI: OFFLINE"
    except Exception:
        return "WIFI: OFFLINE"

def get_wifi_ip():
    if IS_MOCK:
        return "192.168.1.42"
    try:
        import subprocess
        res = subprocess.check_output(['ip', '-4', 'addr', 'show', 'wlan0']).decode('utf-8')
        for line in res.split('\n'):
            if 'inet ' in line:
                return line.split()[1].split('/')[0]
        return None
    except Exception:
        return None
