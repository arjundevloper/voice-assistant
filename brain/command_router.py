"""
brain/command_router.py — Emi OS v6 full command router.
No AI required — all common PC tasks matched locally.
"""
from __future__ import annotations
import logging, re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    # Casual
    GREETING = "greeting"; HOW_ARE_YOU = "how_are_you"
    GET_TIME = "get_time"; GET_DATE = "get_date"; THANKS = "thanks"
    JOKE = "joke"; WHAT_CAN_YOU_DO = "what_can_you_do"

    # Apps
    OPEN_APP = "open_app"; CLOSE_APP = "close_app"; CLOSE_IT = "close_it"
    LIST_APPS = "list_apps"

    # Windows
    ALT_TAB = "alt_tab"; MINIMIZE = "minimize"; MAXIMIZE = "maximize"
    RESTORE = "restore"; SCREENSHOT = "screenshot"; FOCUS_WINDOW = "focus_window"
    MOVE_CORNER = "move_corner"; MOVE_WINDOW = "move_window"
    RESIZE_WINDOW = "resize_window"; CLOSE_WINDOW = "close_window"

    # Virtual desktops
    NEXT_DESKTOP = "next_desktop"; PREV_DESKTOP = "prev_desktop"
    GOTO_DESKTOP = "goto_desktop"; NEW_DESKTOP = "new_desktop"

    # Power
    LOCK = "lock"; SLEEP = "sleep"; RESTART = "restart"
    SHUTDOWN = "shutdown"; ABORT_SHUTDOWN = "abort_shutdown"
    HIBERNATE = "hibernate"

    # Browser
    OPEN_URL = "open_url"; OPEN_WEBSITE = "open_website"
    SEARCH_GOOGLE = "search_google"; SEARCH_YOUTUBE = "search_youtube"
    SEARCH_BING = "search_bing"

    # Volume / Media
    SET_VOLUME = "set_volume"; VOLUME_UP = "volume_up"; VOLUME_DOWN = "volume_down"
    GET_VOLUME = "get_volume"; MUTE = "mute"; UNMUTE = "unmute"
    NEXT_TRACK = "next_track"; PREV_TRACK = "prev_track"
    PAUSE_MEDIA = "pause_media"; RESUME_MEDIA = "resume_media"

    # Clipboard
    GET_CLIPBOARD = "get_clipboard"; SET_CLIPBOARD = "set_clipboard"
    CLEAR_CLIPBOARD = "clear_clipboard"; CLIPBOARD_HISTORY = "clipboard_history"

    # Files
    CREATE_FOLDER = "create_folder"; OPEN_FOLDER = "open_folder"
    OPEN_RECYCLE = "open_recycle"; DELETE_FILE = "delete_file"
    SEARCH_FILES = "search_files"; SEND_RECYCLE = "send_recycle"
    RENAME_FILE = "rename_file"

    # Timer / Reminder
    SET_TIMER = "set_timer"; CANCEL_TIMER = "cancel_timer"
    LIST_TIMERS = "list_timers"

    # Memory
    REMEMBER = "remember"; RECALL = "recall"; FORGET = "forget"
    WHAT_DO_YOU_KNOW = "what_do_you_know"

    # Repeat
    REPEAT_LAST = "repeat_last"

    # User name
    SET_USER_NAME = "Arjun"
    ASK_MY_NAME = "Arjun"

    # AI fallback
    AI_QUERY = "ai_query"


@dataclass
class RouterResult:
    intent: Intent
    params: dict[str, Any]
    raw: str


_WAKE_RE = re.compile(
    r"^(hey\s+)?(emi|amy|emmy|ami|hemi|assistant|cutie)\s*[,.]?\s*",
    re.IGNORECASE
)

def _norm(text: str) -> str:
    return _WAKE_RE.sub("", text.strip()).strip()

def _r(pat, intent, ex=None):
    return (re.compile(pat, re.IGNORECASE), intent, ex or (lambda m: {}))

