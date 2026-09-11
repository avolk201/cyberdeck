import threading
from ..config import IS_MOCK, PIN_BTN_LEFT, PIN_BTN_RIGHT, PIN_BTN_ACTION

# Click-disambiguation windows: a second press within the window is a double
# click, otherwise the timer fires a single click.
LEFT_CLICK_WINDOW = 0.32
ACTION_CLICK_WINDOW = 0.30


class NavButtons:
    """
    Hardware button manager for the 3-button cluster (left / right / action)
    plus touchscreen. Decodes Single Click, Double Click, Hold and the
    two-button Chord from gpiozero press/release/hold events.

    Gestures:
      left   : single = cycle FX, double = cycle FX category,
               hold   = combat-surge while held
      right  : context action (scan / advance / resolve)
      action : single = confirm, double = back/tab, hold = emergency blackout
      chord  : right + action together = return to IDLE

    ``on_raw_press`` (optional) is called with "L" / "R" / "A" on every
    physical press *before* gesture disambiguation, which lets higher layers
    detect button combos without waiting for click timers.

    Callbacks are always invoked outside the internal lock so a handler can
    never deadlock the button thread.
    """

    def __init__(self, on_left_single, on_right, on_action_short, on_action_long,
                 on_action_double, on_chord=None, on_left_double=None,
                 on_left_hold_start=None, on_left_hold_end=None, on_raw_press=None):
        self.on_left_single = on_left_single
        self.on_left_double = on_left_double
        self.on_left_hold_start = on_left_hold_start
        self.on_left_hold_end = on_left_hold_end
        self.on_right = on_right
        self.on_action_short = on_action_short
        self.on_action_long = on_action_long
        self.on_action_double = on_action_double
        self.on_chord = on_chord
        self.on_raw_press = on_raw_press

        self._left_press_count = 0
        self._left_timer = None
        self._left_held = False

        self._action_press_count = 0
        self._action_timer = None
        self._action_held = False
        self._chord_fired_this_press = False
        self._lock = threading.Lock()

        if IS_MOCK:
            return
        try:
            self._setup_gpio()
        except ImportError:
            print("gpiozero not found, mock buttons")

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _fire(callback):
        if callback is None:
            return
        try:
            callback()
        except Exception as e:
            print(f"[BUTTON] callback error: {e}")

    def _fire_raw(self, name):
        if self.on_raw_press is None:
            return
        try:
            self.on_raw_press(name)
        except Exception as e:
            print(f"[BUTTON] raw press callback error: {e}")

    # -- gpio wiring ---------------------------------------------------------
    def _setup_gpio(self):
        from gpiozero import Button
        self.btn_left = Button(PIN_BTN_LEFT, hold_time=1.2, bounce_time=0.05)
        self.btn_right = Button(PIN_BTN_RIGHT, bounce_time=0.05)
        self.btn_action = Button(PIN_BTN_ACTION, hold_time=1.5, bounce_time=0.05)

        # --- Left button (vest FX) ---
        def left_pressed():
            self._fire_raw("L")

        def left_held():
            with self._lock:
                self._left_held = True
                if self._left_timer:
                    self._left_timer.cancel()
                    self._left_timer = None
                self._left_press_count = 0
            self._fire(self.on_left_hold_start)

        def left_released():
            callback = None
            with self._lock:
                if self._left_held:
                    self._left_held = False
                    callback = self.on_left_hold_end
                else:
                    self._left_press_count += 1
                    if self._left_press_count == 1:
                        self._left_timer = threading.Timer(LEFT_CLICK_WINDOW,
                                                           self._eval_left_clicks)
                        self._left_timer.daemon = True
                        self._left_timer.start()
                    else:
                        if self._left_timer:
                            self._left_timer.cancel()
                            self._left_timer = None
                        self._left_press_count = 0
                        callback = self.on_left_double or self.on_left_single
            self._fire(callback)

        self.btn_left.when_pressed = left_pressed
        self.btn_left.when_held = left_held
        self.btn_left.when_released = left_released

        # --- Right button ---
        def right_pressed():
            self._fire_raw("R")
            with self._lock:
                chord = self.btn_action.is_pressed and self.on_chord is not None
                if chord:
                    self._chord_fired_this_press = True
            self._fire(self.on_chord if chord else self.on_right)

        self.btn_right.when_pressed = right_pressed

        # --- Action button ---
        def action_pressed():
            self._fire_raw("A")

        def action_held():
            with self._lock:
                self._action_held = True
                if self._action_timer:
                    self._action_timer.cancel()
                    self._action_timer = None
                self._action_press_count = 0
            self._fire(self.on_action_long)

        def action_released():
            callback = None
            with self._lock:
                if self._action_held:
                    self._action_held = False
                elif self._chord_fired_this_press:
                    self._chord_fired_this_press = False
                elif self.btn_right.is_pressed and self.on_chord is not None:
                    callback = self.on_chord
                else:
                    self._action_press_count += 1
                    if self._action_press_count == 1:
                        self._action_timer = threading.Timer(ACTION_CLICK_WINDOW,
                                                             self._eval_action_clicks)
                        self._action_timer.daemon = True
                        self._action_timer.start()
                    else:
                        if self._action_timer:
                            self._action_timer.cancel()
                            self._action_timer = None
                        self._action_press_count = 0
                        callback = self.on_action_double or self.on_action_short
            self._fire(callback)

        self.btn_action.when_pressed = action_pressed
        self.btn_action.when_held = action_held
        self.btn_action.when_released = action_released

    # -- click-timer evaluation ---------------------------------------------
    def _eval_left_clicks(self):
        with self._lock:
            count = self._left_press_count
            self._left_press_count = 0
            self._left_timer = None
        if count == 1:
            self._fire(self.on_left_single)

    def _eval_action_clicks(self):
        with self._lock:
            count = self._action_press_count
            self._action_press_count = 0
            self._action_timer = None
        if count == 1:
            self._fire(self.on_action_short)
