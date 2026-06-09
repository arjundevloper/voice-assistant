"""
openai.py - OpenAI provider for Emi OS.

Requires a valid OpenAI API key.

Expected settings.json keys under "ai":
    "openai_api_key": "YOUR_KEY"
    "openai_model":   e.g. "gpt-4o", "gpt-4o-mini"  (default: "gpt-4o-mini")
"""

import asyncio
import logging
from typing import Optional

import aiohttp

from .base import BaseProvider

logger = logging.getLogger("emi.ai.openai")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(BaseProvider):
    """
    Sends prompts to the OpenAI Chat Completions API.
    Passes full conversation history for multi-turn context.
    """

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key: str = config.get("openai_api_key", "")
        self.model: str = config.get("openai_model", self.DEFAULT_MODEL)
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------ #

    async def initialize(self) -> bool:
        if not self.api_key:
            logger.error("OpenAI API key is missing from settings.json.")
            return False
        try:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
            available = await self.is_available()
            if not available:
                logger.warning("OpenAI availability check failed.")
                return False
            logger.info("OpenAI provider initialised (model: %s)", self.model)
            return True
        except Exception as exc:
            logger.error("OpenAI initialisation failed: %s", exc)
            return False

    async def ask(self, prompt: str) -> str:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )

        self._append_to_history("user", prompt)

        payload = {
            "model": self.model,
            "messages": self.conversation_history,
        }

        try:
            async with self._session.post(
                OPENAI_CHAT_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status == 401:
                    logger.error("OpenAI: invalid API key.")
                    return "The OpenAI API key doesn't seem to be working."
                if resp.status == 429:
                    logger.warning("OpenAI: rate limited or quota exceeded.")
                    return "OpenAI is busy or my usage limit has been reached. Please try again later."
                resp.raise_for_status()
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                self._append_to_history("assistant", reply)
                return reply

        except asyncio.TimeoutError:
            logger.error("OpenAI request timed out after %ss", self.timeout)
            return "OpenAI took too long to respond. Please try again."
        except aiohttp.ClientError as exc:
            logger.error("OpenAI network error: %s", exc)
            return "I couldn't reach OpenAI right now. Check your internet connection."
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("OpenAI response parse error: %s", exc)
            return "I got an unexpected response from OpenAI."

    async def reset_conversation(self) -> None:
        self._clear_history()
        logger.debug("OpenAI conversation history cleared.")

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            session = self._session or aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            async with session.get(
                "https://api.openai.com/v1/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    @property
    def name(self) -> str:
        return f"OpenAI ({self.model})"
