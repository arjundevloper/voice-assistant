"""
ai/openai.py — OpenAI provider for Emi OS v4.
"""
from __future__ import annotations

import logging

import aiohttp

from ai.ai_engine import BaseAIProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        self._api_key = api_key
        self._model   = model

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    async def query(
        self,
        user_text: str,
        system_prompt: str,
        context: list[dict[str, str]],
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(context)
        messages.append({"role": "user", "content": user_text})

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.85,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
