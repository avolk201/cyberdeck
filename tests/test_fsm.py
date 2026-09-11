from cyberdeck.config import State
from cyberdeck.fsm import CyberdeckFSM


def _fsm_with_log():
    fsm = CyberdeckFSM()
    log = []
    fsm.register_listener(lambda s: log.append(s))
    return fsm, log


def test_initial_state_is_boot():
    fsm = CyberdeckFSM()
    assert fsm.state == State.BOOT


def test_boot_complete_goes_idle():
    fsm, log = _fsm_with_log()
    fsm.boot_complete()
    assert fsm.state == State.IDLE
    assert log == [State.IDLE]


def test_boot_complete_only_from_boot():
    fsm, log = _fsm_with_log()
    fsm.boot_complete()
    fsm.boot_complete()  # already IDLE -> no-op
    assert fsm.state == State.IDLE
    assert log == [State.IDLE]


def test_scan_from_idle_and_running_only():
    fsm, _ = _fsm_with_log()
    fsm.boot_complete()
    fsm.trigger_scan()
    assert fsm.state == State.SCANNING

    fsm2, _ = _fsm_with_log()
    fsm2.boot_complete()
    fsm2.trigger_run()
    fsm2.trigger_scan()
    assert fsm2.state == State.SCANNING

    fsm3, _ = _fsm_with_log()
    fsm3.trigger_scan()  # from BOOT -> ignored
    assert fsm3.state == State.BOOT


def test_run_from_idle_and_scanning():
    fsm, _ = _fsm_with_log()
    fsm.boot_complete()
    fsm.trigger_run()
    assert fsm.state == State.RUNNING

    fsm2, _ = _fsm_with_log()
    fsm2.boot_complete()
    fsm2.trigger_scan()
    fsm2.trigger_run()
    assert fsm2.state == State.RUNNING


def test_alert_resolves_to_cooldown_then_idle():
    fsm, _ = _fsm_with_log()
    fsm.boot_complete()
    fsm.trigger_alert()
    assert fsm.state == State.ALERT
    fsm.resolve_alert()
    assert fsm.state == State.COOLDOWN
    fsm.cooldown_complete()
    assert fsm.state == State.IDLE


def test_blackout_and_wake():
    fsm, _ = _fsm_with_log()
    fsm.boot_complete()
    fsm.trigger_blackout()
    assert fsm.state == State.BLACKOUT
    fsm.wake_from_blackout()
    assert fsm.state == State.BOOT


def test_target_lock_flow():
    fsm, _ = _fsm_with_log()
    fsm.boot_complete()
    fsm.trigger_target_lock()
    assert fsm.state == State.TARGET_LOCK
    fsm.launch_counter_attack()
    assert fsm.state == State.RUNNING


def test_finish_run_returns_idle():
    fsm, _ = _fsm_with_log()
    fsm.boot_complete()
    fsm.trigger_run()
    fsm.finish_run()
    assert fsm.state == State.IDLE


def test_transition_no_notify_on_same_state():
    fsm, log = _fsm_with_log()
    fsm.transition(State.BOOT)  # already BOOT
    assert log == []


def test_multiple_listeners_all_notified():
    fsm = CyberdeckFSM()
    a, b = [], []
    fsm.register_listener(lambda s: a.append(s))
    fsm.register_listener(lambda s: b.append(s))
    fsm.boot_complete()
    assert a == [State.IDLE]
    assert b == [State.IDLE]
