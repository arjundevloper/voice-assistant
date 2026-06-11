"""
system/desktop.py — Virtual desktop control for Windows 10/11.
Uses keyboard shortcuts and VirtualDesktopAccessor (optional DLL) for switching.
"""
from __future__ import annotations

import ctypes
import logging
from pathlib import Path

import pyautogui

logger = logging.getLogger(__name__)

# Optional: VirtualDesktopAccessor.dll for precise desktop switching
_VDA_PATH = Path(__file__).parent.parent / "assets" / "VirtualDesktopAccessor.dll"


class DesktopController:
    """Controls Windows virtual desktops."""

    def __init__(self) -> None:
        self._vda: ctypes.CDLL | None = None
        if _VDA_PATH.exists():
            try:
                self._vda = ctypes.cdll.LoadLibrary(str(_VDA_PATH))
                logger.info("VirtualDesktopAccessor loaded")
            except OSError as exc:
                logger.warning("VDA load failed: %s — falling back to hotkeys", exc)

    def next_desktop(self) -> None:
        """Switch to the next virtual desktop."""
        pyautogui.hotkey("ctrl", "win", "right")
        logger.info("Switched to next desktop")

    def prev_desktop(self) -> None:
        """Switch to the previous virtual desktop."""
        pyautogui.hotkey("ctrl", "win", "left")
        logger.info("Switched to previous desktop")

    def goto_desktop(self, number: int) -> None:
        """
        Switch to a specific desktop (1-indexed).
        Uses VDA DLL when available, otherwise repeated hotkey presses.
        """
        if number < 1 or number > 10:
            logger.warning("Desktop number %d out of range (1-10)", number)
            return

        if self._vda:
            try:
                self._vda.GoToDesktopNumber(number - 1)
                logger.info("Switched to desktop %d (VDA)", number)
                return
            except Exception as exc:
                logger.error("VDA GoToDesktop failed: %s", exc)

        # Fallback: go to desktop 1 first, then step right
        # There's no native Win API shortcut for absolute desktop number via pyautogui alone
        # so we use ctrl+win+home (if supported) or just step from current position.
        logger.info("Goto desktop %d via hotkeys (approximate)", number)
        # Press ctrl+win+home to go to first desktop (Windows 11)
        pyautogui.hotkey("ctrl", "win", "home")
        import time
        time.sleep(0.2)
        for _ in range(number - 1):
            pyautogui.hotkey("ctrl", "win", "right")
            time.sleep(0.15)
