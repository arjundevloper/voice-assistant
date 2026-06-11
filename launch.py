"""
launch.py — Entry point for Emi OS v4.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOGS_DIR / "emi.log", encoding="utf-8"),
    ],
)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

logger = logging.getLogger("launch")

# On Windows, suppress console windows for any subprocess we spawn.
_NOWIN = {}
if sys.platform == "win32":
    _NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}


def _start_electron() -> subprocess.Popen | None:
    overlay_dir = Path(__file__).parent / "overlay"
    node_modules = overlay_dir / "node_modules"

    if not node_modules.exists():
        logger.warning(
            "node_modules not found. Open a terminal in the overlay/ folder and run:  npm install"
        )
        return None

    # Try 'npm start' first (works without npx on PATH), fall back to npx
    for cmd in (["npm", "start"], ["npx", "electron", "."]):
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(overlay_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=(sys.platform == "win32"),  # needed on Windows for npm
                **_NOWIN,
            )
            logger.info("Electron overlay started with %s (pid=%d)", cmd[0], proc.pid)
            return proc
        except FileNotFoundError:
            continue

    logger.warning(
        "Could not start overlay. Make sure Node.js is installed: https://nodejs.org\n"
        "Then run:  cd overlay && npm install"
    )
    return None


async def _main() -> None:
    from brain.emi_brain import EmiBrain
    brain = EmiBrain()
    await brain.run()


def main() -> None:
    logger.info("=" * 60)
    logger.info("  Emi OS v4 — Starting up")
    logger.info("=" * 60)

    electron_proc = _start_electron()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        if electron_proc:
            electron_proc.terminate()
            logger.info("Electron overlay terminated")


if __name__ == "__main__":
    main()
