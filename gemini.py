"""
gemini.py - Google Gemini AI provider for Emi OS.

Requires a valid Gemini API key.

Expected settings.json keys under "ai":
    "gemini_api_key": "YOUR_KEY"
    "gemini_model":   e.g. "gemini-1.5-flash"  (default shown)
"""

import asyncio
import logging
from typing import Optional

import aiohttp

from .base import BaseProvider

logger = logging.getLogger("emi.ai.gemini")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseProvider):
    """
    Sends prompts to the Google Gemini API.
    Converts Emi's role/content history into Gemini's 'contents' format.
    """

    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key: str = config.get("gemini_api_key", "")
        self.model: str = config.get("gemini_model", self.DEFAULT_MODEL)
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------ #

    async def initialize(self) -> bool:
        if not self.api_key:
            logger.error("Gemini API key is missing from settings.json.")
            return False
        try:
            self._session = aiohttp.ClientSession()
            available = await self.is_available()
            if not available:
                logger.warning("Gemini availability check failed.")
                return False
            logger.info("Gemini provider initialised (model: %s)", self.model)
            return True
        except Exception as exc:
            logger.error("Gemini initialisation failed: %s", exc)
            return False

    async def ask(self, prompt: str) -> str:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        self._append_to_history("user", prompt)

        # Convert to Gemini's contents format
        contents = []
        for msg in self.conversation_history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"
        payload = {"contents": contents}

        try:
            async with self._session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status == 401:
                    logger.error("Gemini: invalid API key.")
                    return "The Gemini API key doesn't seem to be working."
                if resp.status == 429:
                    logger.warning("Gemini: rate limited.")
                    return "Gemini is busy right now. Please try again in a moment."
                resp.raise_for_status()
                data = await resp.json()
                reply = data["candidates"][0]["content"]["parts"][0]["text"]
                self._append_to_history("assistant", reply)
                return reply

        except asyncio.TimeoutError:
            logger.error("Gemini request timed out after %ss", self.timeout)
            return "Gemini took too long to respond. Please try again."
        except aiohttp.ClientError as exc:
            logger.error("Gemini network error: %s", exc)
            return "I couldn't reach Gemini right now. Check your internet connection."
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("Gemini response parse error: %s", exc)
            return "I got an unexpected response from Gemini."

    async def reset_conversation(self) -> None:
        self._clear_history()
        logger.debug("Gemini conversation history cleared.")

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            # List models as a lightweight availability ping
            url = f"{GEMINI_API_BASE}?key={self.api_key}"
            session = self._session or aiohttp.ClientSession()
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    @property
    def name(self) -> str:
        return f"Gemini ({self.model})"
