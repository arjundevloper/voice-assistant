"""
ai/gemini.py — Google Gemini provider
"""
from __future__ import annotations
import logging
import aiohttp
from ai.ai_engine import BaseAIProvider

logger = logging.getLogger(__name__)

# Exact model name from Google AI Studio curl examples
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


class GeminiProvider(BaseAIProvider):

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Gemini API key is required")
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "gemini"

    async def query(self, user_text: str, system_prompt: str, context: list[dict[str, str]]) -> str:
        contents = []

        # System prompt as first user/model exchange — compatible with all key tiers
        if system_prompt:
            contents.append({"role": "user",  "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "Understood!"}]})

        for msg in context:
            role = "model" if msg.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})

        contents.append({"role": "user", "parts": [{"text": user_text}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 1000},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_GEMINI_URL}?key={self._api_key}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Gemini Error {resp.status}: {error_text}")
                    raise Exception(f"Gemini API error: {resp.status}")
                data = await resp.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except Exception:
                    logger.error(f"Unexpected Gemini response: {data}")
                    return "Sorry cutie, brain glitch~ Try again?"
