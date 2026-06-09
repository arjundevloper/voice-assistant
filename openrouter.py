"""
openrouter.py - OpenRouter provider for Emi OS.

OpenRouter exposes hundreds of models (Anthropic, Meta, Mistral, etc.)
through a single OpenAI-compatible API.

Expected settings.json keys under "ai":
    "openrouter_api_key": "YOUR_KEY"
    "openrouter_model":   e.g. "meta-llama/llama-3-8b-instruct:free"
                               "anthropic/claude-3-haiku"
                          (default: "meta-llama/llama-3-8b-instruct:free")
"""

import asyncio
import logging
from typing import Optional

import aiohttp

from .base import BaseProvider

logger = logging.getLogger("emi.ai.openrouter")

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseProvider):
    """
    Sends prompts to OpenRouter using the OpenAI-compatible Chat API.
    Any model listed on openrouter.ai can be used by changing the model string.
    """

    DEFAULT_MODEL = "meta-llama/llama-3-8b-instruct:free"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key: str = config.get("openrouter_api_key", "")
        self.model: str = config.get("openrouter_model", self.DEFAULT_MODEL)
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------ #

    def _build_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # OpenRouter recommends these for attribution
            "HTTP-Referer": "https://github.com/project-sakura/emi-os",
            "X-Title": "Emi OS",
        }

    async def initialize(self) -> bool:
        if not self.api_key:
            logger.error("OpenRouter API key is missing from settings.json.")
            return False
        try:
            self._session = aiohttp.ClientSession(headers=self._build_headers())
            available = await self.is_available()
            if not available:
                logger.warning("OpenRouter availability check failed.")
                return False
            logger.info("OpenRouter provider initialised (model: %s)", self.model)
            return True
        except Exception as exc:
            logger.error("OpenRouter initialisation failed: %s", exc)
            return False

    async def ask(self, prompt: str) -> str:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._build_headers())

        self._append_to_history("user", prompt)

        payload = {
            "model": self.model,
            "messages": self.conversation_history,
        }

        try:
            async with self._session.post(
                OPENROUTER_CHAT_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status == 401:
                    logger.error("OpenRouter: invalid API key.")
                    return "The OpenRouter API key doesn't seem to be working."
                if resp.status == 429:
                    logger.warning("OpenRouter: rate limited.")
                    return "The AI router is busy right now. Please try again in a moment."
                resp.raise_for_status()
                data = await resp.json()

                # OpenRouter surfaces model errors in the response body
                if "error" in data:
                    err = data["error"]
                    logger.error("OpenRouter API error: %s", err)
                    return f"The AI returned an error: {err.get('message', 'unknown error')}."

                reply = data["choices"][0]["message"]["content"]
                self._append_to_history("assistant", reply)
                return reply

        except asyncio.TimeoutError:
            logger.error("OpenRouter request timed out after %ss", self.timeout)
            return "The AI took too long to respond. Please try again."
        except aiohttp.ClientError as exc:
            logger.error("OpenRouter network error: %s", exc)
            return "I couldn't reach the AI router right now. Check your internet connection."
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("OpenRouter response parse error: %s", exc)
            return "I got an unexpected response from the AI router."

    async def reset_conversation(self) -> None:
        self._clear_history()
        logger.debug("OpenRouter conversation history cleared.")

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            session = self._session or aiohttp.ClientSession(headers=self._build_headers())
            async with session.get(
                "https://openrouter.ai/api/v1/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    @property
    def name(self) -> str:
        return f"OpenRouter ({self.model})"
