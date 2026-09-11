import os
import sys

import pytest

from cyberdeck.supervisor import Supervisor, RestartPolicy


@pytest.fixture()
def counter_path(tmp_path):
    return str(tmp_path / "crash_counter")


def _crash_then_succeed_cmd(counter_path, succeed_on=3):
    code = (
        "import sys, os\n"
        f"p = {counter_path!r}\n"
        "n = int(open(p).read()) if os.path.exists(p) else 0\n"
        "n += 1\n"
        "open(p, 'w').write(str(n))\n"
        f"sys.exit(0 if n >= {succeed_on} else 1)\n"
    )
    return [sys.executable, "-c", code]


def test_real_crash_restart_until_success(tmp_path, counter_path):
    hb = str(tmp_path / "hb")
    policy = RestartPolicy(base_backoff_s=0.05, max_backoff_s=0.1)
    sup = Supervisor(
        cmd=_crash_then_succeed_cmd(counter_path, succeed_on=3),
        heartbeat_path=hb,
        policy=policy,
        heartbeat_poll_s=0.05,
    )
    rc = sup.run()
    assert rc == 0
    assert sup.restart_count == 2
    with open(counter_path) as f:
        assert int(f.read()) == 3


def test_real_circuit_breaker_on_persistent_crash(tmp_path, counter_path):
    hb = str(tmp_path / "hb")
    policy = RestartPolicy(max_rapid_restarts=3, rapid_window_s=60.0,
                           base_backoff_s=0.02, max_backoff_s=0.05)
    sup = Supervisor(
        cmd=_crash_then_succeed_cmd(counter_path, succeed_on=999),  # never succeeds
        heartbeat_path=hb,
        policy=policy,
        heartbeat_poll_s=0.05,
    )
    rc = sup.run()
    assert rc == 1  # handed off to systemd
    # 3 restarts recorded, then the 4th crash trips the breaker.
    with open(counter_path) as f:
        assert int(f.read()) == 4
