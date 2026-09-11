import pygame
import pytest

from cyberdeck.ui.glitch import GlitchRenderer
from cyberdeck.config import State, RESOLUTION


@pytest.fixture()
def surface():
    return pygame.Surface(RESOLUTION)


@pytest.fixture()
def renderer(surface):
    return GlitchRenderer(surface)


@pytest.mark.parametrize("state", [
    State.BOOT, State.IDLE, State.SCANNING, State.RUNNING,
    State.ALERT, State.COOLDOWN, State.BLACKOUT, State.TARGET_LOCK,
])
def test_render_runs_for_every_state(renderer, state):
    # Must not raise regardless of state.
    renderer.render(state)


def test_no_scanline_method(renderer):
    """Scanlines are owned by hud_effects (cached); GlitchRenderer must not
    re-allocate/draw them per frame."""
    assert not hasattr(renderer, "apply_scanlines")


def test_effects_do_not_resize_surface(renderer, surface):
    renderer.apply_tearing(severity=3)
    renderer.apply_rgb_split(offset=2)
    renderer.apply_noise(alpha=20)
    assert surface.get_size() == RESOLUTION
