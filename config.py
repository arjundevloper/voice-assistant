"""
config.py — Central configuration loader for Emi OS v4.
Reads settings.json and exposes typed, validated config objects.

CHANGES:
- OverlayConfig now carries the full set of size fields used by main.js.
- AIConfig has an `enabled` bool — set to false to bypass all AI calls.
- `overlay_ui` section persisted properly.
- `overlay_size` preset (small/medium/large/custom) added for easy resizing.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.resolve()
DATA_DIR    = BASE_DIR / "data"
LOGS_DIR    = BASE_DIR / "logs"
ASSETS_DIR  = BASE_DIR / "assets"
OUTFITS_DIR = BASE_DIR / "outfits"

SETTINGS_PATH    = DATA_DIR / "settings.json"
APPS_PATH        = DATA_DIR / "apps.json"
MEMORY_PATH      = DATA_DIR / "memory.json"
PERSONALITY_PATH = DATA_DIR / "personality.json"
HITBOXES_PATH    = DATA_DIR / "hitboxes.json"
OVERLAY_PATH     = DATA_DIR / "overlay.json"


# ── Enumerations ─────────────────────────────────────────────────────────────
class AIProvider(str, Enum):
    OFFLINE    = "offline"
    OLLAMA     = "ollama"
    GEMINI     = "gemini"
    OPENAI     = "openai"
    OPENROUTER = "openrouter"


class Expression(str, Enum):
    HAPPY     = "Happy"
    IDLE      = "Idle"
    BLINK     = "Blink"
    LISTENING = "Listening"
    WORKING   = "Working"
    SLEEPING  = "Sleeping"
    BLUSH     = "Blush"
    TSUNDERE  = "Tsundere"


# ── Dataclasses ───────────────────────────────────────────────────────────────
@dataclass
class OverlayConfig:
    width: int          = 320
    height: int         = 520
    x: int              = 100
    y: int              = 100
    opacity: float      = 1.0
    always_on_top: bool = True
    # Size preset: "small" | "medium" | "large" | "custom"
    # custom → use width/height directly; others map to fixed presets.
    size_preset: str    = "large"


# Preset dimensions (width, height) for the Electron window
OVERLAY_PRESETS: dict[str, tuple[int, int]] = {
    "small":  (200, 325),
    "medium": (260, 420),
    "large":  (320, 520),
    "custom": (0, 0),   # placeholder — actual values come from width/height
}


def resolve_overlay_size(cfg: "OverlayConfig") -> tuple[int, int]:
    """Return (width, height) honoring the size_preset."""
    if cfg.size_preset in OVERLAY_PRESETS and cfg.size_preset != "custom":
        return OVERLAY_PRESETS[cfg.size_preset]
    return cfg.width, cfg.height


@dataclass
class VoiceConfig:
    voice: str            = "en-US-AriaNeural"
    volume: float         = 1.0
    rate: str             = "+0%"
    pitch: str            = "+0Hz"
    wake_words: list[str] = field(default_factory=lambda: ["emi", "hey emi", "amy", "emmy"])
    conversation_timeout: int = 15  # seconds


@dataclass
class AIConfig:
    provider: AIProvider  = AIProvider.OFFLINE
    enabled: bool         = True   # NEW: False = skip all AI calls
    ollama_model: str     = "llama3"
    ollama_url: str       = "http://localhost:11434"
    gemini_api_key: str   = ""
    openai_api_key: str   = ""
    openrouter_api_key: str = ""


@dataclass
class EmiConfig:
    overlay:        OverlayConfig = field(default_factory=OverlayConfig)
    voice:          VoiceConfig   = field(default_factory=VoiceConfig)
    ai:             AIConfig      = field(default_factory=AIConfig)
    outfit:         str           = "default"
    startup:        bool          = False
    websocket_port: int           = 8765


# ── Loader ────────────────────────────────────────────────────────────────────
_DEFAULTS: dict[str, Any] = {
    "overlay": {
        "width": 320, "height": 520,
        "x": 100, "y": 100,
        "opacity": 1.0, "always_on_top": True,
        "size_preset": "large",
    },
    "voice": {
        "voice": "en-US-AriaNeural",
        "volume": 1.0, "rate": "+0%", "pitch": "+0Hz",
        "wake_words": ["emi", "hey emi", "amy", "emmy"],
        "conversation_timeout": 15,
    },
    "ai": {
        "provider": "offline",
        "enabled": True,
        "ollama_model": "llama3",
        "ollama_url": "http://localhost:11434",
        "gemini_api_key": "",
        "openai_api_key": "",
        "openrouter_api_key": "",
    },
    "outfit": "default",
    "startup": False,
    "websocket_port": 8765,
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> EmiConfig:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {}
    if SETTINGS_PATH.exists():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            logger.info("Loaded settings from %s", SETTINGS_PATH)
        except json.JSONDecodeError as exc:
            logger.error("Corrupt settings.json (%s) — using defaults", exc)

    merged = _deep_merge(_DEFAULTS, raw)

    overlay_raw = merged["overlay"].copy()
    overlay = OverlayConfig(
        width=int(overlay_raw.get("width", 320)),
        height=int(overlay_raw.get("height", 520)),
        x=int(overlay_raw.get("x", 100)),
        y=int(overlay_raw.get("y", 100)),
        opacity=float(overlay_raw.get("opacity", 1.0)),
        always_on_top=bool(overlay_raw.get("always_on_top", True)),
        size_preset=str(overlay_raw.get("size_preset", "large")),
    )

    voice = VoiceConfig(**{
        **merged["voice"],
        "wake_words": list(merged["voice"]["wake_words"]),
    })

    ai_raw = merged["ai"].copy()
    ai_raw["provider"] = AIProvider(ai_raw.get("provider", "offline"))
    ai_raw["enabled"]  = bool(ai_raw.get("enabled", True))
    ai = AIConfig(**ai_raw)

    return EmiConfig(
        overlay=overlay,
        voice=voice,
        ai=ai,
        outfit=merged.get("outfit", "default"),
        startup=bool(merged.get("startup", False)),
        websocket_port=int(merged.get("websocket_port", 8765)),
    )


def save_config(cfg: EmiConfig) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "overlay": {
            "width": cfg.overlay.width,
            "height": cfg.overlay.height,
            "x": cfg.overlay.x,
            "y": cfg.overlay.y,
            "opacity": cfg.overlay.opacity,
            "always_on_top": cfg.overlay.always_on_top,
            "size_preset": cfg.overlay.size_preset,
        },
        "voice": {
            "voice": cfg.voice.voice,
            "volume": cfg.voice.volume,
            "rate": cfg.voice.rate,
            "pitch": cfg.voice.pitch,
            "wake_words": cfg.voice.wake_words,
            "conversation_timeout": cfg.voice.conversation_timeout,
        },
        "ai": {
            "provider": cfg.ai.provider.value,
            "enabled": cfg.ai.enabled,
            "ollama_model": cfg.ai.ollama_model,
            "ollama_url": cfg.ai.ollama_url,
            "gemini_api_key": cfg.ai.gemini_api_key,
            "openai_api_key": cfg.ai.openai_api_key,
            "openrouter_api_key": cfg.ai.openrouter_api_key,
        },
        "outfit": cfg.outfit,
        "startup": cfg.startup,
        "websocket_port": cfg.websocket_port,
    }
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Settings saved to %s", SETTINGS_PATH)
