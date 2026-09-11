from cyberdeck.ui.theme import ThemeManager


def test_default_theme_set():
    tm = ThemeManager()
    assert tm.current is not None
    assert tm.current.name


def test_cycle_theme_wraps():
    tm = ThemeManager()
    n = len(tm.theme_keys)
    first = tm.current
    for _ in range(n):
        tm.cycle_theme()
    assert tm.current is first


def test_set_theme_valid():
    tm = ThemeManager()
    t = tm.set_theme("ARASAKA_CORP")
    assert t.name == "ARASAKA CORP"
    assert tm.current.name == "ARASAKA CORP"


def test_set_theme_invalid_keeps_current():
    tm = ThemeManager()
    before = tm.current
    tm.set_theme("DOES_NOT_EXIST")
    assert tm.current is before


def test_all_themes_have_rgb_tuples():
    tm = ThemeManager()
    for key in tm.theme_keys:
        t = tm.themes[key]
        for attr in ("primary", "secondary", "accent", "bg", "surface_bg",
                     "text_primary", "text_dim", "border", "danger", "warning"):
            v = getattr(t, attr)
            assert isinstance(v, tuple) and len(v) == 3, f"{key}.{attr} bad"
            assert all(0 <= c <= 255 for c in v), f"{key}.{attr} out of range"
