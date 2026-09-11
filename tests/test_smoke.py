import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(cmd, seconds):
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"
    env["PYTHONUNBUFFERED"] = "1"
    env["CYBERDECK_HEARTBEAT"] = os.path.join(REPO_ROOT, ".test_heartbeat")
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(seconds)
    alive = proc.poll() is None
    if alive:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    else:
        out, _ = proc.communicate()
    return alive, out


def test_app_boots_and_reaches_idle():
    """Run the app directly (unsupervised) and verify it boots to IDLE."""
    alive, out = _run([sys.executable, "-m", "cyberdeck.main"], 12)
    assert alive, f"App exited early. Output:\n{out}"
    assert "Cyberdeck OS started" in out, f"Missing startup banner. Output:\n{out}"
    assert "BOOT -> IDLE" in out, f"Boot did not advance to IDLE. Output:\n{out}"
    assert "Traceback" not in out, f"Traceback during boot:\n{out}"


def test_supervised_app_boots_and_heartbeats():
    """Run the supervised entry point and verify the child boots + heartbeats."""
    hb = os.path.join(REPO_ROOT, ".test_heartbeat")
    if os.path.exists(hb):
        os.remove(hb)
    alive, out = _run([sys.executable, "run.py"], 12)
    assert alive, f"Supervisor exited early. Output:\n{out}"
    assert "Cyberdeck OS started" in out, f"Child did not boot. Output:\n{out}"
    assert "Traceback" not in out, f"Traceback under supervisor:\n{out}"
    # Heartbeat must exist and be recent (app is alive and petting it).
    assert os.path.exists(hb), "Heartbeat file was never created"
    age = time.time() - os.path.getmtime(hb)
    assert age < 10.0, f"Heartbeat stale ({age:.1f}s); app not petting it"
