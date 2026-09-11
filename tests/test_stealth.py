import pygame
import pytest

import cyberdeck.config as config
from cyberdeck.ui.widgets import TelemetryGauges


@pytest.fixture()
def gauges():
    pygame.font.init()
    rect = pygame.Rect(0, 0, 800, 480)
    font = pygame.font.SysFont("courier", 22)
    return TelemetryGauges(rect, font)


@pytest.fixture(autouse=True)
def _restore_stealth():
    prev = config.STEALTH_MODE
    yield
    config.STEALTH_MODE = prev


def test_stealth_fps_lower_than_normal():
    assert config.STEALTH_FPS < config.FPS


def test_stealth_toggle_engages(gauges, monkeypatch):
    nano_calls = []
    visor_calls = []

    class FakeNano:
        def send_brightness(self, b): nano_calls.append(("B", b))
        def send_color(self, r, g, b): nano_calls.append(("C", (r, g, b)))

    class FakeVisor:
        def stream_image(self, surface, eye="L"): visor_calls.append(eye)
        def send_text(self, l, r=None): visor_calls.append(("TXT", l, r))

    import cyberdeck.hw.accessories as acc_mod
    import cyberdeck.hw.wifi_node as wifi_mod
    monkeypatch.setattr(acc_mod, "nano_accessories", FakeNano())
    monkeypatch.setattr(wifi_mod, "wifi_node", FakeVisor())

    config.STEALTH_MODE = False
    gauges.show_wifi_menu = False
    gauges.handle_tap(gauges.stealth_btn.center)

    assert config.STEALTH_MODE is True
    # LEDs darkened: brightness 0 and color black.
    assert ("B", 0) in nano_calls
    assert ("C", (0, 0, 0)) in nano_calls
    # Visor blanked on both eyes (black frame = OLED off).
    assert "L" in visor_calls and "R" in visor_calls


def test_stealth_toggle_disengages_restores(gauges, monkeypatch):
    nano_calls = []
    visor_calls = []

    class FakeNano:
        def send_brightness(self, b): nano_calls.append(("B", b))
        def send_color(self, r, g, b): nano_calls.append(("C", (r, g, b)))

    class FakeVisor:
        def stream_image(self, surface, eye="L"): visor_calls.append(eye)
        def send_text(self, l, r=None): visor_calls.append(("TXT", l, r))

    import cyberdeck.hw.accessories as acc_mod
    import cyberdeck.hw.wifi_node as wifi_mod
    monkeypatch.setattr(acc_mod, "nano_accessories", FakeNano())
    monkeypatch.setattr(wifi_mod, "wifi_node", FakeVisor())

    config.STEALTH_MODE = True
    gauges.show_wifi_menu = False
    gauges.handle_tap(gauges.stealth_btn.center)

    assert config.STEALTH_MODE is False
    # Brightness restored to full.
    assert ("B", 255) in nano_calls
    # Visor text restored.
    assert any(isinstance(c, tuple) and c[0] == "TXT" for c in visor_calls)
