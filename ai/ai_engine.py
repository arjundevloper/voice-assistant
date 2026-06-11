"""
ai/ai_engine.py — AI provider abstraction layer for Emi OS v4.

CHANGES:
- Respects AIConfig.enabled — when False, query() returns a polite
  "AI disabled" stub immediately without touching Ollama/Gemini/etc.
- Added missing `import asyncio` (was already fixed in previous version).
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from config import AIConfig, AIProvider

logger = logging.getLogger(__name__)

_AI_DISABLED_REPLY = "AI is currently disabled. I can still handle commands!"


class BaseAIProvider(ABC):
    @abstractmethod
    async def query(self, user_text: str, system_prompt: str, context: list[dict[str, str]]) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class AIEngine:
    def __init__(self, config: AIConfig, system_prompt: str) -> None:
        self._config        = config
        self._system_prompt = system_prompt
        self._provider      = self._build_provider(config)
        self._offline       = self._build_offline()

    async def query(self, text: str, context: list[dict[str, str]]) -> str:
        # NEW: short-circuit when AI is disabled
        if not self._config.enabled:
            logger.info("AI disabled — skipping provider query")
            return _AI_DISABLED_REPLY

        try:
            response = await self._provider.query(text, self._system_prompt, context)
            logger.debug("AI response from %s: %r", self._provider.name, response[:80])
            return response
        except Exception as exc:
            logger.error("Provider %s failed: %s — falling back to offline", self._provider.name, exc)
            try:
                return await self._offline.query(text, self._system_prompt, context)
            except Exception as exc2:
                logger.critical("Offline fallback also failed: %s", exc2)
                return '{"action": "chat", "params": {"reply": "Sorry, I\'m having trouble thinking right now~"}}'

    def switch_provider(self, new_config: AIConfig) -> None:
        self._config   = new_config
        self._provider = self._build_provider(new_config)
        logger.info("Switched AI provider to %s (enabled=%s)", new_config.provider.value, new_config.enabled)

    @property
    def active_provider_name(self) -> str:
        return self._provider.name if self._config.enabled else "disabled"

    def _build_provider(self, config: AIConfig) -> BaseAIProvider:
        from ai.offline    import OfflineProvider
        from ai.ollama     import OllamaProvider
        from ai.gemini     import GeminiProvider
        from ai.openai     import OpenAIProvider
        from ai.openrouter import OpenRouterProvider

        match config.provider:
            case AIProvider.OLLAMA:
                return OllamaProvider(config.ollama_url, config.ollama_model)
            case AIProvider.GEMINI:
                return GeminiProvider(config.gemini_api_key)
            case AIProvider.OPENAI:
                return OpenAIProvider(config.openai_api_key)
            case AIProvider.OPENROUTER:
                return OpenRouterProvider(config.openrouter_api_key)
            case _:
                return OfflineProvider()

    def _build_offline(self) -> BaseAIProvider:
        from ai.offline import OfflineProvider
        return OfflineProvider()