_P = [
    # ── Casual ───────────────────────────────────────────────────────────────
    _r(r"(how are you|hru|how r u|you okay|you good|you doing)", Intent.HOW_ARE_YOU),
    _r(r"(hi\b|hello\b|hey\b|sup\b|good (morning|evening|afternoon|night))", Intent.GREETING),
    _r(r"(what (time|hour)|current time|time now|what's the time)", Intent.GET_TIME),
    _r(r"(what('?s| is) (the )?date|today('?s)? date|what day is it)", Intent.GET_DATE),
    _r(r"(thank(s| you)|thx|ty\b)", Intent.THANKS),
    _r(r"(tell me a joke|joke\b|be funny|make me (laugh|smile))", Intent.JOKE),
    _r(r"(what can you do|help me|your (features|commands|abilities)|how do you work)", Intent.WHAT_CAN_YOU_DO),

    # ── Repeat ───────────────────────────────────────────────────────────────
    _r(r"(do it again|repeat (that|last|the last|it)|again\b)", Intent.REPEAT_LAST),

    # ── Power (high priority) ─────────────────────────────────────────────────
    _r(r"(shutdown|shut down|turn off (the )?(pc|computer|system)|power off)", Intent.SHUTDOWN),
    _r(r"(restart|reboot).*(pc|computer|system)?", Intent.RESTART),
    _r(r"(abort|cancel) (shutdown|restart|reboot)", Intent.ABORT_SHUTDOWN),
    _r(r"\bhibernate\b", Intent.HIBERNATE),
    _r(r"(sleep|suspend).*(pc|computer)?", Intent.SLEEP),
    _r(r"\block (the )?(screen|pc|computer)?\b", Intent.LOCK),

    # ── Screenshot / Clipboard ────────────────────────────────────────────────
    _r(r"(take (a )?screenshot|capture (screen|desktop|display))", Intent.SCREENSHOT),
    _r(r"(what('?s| is) (in|on) (my )?clipboard|show clipboard|read clipboard|get clipboard)", Intent.GET_CLIPBOARD),
    _r(r"(clipboard history|show (my )?history)", Intent.CLIPBOARD_HISTORY),
    _r(r"(clear|empty|wipe) (the )?clipboard", Intent.CLEAR_CLIPBOARD),
    _r(r"(copy|put|add) (.+?) (to|into|on) (the )?clipboard",
       Intent.SET_CLIPBOARD, lambda m: {"text": m.group(2).strip()}),

    # ── Timer ─────────────────────────────────────────────────────────────────
    _r(r"(set |remind me in |timer for |after )(\d+) ?(minutes?|mins?|seconds?|secs?|hours?|hrs?)",
       Intent.SET_TIMER,
       lambda m: {"amount": int(m.group(2)), "unit": m.group(3).strip()}),
    _r(r"(cancel|stop|clear) (the )?timer", Intent.CANCEL_TIMER),
    _r(r"(list|show|what('?s| are) my) timers?", Intent.LIST_TIMERS),

    # ── Media — volume ────────────────────────────────────────────────────────
    _r(r"(set volume to |volume )(\d+)%?", Intent.SET_VOLUME, lambda m: {"level": int(m.group(2))}),
    _r(r"volume (\d+)", Intent.SET_VOLUME, lambda m: {"level": int(m.group(1))}),
    _r(r"(what('?s)? (the )?volume|current volume|volume level)", Intent.GET_VOLUME),
    _r(r"(increase|raise|louder|turn up|vol up|volume up)", Intent.VOLUME_UP),
    _r(r"(decrease|lower|quieter|turn down|vol down|volume down)", Intent.VOLUME_DOWN),
    _r(r"\bunmute\b", Intent.UNMUTE),
    _r(r"\bmute\b", Intent.MUTE),

    # ── Media — playback ──────────────────────────────────────────────────────
    _r(r"(next|skip).*(song|track|music)?", Intent.NEXT_TRACK),
    _r(r"(prev(ious)?|back|go back).*(song|track|music)?", Intent.PREV_TRACK),
    _r(r"(pause|stop) (the )?(music|song|media|playback|playing|audio)", Intent.PAUSE_MEDIA),
    _r(r"(play|resume) (the )?(music|song|media|playback|audio)", Intent.RESUME_MEDIA),
    _r(r"\bpause\b", Intent.PAUSE_MEDIA),
    _r(r"\bresume\b", Intent.RESUME_MEDIA),

    # ── Window management ─────────────────────────────────────────────────────
    _r(r"\bminimize\b", Intent.MINIMIZE),
    _r(r"\bmaximize\b", Intent.MAXIMIZE),
    _r(r"\brestore\b", Intent.RESTORE),
    _r(r"(alt.?tab|switch (window|app|between apps?))", Intent.ALT_TAB),
    _r(r"(close (it|this|the (window|app|active))|close current)", Intent.CLOSE_IT),
    _r(r"(focus|bring up|switch to) (window )?(.+)",
       Intent.FOCUS_WINDOW, lambda m: {"name": m.group(3).strip()}),
    _r(r"(snap|move|send) (window )?to (left|right|center|top.?left|top.?right|bottom.?left|bottom.?right|corner)",
       Intent.MOVE_CORNER, lambda m: {"corner": m.group(3).strip().lower()}),
    _r(r"move window (\d+)[, x]+(\d+)",
       Intent.MOVE_WINDOW, lambda m: {"x": int(m.group(1)), "y": int(m.group(2))}),
    _r(r"resize window (\d+)[, x]+(\d+)",
       Intent.RESIZE_WINDOW, lambda m: {"width": int(m.group(1)), "height": int(m.group(2))}),

    # ── Virtual desktops ──────────────────────────────────────────────────────
    _r(r"(new|create) (virtual )?desktop", Intent.NEW_DESKTOP),
    _r(r"next (virtual )?desktop", Intent.NEXT_DESKTOP),
    _r(r"(prev(ious)?|back) (virtual )?desktop", Intent.PREV_DESKTOP),
    _r(r"(go to |switch to |jump to )?desktop (\d+)",
       Intent.GOTO_DESKTOP, lambda m: {"num": int(m.group(2))}),

    # ── Browser ───────────────────────────────────────────────────────────────
    _r(r"(open|go to|visit|navigate to) (https?://\S+)",
       Intent.OPEN_URL, lambda m: {"url": m.group(2)}),
    _r(r"search (bing|microsoft) (for )?(.+)",
       Intent.SEARCH_BING, lambda m: {"query": m.group(3).strip()}),
    _r(r"(search youtube( for)?|youtube search) (.+)",
       Intent.SEARCH_YOUTUBE, lambda m: {"query": m.group(3).strip()}),
    _r(r"(search( google| for)?|google) (.+)",
       Intent.SEARCH_GOOGLE, lambda m: {"query": m.group(3).strip()}),
    _r(r"(open|go to|launch|visit)\s+(youtube|google|reddit|github|instagram|x\.?com|x|twitter|facebook|chatgpt|chat.?gpt|gmail|netflix|spotify|amazon|twitch|discord|linkedin|pinterest|tiktok|whatsapp|telegram|notion|figma|canva|medium|stackoverflow|stack overflow)",
       Intent.OPEN_WEBSITE, lambda m: {"site": m.group(2).lower().replace(" ", "")}),

    # ── File management ───────────────────────────────────────────────────────
    _r(r"(create|make|new) (a )?folder( named| called)? (.+)",
       Intent.CREATE_FOLDER, lambda m: {"name": m.group(4).strip()}),
    _r(r"(create|make|new) (a )?folder",
       Intent.CREATE_FOLDER, lambda m: {"name": "New Folder"}),
    _r(r"(open|show|browse) (the )?(recycle bin|trash|recycler)",
       Intent.OPEN_RECYCLE),
    _r(r"(search|find|look for) (files?|folders?)? ?(.+)",
       Intent.SEARCH_FILES, lambda m: {"query": m.group(3).strip()}),
    _r(r"(open|show|browse|go to) (the )?(downloads?|desktop|documents?|pictures?|photos?|videos?|music|home|onedrive)",
       Intent.OPEN_FOLDER, lambda m: {"path": m.group(3).strip()}),
    _r(r"(delete|remove) (file |folder )?(.+)",
       Intent.DELETE_FILE, lambda m: {"path": m.group(3).strip()}),
    _r(r"(send|move|trash) (.+) to (recycle|trash|bin)",
       Intent.SEND_RECYCLE, lambda m: {"path": m.group(2).strip()}),

    # ── Memory ────────────────────────────────────────────────────────────────
    _r(r"remember (that )?(.+?) (is|are|=) (.+)",
       Intent.REMEMBER, lambda m: {"key": m.group(2).strip(), "value": m.group(4).strip()}),
    _r(r"remember (.+?) as (.+)",
       Intent.REMEMBER, lambda m: {"key": m.group(1).strip(), "value": m.group(2).strip()}),
    _r(r"what('?s| do you know about| is| was)? (my |the )?(.+?)\??$",
       Intent.RECALL, lambda m: {"key": m.group(3).strip()}),
    _r(r"(do you (know|remember)|recall) (my )?(.+?)\??$",
       Intent.RECALL, lambda m: {"key": m.group(4).strip()}),
    _r(r"what do you (know|remember)",
       Intent.WHAT_DO_YOU_KNOW),
    _r(r"forget( about)? (.+)",
       Intent.FORGET, lambda m: {"key": m.group(2).strip()}),

    # ── User name ─────────────────────────────────────────────────────────────
    _r(r"(my name is|call me|i('?m| am)) ([a-zA-Z]+)",
       Intent.SET_USER_NAME, lambda m: {"name": m.group(3).strip()}),
    _r(r"(do you know (my name|who i am)|what('?s| is) my name)",
       Intent.ASK_MY_NAME),

    # ── Apps — LAST (after browser/power) ─────────────────────────────────────
    _r(r"(launch|start|run|open) (.+)",
       Intent.OPEN_APP, lambda m: {"app": m.group(2).strip()}),
    _r(r"(close|quit|kill|exit|terminate) (.+)",
       Intent.CLOSE_APP, lambda m: {"app": m.group(2).strip()}),
]


class CommandRouter:
    def route(self, text: str) -> RouterResult:
        cleaned = _norm(text)
        if not cleaned:
            return RouterResult(Intent.AI_QUERY, {"query": ""}, text)
        lo = cleaned.lower()
        for pat, intent, ex in _P:
            m = pat.search(lo)
            if m:
                try:   params = ex(m)
                except: params = {}
                logger.info("→ %s %s", intent.value, params)
                return RouterResult(intent, params, text)
        return RouterResult(Intent.AI_QUERY, {"query": cleaned}, text)
