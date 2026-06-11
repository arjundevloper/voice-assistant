"""
system/windows.py — Window management for Emi OS v5.
Full support: minimize, maximize, restore, move, resize, focus, alt-tab,
screenshot, clipboard, and close-last-focused-app tracking.
"""
from __future__ import annotations

import ctypes
import datetime
import logging
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pyautogui
import pygetwindow as gw

logger = logging.getLogger(__name__)

# Win32 constants
user32   = ctypes.windll.user32
psapi    = ctypes.windll.psapi
kernel32 = ctypes.windll.kernel32

WM_CLOSE = 0x0010

# Class names that belong to the Windows shell — never close these
_SHELL_CLASSES = {
    "Shell_TrayWnd",       # taskbar
    "DV2ControlHost",      # start menu
    "Windows.UI.Core.CoreWindow",  # immersive shell
    "Progman",             # desktop "Program Manager"
    "WorkerW",             # desktop wallpaper worker
    "Button",              # Start button
}

_NOWIN: dict = {}
if sys.platform == "win32":
    _NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW}


def _get_hwnd_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _get_foreground_exe() -> str | None:
    """Return the .exe filename of the currently focused process."""
    try:
        hwnd = user32.GetForegroundWindow()
        pid  = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x0400 | 0x0010, False, pid.value)
        if not h:
            return None
        buf = (ctypes.c_char * 260)()
        psapi.GetModuleFileNameExA(h, None, buf, ctypes.sizeof(buf))
        kernel32.CloseHandle(h)
        exe_path = buf.value.decode("utf-8", errors="ignore")
        return Path(exe_path).name if exe_path else None
    except Exception as exc:
        logger.debug("_get_foreground_exe failed: %s", exc)
        return None


def _safe_close_hwnd(hwnd: int) -> None:
    """
    Send WM_CLOSE to a specific window handle.
    This closes only THAT window — it does NOT kill the process.
    Safe for explorer.exe folder windows: the desktop shell keeps running.
    """
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


