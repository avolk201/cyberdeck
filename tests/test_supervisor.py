import os

import pytest

from cyberdeck.supervisor import (
    Supervisor, RestartPolicy, touch_heartbeat, heartbeat_age,
    HEARTBEAT_TIMEOUT_S,
)


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


class FakeProc:
    def __init__(self, exit_code, alive_for=0.0, clock=None):
        # exit_code: final code. alive_for: seconds it stays alive before exiting.
        self._exit_code = exit_code
        self._spawn_time = clock.now if clock else 0.0
        self._alive_for = alive_for
        self._clock = clock
        self.killed = False
        self.terminated = False
        self._forced_exit = None

    def poll(self):
        if self._forced_exit is not None:
            return self._forced_exit
        if self._clock is not None and self._clock.now - self._spawn_time < self._alive_for:
            return None
        return self._exit_code

    def wait(self, timeout=None):
        code = self.poll()
        if code is None:
            self._forced_exit = -9
            return -9
        return code

    def kill(self):
        self.killed = True
        self._forced_exit = -9

    def terminate(self):
        self.terminated = True
        self._forced_exit = -15


# ---------------------------------------------------------------------------
# RestartPolicy
# ---------------------------------------------------------------------------
def test_policy_clean_exit_no_restart():
    p = RestartPolicy()
    assert not p.circuit_open()
    assert p.backoff_seconds() == p.base_backoff_s


def test_policy_exponential_backoff():
    p = RestartPolicy(base_backoff_s=2.0, max_backoff_s=30.0)
    t = 0.0
    p.record_restart(t); assert p.backoff_seconds() == 2.0
    p.record_restart(t); assert p.backoff_seconds() == 4.0
    p.record_restart(t); assert p.backoff_seconds() == 8.0
    p.record_restart(t); assert p.backoff_seconds() == 16.0
    p.record_restart(t); assert p.backoff_seconds() == 30.0  # capped


def test_policy_circuit_breaker_opens():
    p = RestartPolicy(max_rapid_restarts=3, rapid_window_s=60.0)
    for i in range(3):
        p.record_restart(float(i))
    assert p.circuit_open()


def test_policy_circuit_resets_after_window():
    p = RestartPolicy(max_rapid_restarts=3, rapid_window_s=10.0)
    p.record_restart(0.0)
    p.record_restart(1.0)
    # Third restart far outside the window: old ones pruned.
    p.record_restart(100.0)
    assert not p.circuit_open()


def test_policy_healthy_run_resets():
    p = RestartPolicy(base_backoff_s=2.0)
    p.record_restart(0.0)
    p.record_restart(0.0)
    assert p.backoff_seconds() == 4.0
    p.record_healthy_run()
    assert p.backoff_seconds() == 2.0


# ---------------------------------------------------------------------------
# Heartbeat helpers
# ---------------------------------------------------------------------------
def test_heartbeat_touch_and_age(tmp_path):
    path = str(tmp_path / "hb")
    touch_heartbeat(path, now=100.0)
    assert os.path.exists(path)
    assert heartbeat_age(path, now=100.0) == 0.0
    assert heartbeat_age(path, now=105.5) == pytest.approx(5.5)


def test_heartbeat_missing_is_infinite(tmp_path):
    path = str(tmp_path / "does_not_exist")
    assert heartbeat_age(path) == float("inf")


def test_heartbeat_corrupt_is_infinite(tmp_path):
    path = str(tmp_path / "hb")
    with open(path, "w") as f:
        f.write("not-a-number")
    assert heartbeat_age(path) == float("inf")


# ---------------------------------------------------------------------------
# Supervisor run loop
# ---------------------------------------------------------------------------
def _make_supervisor(tmp_path, procs, clock):
    hb = str(tmp_path / "hb")
    spawned = []

    def spawner(cmd):
        proc = procs.pop(0)
        spawned.append(proc)
        return proc

    sleeps = []

    def sleeper(dt):
        sleeps.append(dt)
        clock.advance(dt)
        # keep heartbeat fresh (in the fake clock's domain) so the watchdog
        # does not fire unless the test wants it to
        touch_heartbeat(hb, clock.now)

    sup = Supervisor(cmd=["fake"], heartbeat_path=hb, policy=RestartPolicy(),
                     spawner=spawner, clock=clock, sleeper=sleeper)
    return sup, spawned, sleeps


def test_clean_exit_stops(tmp_path):
    clock = FakeClock()
    procs = [FakeProc(0, clock=clock)]
    sup, spawned, _ = _make_supervisor(tmp_path, procs, clock)
    rc = sup.run()
    assert rc == 0
    assert len(spawned) == 1
    assert sup.restart_count == 0


def test_crash_restarts_then_clean_exit(tmp_path):
    clock = FakeClock()
    procs = [
        FakeProc(1, clock=clock),   # crash
        FakeProc(1, clock=clock),   # crash
        FakeProc(0, clock=clock),   # clean exit
    ]
    sup, spawned, _ = _make_supervisor(tmp_path, procs, clock)
    rc = sup.run()
    assert rc == 0
    assert len(spawned) == 3
    assert sup.restart_count == 2


def test_circuit_breaker_exits_nonzero(tmp_path):
    clock = FakeClock()
    policy = RestartPolicy(max_rapid_restarts=3, rapid_window_s=1000.0)
    procs = [FakeProc(1, clock=clock) for _ in range(10)]
    hb = str(tmp_path / "hb")
    idx = {"i": 0}

    def spawner(cmd):
        p = procs[idx["i"]]
        idx["i"] += 1
        return p

    def sleeper(dt):
        clock.advance(dt)
        touch_heartbeat(hb, clock.now)

    sup = Supervisor(cmd=["fake"], heartbeat_path=hb, policy=policy,
                     spawner=spawner, clock=clock, sleeper=sleeper)
    rc = sup.run()
    assert rc == 1  # handed off to systemd


def test_hung_process_is_killed_and_restarted(tmp_path):
    clock = FakeClock()
    hb = str(tmp_path / "hb")

    # First proc never exits on its own (alive_for huge) -> heartbeat goes stale.
    hung = FakeProc(None, alive_for=10**9, clock=clock)
    good = FakeProc(0, clock=clock)
    procs = [hung, good]
    spawned = []

    def spawner(cmd):
        p = procs.pop(0)
        spawned.append(p)
        return p

    def sleeper(dt):
        clock.advance(dt)
        # Do NOT touch heartbeat: simulate the app being hung.

    sup = Supervisor(cmd=["fake"], heartbeat_path=hb, policy=RestartPolicy(),
                     spawner=spawner, clock=clock, sleeper=sleeper)
    # Pre-touch so the first watch has a valid starting heartbeat.
    touch_heartbeat(hb)
    rc = sup.run()
    assert rc == 0
    assert spawned[0].killed is True
    assert sup.restart_count == 1


def test_backoff_sleeps_between_restarts(tmp_path):
    clock = FakeClock()
    procs = [FakeProc(1, clock=clock), FakeProc(0, clock=clock)]
    sup, spawned, sleeps = _make_supervisor(tmp_path, procs, clock)
    rc = sup.run()
    assert rc == 0
    # Backoff is chunked into <=0.5s slices so the supervisor stays responsive;
    # the total slept should be at least the base backoff (2s).
    assert sum(sleeps) >= 2.0
