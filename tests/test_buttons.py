"""Hardware-button gesture tests using a fake gpiozero module.

These verify every physical button path the wearer has:
  left   -> single / double / hold(start+end)
  right  -> press / chord-with-action
  action -> short / double / hold(blackout) / chord
"""

import sys
import time
import types

import pytest

import cyberdeck.hw.button as button_mod
from cyberdeck.config import PIN_BTN_LEFT, PIN_BTN_RIGHT, PIN_BTN_ACTION

SINGLE_WAIT = 0.45  # > the 0.32/0.30 s click-disambiguation timers


class FakeButton:
    instances = {}

    def __init__(self, pin, hold_time=None, bounce_time=None):
        self.pin = pin
        self.hold_time = hold_time
        self.when_pressed = None
        self.when_released = None
        self.when_held = None
        self._pressed = False
        FakeButton.instances[pin] = self

    @property
    def is_pressed(self):
        return self._pressed

    # -- simulation helpers --------------------------------------------------
    def press(self):
        self._pressed = True
        if self.when_pressed:
            self.when_pressed()

    def release(self):
        self._pressed = False
        if self.when_released:
            self.when_released()

    def hold(self):
        """gpiozero fires when_held once hold_time elapses while pressed."""
        assert self._pressed, "hold() while not pressed"
        if self.when_held:
            self.when_held()


@pytest.fixture()
def nav():
    FakeButton.instances = {}
    fake = types.ModuleType("gpiozero")
    fake.Button = FakeButton

    calls = []
    import sys as _sys
    saved = _sys.modules.get("gpiozero")
    _sys.modules["gpiozero"] = fake
    saved_mock = button_mod.IS_MOCK
    button_mod.IS_MOCK = False
    try:
        buttons = button_mod.NavButtons(
            on_left_single=lambda: calls.append("L1"),
            on_right=lambda: calls.append("R"),
            on_action_short=lambda: calls.append("A1"),
            on_action_long=lambda: calls.append("A_LONG"),
            on_action_double=lambda: calls.append("A2"),
            on_chord=lambda: calls.append("CHORD"),
            on_left_double=lambda: calls.append("L2"),
            on_left_hold_start=lambda: calls.append("L_HOLD_START"),
            on_left_hold_end=lambda: calls.append("L_HOLD_END"),
        )
        yield buttons, calls
    finally:
        button_mod.IS_MOCK = saved_mock
        if saved is None:
            _sys.modules.pop("gpiozero", None)
        else:
            _sys.modules["gpiozero"] = saved


def _left():
    return FakeButton.instances[PIN_BTN_LEFT]


def _right():
    return FakeButton.instances[PIN_BTN_RIGHT]


def _action():
    return FakeButton.instances[PIN_BTN_ACTION]


def test_left_single_click(nav):
    _, calls = nav
    _left().press()
    _left().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["L1"]


def test_left_double_click(nav):
    _, calls = nav
    _left().press(); _left().release()
    _left().press(); _left().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["L2"]


def test_left_hold_fires_start_and_end(nav):
    _, calls = nav
    _left().press()
    _left().hold()
    _left().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["L_HOLD_START", "L_HOLD_END"]


def test_right_press(nav):
    _, calls = nav
    _right().press()
    assert calls == ["R"]


def test_action_short_click(nav):
    _, calls = nav
    _action().press()
    _action().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["A1"]


def test_action_double_click(nav):
    _, calls = nav
    _action().press(); _action().release()
    _action().press(); _action().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["A2"]


def test_action_hold_fires_long_only(nav):
    _, calls = nav
    _action().press()
    _action().hold()
    _action().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["A_LONG"]


def test_chord_action_then_right(nav):
    _, calls = nav
    _action().press()          # hold action down first
    _right().press()           # right sees action pressed -> chord
    assert calls == ["CHORD"]
    _action().release()        # must NOT fire a short click afterwards
    _right().release()
    time.sleep(SINGLE_WAIT)
    assert calls == ["CHORD"]


def test_three_buttons_created_with_expected_pins(nav):
    buttons, _ = nav
    assert buttons.btn_left.pin == PIN_BTN_LEFT
    assert buttons.btn_right.pin == PIN_BTN_RIGHT
    assert buttons.btn_action.pin == PIN_BTN_ACTION


def test_raw_press_fires_immediately_on_every_press():
    """on_raw_press must fire on the physical press, before click timers, so
    combos can be detected without waiting for single/double disambiguation."""
    FakeButton.instances = {}
    fake = types.ModuleType("gpiozero")
    fake.Button = FakeButton
    import sys as _sys
    saved = _sys.modules.get("gpiozero")
    _sys.modules["gpiozero"] = fake
    saved_mock = button_mod.IS_MOCK
    button_mod.IS_MOCK = False
    raw = []
    try:
        button_mod.NavButtons(
            on_left_single=lambda: None, on_right=lambda: None,
            on_action_short=lambda: None, on_action_long=lambda: None,
            on_action_double=lambda: None,
            on_raw_press=lambda name: raw.append(name),
        )
        _left().press(); _left().release()
        _right().press(); _right().release()
        _action().press(); _action().release()
        # Raw taps are immediate: no sleep needed.
        assert raw == ["L", "R", "A"]
    finally:
        button_mod.IS_MOCK = saved_mock
        if saved is None:
            _sys.modules.pop("gpiozero", None)
        else:
            _sys.modules["gpiozero"] = saved


def test_callback_exception_does_not_break_buttons():
    """A raising handler must not kill the button thread or later events."""
    FakeButton.instances = {}
    fake = types.ModuleType("gpiozero")
    fake.Button = FakeButton
    import sys as _sys
    saved = _sys.modules.get("gpiozero")
    _sys.modules["gpiozero"] = fake
    saved_mock = button_mod.IS_MOCK
    button_mod.IS_MOCK = False
    calls = []

    def boom():
        raise RuntimeError("boom")

    try:
        button_mod.NavButtons(
            on_left_single=boom, on_right=lambda: calls.append("R"),
            on_action_short=lambda: None, on_action_long=lambda: None,
            on_action_double=lambda: None,
        )
        _left().press(); _left().release()
        time.sleep(SINGLE_WAIT)          # raising single is swallowed safely
        _right().press()                 # next button still works
        assert calls == ["R"]
    finally:
        button_mod.IS_MOCK = saved_mock
        if saved is None:
            _sys.modules.pop("gpiozero", None)
        else:
            _sys.modules["gpiozero"] = saved
