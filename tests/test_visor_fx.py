import pygame
import pytest

from cyberdeck.ui.visor_fx import VISOR_FX


@pytest.fixture()
def eyes():
    return pygame.Surface((128, 64)), pygame.Surface((128, 64))


def test_all_visor_effects_registered():
    assert len(VISOR_FX) == 15


@pytest.mark.parametrize("name", list(VISOR_FX.keys()))
def test_every_visor_effect_renders_without_error(eyes, name):
    left, right = eyes
    fx = VISOR_FX[name]
    left.fill((0, 0, 0))
    right.fill((0, 0, 0))
    # Run across a few time samples to catch time-dependent branches.
    for t in (0.0, 1.3, 7.7, 42.0):
        fx(t, left, right)


def test_vitals_handles_no_signal(eyes, monkeypatch):
    """VITALS reads the heart-rate monitor; force the no-signal path."""
    from cyberdeck.ui import visor_fx
    left, right = eyes

    class NoHR:
        bpm = 0
        last_beat = 0.0

        def get_waveform(self, n, span=None):
            return None

    monkeypatch.setattr(visor_fx, "hr_monitor", NoHR())
    VISOR_FX["VITALS"](1.0, left, right)
