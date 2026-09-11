"""
Button-combo detection from raw press taps.

Fed by NavButtons' ``on_raw_press`` (which fires on the physical press, before
click disambiguation), so combos feel immediate. Used for the wearer-facing
easter egg: L, L, R, R, A within the window triggers a Cyberpsycho Surge.
"""

import time


class ComboDetector:
    def __init__(self, sequence, window=4.0):
        self.sequence = list(sequence)
        self.window = window
        self._taps = []

    def feed(self, name, now=None):
        """Record a raw tap; returns True when the full sequence just matched."""
        if not self.sequence:
            return False
        now = time.time() if now is None else now
        # Drop taps that fell out of the window.
        self._taps = [(n, t) for n, t in self._taps if now - t <= self.window]
        self._taps.append((name, now))
        if len(self._taps) >= len(self.sequence):
            recent = [n for n, _ in self._taps[-len(self.sequence):]]
            if recent == self.sequence:
                self._taps = []
                return True
        return False

    def reset(self):
        self._taps = []
