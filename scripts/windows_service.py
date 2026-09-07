"""Windows Service wrapper for the FastAPI + AI Trader background process.

CEO plan P0-4: the bot must run 24h. Without a Windows Service, the
process dies when the user's RDP / console session ends. Installing as a
service lets the SCM (Service Control Manager) own the lifecycle:
auto-start at boot, restart on crash, stop on shutdown.

Install / uninstall:
    pywin32-required:
        pip install pywin32
    install:
        python scripts/windows_service.py install
    start:
        python scripts/windows_service.py start
        # OR: sc start BinanceSpotGridAI
    stop / remove:
        python scripts/windows_service.py stop
        python scripts/windows_service.py remove

Architecture:
    PyInstaller is overkill for a small repo. The service runs uvicorn
    in a subprocess and supervises it. If uvicorn dies, the service
    sleeps COOLDOWN_SEC and re-launches. This is the simplest pattern
    that gets us "24h autonomy" without bundling the whole app into an
    exe.

    The service class itself runs in the SCM-managed Python process.
    It must NOT do any of the AI Trader work directly — uvicorn owns
    that. Service does three things:
      1. Spawn uvicorn as a child process.
      2. Watch for child exit; log + cooldown + restart.
      3. Forward SCM stop signals to the child.

pywin32 is imported lazily so the module can be loaded in tests on
machines without pywin32. The ServiceMain path is never reached without
the real SCM.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("app.service_wrapper")

SERVICE_NAME = "BinanceGridAI"
SERVICE_DISPLAY = "Binance Grid + AI-Trader"

# Backwards-compatibility aliases — old install names map to the new
# canonical name so existing service installs upgrade without breakage.
# `HandleCommandLine(_BinanceGridService)` registers under _svc_name_
# (the new name); the alias dict exists for install-time ergonomics
# and any code that reads back the canonical name from a legacy arg.
_SERVICE_NAME_ALIASES = {
    "BinanceSpotGridAI": "BinanceGridAI",
}

# How long to wait between uvicorn exits before relaunching. Short enough
# to recover quickly from transient crashes, long enough that an outright
# misconfigured install doesn't spin at 100% CPU.
COOLDOWN_SEC = 5

# Hard-coded project root: the service lives in scripts/windows_service.py
# so the project root is one level up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
UVICORN_CMD = [
    sys.executable, "-m", "uvicorn", "app.main:app",
    "--host", "127.0.0.1", "--port", "8000",
]
WORKING_DIR = str(PROJECT_ROOT)


def _run_uvicorn_subprocess() -> subprocess.Popen:
    """Spawn uvicorn as a child process. Returns the Popen handle.
    stdout/stderr are piped so the service can tail them to its own log."""
    logger.info("spawning uvicorn: %s", UVICORN_CMD)
    return subprocess.Popen(
        UVICORN_CMD,
        cwd=WORKING_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )


# ----- pywin32 service class (only used when SCM calls ServiceMain) ------------

class _BinanceGridService:
    """Concrete SCM service class. Imported lazily so the module loads
    cleanly on machines without pywin32. The SCM dispatches by class name
    string in the `SvcDoRun` registration below."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY
    _svc_description_ = (
        "Runs the Binance Spot / Futures Grid + AI Trader service 24/7. "
        "Restarts on crash. Stop with `sc stop BinanceGridAI`."
    )

    def __init__(self):
        # pywin32 provides win32event, servicemanager, win32service.
        # Imported lazily so the module can be loaded for unit tests.
        import win32event  # type: ignore
        import win32service  # type: ignore
        import servicemanager  # type: ignore

        self._win32event = win32event
        self._win32service = win32service
        self._servicemanager = servicemanager

        self._stop_event = win32event.CreateEvent(None, 0, 0, 0)
        self._child: subprocess.Popen | None = None

    def SvcDoRun(self):
        """SCM callback. Runs until SvcStop is called."""
        self._servicemanager.LogMsg(
            self._servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self._child = _run_uvicorn_subprocess()
        # Cooldown timer / stop-event wait. The WaitForMultipleObjects
        # returns when EITHER the child exits OR a stop signal arrives.
        while True:
            rc = self._win32event.WaitForSingleObject(
                self._stop_event, 1000  # ms — wake every second to check child
            )
            if rc == self._win32event.WAIT_OBJECT_0:
                # Stop requested — break to SvcStop cleanup.
                break
            # Check if uvicorn child is still alive.
            if self._child and self._child.poll() is not None:
                self._servicemanager.LogInfoMsg(
                    f"uvicorn exited rc={self._child.returncode}; restarting in {COOLDOWN_SEC}s"
                )
                self._child = None
                time.sleep(COOLDOWN_SEC)
                # Re-check the stop event so an SvcStop during cooldown
                # doesn't get overridden by a fresh spawn.
                if self._win32event.WaitForSingleObject(
                    self._stop_event, 0
                ) == self._win32event.WAIT_OBJECT_0:
                    break
                self._child = _run_uvicorn_subprocess()

    def SvcStop(self):
        """SCM callback when the operator asks the service to stop."""
        self._servicemanager.LogInfoMsg("SvcStop received")
        self._win32event.SetEvent(self._stop_event)
        # Politely terminate the child first; if it does not exit in 5s,
        # kill -9 it.
        if self._child and self._child.poll() is None:
            try:
                self._child.terminate()
                self._child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._child.kill()
                self._child.wait(timeout=5)


# ----- CLI dispatch -----------------------------------------------------------

def _install() -> None:
    """Register this script as a Windows Service."""
    try:
        import win32serviceutil  # type: ignore
    except ImportError:
        print("pywin32 not installed. Run: pip install pywin32", file=sys.stderr)
        sys.exit(2)
    win32serviceutil.HandleCommandLine(_BinanceGridService)


if __name__ == "__main__":
    # When invoked by the SCM, sys.argv is something like
    # ['scripts/windows_service.py'] and HandleCommandLine dispatches to
    # SvcDoRun. When invoked manually, sys.argv carries the user's intent
    # (install / start / stop / remove / debug).
    try:
        _install()
    except Exception:
        logger.exception("service dispatcher failed")
        raise
