from cyberdeck.hw.thermal import (
    ThermalGuard, NORMAL, WARM, CRITICAL,
    WARN_TEMP, CRIT_TEMP, WARN_CLEAR, CRIT_CLEAR,
)


def test_starts_normal():
    g = ThermalGuard()
    assert g.level == NORMAL
    assert not g.should_throttle


def test_rises_to_warm():
    g = ThermalGuard()
    assert g.update(WARN_TEMP + 1) == WARM
    assert not g.should_throttle


def test_rises_to_critical():
    g = ThermalGuard()
    g.update(WARN_TEMP + 1)
    assert g.update(CRIT_TEMP + 1) == CRITICAL
    assert g.should_throttle


def test_jumps_straight_to_critical():
    g = ThermalGuard()
    assert g.update(CRIT_TEMP + 5) == CRITICAL


def test_hysteresis_warm_does_not_flap():
    g = ThermalGuard()
    g.update(WARN_TEMP + 1)          # -> WARM
    # Between WARN_CLEAR and WARN_TEMP stays WARM (no flap to NORMAL).
    assert g.update((WARN_CLEAR + WARN_TEMP) / 2) == WARM
    assert g.update(WARN_CLEAR - 0.1) == NORMAL


def test_hysteresis_critical_drops_to_warm_first():
    g = ThermalGuard()
    g.update(CRIT_TEMP + 5)          # -> CRITICAL
    # Cooling just below CRIT_CLEAR drops to WARM, not straight to NORMAL.
    assert g.update(CRIT_CLEAR - 0.1) == WARM
    assert g.should_throttle is False
    # Still warm until below WARN_CLEAR.
    assert g.update(WARN_CLEAR - 0.1) == NORMAL


def test_label():
    g = ThermalGuard()
    assert g.label == "NOMINAL"
    g.update(WARN_TEMP + 1)
    assert g.label == "WARM"
    g.update(CRIT_TEMP + 1)
    assert g.label == "CRITICAL"


def test_update_reads_sensor_by_default(monkeypatch):
    import cyberdeck.hw.thermal as thermal_mod
    monkeypatch.setattr(thermal_mod, "get_temp", lambda: 99.0)
    g = ThermalGuard()
    assert g.update() == CRITICAL
    assert g.temp == 99.0
