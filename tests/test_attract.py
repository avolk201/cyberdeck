import pytest

import cyberdeck.config as config
from cyberdeck.ui.widgets import apply_suit_preset, SUIT_GLOBAL_PRESETS
from cyberdeck.ui.theme import theme_manager


@pytest.fixture(autouse=True)
def _restore():
    fields = ["ACTIVE_SUIT_PRESET", "ACTIVE_VISOR_MODE", "ACTIVE_VISOR_TEXT",
              "ACTIVE_MATRIX_FX", "ACTIVE_MC_OLED_FX", "ACTIVE_FX"]
    saved = {f: getattr(config, f) for f in fields}
    saved_theme_idx = theme_manager.current_idx
    yield
    for f, v in saved.items():
        setattr(config, f, v)
    theme_manager.current_idx = saved_theme_idx
    theme_manager.current = theme_manager.themes[theme_manager.theme_keys[saved_theme_idx]]


def test_apply_suit_preset_sets_config(monkeypatch):
    nano_calls = []
    visor_calls = []

    class FakeNano:
        def broadcast(self, s): nano_calls.append(("S", s))
        def send_color(self, r, g, b): nano_calls.append(("C", (r, g, b)))

    class FakeVisor:
        def send_text(self, l, r=None): visor_calls.append((l, r))

    import cyberdeck.hw.accessories as acc_mod
    import cyberdeck.hw.wifi_node as wifi_mod
    monkeypatch.setattr(acc_mod, "nano_accessories", FakeNano())
    monkeypatch.setattr(wifi_mod, "wifi_node", FakeVisor())

    preset = SUIT_GLOBAL_PRESETS[0]
    fx_id = apply_suit_preset(preset)

    assert config.ACTIVE_SUIT_PRESET == preset["name"]
    assert config.ACTIVE_VISOR_MODE == "TEXT"
    assert config.ACTIVE_VISOR_TEXT == preset["text"]
    assert config.ACTIVE_MATRIX_FX == preset["matrix"]
    assert config.ACTIVE_MC_OLED_FX == preset["mc"]
    assert config.ACTIVE_FX == fx_id
    assert fx_id == f"SUIT_{preset['name'].replace(' ', '_')}"

    # Broadcast the loadout id + its color to the Nano, and text to the visor.
    assert ("S", fx_id) in nano_calls
    assert ("C", preset["rgb"]) in nano_calls
    assert preset["text"] in visor_calls

    # Theme switched to the preset's theme.
    assert theme_manager.current.name == theme_manager.themes[preset["theme"]].name


def test_all_presets_have_required_keys():
    required = {"name", "desc", "theme", "text", "matrix", "mc", "rgb"}
    for p in SUIT_GLOBAL_PRESETS:
        assert required.issubset(p.keys()), f"preset {p.get('name')} missing keys"
        assert len(p["text"]) == 2
        assert len(p["rgb"]) == 3
        # Theme must exist so set_theme does not silently no-op.
        assert p["theme"] in theme_manager.themes, f"{p['name']} bad theme"
