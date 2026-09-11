import json

import pytest

import cyberdeck.config as config
from cyberdeck import settings


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point settings at a temp file and restore config/theme afterwards."""
    path = str(tmp_path / "settings.json")
    monkeypatch.setattr(settings, "DEFAULT_PATH", path)
    settings.reset_cache()
    saved = {attr: getattr(config, attr) for attr, _ in settings._FIELDS}
    from cyberdeck.ui.theme import theme_manager
    saved_theme_idx = theme_manager.current_idx
    yield path
    for attr, value in saved.items():
        setattr(config, attr, value)
    theme_manager.current_idx = saved_theme_idx
    theme_manager.current = theme_manager.themes[theme_manager.theme_keys[saved_theme_idx]]
    settings.reset_cache()


def test_snapshot_captures_fields(_isolate):
    config.STEALTH_MODE = True
    config.ACTIVE_FX = "MATRIX_CYBER_SKULL"
    data = settings.snapshot()
    assert data["STEALTH_MODE"] is True
    assert data["ACTIVE_FX"] == "MATRIX_CYBER_SKULL"
    assert "THEME" in data


def test_snapshot_tuple_serialised_as_list(_isolate):
    config.ACTIVE_VISOR_TEXT = ("LEFT", "RIGHT")
    data = settings.snapshot()
    assert data["ACTIVE_VISOR_TEXT"] == ["LEFT", "RIGHT"]


def test_apply_roundtrip(_isolate):
    config.STEALTH_MODE = False
    config.ACTIVE_FX = "A"
    config.ACTIVE_VISOR_TEXT = ("X", "Y")
    data = settings.snapshot()

    # Mutate config, then re-apply the snapshot to restore it.
    config.STEALTH_MODE = True
    config.ACTIVE_FX = "B"
    config.ACTIVE_VISOR_TEXT = ("Z", "Z")
    settings.apply(data)

    assert config.STEALTH_MODE is False
    assert config.ACTIVE_FX == "A"
    assert config.ACTIVE_VISOR_TEXT == ("X", "Y")


def test_save_and_load_file(_isolate):
    path = _isolate
    config.ACTIVE_FX = "SUIT_SANDEVISTAN_APEX"
    config.STEALTH_MODE = True
    assert settings.save_if_changed(path) is True
    assert settings.save_if_changed(path) is False  # unchanged -> no rewrite

    # Scramble in-memory config, then load from disk.
    config.ACTIVE_FX = "GONE"
    config.STEALTH_MODE = False
    assert settings.load(path) is True
    assert config.ACTIVE_FX == "SUIT_SANDEVISTAN_APEX"
    assert config.STEALTH_MODE is True


def test_load_missing_file_returns_false(_isolate):
    assert settings.load(str(_isolate) + ".nope") is False


def test_load_corrupt_file_returns_false(_isolate):
    path = _isolate
    with open(path, "w") as f:
        f.write("{ this is not json")
    assert settings.load(path) is False


def test_apply_ignores_bad_values(_isolate):
    before = config.ACTIVE_FX
    settings.apply({"ACTIVE_FX": 12345, "STEALTH_MODE": "yes",
                    "ACTIVE_VISOR_TEXT": ["only_one"]})
    # str field with non-str value left untouched; bool coerced; bad tuple ignored
    assert config.ACTIVE_FX == before
    assert config.STEALTH_MODE is True  # "yes" -> bool("yes") == True


def test_theme_persisted(_isolate):
    from cyberdeck.ui.theme import theme_manager
    path = _isolate
    theme_manager.set_theme("ARASAKA_CORP")
    settings.save_if_changed(path)

    theme_manager.set_theme("TRAUMA_TEAM")
    assert theme_manager.current.name == "TRAUMA TEAM"

    settings.load(path)
    assert theme_manager.current.name == "ARASAKA CORP"