class WindowController:
    """Controls windows: minimize, maximize, restore, move, resize, focus, screenshot, clipboard."""

    def __init__(self, on_focus_change: Callable[[str, str | None], None] | None = None) -> None:
        self._on_focus_change = on_focus_change

    # ── Window state ──────────────────────────────────────────────────────────

    def minimize(self) -> bool:
        win = self._active()
        if not win:
            return False
        self._notify_focus(win)
        win.minimize()
        logger.info("Minimized: %s", win.title)
        return True

    def maximize(self) -> bool:
        win = self._active()
        if not win:
            return False
        self._notify_focus(win)
        win.maximize()
        logger.info("Maximized: %s", win.title)
        return True

    def restore(self) -> bool:
        win = self._active()
        if not win:
            return False
        self._notify_focus(win)
        win.restore()
        logger.info("Restored: %s", win.title)
        return True

    def alt_tab(self) -> None:
        pyautogui.hotkey("alt", "tab")
        logger.info("Alt+Tab sent")

    # ── Focus by name ─────────────────────────────────────────────────────────

    def focus(self, title_fragment: str) -> bool:
        matches = [w for w in gw.getAllWindows() if title_fragment.lower() in w.title.lower()]
        if not matches:
            logger.warning("No window matching %r", title_fragment)
            return False
        win = matches[0]
        try:
            win.activate()
        except Exception:
            pass
        self._notify_focus(win)
        logger.info("Focused: %s", win.title)
        return True

    def get_active_title(self) -> str | None:
        win = self._active()
        return win.title if win else None

    def get_active_exe(self) -> str | None:
        return _get_foreground_exe()

    # ── Close active window ───────────────────────────────────────────────────

    def close_active(self) -> bool:
        """
        Close the foreground window safely.
        For explorer.exe we send WM_CLOSE to just that HWND so the
        desktop/taskbar shell stays alive (no purple screen).
        For other processes we still use taskkill on the specific PID.
        """
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        cls = _get_hwnd_class(hwnd)
        if cls in _SHELL_CLASSES:
            logger.warning("Refusing to close shell window (%s)", cls)
            return False

        exe = _get_foreground_exe()

        # explorer.exe: close only this window via WM_CLOSE, not the whole process
        if exe and exe.lower() == "explorer.exe":
            _safe_close_hwnd(hwnd)
            logger.info("Sent WM_CLOSE to explorer window (hwnd=%d)", hwnd)
            return True

        # Any other app: kill by PID (safer than by image name — won't hit other instances)
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            result = subprocess.run(
                ["taskkill", "/f", "/pid", str(pid.value)],
                capture_output=True, text=True, **_NOWIN,
            )
            if result.returncode == 0:
                logger.info("Killed pid=%d (%s)", pid.value, exe)
                return True

        # Fallback: pygetwindow close
        win = self._active()
        if win:
            try:
                win.close()
                return True
            except Exception:
                pass
        return False

    # ── Close all non-shell windows ───────────────────────────────────────────

    def close_all_windows(self) -> int:
        """
        Send WM_CLOSE to every visible, non-shell top-level window.
        Returns the number of windows messaged.
        Explorer folder windows are closed safely via WM_CLOSE (no desktop kill).
        """
        closed = 0

        def _enum_callback(hwnd, _):
            nonlocal closed
            if not user32.IsWindowVisible(hwnd):
                return True
            cls = _get_hwnd_class(hwnd)
            if cls in _SHELL_CLASSES:
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            # Skip minimized-to-tray / zero-size windows
            rect = (ctypes.c_long * 4)()
            user32.GetWindowRect(hwnd, rect)
            if rect[2] - rect[0] == 0 and rect[3] - rect[1] == 0:
                return True
            _safe_close_hwnd(hwnd)
            closed += 1
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        user32.EnumWindows(EnumWindowsProc(_enum_callback), 0)
        logger.info("Sent WM_CLOSE to %d windows", closed)
        return closed

    # ── Move / resize ─────────────────────────────────────────────────────────

    def move(self, x: int, y: int) -> bool:
        win = self._active()
        if not win:
            return False
        win.moveTo(x, y)
        logger.info("Moved window to (%d, %d)", x, y)
        return True

    def resize(self, width: int, height: int) -> bool:
        win = self._active()
        if not win:
            return False
        win.resizeTo(width, height)
        logger.info("Resized window to %dx%d", width, height)
        return True

    def move_to_corner(self, corner: str) -> bool:
        """Move window to 'left', 'right', 'top-left', 'top-right', 'center'."""
        win = self._active()
        if not win:
            return False
        sw, sh = pyautogui.size()
        ww, wh = win.width, win.height
        positions = {
            "left":         (0, 0),
            "right":        (sw - ww, 0),
            "top-left":     (0, 0),
            "top-right":    (sw - ww, 0),
            "bottom-left":  (0, sh - wh),
            "bottom-right": (sw - ww, sh - wh),
            "center":       ((sw - ww) // 2, (sh - wh) // 2),
        }
        pos = positions.get(corner.lower())
        if not pos:
            return False
        win.moveTo(*pos)
        return True

    # ── Screenshot ────────────────────────────────────────────────────────────

    def screenshot(self, save_path: str | None = None) -> str:
        if save_path is None:
            desktop = Path.home() / "Desktop"
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(desktop / f"screenshot_{ts}.png")
        img = pyautogui.screenshot()
        img.save(save_path)
        logger.info("Screenshot saved: %s", save_path)
        return save_path

    # ── Clipboard ─────────────────────────────────────────────────────────────

    def get_clipboard(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste()
        except Exception:
            return ""

    def set_clipboard(self, text: str) -> None:
        try:
            import pyperclip
            pyperclip.copy(text)
            logger.info("Clipboard set (%d chars)", len(text))
        except Exception as exc:
            logger.error("set_clipboard failed: %s", exc)

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _active() -> gw.Win32Window | None:
        win = gw.getActiveWindow()
        if not win:
            logger.warning("No active window found")
        return win

    def _notify_focus(self, win) -> None:
        if self._on_focus_change and win:
            exe = _get_foreground_exe()
            self._on_focus_change(win.title, exe)
