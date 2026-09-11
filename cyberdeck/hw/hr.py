import time
from collections import deque
from ..config import IS_MOCK

_ECG = [(0.0, 0.0), (0.12, 0.0), (0.18, 0.18), (0.24, 0.0), (0.28, -0.22),
        (0.33, 1.0), (0.38, -0.3), (0.44, 0.0), (0.58, 0.0), (0.66, 0.28),
        (0.74, 0.0), (1.0, 0.0)]

def _ecg_shape(x):
    x %= 1.0
    for i in range(len(_ECG) - 1):
        x0, y0 = _ECG[i]
        x1, y1 = _ECG[i + 1]
        if x0 <= x < x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return 0.0

class HRMonitor:
    """
    Consumes raw HR sensor samples from the Nano (~20 Hz analog readings),
    keeps a rolling waveform buffer and derives BPM via threshold crossing
    with a refractory period.
    """
    SAMPLE_RATE = 20.0
    WINDOW_S = 12.0
    SCOPE_SPAN_S = 6.0

    def __init__(self):
        self.samples = deque(maxlen=int(self.SAMPLE_RATE * self.WINDOW_S))
        self.beat_times = deque(maxlen=10)
        self.bpm = 0
        self.raw = 0
        self.last_beat = 0.0
        self.last_sample = 0.0
        self._mock_last = 0.0
        self._mock_phase = 0.0

    def add_sample(self, value):
        now = time.time()
        self.raw = value
        self.last_sample = now
        self.samples.append((now, float(value)))
        self._detect_beat(now, float(value))

    def _detect_beat(self, now, value):
        if len(self.samples) < 20:
            return
        vals = [v for _, v in self.samples]
        mean = sum(vals) / len(vals)
        amp = max(vals) - min(vals)
        if amp < 10:
            return
        # Rising crossing at 35% of recent amplitude, 350 ms refractory
        if value - mean > amp * 0.35 and now - self.last_beat > 0.35:
            self.last_beat = now
            self.beat_times.append(now)
            ibis = sorted(b - a for a, b in zip(self.beat_times, list(self.beat_times)[1:]))
            ibis = [i for i in ibis if 0.33 < i < 2.5]
            if ibis:
                self.bpm = int(round(60.0 / ibis[len(ibis) // 2]))

    @property
    def has_signal(self):
        return len(self.samples) >= 20 and time.time() - self.last_sample < 3.0

    def get_waveform(self, points, span=None):
        """
        Returns `points` floats (0..1) covering the last `span` seconds,
        DC-removed and amplitude-normalized, or None if not enough data.
        """
        if IS_MOCK:
            self._mock_fill()
        if time.time() - self.last_beat > 5.0:
            self.bpm = 0
        if span is None:
            span = self.SCOPE_SPAN_S
        now = time.time()
        cutoff = now - span
        pts = [(t, v) for t, v in self.samples if t >= cutoff]
        if len(pts) < 8:
            return None
        vals = [v for _, v in self.samples]
        mean = sum(vals) / len(vals)
        amp = max(vals) - min(vals)
        if amp < 1e-6:
            return [0.5] * points
        out = []
        idx = 0
        n = len(pts)
        for i in range(points):
            t = cutoff + span * i / (points - 1)
            while idx < n - 2 and pts[idx + 1][0] <= t:
                idx += 1
            t0, v0 = pts[idx]
            t1, v1 = pts[min(idx + 1, n - 1)]
            f = min(max((t - t0) / (t1 - t0), 0.0), 1.0) if t1 > t0 else 0.0
            v = (v0 + (v1 - v0) * f - mean) / amp + 0.5
            out.append(min(max(v, 0.0), 1.0))
        return out

    def _mock_fill(self):
        now = time.time()
        t = self._mock_last if self._mock_last else now - self.SCOPE_SPAN_S
        t = max(t, now - self.WINDOW_S)
        while t < now:
            t += 1.0 / self.SAMPLE_RATE
            self._mock_phase += 1.25 / self.SAMPLE_RATE
            v = 512.0 + 180.0 * _ecg_shape(self._mock_phase)
            self.samples.append((t, v))
            self._detect_beat(t, v)
        self._mock_last = now
        self.last_sample = now

hr_monitor = HRMonitor()
