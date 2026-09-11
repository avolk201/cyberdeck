import os
import subprocess
import sys
import time

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_double_import_regression_module_main():
    """Regression: launching via `python -m cyberdeck.main` used to load main
    as __main__, so `from ..main import fsm` in the UI bound to a second copy
    with fsm=None and boot never auto-advanced. Verify BOOT->IDLE now fires."""
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "cyberdeck.main"],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(10)
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    assert "BOOT -> IDLE" in out, f"Boot did not auto-advance. Output:\n{out}"


def test_power_manager_shutdown_darkens_suit(monkeypatch):
    from cyberdeck.hw import power

    calls = []
    monkeypatch.setattr(power.os, "system", lambda cmd: calls.append(cmd))
    monkeypatch.setattr(power.time, "sleep", lambda s: None)

    pm = power.PowerManager()
    pm.shutdown()

    assert calls == ["sudo shutdown -h now"]


def test_power_manager_mock_has_no_device():
    from cyberdeck.hw.power import PowerManager
    pm = PowerManager()
    assert pm.device is None  # mock mode: no GPIO hardware


def test_get_screen_for_state_none_surface(tmp_path):
    """get_screen_for_state(state, None) must not construct screens around a
    None surface; it should fall back to the live display surface."""
    import pygame
    from cyberdeck.ui import screens
    from cyberdeck import runtime

    pygame.font.init()
    surf = pygame.Surface((800, 480))
    runtime.screen = surf
    screens._screens = None  # force a cold build
    from cyberdeck.config import State
    s = screens.get_screen_for_state(State.IDLE, None)
    assert s is not None
    assert s.surface is surf
    screens._screens = None  # reset for other tests
