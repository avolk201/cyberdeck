from cyberdeck.hw import telemetry


def test_get_temp_in_range():
    t = telemetry.get_temp()
    assert isinstance(t, float)
    assert 30.0 <= t <= 90.0


def test_get_cpu_usage_range():
    c = telemetry.get_cpu_usage()
    assert 0.0 <= c <= 100.0


def test_get_ram_usage_tuple():
    used, total, pct = telemetry.get_ram_usage()
    assert used <= total
    assert 0 <= pct <= 100


def test_get_uptime_format():
    s = telemetry.get_uptime()
    assert "h" in s and "m" in s and "s" in s


def test_power_telemetry_normal():
    p = telemetry.get_power_telemetry(active_fx="")
    assert p["is_stealth"] is False
    assert p["total_watts"] > 0
    assert p["current_amps"] > 0
    assert 1 <= p["battery_pct"] <= 100
    assert "h" in p["runtime_str"]


def test_power_telemetry_stealth_lower_draw():
    import cyberdeck.config as config
    normal = telemetry.get_power_telemetry(active_fx="")
    config.STEALTH_MODE = True
    try:
        stealth = telemetry.get_power_telemetry(active_fx="")
        assert stealth["is_stealth"] is True
        assert stealth["total_watts"] < normal["total_watts"]
    finally:
        config.STEALTH_MODE = False


def test_power_telemetry_stealth_monitors_physical_el_switch(monkeypatch):
    """The EL wire switch is physical; stealth mode must still monitor it."""
    import cyberdeck.config as config
    config.STEALTH_MODE = True
    try:
        monkeypatch.setattr(config, "NANO_SW", 1)
        p_on = telemetry.get_power_telemetry(active_fx="")
        assert p_on["nano_sw_on"] is True
        assert p_on["el_wire_watts"] == 4.0
        assert p_on["el_status_str"] == "NANO SW: ON"

        monkeypatch.setattr(config, "NANO_SW", 0)
        p_off = telemetry.get_power_telemetry(active_fx="")
        assert p_off["nano_sw_on"] is False
        assert p_off["el_wire_watts"] == 0.0
        assert p_off["el_status_str"] == "NANO SW: OFF"
    finally:
        config.STEALTH_MODE = False


def test_power_telemetry_keys_complete():
    p = telemetry.get_power_telemetry(active_fx="SANDEVISTAN")
    for key in ("cpu_pct", "is_stealth", "nano_sw_on", "el_status_str",
                "pi_watts", "led_strip_watts", "matrix_watts", "el_wire_watts",
                "oled_watts", "total_watts", "current_amps", "battery_pct",
                "est_hours", "est_mins", "runtime_str", "nano_ma", "esp_ma"):
        assert key in p, f"missing key {key}"


def test_nano_ma_callback_parsed(monkeypatch):
    """The Nano serial callback should parse 'MA <value>' and store it."""
    import cyberdeck.config as config
    from cyberdeck.hw.accessories import _default_nano_callback

    monkeypatch.setattr(config, "NANO_MA", 0)
    _default_nano_callback("MA 327")
    assert config.NANO_MA == 327


def test_power_telemetry_uses_nano_ma(monkeypatch):
    """When NANO_MA > 0, telemetry should use real data instead of heuristic."""
    import cyberdeck.config as config

    monkeypatch.setattr(config, "NANO_MA", 400)
    p = telemetry.get_power_telemetry(active_fx="")
    # 400 mA @ 5V = 2.0 W — should appear as led_strip_watts
    assert p["led_strip_watts"] == 2.0
    # matrix_watts folded into nano_ma, so should be 0
    assert p["matrix_watts"] == 0.0
    assert p["nano_ma"] == 400


def test_power_telemetry_uses_esp_ma(monkeypatch):
    """When ESP_MA > 0, telemetry should use real ESP32 visor data."""
    import cyberdeck.config as config

    monkeypatch.setattr(config, "ESP_MA", 200)
    p = telemetry.get_power_telemetry(active_fx="")
    # 200 mA @ 5V = 1.0W + 0.1W (micro-OLED) = 1.1W
    assert p["oled_watts"] == 1.1
    assert p["esp_ma"] == 200

