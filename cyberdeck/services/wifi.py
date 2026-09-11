import subprocess
import threading
import time
from ..config import IS_MOCK

VISOR_SSID = "VISOR_LINK"

_cached_networks = [
    {"ssid": "VISOR_LINK", "in_use": False, "signal": 100},
]
_cache_lock = threading.Lock()
_connection_status = "IDLE"
_status_lock = threading.Lock()
_scanner_running = False

def set_wifi_status_msg(msg):
    global _connection_status
    with _status_lock:
        _connection_status = msg

def get_wifi_status_msg():
    with _status_lock:
        return _connection_status

def _init_wifi_hardware():
    if not IS_MOCK:
        try:
            subprocess.run(['sudo', 'nmcli', 'radio', 'wifi', 'on'], capture_output=True, timeout=5)
            subprocess.run(['sudo', 'nmcli', 'dev', 'set', 'wlan0', 'managed', 'yes'], capture_output=True, timeout=5)
        except Exception:
            pass

def _get_saved_connections():
    """Returns a list of saved wifi profile names."""
    if IS_MOCK:
        return ["HOME_NETWORK_5G"]
    try:
        out = subprocess.check_output(
            ['sudo', 'nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
            timeout=5
        ).decode('utf-8', errors='ignore')
        saved = []
        for line in out.strip().split('\n'):
            if ':' in line:
                name, ctype = line.rsplit(':', 1)
                if ctype in ('802-11-wireless', 'wifi') and name != VISOR_SSID:
                    saved.append(name.strip())
        return saved
    except Exception:
        return []

def _scanner_worker():
    global _cached_networks, _scanner_running
    _init_wifi_hardware()
    
    while _scanner_running:
        if not IS_MOCK:
            try:
                # Query scanned networks without hard-blocking rescan
                out = subprocess.check_output(
                    ['sudo', 'nmcli', '-t', '-f', 'SSID,IN-USE,SIGNAL', 'dev', 'wifi', 'list', '--rescan', 'auto'],
                    timeout=8
                ).decode('utf-8', errors='ignore')

                networks = []
                seen = set()
                for line in out.strip().split('\n'):
                    if not line or line.startswith('--'):
                        continue
                    parts = line.replace('\\:', '@@COLON@@').split(':')
                    if len(parts) >= 3:
                        ssid = parts[0].replace('@@COLON@@', ':').strip()
                        if not ssid or ssid == '--' or ssid in seen:
                            continue
                        seen.add(ssid)
                        in_use = (parts[1] == '*')
                        try:
                            signal = int(parts[2])
                        except Exception:
                            signal = 0
                        networks.append({"ssid": ssid, "in_use": in_use, "signal": signal})

                # Include saved connections if they weren't in beacon range
                for saved_name in _get_saved_connections():
                    if saved_name not in seen:
                        seen.add(saved_name)
                        networks.append({"ssid": saved_name, "in_use": False, "signal": 50})

                # Always keep VISOR_LINK pinned in list
                if not any(n["ssid"] == VISOR_SSID for n in networks):
                    networks.insert(0, {"ssid": VISOR_SSID, "in_use": False, "signal": 95})

                if networks:
                    with _cache_lock:
                        _cached_networks = networks
            except Exception:
                # On error or transient busyness, keep existing valid cached list
                pass
        time.sleep(6.0)

def start_wifi_scanner():
    global _scanner_running
    if not _scanner_running:
        _scanner_running = True
        t = threading.Thread(target=_scanner_worker, daemon=True)
        t.start()

start_wifi_scanner()

def scan_wifi():
    """
    Instantly returns the cached list of networks without blocking the Pygame UI thread.
    """
    if IS_MOCK:
        return [
            {"ssid": "VISOR_LINK", "in_use": False, "signal": 100},
            {"ssid": "HOME_NETWORK_5G", "in_use": True, "signal": 85},
            {"ssid": "CYBER_HOTSPOT", "in_use": False, "signal": 60},
        ]

    with _cache_lock:
        return list(_cached_networks)

def _nm(args, check=True, timeout=12):
    return subprocess.run(['sudo', 'nmcli'] + args, check=check,
                          capture_output=True, timeout=timeout)

def _connect_visor_sync():
    """
    Non-crashing, bounded VISOR_LINK connection sequence with automatic network recovery.
    """
    ssid = VISOR_SSID
    set_wifi_status_msg("LINKING VISOR_LINK...")
    try:
        _nm(['radio', 'wifi', 'on'], check=False, timeout=3)
        _nm(['dev', 'disconnect', 'wlan0'], check=False, timeout=3)
        _nm(['connection', 'delete', ssid], check=False, timeout=3)

        # Add profile
        _nm(['connection', 'add', 'type', 'wifi', 'con-name', ssid, 'ifname', 'wlan0', 'ssid', ssid], timeout=6)
        _nm(['connection', 'modify', ssid,
             'wifi-sec.key-mgmt', 'wpa-psk',
             'wifi-sec.proto', 'rsn',
             'wifi-sec.group', 'ccmp',
             'wifi-sec.pairwise', 'ccmp',
             'wifi-sec.pmf', '1',
             'wifi-sec.psk', 'cyberdeck'], timeout=6)

        _nm(['connection', 'modify', ssid,
             '802-11-wireless.hidden', 'yes',
             '802-11-wireless.powersave', '2'], timeout=6)

        _nm(['connection', 'modify', ssid,
             'ipv4.method', 'manual',
             'ipv4.addresses', '192.168.4.99/24',
             'ipv4.gateway', '192.168.4.1'], timeout=6)

        # Bring connection up (10s timeout)
        res = _nm(['connection', 'up', ssid], timeout=10)
        if res.returncode == 0:
            set_wifi_status_msg("VISOR LINKED (192.168.4.99)")
            print("[WIFI] Successfully associated with VISOR_LINK")
        else:
            set_wifi_status_msg("VISOR NOT FOUND - RESTORING NETWORKS")
            print("[WIFI] VISOR_LINK connection failed. Restoring adapter...")
            # Restore regular connections so user is not stranded
            _nm(['dev', 'connect', 'wlan0'], check=False, timeout=5)
    except subprocess.TimeoutExpired:
        set_wifi_status_msg("VISOR TIMEOUT - RESTORING")
        print("[WIFI] VISOR_LINK connection timed out. Restoring adapter...")
        _nm(['dev', 'connect', 'wlan0'], check=False, timeout=5)
    except Exception as e:
        set_wifi_status_msg(f"VISOR LINK FAILED: {e}")
        print(f"[WIFI] Error connecting to VISOR_LINK: {e}")
        _nm(['dev', 'connect', 'wlan0'], check=False, timeout=5)

def connect_wifi(ssid):
    """
    Attempts to connect to the given SSID in a background thread safely.
    """
    if IS_MOCK:
        print(f"[MOCK] Connecting to {ssid}...")
        set_wifi_status_msg(f"LINKED: {ssid}")
        return

    def _connect():
        try:
            print(f"[WIFI] Connecting to {ssid}...")
            set_wifi_status_msg(f"CONNECTING TO {ssid}...")
            if ssid == VISOR_SSID:
                _connect_visor_sync()
            elif ssid == "DISCONNECT":
                _nm(['dev', 'disconnect', 'wlan0'], timeout=5)
                set_wifi_status_msg("WLAN DISCONNECTED")
                print("[WIFI] Disconnected from WiFi")
            else:
                res = _nm(['device', 'wifi', 'connect', ssid], timeout=15)
                if res.returncode == 0:
                    set_wifi_status_msg(f"LINKED: {ssid}")
                    print(f"[WIFI] Successfully connected to {ssid}")
                else:
                    set_wifi_status_msg(f"CONNECT FAILED: {ssid}")
                    print(f"[WIFI] Failed to connect to {ssid}")
        except Exception as e:
            set_wifi_status_msg(f"ERR: {e}")
            print(f"[WIFI] Error connecting to {ssid}: {e}")

    t = threading.Thread(target=_connect, daemon=True)
    t.start()
