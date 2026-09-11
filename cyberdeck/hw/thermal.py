"""
Thermal guard for a deck that is worn against a body.

The Pi 3B+ soft-throttles around 80 C; inside a costume it can climb fast.
This guard watches the SoC temperature and reports a small integer level the
main loop uses to shed load *before* the hardware throttles, and to warn the
wearer. Hysteresis keeps the level from flapping when the temperature hovers
near a threshold.

Levels: 0 = nominal, 1 = warm (warn the wearer), 2 = critical (shed load).
"""

from .telemetry import get_temp

WARN_TEMP = 72.0      # start warning
CRIT_TEMP = 80.0      # shed load (just under the Pi's throttle point)
WARN_CLEAR = 68.0     # drop back to nominal
CRIT_CLEAR = 76.0     # drop from critical back to warm

NORMAL, WARM, CRITICAL = 0, 1, 2


class ThermalGuard:
    def __init__(self):
        self.level = NORMAL
        self.temp = 0.0

    def update(self, temp=None):
        """Feed a temperature (defaults to reading the real sensor) and return
        the current level."""
        if temp is None:
            temp = get_temp()
        self.temp = temp

        if self.level == NORMAL:
            if temp >= CRIT_TEMP:
                self.level = CRITICAL
            elif temp >= WARN_TEMP:
                self.level = WARM
        elif self.level == WARM:
            if temp >= CRIT_TEMP:
                self.level = CRITICAL
            elif temp < WARN_CLEAR:
                self.level = NORMAL
        else:  # CRITICAL
            if temp < CRIT_CLEAR:
                self.level = WARM
        return self.level

    @property
    def should_throttle(self):
        return self.level >= CRITICAL

    @property
    def label(self):
        return {NORMAL: "NOMINAL", WARM: "WARM", CRITICAL: "CRITICAL"}[self.level]
