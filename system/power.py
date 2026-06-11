"""
system/power.py — Power management for Emi OS v4.
Lock, sleep, restart, shutdown — all via subprocess / ctypes.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_NOWIN: dict = {}
if sys.platform == "win32":
    _NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}


class PowerController:
    """Manages Windows power actions."""

    def lock(self) -> None:
        """Lock the workstation immediately."""
        ctypes.windll.user32.LockWorkStation()
        logger.info("Workstation locked")

    def sleep(self) -> None:
        """Put the system to sleep."""
        subprocess.run(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            check=False, **_NOWIN,
        )
        logger.info("Sleep initiated")

    def restart(self, delay: int = 0) -> None:
        """Restart Windows. delay in seconds."""
        subprocess.run(
            ["shutdown", "/r", "/t", str(delay)],
            check=False, **_NOWIN,
        )
        logger.info("Restart initiated (delay=%ds)", delay)

    def shutdown(self, delay: int = 0) -> None:
        """Shut down Windows. delay in seconds."""
        subprocess.run(
            ["shutdown", "/s", "/t", str(delay)],
            check=False, **_NOWIN,
        )
        logger.info("Shutdown initiated (delay=%ds)", delay)

    def abort_shutdown(self) -> None:
        """Cancel a pending shutdown or restart."""
        subprocess.run(["shutdown", "/a"], check=False, **_NOWIN)
        logger.info("Shutdown aborted")
