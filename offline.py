"""
offline.py - Offline (no-AI) provider for Emi OS.

When the user selects provider "none", Emi still runs fully — she just
won't answer open-ended questions. All Windows automation works as normal.
"""

from .base import BaseProvider


class OfflineProvider(BaseProvider):
    """
    Stub provider used when no AI backend is configured.
    Always available; returns a polite message explaining AI is off.
    """

    OFFLINE_RESPONSE = (
        "I'm running in offline mode right now, so I can't answer that. "
        "I can still help with things like opening apps, adjusting volume, "
        "or switching desktops. Would you like to do something like that?"
    )

    async def initialize(self) -> bool:
        # Nothing to set up — offline mode is always ready.
        return True

    async def ask(self, prompt: str) -> str:
        # In offline mode we never touch an AI model.
        return self.OFFLINE_RESPONSE

    async def reset_conversation(self) -> None:
        self._clear_history()

    async def is_available(self) -> bool:
        return True

    @property
    def name(self) -> str:
        return "Offline (no AI)"
