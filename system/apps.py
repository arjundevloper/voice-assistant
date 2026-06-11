"""
system/apps.py — Application launcher and manager for Emi OS v5.
Auto-detects installed software, opens/closes by spoken name,
tracks last launched app, and supports "close it" for last focused app.
"""
from __future__ import annotations

import json
import logging
import subprocess
import winreg
from pathlib import Path
from typing import Optional

from config import APPS_PATH

logger = logging.getLogger(__name__)

# Well-known app aliases → executable name or path fragment
_BUILTIN_ALIASES: dict[str, str] = {
    "chrome":              "chrome.exe",
    "google chrome":       "chrome.exe",
    "firefox":             "firefox.exe",
    "mozilla firefox":     "firefox.exe",
    "brave":               "brave.exe",
    "edge":                "msedge.exe",
    "microsoft edge":      "msedge.exe",
    "notepad":             "notepad.exe",
    "calculator":          "calc.exe",
    "calc":                "calc.exe",
    "explorer":            "explorer.exe",
    "file explorer":       "explorer.exe",
    "files":               "explorer.exe",
    "paint":               "mspaint.exe",
    "ms paint":            "mspaint.exe",
    "word":                "winword.exe",
    "microsoft word":      "winword.exe",
    "excel":               "excel.exe",
    "microsoft excel":     "excel.exe",
    "powerpoint":          "powerpnt.exe",
    "outlook":             "outlook.exe",
    "teams":               "teams.exe",
    "microsoft teams":     "teams.exe",
    "discord":             "discord.exe",
    "spotify":             "spotify.exe",
    "vlc":                 "vlc.exe",
    "vlc media player":    "vlc.exe",
    "steam":               "steam.exe",
    "obs":                 "obs64.exe",
    "obs studio":          "obs64.exe",
    "vscode":              "code.exe",
    "visual studio code":  "code.exe",
    "vs code":             "code.exe",
    "terminal":            "wt.exe",
    "windows terminal":    "wt.exe",
    "cmd":                 "cmd.exe",
    "command prompt":      "cmd.exe",
    "powershell":          "powershell.exe",
    "task manager":        "taskmgr.exe",
    "snipping tool":       "SnippingTool.exe",
    "snip":                "SnippingTool.exe",
    "winrar":              "WinRAR.exe",
    "7zip":                "7zFM.exe",
    "seven zip":           "7zFM.exe",
    "zoom":                "zoom.exe",
    "slack":               "slack.exe",
    "telegram":            "telegram.exe",
    "whatsapp":            "whatsapp.exe",
    "epic games":          "EpicGamesLauncher.exe",
    "epic":                "EpicGamesLauncher.exe",
    "nvidia":              "NVIDIA Share.exe",
    "geforce":             "NVIDIA Share.exe",
    "afterburner":         "MSIAfterburner.exe",
    "taskmgr":             "taskmgr.exe",
}

# Additional Start Menu scan paths
_START_MENU_DIRS = [
    Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
]


class AppManager:
    """
    Manages app launching and closing by spoken name.
    Loads and persists a user-customised app registry in apps.json.
    Auto-detects installed software from the registry and Start Menu.
    """

    def __init__(self) -> None:
        self._registry: dict[str, str] = {}
        self._load()
        self._detect_installed()

    # ── Public API ─────────────────────────────────────────────────────────────

    def open(self, spoken_name: str) -> tuple[bool, str | None]:
        """
        Launch an app by spoken name.
        Returns (success, exe_name_used).
        """
        key = spoken_name.lower().strip()
        exe = self._registry.get(key) or _BUILTIN_ALIASES.get(key)

        # Fuzzy fallback: substring match in registry
        if not exe:
            for reg_key, reg_exe in self._registry.items():
                if key in reg_key or reg_key in key:
                    exe = reg_exe
                    break

        if not exe:
            logger.warning("Unknown app: %r", spoken_name)
            return False, None
        try:
            subprocess.Popen([exe], shell=True)
            logger.info("Opened app: %r (%s)", spoken_name, exe)
            return True, Path(exe).name
        except Exception as exc:
            logger.error("Failed to open %r: %s", exe, exc)
            return False, None

    def close(self, spoken_name: str) -> bool:
        """Kill a process by spoken name. Returns True if at least one killed."""
        key = spoken_name.lower().strip()
        exe = self._registry.get(key) or _BUILTIN_ALIASES.get(key)

        if not exe:
            for reg_key, reg_exe in self._registry.items():
                if key in reg_key or reg_key in key:
                    exe = reg_exe
                    break

        if not exe:
            logger.warning("Unknown app to close: %r", spoken_name)
            return False
        return self.close_by_exe(Path(exe).name)

    def close_by_exe(self, exe_name: str) -> bool:
        """Kill a process directly by executable filename."""
        result = subprocess.run(
            ["taskkill", "/f", "/im", exe_name],
            capture_output=True, text=True,
        )
        success = result.returncode == 0
        if success:
            logger.info("Closed: %s", exe_name)
        else:
            logger.warning("Could not close %s: %s", exe_name, result.stderr.strip())
        return success

    def register(self, spoken_name: str, exe_path: str) -> None:
        """Add a custom app mapping and persist it."""
        self._registry[spoken_name.lower()] = exe_path
        self._save()

    def list_apps(self) -> dict[str, str]:
        return dict(self._registry)

    def get_exe(self, spoken_name: str) -> str | None:
        key = spoken_name.lower().strip()
        return self._registry.get(key) or _BUILTIN_ALIASES.get(key)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if APPS_PATH.exists():
            try:
                data = json.loads(APPS_PATH.read_text(encoding="utf-8"))
                self._registry = data.get("apps", {})
                logger.info("Loaded %d app entries", len(self._registry))
            except json.JSONDecodeError as exc:
                logger.error("apps.json corrupt: %s", exc)

    def _save(self) -> None:
        APPS_PATH.parent.mkdir(parents=True, exist_ok=True)
        APPS_PATH.write_text(
            json.dumps({"apps": self._registry}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _detect_installed(self) -> None:
        """Scan Windows Registry + Start Menu for installed apps."""
        found: dict[str, str] = {}

        # 1. Registry App Paths
        reg_keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key_path in reg_keys:
                try:
                    with winreg.OpenKey(root, key_path) as base:
                        i = 0
                        while True:
                            try:
                                subkey_name = winreg.EnumKey(base, i)
                                i += 1
                                with winreg.OpenKey(base, subkey_name) as sub:
                                    try:
                                        exe_path, _ = winreg.QueryValueEx(sub, "")
                                        alias = Path(subkey_name).stem.lower()
                                        if alias and exe_path:
                                            found[alias] = exe_path
                                    except OSError:
                                        pass
                            except OSError:
                                break
                except OSError:
                    pass

        # 2. Start Menu .lnk files — extract display names
        for start_dir in _START_MENU_DIRS:
            if start_dir.exists():
                for lnk in start_dir.rglob("*.lnk"):
                    alias = lnk.stem.lower()
                    if alias not in found and alias not in self._registry:
                        # Store .lnk path — shell=True can run it directly
                        found[alias] = str(lnk)

        added = 0
        for alias, path in found.items():
            if alias not in self._registry:
                self._registry[alias] = path
                added += 1

        if added:
            self._save()
            logger.info("Auto-detected %d installed apps", added)
