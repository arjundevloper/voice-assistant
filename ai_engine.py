"""
ai_engine.py - The single AI gateway for Emi OS (Project Sakura).

NO other module should import from ai/providers/ directly.
Everything goes through AIEngine.

Usage
-----
    from ai.ai_engine import AIEngine

    ai = AIEngine(settings["ai"])
    await ai.initialize()

    response = await ai.ask("Explain recursion simply.")
    await ai.reset_conversation()
    await ai.shutdown()

The rest of Emi only ever needs:
    answer = await ai.ask(prompt)
"""

import asyncio
import logging
from typing import Optional

from .providers.base import BaseProvider
from .providers.offline import OfflineProvider
from .providers.ollama import OllamaProvider
from .providers.gemini import GeminiProvider
from .providers.openai import OpenAIProvider
from .providers.openrouter import OpenRouterProvider

logger = logging.getLogger("emi.ai")


# ─────────────────────────────────────────────────────────────────────────────
# Provider registry
# Add new providers here — nothing else needs to change.
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "none":        OfflineProvider,
    "offline":     OfflineProvider,
    "ollama":      OllamaProvider,
    "gemini":      GeminiProvider,
    "openai":      OpenAIProvider,
    "openrouter":  OpenRouterProvider,
}

# Friendly message returned when every provider fails at runtime
_FALLBACK_MESSAGE = (
    "I'm having trouble thinking right now — something went wrong on my end. "
    "I'm still here for app control and system tasks though!"
)


# ─────────────────────────────────────────────────────────────────────────────

class AIEngine:
    """
    Provider-agnostic AI gateway for Emi OS.

    Responsibilities
    ----------------
    - Load and initialise the correct provider from settings.
    - Fall back gracefully if the provider is unavailable.
    - Expose a single public coroutine: ask(prompt) → str.
    - Manage conversation history lifecycle.
    - Never crash Emi — all exceptions are caught and logged.
    """

    def __init__(self, config: dict):
        """
        Args:
            config: The "ai" block from settings.json.
                    Expected keys:
                      provider           (str)  – e.g. "none", "ollama", "openai"
                      conversation_memory (bool) – whether to keep history
                      timeout            (int)  – seconds before giving up
                      max_history        (int)  – max user/assistant pairs kept
        """
        self._config = config
        self._provider_name: str = config.get("provider", "none").lower()
        self._conversation_memory: bool = config.get("conversation_memory", True)
        self._provider: Optional[BaseProvider] = None
        self._ready: bool = False

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def initialize(self) -> bool:
        """
        Instantiate and initialise the configured provider.
        Falls back to OfflineProvider if the chosen provider fails.

        Returns True if the primary provider started successfully.
        """
        provider_class = PROVIDER_REGISTRY.get(self._provider_name)

        if provider_class is None:
            logger.warning(
                "Unknown AI provider '%s'. Falling back to offline mode.",
                self._provider_name,
            )
            provider_class = OfflineProvider

        logger.info("Initialising AI provider: %s", self._provider_name)
        self._provider = provider_class(self._config)

        try:
            success = await self._provider.initialize()
        except Exception as exc:
            logger.error(
                "Provider '%s' raised during initialize(): %s",
                self._provider_name, exc
            )
            success = False

        if not success and self._provider_name not in ("none", "offline"):
            logger.warning(
                "Provider '%s' failed to initialise. Falling back to offline mode.",
                self._provider_name,
            )
            self._provider = OfflineProvider(self._config)
            await self._provider.initialize()

        self._ready = True
        logger.info("AI Engine ready. Active provider: %s", self._provider.name)
        return success

    async def shutdown(self) -> None:
        """
        Clean up any open connections held by the provider.
        Call this when Emi is shutting down.
        """
        if self._provider is None:
            return
        # Close aiohttp sessions if the provider exposes one
        session = getattr(self._provider, "_session", None)
        if session is not None and not session.closed:
            await session.close()
            logger.debug("Closed HTTP session for %s.", self._provider.name)
        self._ready = False
        logger.info("AI Engine shut down.")

    # ------------------------------------------------------------------ #
    # Public API — the ONLY method the rest of Emi should call            #
    # ------------------------------------------------------------------ #

    async def ask(self, prompt: str) -> str:
        """
        Send a prompt to the active AI provider and return its raw response.

        The response has NOT been processed by the personality layer.
        The personality layer wraps this call; nothing else should.

        Args:
            prompt: Free-form text from the command router.

        Returns:
            AI response string, or a safe fallback message on any failure.
        """
        if not self._ready or self._provider is None:
            logger.error("ask() called before initialize().")
            return _FALLBACK_MESSAGE

        if not prompt or not prompt.strip():
            return "I didn't catch that — could you say it again?"

        try:
            # Optionally suppress history to keep each exchange independent
            if not self._conversation_memory:
                await self._provider.reset_conversation()

            response = await self._provider.ask(prompt.strip())
            return response if response else _FALLBACK_MESSAGE

        except asyncio.CancelledError:
            # Let task cancellation propagate normally (e.g. Emi shutting down)
            raise
        except Exception as exc:
            logger.error(
                "Unhandled error in provider '%s': %s",
                self._provider.name, exc, exc_info=True
            )
            return _FALLBACK_MESSAGE

    # ------------------------------------------------------------------ #
    # Conversation management                                              #
    # ------------------------------------------------------------------ #

    async def reset_conversation(self) -> None:
        """
        Clear conversation history in the active provider.
        Safe to call even when no provider is active.
        """
        if self._provider is not None:
            await self._provider.reset_conversation()
            logger.info("Conversation history cleared (%s).", self._provider.name)

    # ------------------------------------------------------------------ #
    # Introspection helpers (for overlay / status display)                #
    # ------------------------------------------------------------------ #

    @property
    def is_ready(self) -> bool:
        """True once initialize() has completed successfully."""
        return self._ready

    @property
    def provider_name(self) -> str:
        """Human-readable name of the active provider."""
        if self._provider is None:
            return "Not initialised"
        return self._provider.name

    async def is_provider_available(self) -> bool:
        """
        Live availability check for the active provider.
        Useful for status overlays or health-check routines.
        """
        if self._provider is None:
            return False
        try:
            return await self._provider.is_available()
        except Exception:
            return False
