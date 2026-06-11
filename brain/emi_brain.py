"""
brain/emi_brain.py — Emi OS v6 brain.
New: timer/reminder, repeat-last, clipboard history, time-aware greetings,
     abort shutdown, get volume, what-can-you-do, multi-intent via ;
     toast notifications pushed to overlay via WS.
"""
import asyncio, json, logging, random, sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import websockets
from websockets.server import WebSocketServerProtocol

from config import load_config, PERSONALITY_PATH
from brain.memory import MemoryManager
from brain.emotions import EmotionManager
from brain.scheduler import Scheduler
from brain.command_router import CommandRouter, Intent
from speech.stt import SpeechToText
from speech.tts import TextToSpeech
from speech.wakeword import WakeWordDetector
from system.apps import AppManager
from system.browser import BrowserController
from system.windows import WindowController
from system.desktop import DesktopController
from system.media import MediaController
from system.power import PowerController
from system.files import FileController
from ai.ai_engine import AIEngine

logger = logging.getLogger(__name__)

_WAKE = ["Yes?", "I'm listening~", "What do you need?", "Here~", "What's up?", "Mm?"]
_IDLE = ["Zzz...", "Taking a little nap~", "Wake me when you need me.", "Still here~"]

_INTENT_TONE: dict[Intent, str] = {
    Intent.GREETING: "happy", Intent.HOW_ARE_YOU: "happy",
    Intent.GET_TIME: "happy", Intent.GET_DATE: "happy", Intent.THANKS: "happy",
    Intent.JOKE: "happy", Intent.SCREENSHOT: "happy",
    Intent.REMEMBER: "happy", Intent.RECALL: "happy",
    Intent.SHUTDOWN: "annoyed", Intent.RESTART: "annoyed", Intent.ABORT_SHUTDOWN: "annoyed",
    Intent.SLEEP: "sleepy", Intent.HIBERNATE: "sleepy",
    Intent.LOCK: "neutral", Intent.OPEN_APP: "neutral", Intent.CLOSE_APP: "neutral",
    Intent.AI_QUERY: "neutral",
    Intent.SET_USER_NAME: "happy", Intent.ASK_MY_NAME: "happy",
}

_JOKES = [
    "Why do programmers prefer dark mode? Because light attracts bugs~",
    "I would tell you a UDP joke, but you might not get it.",
    "Why did the computer go to the doctor? It had a virus~",
    "There are only 10 types of people — those who understand binary, and those who don't.",
    "A SQL query walks into a bar, walks up to two tables and asks: 'Can I join you?'",
    "Why do Java developers wear glasses? Because they don't C sharp~",
]

_TIME_GREET = {
    range(5, 12):  ["Good morning~", "Rise and shine!", "Morning~ Did you sleep well?"],
    range(12, 17): ["Good afternoon~", "Hey, afternoon already!", "Hope the day's going well~"],
    range(17, 21): ["Good evening~", "Evening! How was your day?", "Hey, evening~"],
    range(21, 24): ["Still up?~", "Good night owl~", "Late night, huh?"],
    range(0, 5):   ["You're up very late~", "Burning the midnight oil?", "It's pretty late~"],
}

def _time_greeting() -> str:
    h = datetime.now().hour
    for rng, msgs in _TIME_GREET.items():
        if h in rng:
            return random.choice(msgs)
    return "Hey there~"


def _fmt(text: str, name: str) -> str:
    """Replace {name} placeholders. If no name saved, use a cute fallback."""
    display = name if name else "you"
    return text.replace("{name}", display)


_SETTINGS_PATH = ROOT / "data" / "settings.json"


def _load_user_name() -> str:
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data.get("user_name", "").strip()
    except Exception:
        return ""


def _save_user_name(name: str) -> None:
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        data["user_name"] = name
        _SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to save user name: %s", exc)


class Timer:
    def __init__(self, name: str, seconds: int, brain: "EmiBrain") -> None:
        self.name    = name
        self.seconds = seconds
        self._brain  = brain
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self.seconds)
            await self._brain._say(f"⏰ Timer done: {self.name}!", tone="happy")
            await self._brain._toast(f"⏰ {self.name} timer done!", "ok")
        except asyncio.CancelledError:
            pass


