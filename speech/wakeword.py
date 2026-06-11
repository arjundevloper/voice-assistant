"""
speech/wakeword.py — Wake-word detector for Emi OS v4.
Monitors the raw transcript stream and fires a callback when a wake word is heard.
"""
from __future__ import annotations

import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

WakeCallback = Callable[[], Awaitable[None]]


class WakeWordDetector:
    """
    Checks incoming transcripts for configured wake words.
    Stateless — the brain decides what conversation mode means.
    """

    def __init__(
        self,
        wake_words: list[str],
        on_wake: WakeCallback,
    ) -> None:
        self._wake_words = [w.lower().strip() for w in wake_words]
        self._on_wake    = on_wake

    async def process(self, text: str) -> bool:
        """
        Check *text* for a wake word. Returns True if detected.
        """
        lower = text.lower().strip()
        for word in self._wake_words:
            if lower == word or lower.startswith(word + " ") or lower.startswith(word + ","):
                logger.info("Wake word detected: %r in %r", word, text)
                await self._on_wake()
                return True
        return False

    def extract_command(self, text: str) -> str:
        """Strip wake word prefix, return remaining command (if any)."""
        lower = text.lower().strip()
        for word in self._wake_words:
            if lower.startswith(word):
                remainder = text[len(word):].strip(" ,")
                return remainder
        return text

    def update_wake_words(self, words: list[str]) -> None:
        self._wake_words = [w.lower().strip() for w in words]
        logger.info("Wake words updated: %s", self._wake_words)
