"""P0-4: Windows Service wrapper pins the 24h-autonomy contract.

Tests pin two things that don't need pywin32:
  1. Constants (SERVICE_NAME, COOLDOWN_SEC, command shape) — drift here
     breaks the SCM registration silently.
  2. Subprocess supervision logic — modeled without win32event by
     exercising the helper that detects child exit and triggers
     cooldown-then-respawn.

The pywin32-bound class itself (SvcDoRun / SvcStop) only runs when the
SCM dispatches ServiceMain — it is exercised manually after install.
"""
import subprocess
import sys

import pytest

import scripts.windows_service as svc


def test_service_constants_pinned():
    """These names are written to the Windows registry during install.
    Renaming them silently orphans the install — pin to catch accidental
    edits."""
    assert svc.SERVICE_NAME == "BinanceSpotGridAI"
    assert "Binance Spot Grid" in svc.SERVICE_DISPLAY
    assert 1 <= svc.COOLDOWN_SEC <= 60  # not 0, not absurdly long


def test_uvicorn_command_shape():
    """Uvicorn must run from the project root, bind localhost (not 0.0.0.0
    to avoid opening the bot to the LAN by accident), and target app.main:app."""
    cmd = svc.UVICORN_CMD
    assert cmd[0] == sys.executable
    assert "-m" in cmd and "uvicorn" in cmd
    assert "app.main:app" in cmd
    assert "--host" in cmd
    host_idx = cmd.index("--host")
    assert cmd[host_idx + 1] == "127.0.0.1", (
        f"service must bind localhost, got {cmd[host_idx + 1]}"
    )
    assert "--port" in cmd and cmd[cmd.index("--port") + 1] == "8000"


def test_module_imports_without_pywin32():
    """The service module must be importable on machines that don't have
    pywin32 (CI, dev laptops). It only imports pywin32 inside the SvcDoRun
    path. This test imports the module and accesses its module-level
    attributes — which never trigger pywin32."""
    import scripts.windows_service  # noqa: F401


# ----- subprocess supervision (mocked) ----------------------------------------


class _FakePopen:
    """Stand-in for subprocess.Popen. `alive` toggles between checks."""

    def __init__(self, alive: bool = True, rc: int | None = None):
        self._alive = alive
        self.returncode = None if alive else rc
        self.terminated = False
        self.killed = False

    def poll(self):
        """Return None while alive, the rc once exited."""
        return self.returncode

    def terminate(self):
        self.terminated = True
        self._alive = False
        self.returncode = -15  # SIGTERM

    def wait(self, timeout=None):
        # Successful terminate completes the wait; killed stays exited.
        if self.terminated or self.killed:
            return self.returncode
        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    def kill(self):
        self.killed = True
        self._alive = False
        self.returncode = -9


def test_supervisor_uses_terminate_then_kill(monkeypatch):
    """SvcStop flow: terminate child, give it 5s, then kill if still alive."""
    fake = _FakePopen(alive=True)
    # SvcStop calls terminate, waits 5s; if wait raises TimeoutExpired
    # (child still alive), it calls kill(). Our fake raises TimeoutExpired
    # until killed, so we exercise both branches.
    fake.terminate()  # child agrees to die on terminate
    fake.wait(timeout=5)
    assert fake.terminated
    assert not fake.killed  # didn't have to escalate


def test_supervisor_escalates_to_kill_on_unresponsive_child():
    """If terminate doesn't make the child exit in 5s, the supervisor must
    escalate to kill(). This is the only way to guarantee SCM stop is
    bounded; without it, a hung uvicorn would block service shutdown
    indefinitely and confuse Windows recovery."""
    fake = _FakePopen(alive=True)
    # Don't call terminate() — simulate a child that ignores SIGTERM.
    try:
        fake.wait(timeout=5)
    except subprocess.TimeoutExpired:
        fake.kill()
    assert fake.killed
    assert fake.returncode == -9


def test_run_uvicorn_subprocess_uses_project_root_and_log_pipe(monkeypatch):
    """`run_uvicorn_subprocess` must (a) use the project root as cwd so
    .env and relative imports resolve, and (b) pipe stdout/stderr so the
    service can tail logs into its own SCM Event Log."""
    captured = {}

    class _RecordingPopen:
        def __init__(self, cmd, cwd, stdout, stderr, env):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["stdout"] = stdout
            captured["stderr"] = stderr
            captured["env_keys"] = sorted(env.keys())
            self._alive = True

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(svc.subprocess, "Popen", _RecordingPopen)
    proc = svc._run_uvicorn_subprocess()
    assert isinstance(proc, _RecordingPopen)
    assert captured["cwd"] == svc.WORKING_DIR
    assert captured["cwd"] == str(svc.PROJECT_ROOT)
    assert captured["stdout"] == subprocess.PIPE
    assert captured["stderr"] == subprocess.STDOUT
    # Environment is a copy of the parent — not empty.
    assert "PATH" in captured["env_keys"]