class EmiBrain:
    def __init__(self) -> None:
        self._config   = load_config()
        self._clients: set[WebSocketServerProtocol] = set()
        self._in_conversation = False
        self._conversation_timer: asyncio.Task | None = None
        self._last_opened_app: str | None = None
        self._timers: dict[str, Timer] = {}
        self._user_name: str = _load_user_name()

        self._personality = self._load_personality()
        self._memory   = MemoryManager()
        self._scheduler = Scheduler()
        self._router   = CommandRouter()

        self._tts  = TextToSpeech(voice="en-US-AvaNeural", volume="+85%", rate="+6%", pitch="+3Hz")
        self._stt  = SpeechToText(on_transcript=self._on_transcript, loop=asyncio.get_event_loop())
        self._ww   = WakeWordDetector(self._config.voice.wake_words, self._on_wake)

        self._apps    = AppManager()
        self._browser = BrowserController()
        self._windows = WindowController()
        self._desktop = DesktopController()
        self._media   = MediaController()
        self._power   = PowerController()
        self._files   = FileController()
        self._ai      = AIEngine(self._config.ai, self._personality.get("system_prompt", ""))
        self._emotions = EmotionManager(self._broadcast)

        self._idle_timer = self._scheduler.register_idle_timer(
            "idle", timeout=300.0, callback=self._on_idle
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _n(self, text: str) -> str:
        """Format a string, substituting {name} with the saved user name."""
        return _fmt(text, self._user_name)

    def _greet_name(self) -> str:
        """Return ', {name}' if we know it, else empty string."""
        return f", {self._user_name}" if self._user_name else ""

    # ── WebSocket ─────────────────────────────────────────────────────────────
    async def _broadcast(self, payload: dict) -> None:
        if not self._clients: return
        data = json.dumps(payload)
        dead: set = set()
        for ws in list(self._clients):
            try: await ws.send(data)
            except: dead.add(ws)
        self._clients -= dead

    async def _toast(self, msg: str, style: str = "", duration: int = 2500) -> None:
        await self._broadcast({"type": "toast", "text": msg, "style": style, "duration": duration})

    async def run(self) -> None:
        logger.info("Emi v6 starting (AI: %s)", self._config.ai.provider.value)
        server = await websockets.serve(self._ws_handler, "localhost", self._config.websocket_port)
        self._stt.start()
        self._idle_timer.reset()
        asyncio.create_task(self._startup_greeting())
        try:
            await asyncio.Future()
        finally:
            self._stt.stop()
            server.close()

    async def _ws_handler(self, ws):
        self._clients.add(ws)
        try:
            await self._broadcast({"type": "init", "expression": "Idle"})
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    t = msg.get("type")
                    if t == "hitbox_click":
                        await self._on_hitbox(msg.get("zone", "body"))
                    elif t == "text_command":
                        await self._on_transcript(msg.get("text", ""))
                    elif t == "mute":
                        pass
                except Exception as e:
                    logger.debug("WS msg error: %s", e)
        finally:
            self._clients.discard(ws)

    async def _on_hitbox(self, zone: str) -> None:
        n = self._greet_name()
        replies = {
            "head": [
                f"Hey{n}! Don't just pat me like that~",
                "That tickles...",
                f"W-what are you doing{n}?!",
                f"Mmph~ You're so bold{n}~",
            ],
            "body": [
                f"Stop poking me{n}!",
                "Hey~!",
                "Quit it.",
                f"You're such a tease{n}~",
            ],
        }
        reply = random.choice(replies.get(zone, [f"Hey{n}!"]))
        if zone == "head": await self._emotions.blush()
        else: await self._emotions.tsundere()
        await self._say(reply, tone="blush" if zone == "head" else "annoyed")

    # ── Voice pipeline ────────────────────────────────────────────────────────
    async def _on_transcript(self, text: str) -> None:
        print(f"\n🎤 [{datetime.now().strftime('%H:%M:%S')}] {text}")
        self._idle_timer.reset()

        lower = text.lower()
        has_wake = any(w in lower for w in self._config.voice.wake_words)

        if not self._in_conversation and has_wake:
            self._in_conversation = True
            await self._on_wake()
            return

        if self._in_conversation and text.strip():
            self._reset_conv_timer()
            parts = [p.strip() for p in
                     __import__("re").split(r"\s+and then\s+|\s+also\s+|;", text, flags=__import__("re").IGNORECASE)
                     if p.strip()]
            for part in parts:
                await self._process(part)

    async def _on_wake(self) -> None:
        await self._emotions.listen()
        n = self._greet_name()
        acks = self._personality.get("wake_acknowledgements") or _WAKE
        msg = self._n(random.choice(acks)) if random.random() < 0.6 else (
            _time_greeting() + (n or "~")
        )
        await self._say(msg, tone="happy")

    def _reset_conv_timer(self) -> None:
        if self._conversation_timer and not self._conversation_timer.done():
            self._conversation_timer.cancel()
        self._conversation_timer = asyncio.create_task(
            self._conv_timeout(self._config.voice.conversation_timeout)
        )

    async def _conv_timeout(self, s: int) -> None:
        await asyncio.sleep(s)
        self._in_conversation = False

    # ── Command dispatcher ────────────────────────────────────────────────────
    async def _process(self, text: str) -> None:
        result = self._router.route(text)
        await self._emotions.work()
        await self._broadcast({"type": "mode", "label": result.intent.value.replace("_", " ")})

        i    = result.intent
        p    = result.params
        r    = ""
        tone = _INTENT_TONE.get(i, "neutral")
        n    = self._greet_name()

        # ── Casual ───────────────────────────────────────────────────────────
        if i == Intent.GET_TIME:
            r = datetime.now().strftime(f"It's %I:%M %p{n}~")

        elif i == Intent.GET_DATE:
            r = datetime.now().strftime("Today is %A, %B %d, %Y")

        elif i == Intent.HOW_ARE_YOU:
            r = random.choice([
                f"I'm doing great, thanks{n}~",
                f"Pretty good! Ready to help you{n}.",
                "All systems running fine~",
                f"Wonderful, now that you asked{n}~",
                f"Better now that you're talking to me{n}~",
            ])

        elif i == Intent.GREETING:
            r = _time_greeting() + (n or "~")

        elif i == Intent.THANKS:
            r = random.choice([
                f"You're welcome{n}~",
                "Anytime!",
                f"Happy to help{n}~",
                "Of course~",
                f"Anything for you{n}~",
            ])

        elif i == Intent.JOKE:
            r = random.choice(_JOKES)

        elif i == Intent.WHAT_CAN_YOU_DO:
            r = (f"I can open & close apps, control volume & media, take screenshots, "
                 f"search Google/YouTube, manage files, set timers, lock/restart your PC, "
                 f"remember things, and much more{n}~")

        # ── User name ─────────────────────────────────────────────────────────
        elif i == Intent.SET_USER_NAME:
            new_name = p.get("name", "").strip().capitalize()
            if new_name:
                self._user_name = new_name
                _save_user_name(new_name)
                n = f", {new_name}"
                r = random.choice([
                    f"{new_name}~ I love that name. I'll remember it~",
                    f"Ooh, {new_name}. That suits you perfectly~",
                    f"Got it~ I'll call you {new_name} from now on~",
                    f"{new_name}... I like saying that~",
                ])
            else:
                r = "I didn't catch that — what should I call you?"

        elif i == Intent.ASK_MY_NAME:
            if self._user_name:
                r = random.choice([
                    f"Of course I know you~ You're {self._user_name}~",
                    f"How could I forget? You're {self._user_name}~",
                    f"Your name is {self._user_name}. See? I pay attention~",
                ])
            else:
                r = random.choice([
                    "I don't know your name yet~ What should I call you?",
                    "You haven't told me your name... Say 'my name is...' and I'll remember it~",
                ])

        # ── Repeat last ───────────────────────────────────────────────────────
        elif i == Intent.REPEAT_LAST:
            last = self._memory.last_command
            if last:
                r = f"Repeating: {last}"
                await self._say(r, tone="neutral")
                await self._process(last)
                return
            else:
                r = "I don't have a last command to repeat"

        # ── Apps ──────────────────────────────────────────────────────────────
        elif i == Intent.OPEN_APP:
            app = p.get("app", "").strip()
            ok, exe = self._apps.open(app)
            if ok:
                self._last_opened_app = app
                self._memory.set_last_app(app, exe)
                self._memory.set_last_command(text)
                r = f"Opening {app}~"
                await self._toast(f"✓ Opening {app}", "ok")
            else:
                r = f"I couldn't find {app}"
                tone = "annoyed"

        elif i in (Intent.CLOSE_APP, Intent.CLOSE_IT):
            app = p.get("app") or self._last_opened_app or self._memory.last_app
            if app and self._apps.close(str(app)):
                r = f"Closed {app}"
                await self._toast(f"✓ Closed {app}", "ok")
            elif self._windows.close_active():
                r = "Closed the active window"
            else:
                r = "What should I close?"; tone = "annoyed"

        # ── Window ────────────────────────────────────────────────────────────
        elif i == Intent.MINIMIZE:
            r = "Minimized" if self._windows.minimize() else "Nothing to minimize"
        elif i == Intent.MAXIMIZE:
            r = "Maximized" if self._windows.maximize() else "Nothing to maximize"
        elif i == Intent.RESTORE:
            r = "Restored" if self._windows.restore() else "Nothing to restore"
        elif i == Intent.ALT_TAB:
            self._windows.alt_tab(); r = "Switching windows"
        elif i == Intent.CLOSE_WINDOW:
            r = "Closed active window" if self._windows.close_active() else "Nothing to close"
        elif i == Intent.SCREENSHOT:
            self._windows.screenshot()
            r = f"Screenshot saved to desktop{n}~"
            await self._toast("📸 Screenshot saved!", "ok")
        elif i == Intent.FOCUS_WINDOW:
            name_w = p.get("name", "")
            r = f"Focused {name_w}" if (name_w and self._windows.focus(name_w)) else f"Couldn't find {name_w}"
        elif i == Intent.MOVE_CORNER:
            corner = p.get("corner", "right")
            r = f"Moved to {corner}" if self._windows.move_to_corner(corner) else "Nothing to move"
        elif i == Intent.MOVE_WINDOW:
            r = "Window moved" if self._windows.move(p.get("x",0), p.get("y",0)) else "Nothing to move"
        elif i == Intent.RESIZE_WINDOW:
            r = "Window resized" if self._windows.resize(p.get("width",800), p.get("height",600)) else "Nothing to resize"

        # ── Virtual desktops ──────────────────────────────────────────────────
        elif i == Intent.NEXT_DESKTOP:
            self._desktop.next_desktop(); r = "Next desktop"
        elif i == Intent.PREV_DESKTOP:
            self._desktop.prev_desktop(); r = "Previous desktop"
        elif i == Intent.NEW_DESKTOP:
            import pyautogui
            pyautogui.hotkey("ctrl","win","d"); r = "Created new desktop"
        elif i == Intent.GOTO_DESKTOP:
            num = max(1, min(10, int(p.get("num", 1))))
            self._desktop.goto_desktop(num); r = f"Desktop {num}"

        # ── Power ─────────────────────────────────────────────────────────────
        elif i == Intent.LOCK:
            self._power.lock()
            r = f"Locking the screen{n}~ Don't go anywhere~"
        elif i == Intent.SLEEP:
            await self._say(f"Going to sleep{n}. Goodnight~", tone="sleepy")
            self._power.sleep(); return
        elif i == Intent.HIBERNATE:
            await self._say(f"Hibernating{n}~ See you later~", tone="sleepy")
            import subprocess; subprocess.run(["shutdown","/h"], **{"creationflags": __import__("subprocess").CREATE_NO_WINDOW} if sys.platform=="win32" else {}); return
        elif i == Intent.RESTART:
            await self._say(f"Restarting in 10 seconds{n}~", tone="annoyed")
            self._power.restart(delay=10); return
        elif i == Intent.SHUTDOWN:
            # Close all open windows first, then shut down
            count = self._windows.close_all_windows()
            if count:
                await self._toast(f"Closing {count} window(s)...", "ok", 2000)
                await asyncio.sleep(1.5)
            farewell = random.choice([
                f"Closing everything and shutting down{n}~ Miss me~",
                f"All cleaned up! Shutting down in 10 seconds{n}. See you soon~",
                f"Bye bye{n}~ Don't forget about me while I'm gone~",
            ])
            await self._say(farewell, tone="annoyed")
            self._power.shutdown(delay=10); return
        elif i == Intent.ABORT_SHUTDOWN:
            self._power.abort_shutdown()
            r = random.choice([
                f"Shutdown cancelled{n}~ Glad you decided to stay~",
                f"Phew! I didn't want you to leave anyway{n}~",
            ])
            tone = "happy"

        # ── Browser ───────────────────────────────────────────────────────────
        elif i == Intent.OPEN_URL:
            url = p.get("url", "")
            self._browser.open_url(url)
            self._memory.last_website = url
            r = f"Opening {url}"
        elif i == Intent.OPEN_WEBSITE:
            site = p.get("site", "")
            self._browser.open_site(site)
            self._memory.last_website = site
            r = f"Opening {site}"
        elif i == Intent.SEARCH_GOOGLE:
            q = p.get("query", "")
            if q:
                self._browser.search_google(q)
                self._memory.set_last_search(q)
                r = f"Searching for: {q}"
            else: r = "What should I search for?"
        elif i == Intent.SEARCH_YOUTUBE:
            q = p.get("query", "")
            if q:
                self._browser.search_youtube(q)
                self._memory.set_last_search(q)
                r = f"Searching YouTube for: {q}"
            else: r = "What should I search on YouTube?"
        elif i == Intent.SEARCH_BING:
            q = p.get("query", "")
            if q:
                self._browser.search_bing(q)
                r = f"Searching Bing for: {q}"
            else: r = "What should I search on Bing?"

        # ── Volume / Media ────────────────────────────────────────────────────
        elif i == Intent.GET_VOLUME:
            vol = self._media.get_volume()
            r = f"Volume is at {vol}%" if vol >= 0 else "I can't read the volume right now"
            if vol >= 0:
                await self._broadcast({"type": "volume", "level": vol})
        elif i == Intent.SET_VOLUME:
            level = max(0, min(100, int(p.get("level", 50))))
            self._media.set_volume(level)
            r = f"Volume set to {level}%"
            await self._broadcast({"type": "volume", "level": level})
        elif i == Intent.VOLUME_UP:
            v = self._media.get_volume()
            new = min(100, (v if v >= 0 else 50) + 15)
            self._media.set_volume(new)
            r = f"Volume up to {new}%"
            await self._broadcast({"type": "volume", "level": new})
        elif i == Intent.VOLUME_DOWN:
            v = self._media.get_volume()
            new = max(0, (v if v >= 0 else 50) - 15)
            self._media.set_volume(new)
            r = f"Volume down to {new}%"
            await self._broadcast({"type": "volume", "level": new})
        elif i == Intent.MUTE:
            self._media.mute(); r = "Muted"
            await self._broadcast({"type": "volume", "level": 0})
        elif i == Intent.UNMUTE:
            self._media.unmute(); r = "Unmuted"
        elif i == Intent.NEXT_TRACK:
            self._media.next_track(); r = "Next track~"
        elif i == Intent.PREV_TRACK:
            self._media.prev_track(); r = "Previous track~"
        elif i == Intent.PAUSE_MEDIA:
            self._media.pause(); r = "Paused"
        elif i == Intent.RESUME_MEDIA:
            self._media.resume(); r = "Playing~"

        # ── Clipboard ─────────────────────────────────────────────────────────
        elif i == Intent.GET_CLIPBOARD:
            content = self._windows.get_clipboard()
            if content:
                self._memory.push_clipboard(content)
                short = content[:80] + ("…" if len(content) > 80 else "")
                r = f"Clipboard: {short}"
            else:
                r = "Clipboard is empty"
            tone = "happy"
        elif i == Intent.CLIPBOARD_HISTORY:
            hist = self._memory.get_clipboard_history()
            if hist:
                r = f"Clipboard history ({len(hist)} items): " + " / ".join(h[:30] for h in hist[:3])
            else:
                r = "No clipboard history yet"
            tone = "happy"
        elif i == Intent.SET_CLIPBOARD:
            txt = p.get("text", "")
            if txt:
                self._windows.set_clipboard(txt)
                self._memory.push_clipboard(txt)
                r = "Copied to clipboard~"
            else:
                r = "What should I copy?"
        elif i == Intent.CLEAR_CLIPBOARD:
            self._windows.set_clipboard("")
            self._memory.clear_clipboard_history()
            r = "Clipboard cleared"

        # ── Timers ────────────────────────────────────────────────────────────
        elif i == Intent.SET_TIMER:
            amount = int(p.get("amount", 1))
            unit   = p.get("unit", "minutes").lower()
            secs   = amount * (60 if "min" in unit else 3600 if "hour" in unit or "hr" in unit else 1)
            name_t = f"{amount} {unit}"
            t = Timer(name_t, secs, self)
            self._timers[name_t] = t
            t.start()
            r = f"Timer set for {amount} {unit}{n}~"
            await self._toast(f"⏰ Timer: {name_t}", "ok")
            tone = "happy"

        elif i == Intent.CANCEL_TIMER:
            if self._timers:
                name_t, t = next(iter(self._timers.items()))
                t.cancel()
                del self._timers[name_t]
                r = f"Timer '{name_t}' cancelled"
            else:
                r = "No active timers"

        elif i == Intent.LIST_TIMERS:
            if self._timers:
                r = "Active timers: " + ", ".join(self._timers.keys())
            else:
                r = "No active timers~"
            tone = "happy"

        # ── Files ─────────────────────────────────────────────────────────────
        elif i == Intent.CREATE_FOLDER:
            name_f = p.get("name", "New Folder")
            self._files.create_folder(name_f)
            r = f"Created folder: {name_f}"
        elif i == Intent.OPEN_FOLDER:
            path_str = p.get("path", "")
            ok = self._files.open_named(path_str) or self._files.open_folder(path_str)
            r = f"Opening {path_str}" if ok else f"Couldn't find {path_str}"
        elif i == Intent.OPEN_RECYCLE:
            self._files.open_recycle_bin(); r = "Opening recycle bin"
        elif i == Intent.SEARCH_FILES:
            q = p.get("query", "")
            if q:
                results = self._files.search_files_fast(q)
                r = f"Found {len(results)} file(s) for '{q}'" if results else f"No files found for '{q}'"
            else:
                r = "What should I search for?"
        elif i == Intent.DELETE_FILE:
            path_str = p.get("path", "")
            ok = self._files.delete_file(path_str) if path_str else False
            r = f"Deleted {path_str}" if ok else "Couldn't delete that"
        elif i == Intent.SEND_RECYCLE:
            path_str = p.get("path", "")
            ok = self._files.send_to_recycle(path_str) if path_str else False
            r = "Sent to recycle bin" if ok else "Couldn't recycle that"

        # ── Memory ────────────────────────────────────────────────────────────
        elif i == Intent.REMEMBER:
            key, value = p.get("key",""), p.get("value","")
            if key and value:
                self._memory.remember(key, value)
                r = f"Got it{n}~ I'll remember that {key} is {value}"; tone = "happy"
            else:
                r = "What should I remember?"
        elif i == Intent.RECALL:
            key = p.get("key","")
            val = self._memory.recall(key) if key else None
            if val is not None:
                r = f"{key} is {val}"; tone = "happy"
            elif "last app" in key.lower():
                la = self._memory.last_app
                r = f"Last app was {la}" if la else "I don't remember the last app"
            elif "last site" in key.lower() or "last website" in key.lower():
                lw = self._memory.last_website
                r = f"Last site was {lw}" if lw else "I don't remember the last site"
            else:
                r = f"I don't remember anything about '{key}'"
        elif i == Intent.WHAT_DO_YOU_KNOW:
            prefs = self._memory.get_all_preferences()
            if prefs:
                r = "I know: " + ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:5])
            else:
                r = f"I don't have anything saved yet{n}~"
            tone = "happy"
        elif i == Intent.FORGET:
            key = p.get("key","")
            if key and self._memory.forget(key):
                r = f"Forgotten: {key}"; tone = "happy"
            else:
                r = f"I didn't have anything saved for '{key}'"

        # ── AI fallback ───────────────────────────────────────────────────────
        elif i == Intent.AI_QUERY:
            q = p.get("query", text)
            if self._config.ai.provider.value == "offline":
                r = self._offline_response(q)
            else:
                try:
                    raw = await self._ai.query(text, self._memory.get_context())
                    r   = await self._extract_reply(raw)
                except Exception as exc:
                    logger.error("AI error: %s", exc)
                    r = f"Sorry{n}, I'm having trouble right now~"; tone = "annoyed"

        # ── Save & respond ────────────────────────────────────────────────────
        if text and i != Intent.REPEAT_LAST:
            self._memory.add_exchange("user", text)
            self._memory.set_last_command(text)
        if r:
            self._memory.add_exchange("assistant", r)

        await self._broadcast({"type": "mode", "label": "IDLE"})
        await self._say(r or "Got it~", tone=tone)

    def _offline_response(self, q: str) -> str:
        n = self._greet_name()
        q = q.lower()
        if any(w in q for w in ["who are you", "your name", "what are you"]):
            return f"I'm Emi, your personal desktop assistant{n}~"
        if any(w in q for w in ["thank", "thanks", "thx"]):
            return random.choice([f"You're welcome{n}~", "Anytime!", f"Anything for you{n}~"])
        if any(w in q for w in ["joke", "funny", "laugh"]):
            return random.choice(_JOKES)
        if any(w in q for w in ["weather", "temperature", "rain", "forecast"]):
            return f"I don't have internet access for weather{n}, but you can say 'search weather' to Google it~"
        if any(w in q for w in ["help", "what can you do", "command", "features"]):
            return (f"I can open/close apps, control volume, screenshots, timers, "
                    f"search the web, manage files, and control Windows — all locally{n}~")
        if any(w in q for w in ["version", "what version"]):
            return "I'm Emi OS v6~"
        if any(w in q for w in ["morning", "afternoon", "evening", "night"]):
            return _time_greeting() + (n or "~")
        return random.choice([
            f"I'm in offline mode{n} — but I can still handle all Windows tasks~",
            f"My AI brain is resting, but I'm fully operational for PC commands{n}~",
            "Offline! Ask me to open something or search the web~",
            f"AI is paused. I can still control your Windows though{n}~",
        ])

    async def _extract_reply(self, raw: str) -> str:
        raw = raw.strip()
        if not raw: return "I'm not sure about that~"
        try:
            import json as _j
            obj = _j.loads(raw)
            return obj.get("params", {}).get("reply", raw)
        except:
            return raw

    async def _say(self, text: str, tone: str = "neutral") -> None:
        await self._emotions.speak(tone=tone)
        await self._emotions.show_speech_bubble(text)
        await self._tts.speak(text)
        await self._emotions.hide_speech_bubble()
        await self._emotions.idle()

    async def _startup_greeting(self) -> None:
        await asyncio.sleep(1.5)
        greets = self._personality.get("greeting_lines")
        msg    = self._n(random.choice(greets)) if greets else (_time_greeting() + self._greet_name())
        await self._say(msg, tone="happy")
        vol = self._media.get_volume()
        if vol >= 0:
            await self._broadcast({"type": "volume", "level": vol})

    async def _on_idle(self) -> None:
        await self._emotions.sleep()
        idle = self._personality.get("idle_lines")
        msg  = self._n(random.choice(idle)) if idle else random.choice(_IDLE)
        await self._say(msg, tone="sleepy")

    def _load_personality(self) -> dict:
        try:
            return json.loads(PERSONALITY_PATH.read_text(encoding="utf-8"))
        except:
            return {}
