import pygame

from cyberdeck.hw.wifi_node import pack_surface, WifiNode


def _solid(color):
    s = pygame.Surface((128, 64))
    s.fill(color)
    return s


def test_pack_surface_size():
    out = pack_surface(_solid((0, 0, 0)))
    assert isinstance(out, bytes)
    assert len(out) == 1024


def test_pack_surface_black_is_zero():
    out = pack_surface(_solid((0, 0, 0)))
    assert out == b"\x00" * 1024


def test_pack_surface_white_is_ones():
    out = pack_surface(_solid((255, 255, 255)))
    assert out == b"\xff" * 1024


def test_pack_surface_scales_non_128x64():
    s = pygame.Surface((64, 32))
    s.fill((255, 255, 255))
    out = pack_surface(s)
    assert len(out) == 1024
    assert out == b"\xff" * 1024


def test_pack_surface_threshold():
    # A pixel just above threshold counts as on, below as off.
    s = pygame.Surface((128, 64))
    s.fill((0, 0, 0))
    s.fill((200, 200, 200), (0, 0, 64, 64))  # left half bright
    out = pack_surface(s)
    # Each row: 16 bytes; left half = first 8 bytes set, right 8 clear.
    row = out[:16]
    assert row[:8] == b"\xff" * 8
    assert row[8:] == b"\x00" * 8


def test_wifi_node_dedup_state():
    n = WifiNode()
    sent = []
    n._send = lambda msg: sent.append(msg)
    n.send_state("IDLE")
    n.send_state("IDLE")      # duplicate — should be suppressed
    n.send_state("RUNNING")   # new state — should go through
    assert sent == ["S IDLE\n", "S RUNNING\n"]


def test_wifi_node_handles_incoming_power(monkeypatch):
    import cyberdeck.config as config
    monkeypatch.setattr(config, "ESP_MA", 0)
    n = WifiNode()
    n._handle_incoming(b"PWR 185\n", ("192.168.4.1", 1337))
    assert config.ESP_MA == 185

