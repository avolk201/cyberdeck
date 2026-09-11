"""
Persistent netrunner career stats.

Every breach the wearer runs is tallied (attempts, successes, failures and the
credits "extracted") and survives power cycles, so the deck remembers their
career across convention days. Kept separate from user settings because these
are accumulators, not preferences.
"""

import json
import os
import threading

DEFAULT_PATH = os.environ.get(
    "CYBERDECK_STATS",
    os.path.join(os.path.expanduser("~"), ".cyberdeck", "stats.json"),
)


class SessionStats:
    FIELDS = ("runs", "solved", "failed", "credits", "streak", "best_streak")

    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.runs = 0
        self.solved = 0
        self.failed = 0
        self.credits = 0
        self.streak = 0
        self.best_streak = 0
        self._lock = threading.Lock()
        self.load()

    def record_run(self, success, credits=0):
        with self._lock:
            self.runs += 1
            if success:
                self.solved += 1
                self.streak += 1
                if self.streak > self.best_streak:
                    self.best_streak = self.streak
            else:
                self.failed += 1
                self.streak = 0
            self.credits += max(0, int(credits))
        self.save()

    @property
    def success_rate(self):
        return int(round(100.0 * self.solved / self.runs)) if self.runs else 0

    def as_dict(self):
        return {f: getattr(self, f) for f in self.FIELDS}

    def load(self):
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        for field in self.FIELDS:
            try:
                setattr(self, field, int(data.get(field, 0)))
            except (TypeError, ValueError):
                setattr(self, field, 0)
        return True

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.as_dict(), f, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False


# Shared instance used by the app.
session_stats = SessionStats()
