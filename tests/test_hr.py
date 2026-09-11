import time

from cyberdeck.hw.hr import HRMonitor


def test_mock_waveform_generated():
    m = HRMonitor()
    wave = m.get_waveform(64)
    assert wave is not None
    assert len(wave) == 64
    assert all(0.0 <= v <= 1.0 for v in wave)


def test_mock_derives_bpm():
    m = HRMonitor()
    m.get_waveform(64)  # triggers mock fill + beat detection
    # Mock ECG runs at 1.25 beats/sec -> ~75 BPM
    assert 60 <= m.bpm <= 90


def test_add_sample_updates_raw():
    m = HRMonitor()
    m.add_sample(512)
    assert m.raw == 512
    assert m.last_sample > 0


def test_no_signal_when_empty():
    m = HRMonitor()
    m.samples.clear()
    m.last_sample = 0.0
    assert m.has_signal is False


def test_bpm_decays_to_zero_after_silence():
    m = HRMonitor()
    m.get_waveform(64)
    assert m.bpm > 0
    m.last_beat = time.time() - 10.0
    m.get_waveform(64)
    assert m.bpm == 0
