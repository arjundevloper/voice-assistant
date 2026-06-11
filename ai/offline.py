"""
ai/offline.py — Emi OS v6 offline provider.
Smart local responses. Brain handles commands; this fires for open-ended chat.
"""
from __future__ import annotations
import random
from ai.ai_engine import BaseAIProvider

class OfflineProvider(BaseAIProvider):
    _RESPONSES = [
        "My AI is off, but I can still handle all Windows tasks~ Just ask!",
        "Offline mode. I can open apps, control volume, search, manage files...",
        "No AI active, but I'm fully operational for PC commands~",
        "AI is paused. Ask me to do something on your Windows~",
        "I'm running local-only. What can I help you with?",
    ]

    @property
    def name(self) -> str:
        return "offline"

    async def query(self, user_text: str, system_prompt: str, context: list) -> str:
        return random.choice(self._RESPONSES)
