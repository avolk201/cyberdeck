import os

# Force headless SDL before any module imports pygame display.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_MOUSE_TOUCH_EVENTS", "1")

import pytest


@pytest.fixture(autouse=True)
def _mock_platform(monkeypatch):
    """Ensure every test runs in mock mode regardless of host OS."""
    import cyberdeck.config as config
    monkeypatch.setattr(config, "IS_MOCK", True, raising=False)
    yield
