"""
Crash-resilient supervisor for the Cyberdeck OS.

The app keeps all of its hardware/UI state in module-level singletons
(wifi_node socket, nano_accessories threads, the cached screens, etc.), so a
crash cannot be safely recovered *inside* the process. Instead the supervisor
runs the app as a child process and respawns it fresh on failure. Because the
supervisor itself is the xinit client, the X server stays up across restarts
and the wearer never sees a blank screen for more than a moment.

Recovery model
--------------
* child exits 0            -> intentional shutdown, supervisor exits 0
* child exits non-zero     -> crash, respawn after exponential backoff
* child alive but heartbeat
  goes stale               -> hang, SIGKILL + respawn
* too many rapid restarts  -> circuit breaker opens, supervisor exits 1 so
                              systemd (Restart=on-failure) can do a full reset
"""

import os
import signal
import subprocess
import sys
import time

DEFAULT_HEARTBEAT_PATH = os.environ.get(
    "CYBERDECK_HEARTBEAT", os.path.join("/tmp", "cyberdeck.heartbeat")
)

# Repo root = parent of the package directory this file lives in. Used as the
# child's working directory so `python -m cyberdeck.main` always resolves.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_spawner(cmd):
    # PYTHONUNBUFFERED makes the child's logs stream straight to journald,
    # which is how a wearer debugs the suit at a convention.
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(cmd, cwd=REPO_ROOT, env=env)

# Seconds of heartbeat silence before we declare the app hung. Doubles as the
# boot grace period because the supervisor touches the file just before spawn.
HEARTBEAT_TIMEOUT_S = 25.0
HEARTBEAT_POLL_S = 2.0
# A run longer than this is considered healthy, so its failure resets backoff.
HEALTHY_RUN_S = 30.0


class RestartPolicy:
    """Pure decision logic for when/how to restart. Fully unit-testable."""

    def __init__(self, max_rapid_restarts=5, rapid_window_s=60.0,
                 base_backoff_s=2.0, max_backoff_s=30.0):
        self.max_rapid_restarts = max_rapid_restarts
        self.rapid_window_s = rapid_window_s
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self._restart_times = []
        self._consecutive = 0

    def _prune(self, now):
        cutoff = now - self.rapid_window_s
        self._restart_times = [t for t in self._restart_times if t >= cutoff]

    def record_restart(self, now):
        self._consecutive += 1
        self._prune(now)
        self._restart_times.append(now)

    def record_healthy_run(self):
        self._consecutive = 0
        self._restart_times = []

    def backoff_seconds(self):
        exponent = max(0, self._consecutive - 1)
        return min(self.max_backoff_s, self.base_backoff_s * (2 ** exponent))

    def circuit_open(self, now=None):
        if now is not None:
            self._prune(now)
        return len(self._restart_times) >= self.max_rapid_restarts


def touch_heartbeat(path=DEFAULT_HEARTBEAT_PATH, now=None):
    """Write the current timestamp into the heartbeat file.

    The app calls this ~once per second from its main loop. The timestamp is
    stored as the file's *content* (not its mtime) so the supervisor and the
    app always agree on the time base, even across a fake/injected clock.
    """
    now = time.time() if now is None else now
    try:
        with open(path, "w") as f:
            f.write(f"{now:.3f}")
    except OSError:
        pass


def heartbeat_age(path, now=None):
    now = time.time() if now is None else now
    try:
        with open(path) as f:
            ts = float(f.read().strip())
        return now - ts
    except (OSError, ValueError):
        return float("inf")


class Supervisor:
    def __init__(self, cmd=None, heartbeat_path=DEFAULT_HEARTBEAT_PATH,
                 policy=None, spawner=None, clock=None, sleeper=None,
                 heartbeat_poll_s=HEARTBEAT_POLL_S):
        self.cmd = cmd or [sys.executable, "-m", "cyberdeck.main"]
        self.heartbeat_path = heartbeat_path
        self.policy = policy or RestartPolicy()
        self.heartbeat_poll_s = heartbeat_poll_s
        # Injectable seams for testing.
        self._spawner = spawner or _default_spawner
        self._clock = clock or time.time
        self._sleeper = sleeper or time.sleep
        self._stopping = False
        self.restart_count = 0

    # -- signal handling ----------------------------------------------------
    def _install_signal_handlers(self):
        def _stop(signum, frame):
            self._stopping = True
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

    def _terminate_child(self, proc, timeout=5.0):
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=timeout)
            except Exception:
                try:
                    proc.kill()
                except OSError:
                    pass

    # -- main loop ----------------------------------------------------------
    def run(self, max_iterations=None):
        """Run the app forever (or up to max_iterations for tests).

        Returns the final exit code the supervisor itself should report.
        """
        self._install_signal_handlers()
        iterations = 0
        while not self._stopping:
            if max_iterations is not None and iterations >= max_iterations:
                return 0
            iterations += 1

            # Fresh heartbeat gives the child a full timeout to finish booting.
            touch_heartbeat(self.heartbeat_path, self._clock())
            spawned_at = self._clock()
            proc = self._spawner(self.cmd)

            exit_code = self._watch(proc)

            if self._stopping:
                # We were asked to stop; make sure the child is gone.
                self._terminate_child(proc)
                return 0

            lifetime = self._clock() - spawned_at
            if exit_code == 0:
                # Intentional shutdown (user halt / SIGTERM forwarded).
                return 0

            if lifetime >= HEALTHY_RUN_S:
                self.policy.record_healthy_run()

            if self.policy.circuit_open(self._clock()):
                print("[SUPERVISOR] Restart circuit breaker open; handing off "
                      "to systemd for a full reset.", flush=True)
                return 1

            self.policy.record_restart(self._clock())
            self.restart_count += 1
            delay = self.policy.backoff_seconds()
            print(f"[SUPERVISOR] App exited with code {exit_code} after "
                  f"{lifetime:.1f}s. Restart #{self.restart_count} in "
                  f"{delay:.1f}s.", flush=True)
            self._sleep_interruptible(delay)

        return 0

    def _watch(self, proc):
        """Block until the child exits, killing it if it hangs."""
        while True:
            if self._stopping:
                self._terminate_child(proc)
                return proc.wait()

            code = proc.poll()
            if code is not None:
                return code

            if heartbeat_age(self.heartbeat_path, self._clock()) > HEARTBEAT_TIMEOUT_S:
                print("[SUPERVISOR] Heartbeat stale; app appears hung. "
                      "Killing for restart.", flush=True)
                try:
                    proc.kill()
                except OSError:
                    pass
                return proc.wait()

            self._sleeper(self.heartbeat_poll_s)

    def _sleep_interruptible(self, total):
        end = self._clock() + total
        while not self._stopping:
            remaining = end - self._clock()
            if remaining <= 0:
                return
            self._sleeper(min(0.5, remaining))


def run_forever():
    return Supervisor().run()


if __name__ == "__main__":
    sys.exit(run_forever())
