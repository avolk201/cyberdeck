from cyberdeck.combo import ComboDetector

SEQ = ["L", "L", "R", "R", "A"]


def test_exact_sequence_triggers():
    d = ComboDetector(SEQ, window=4.0)
    t = 100.0
    results = [d.feed(n, now=t + i * 0.3) for i, n in enumerate(SEQ)]
    assert results == [False, False, False, False, True]


def test_wrong_order_does_not_trigger():
    d = ComboDetector(SEQ, window=4.0)
    t = 100.0
    for i, n in enumerate(["L", "R", "L", "R", "A"]):
        assert d.feed(n, now=t + i * 0.3) is False


def test_taps_outside_window_expire():
    d = ComboDetector(SEQ, window=4.0)
    d.feed("L", now=100.0)
    d.feed("L", now=101.0)
    # 5 seconds later the first taps have expired; sequence can't complete.
    assert d.feed("R", now=106.0) is False
    assert d.feed("R", now=106.5) is False
    assert d.feed("A", now=107.0) is False


def test_trigger_resets_so_it_can_fire_again():
    d = ComboDetector(SEQ, window=4.0)
    t = 100.0
    for i, n in enumerate(SEQ):
        d.feed(n, now=t + i * 0.2)
    # Second round
    t2 = 200.0
    results = [d.feed(n, now=t2 + i * 0.2) for i, n in enumerate(SEQ)]
    assert results[-1] is True


def test_partial_then_correct_continues():
    d = ComboDetector(["L", "A"], window=4.0)
    assert d.feed("L", now=1.0) is False
    assert d.feed("L", now=1.5) is False   # extra L, still no match
    assert d.feed("A", now=2.0) is True     # last two are L, A


def test_empty_sequence_never_fires():
    d = ComboDetector([], window=4.0)
    assert d.feed("L", now=1.0) is False


def test_reset_clears_history():
    d = ComboDetector(["L", "A"], window=4.0)
    d.feed("L", now=1.0)
    d.reset()
    assert d.feed("A", now=1.5) is False
