import pytest

from cyberdeck.stats import SessionStats


@pytest.fixture()
def stats(tmp_path):
    return SessionStats(path=str(tmp_path / "stats.json"))


def test_initial_zero(stats):
    assert stats.runs == 0
    assert stats.solved == 0
    assert stats.failed == 0
    assert stats.credits == 0
    assert stats.success_rate == 0


def test_record_success(stats):
    stats.record_run(True, credits=750)
    assert stats.runs == 1
    assert stats.solved == 1
    assert stats.failed == 0
    assert stats.credits == 750
    assert stats.success_rate == 100


def test_record_failure(stats):
    stats.record_run(False)
    assert stats.runs == 1
    assert stats.failed == 1
    assert stats.solved == 0
    assert stats.success_rate == 0


def test_success_rate_mixed(stats):
    stats.record_run(True, 100)
    stats.record_run(True, 100)
    stats.record_run(False)
    assert stats.runs == 3
    assert stats.success_rate == 67  # 2/3 rounded


def test_negative_credits_clamped(stats):
    stats.record_run(True, credits=-50)
    assert stats.credits == 0


def test_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "stats.json")
    a = SessionStats(path=path)
    a.record_run(True, 500)
    a.record_run(False)

    b = SessionStats(path=path)  # fresh instance loads from disk
    assert b.runs == 2
    assert b.solved == 1
    assert b.failed == 1
    assert b.credits == 500


def test_corrupt_file_resets(tmp_path):
    path = str(tmp_path / "stats.json")
    with open(path, "w") as f:
        f.write("not json")
    s = SessionStats(path=path)
    assert s.runs == 0


def test_streak_tracks_consecutive_success(stats):
    stats.record_run(True, 100)
    stats.record_run(True, 100)
    assert stats.streak == 2
    assert stats.best_streak == 2
    stats.record_run(False)
    assert stats.streak == 0
    assert stats.best_streak == 2
    stats.record_run(True, 50)
    assert stats.streak == 1
    assert stats.best_streak == 2


def test_streak_persisted(tmp_path):
    path = str(tmp_path / "stats.json")
    a = SessionStats(path=path)
    a.record_run(True, 10)
    a.record_run(True, 10)

    b = SessionStats(path=path)
    assert b.streak == 2
    assert b.best_streak == 2
