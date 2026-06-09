"""
base.py - Abstract base class for all AI providers in Emi OS.
Every provider must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseProvider(ABC):
    """
    Abstract base class that all AI providers must implement.
    The rest of Emi should only ever interact with providers through this interface.
    """

    def __init__(self, config: dict):
        """
        Args:
            config: The full 'ai' block from settings.json.
        """
        self.config = config
        self.conversation_history: list[dict] = []
        self.max_history: int = config.get("max_history", 10)
        self.timeout: int = config.get("timeout", 30)

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Perform any setup required before the provider can be used.
        Returns True if initialization succeeded, False otherwise.
        Should NOT raise — failure is handled via return value.
        """
        ...

    @abstractmethod
    async def ask(self, prompt: str) -> str:
        """
        Send a prompt and return the AI's raw text response.
        This response has NOT yet been processed by the personality layer.

        Args:
            prompt: The user's input or command router's query.

        Returns:
            Raw response string, or a fallback message if the call fails.
        """
        ...

    @abstractmethod
    async def reset_conversation(self) -> None:
        """Clear all stored conversation history."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check whether this provider is reachable and ready.
        Should be a lightweight check (e.g. a ping, not a full inference call).
        Returns True if usable, False otherwise.
        """
        ...

    # ------------------------------------------------------------------ #
    # Shared helpers available to all subclasses                          #
    # ------------------------------------------------------------------ #

    def _append_to_history(self, role: str, content: str) -> None:
        """Add a message to the conversation history, trimming if needed."""
        self.conversation_history.append({"role": role, "content": content})
        # Keep history within the configured limit (pairs of user+assistant)
        max_messages = self.max_history * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def _clear_history(self) -> None:
        self.conversation_history = []

    @property
    def name(self) -> str:
        """Human-readable provider name. Override in subclasses."""
        return self.__class__.__name__
