"""
system/files.py — File and folder operations for Emi OS v5.
Supports: create, rename, delete, open, move, copy, recycle bin, search.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Common named paths Emi understands
_NAMED_PATHS: dict[str, Path] = {
    "desktop":   Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "downloads": Path.home() / "Downloads",
    "pictures":  Path.home() / "Pictures",
    "music":     Path.home() / "Music",
    "videos":    Path.home() / "Videos",
    "home":      Path.home(),
    "temp":      Path(os.environ.get("TEMP", "C:/Windows/Temp")),
}


class FileController:
    """Create, rename, delete, move, copy, and search files/folders."""

    # ── Folders ───────────────────────────────────────────────────────────────

    def create_folder(self, name: str, parent: Path | str | None = None) -> Path | None:
        base   = self._resolve_parent(parent)
        target = base / name
        try:
            target.mkdir(parents=True, exist_ok=True)
            logger.info("Created folder: %s", target)
            return target
        except OSError as exc:
            logger.error("create_folder failed: %s", exc)
            return None

    def rename_folder(self, old_name: str, new_name: str, parent: Path | str | None = None) -> bool:
        base = self._resolve_parent(parent)
        old  = base / old_name
        new  = base / new_name
        if not old.exists():
            # Try as absolute path
            old = Path(old_name)
        if not old.exists():
            logger.warning("rename: source not found: %s", old_name)
            return False
        try:
            old.rename(new if not new.is_absolute() else new)
            logger.info("Renamed %s → %s", old, new)
            return True
        except OSError as exc:
            logger.error("rename failed: %s", exc)
            return False

    def delete_folder(self, name: str, parent: Path | str | None = None) -> bool:
        base   = self._resolve_parent(parent)
        target = base / name
        if not target.exists():
            target = Path(name)
        if not target.exists():
            logger.warning("delete: not found: %s", name)
            return False
        try:
            shutil.rmtree(target)
            logger.info("Deleted folder: %s", target)
            return True
        except OSError as exc:
            logger.error("delete_folder failed: %s", exc)
            return False

    def open_folder(self, path_str: str) -> bool:
        """Open a folder in Windows Explorer. Understands named shortcuts."""
        path = self._resolve_named(path_str)
        if not path:
            path = Path(path_str).expanduser()
        if not path or not path.exists():
            path = Path.home() / path_str
        if not path.exists():
            logger.warning("open_folder: path not found: %s", path_str)
            return False
        subprocess.Popen(["explorer", str(path)])
        logger.info("Opened folder: %s", path)
        return True

    def open_named(self, name: str) -> bool:
        """Open a named location like 'downloads', 'desktop', 'documents'."""
        path = _NAMED_PATHS.get(name.lower())
        if path and path.exists():
            subprocess.Popen(["explorer", str(path)])
            logger.info("Opened named location: %s → %s", name, path)
            return True
        return False

    # ── Files ─────────────────────────────────────────────────────────────────

    def move(self, src: str, dst: str) -> bool:
        try:
            shutil.move(src, dst)
            logger.info("Moved %s → %s", src, dst)
            return True
        except Exception as exc:
            logger.error("move failed: %s", exc)
            return False

    def copy(self, src: str, dst: str) -> bool:
        try:
            if Path(src).is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            logger.info("Copied %s → %s", src, dst)
            return True
        except Exception as exc:
            logger.error("copy failed: %s", exc)
            return False

    def delete_file(self, path_str: str) -> bool:
        path = Path(path_str)
        if not path.exists():
            path = Path.home() / "Desktop" / path_str
        if not path.exists():
            logger.warning("delete_file: not found: %s", path_str)
            return False
        try:
            path.unlink()
            logger.info("Deleted file: %s", path)
            return True
        except OSError as exc:
            logger.error("delete_file failed: %s", exc)
            return False

    # ── Recycle Bin ───────────────────────────────────────────────────────────

    def open_recycle_bin(self) -> None:
        subprocess.Popen(["explorer", "shell:RecycleBinFolder"])
        logger.info("Opened Recycle Bin")

    def send_to_recycle(self, path_str: str) -> bool:
        """Send a file or folder to the Recycle Bin (requires winshell or send2trash)."""
        try:
            import send2trash  # type: ignore
            send2trash.send2trash(path_str)
            logger.info("Sent to recycle bin: %s", path_str)
            return True
        except ImportError:
            logger.warning("send2trash not installed — install with: pip install send2trash")
            return False
        except Exception as exc:
            logger.error("send_to_recycle failed: %s", exc)
            return False

    # ── Search ────────────────────────────────────────────────────────────────

    def search_files(self, query: str, root: Path | str | None = None,
                     max_results: int = 50) -> list[Path]:
        """Walk *root* (default: home) and return paths whose name contains *query*."""
        search_root = Path(str(root)) if root else Path.home()
        found: list[Path] = []
        try:
            for item in search_root.rglob(f"*{query}*"):
                found.append(item)
                if len(found) >= max_results:
                    break
        except PermissionError:
            pass
        logger.info("File search %r in %s: %d results", query, search_root, len(found))
        return found

    def search_files_fast(self, query: str) -> list[str]:
        """Use Windows 'where' / Everything SDK if available for fast search."""
        try:
            result = subprocess.run(
                ["where", "/r", str(Path.home()), f"*{query}*"],
                capture_output=True, text=True, timeout=10,
            )
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            return lines[:50]
        except Exception:
            return [str(p) for p in self.search_files(query)]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_parent(parent: Path | str | None) -> Path:
        if parent is None:
            return Path.home() / "Desktop"
        if isinstance(parent, str):
            named = _NAMED_PATHS.get(parent.lower())
            return named if named else Path(parent)
        return parent

    @staticmethod
    def _resolve_named(name: str) -> Path | None:
        return _NAMED_PATHS.get(name.lower().strip())
