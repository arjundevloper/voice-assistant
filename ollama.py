"""
ollama.py - Ollama local AI provider for Emi OS.

Ollama runs entirely on the user's machine — free, private, no API key needed.
Requires Ollama to be installed and running (https://ollama.com).

Expected settings.json keys under "ai":
    "ollama_model":   e.g. "llama3", "mistral", "phi3"   (default: "llama3")
    "ollama_base_url": e.g. "http://localhost:11434"       (default shown)
"""

import asyncio
import logging
from typing import Optional

import aiohttp

from .base import BaseProvider

logger = logging.getLogger("emi.ai.ollama")


class OllamaProvider(BaseProvider):
    """
    Sends prompts to a locally running Ollama instance via its REST API.
    Maintains conversation history as a list of role/content pairs.
    """

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3"

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url: str = config.get("ollama_base_url", self.DEFAULT_BASE_URL).rstrip("/")
        self.model: str = config.get("ollama_model", self.DEFAULT_MODEL)
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------ #

    async def initialize(self) -> bool:
        try:
            self._session = aiohttp.ClientSession()
            available = await self.is_available()
            if not available:
                logger.warning("Ollama is not reachable at %s", self.base_url)
                return False
            logger.info("Ollama provider initialised (model: %s)", self.model)
            return True
        except Exception as exc:
            logger.error("Ollama initialisation failed: %s", exc)
            return False

    async def ask(self, prompt: str) -> str:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        self._append_to_history("user", prompt)

        payload = {
            "model": self.model,
            "messages": self.conversation_history,
            "stream": False,
        }

        try:
            async with self._session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                reply = data["message"]["content"]
                self._append_to_history("assistant", reply)
                return reply

        except asyncio.TimeoutError:
            logger.error("Ollama request timed out after %ss", self.timeout)
            return "Ollama took too long to respond. It might be busy loading the model."
        except aiohttp.ClientError as exc:
            logger.error("Ollama network error: %s", exc)
            return "I couldn't reach the local AI right now. Is Ollama running?"
        except (KeyError, ValueError) as exc:
            logger.error("Ollama response parse error: %s", exc)
            return "I got an unexpected response from the local AI."

    async def reset_conversation(self) -> None:
        self._clear_history()
        logger.debug("Ollama conversation history cleared.")

    async def is_available(self) -> bool:
        try:
            session = self._session or aiohttp.ClientSession()
            async with session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"
