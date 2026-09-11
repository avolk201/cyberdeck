"""
Persistent settings for the Cyberdeck OS.

A wearer picks a theme, a loadout and maybe stealth mode, then powers the suit
off and on again at a convention; those choices should come back. Settings are
stored *outside* the repo (``~/.cyberdeck/settings.json``) so a code deploy
(rsync) never clobbers them.

The module is defensive: a missing, corrupt or partial file simply falls back
to defaults rather than crashing the suit. Writes only happen when something
actually changed, to avoid needlessly wearing the SD card.
"""

import json
import os
import threading

from . import config

DEFAULT_PATH = os.environ.get(
    "CYBERDECK_SETTINGS",
    os.path.join(os.path.expanduser("~"), ".cyberdeck", "settings.json"),
)

# (config attribute, kind) pairs that are persisted. `kind` is used to coerce
# JSON values back to the right Python type.
_FIELDS = [
    ("STEALTH_MODE", "bool"),
    ("ACTIVE_FX", "str"),
    ("ACTIVE_VISOR_MODE", "str"),
    ("ACTIVE_VISOR_FX", "str"),
    ("ACTIVE_VISOR_TEXT", "tuple"),
    ("ACTIVE_SUIT_PRESET", "str"),
    ("ACTIVE_MATRIX_FX", "str"),
    ("ACTIVE_MC_OLED_FX", "str"),
]

_lock = threading.Lock()
_last_saved = None


def _theme_key():
    from .ui.theme import theme_manager
    try:
        return theme_manager.theme_keys[theme_manager.current_idx]
    except Exception:
        return None


def snapshot():
    """Capture the current user-facing settings as a JSON-serialisable dict."""
    data = {}
    for attr, kind in _FIELDS:
        value = getattr(config, attr, None)
        if kind == "tuple" and isinstance(value, (list, tuple)):
            value = list(value)
        data[attr] = value
    data["THEME"] = _theme_key()
    return data


def apply(data):
    """Apply a settings dict to config/theme. Ignores unknown/bad values."""
    if not isinstance(data, dict):
        return
    for attr, kind in _FIELDS:
        if attr not in data:
            continue
        value = data[attr]
        try:
            if kind == "bool":
                setattr(config, attr, bool(value))
            elif kind == "str":
                if isinstance(value, str):
                    setattr(config, attr, value)
            elif kind == "tuple":
                if isinstance(value, (list, tuple)) and len(value) == 2:
                    setattr(config, attr, (str(value[0]), str(value[1])))
        except Exception:
            pass

    theme = data.get("THEME")
    if isinstance(theme, str):
        try:
            from .ui.theme import theme_manager
            theme_manager.set_theme(theme)
        except Exception:
            pass


def load(path=DEFAULT_PATH):
    """Load settings from disk. Returns True if a settings file was applied."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    apply(data)
    return True


def save_if_changed(path=DEFAULT_PATH):
    """Write settings if they differ from the last saved snapshot.

    Returns True if a write occurred. Safe to call frequently (it is invoked
    from the main loop every couple of seconds).
    """
    global _last_saved
    data = snapshot()
    with _lock:
        if data == _last_saved:
            return False
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except OSError:
            return False
        _last_saved = data
        return True


def reset_cache():
    """Forget the last-saved snapshot (used by tests)."""
    global _last_saved
    with _lock:
        _last_saved = None
