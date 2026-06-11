"""
brain/memory.py — Emi OS v6 persistent memory.
New: clipboard_history, timers list, routines, debounced save.
"""
from __future__ import annotations
import json, logging, threading
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from config import MEMORY_PATH

logger = logging.getLogger(__name__)
MAX_CTX = 120
MAX_CLIP = 10


@dataclass
class MemoryState:
    last_app: str | None                       = None
    last_app_exe: str | None                   = None
    last_focused_app: str | None               = None
    last_focused_exe: str | None               = None
    last_website: str | None                   = None
    last_search_query: str | None              = None
    last_command: str | None                   = None
    current_outfit: str                        = "default"
    conversation_context: list[dict]           = field(default_factory=list)
    clipboard_history: list[str]               = field(default_factory=list)
    user_preferences: dict[str, Any]           = field(default_factory=dict)
    last_session_summary: str                  = ""
    total_sessions: int                        = 0


class MemoryManager:
    def __init__(self) -> None:
        self._state = MemoryState()
        self._save_timer: threading.Timer | None = None
        self.load()

    # ── Persistence (debounced) ───────────────────────────────────────────────
    def load(self) -> None:
        if not MEMORY_PATH.exists():
            return
        try:
            raw = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            self._state = MemoryState(
                last_app            = raw.get("last_app"),
                last_app_exe        = raw.get("last_app_exe"),
                last_focused_app    = raw.get("last_focused_app"),
                last_focused_exe    = raw.get("last_focused_exe"),
                last_website        = raw.get("last_website"),
                last_search_query   = raw.get("last_search_query"),
                last_command        = raw.get("last_command"),
                current_outfit      = raw.get("current_outfit", "default"),
                conversation_context= raw.get("conversation_context", []),
                clipboard_history   = raw.get("clipboard_history", []),
                user_preferences    = raw.get("user_preferences", {}),
                last_session_summary= raw.get("last_session_summary", ""),
                total_sessions      = raw.get("total_sessions", 0),
            )
            logger.info("Memory loaded (%d ctx, %d clips)", len(self._state.conversation_context),
                        len(self._state.clipboard_history))
        except Exception as e:
            logger.error("Memory load failed: %s", e)

    def save(self) -> None:
        """Debounced save — writes at most once per 2 seconds."""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(2.0, self._do_save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _do_save(self) -> None:
        try:
            MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            MEMORY_PATH.write_text(json.dumps(asdict(self._state), indent=2, ensure_ascii=False), "utf-8")
        except Exception as e:
            logger.error("Memory save failed: %s", e)

    def force_save(self) -> None:
        if self._save_timer:
            self._save_timer.cancel()
        self._do_save()

    # ── Conversation ──────────────────────────────────────────────────────────
    def add_exchange(self, role: str, content: str) -> None:
        self._state.conversation_context.append({"role": role, "content": content})
        if len(self._state.conversation_context) > MAX_CTX:
            self._state.conversation_context = self._state.conversation_context[-MAX_CTX:]
        self.save()

    def get_context(self) -> list[dict]:
        return list(self._state.conversation_context)

    def clear_context(self) -> None:
        self._state.conversation_context = []
        self.save()

    # ── Last command (for repeat) ─────────────────────────────────────────────
    @property
    def last_command(self) -> str | None:
        return self._state.last_command

    def set_last_command(self, cmd: str) -> None:
        self._state.last_command = cmd
        self.save()

    # ── App tracking ──────────────────────────────────────────────────────────
    @property
    def last_app(self) -> str | None: return self._state.last_app
    @property
    def last_app_exe(self) -> str | None: return self._state.last_app_exe

    def set_last_app(self, name: str, exe: str | None = None) -> None:
        self._state.last_app = name
        if exe: self._state.last_app_exe = exe
        self.save()

    def set_last_focused(self, title: str, exe: str | None = None) -> None:
        self._state.last_focused_app = title
        if exe: self._state.last_focused_exe = exe
        self.save()

    @property
    def last_focused_app(self) -> str | None: return self._state.last_focused_app
    @property
    def last_focused_exe(self) -> str | None: return self._state.last_focused_exe

    # ── Website ───────────────────────────────────────────────────────────────
    @property
    def last_website(self) -> str | None: return self._state.last_website

    @last_website.setter
    def last_website(self, v: str | None) -> None:
        self._state.last_website = v
        self.save()

    def set_last_search(self, q: str) -> None:
        self._state.last_search_query = q
        self.save()

    # ── Clipboard history ─────────────────────────────────────────────────────
    def push_clipboard(self, text: str) -> None:
        if not text: return
        hist = self._state.clipboard_history
        if hist and hist[0] == text: return   # dedup
        hist.insert(0, text)
        if len(hist) > MAX_CLIP:
            self._state.clipboard_history = hist[:MAX_CLIP]
        self.save()

    def get_clipboard_history(self) -> list[str]:
        return list(self._state.clipboard_history)

    def clear_clipboard_history(self) -> None:
        self._state.clipboard_history = []
        self.save()

    # ── Preferences ───────────────────────────────────────────────────────────
    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._state.user_preferences.get(key, default)

    def set_preference(self, key: str, value: Any) -> None:
        self._state.user_preferences[key] = value
        self.save()

    def remember(self, key: str, value: Any) -> None:
        self.set_preference(key, value)

    def recall(self, key: str) -> Any:
        return self._state.user_preferences.get(key)

    def forget(self, key: str) -> bool:
        if key in self._state.user_preferences:
            del self._state.user_preferences[key]
            self.save()
            return True
        return False

    def get_all_preferences(self) -> dict:
        return dict(self._state.user_preferences)

    # ── Outfit ────────────────────────────────────────────────────────────────
    @property
    def current_outfit(self) -> str: return self._state.current_outfit
    @current_outfit.setter
    def current_outfit(self, v: str) -> None:
        self._state.current_outfit = v
        self.save()

    # ── Session ───────────────────────────────────────────────────────────────
    def start_session(self) -> None:
        self._state.total_sessions += 1
        self.save()

    @property
    def total_sessions(self) -> int: return self._state.total_sessions
