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
