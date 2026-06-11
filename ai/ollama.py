"""
ai/ollama.py — Robust Ollama provider optimised for phi3:mini on low-spec hardware.
Handles JSON + plain-text replies, aggressive cleanup, short timeouts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import aiohttp

from ai.ai_engine import BaseAIProvider

logger = logging.getLogger(__name__)

# Keep the system prompt very short — phi3:mini has a small context window
SYSTEM_PROMPT = """\
You are Emi, a helpful desktop assistant. Reply in 1-2 short sentences max.
If the user asks you to do something (open an app, search, etc.) say you will do it.
Never use markdown. Never use emojis. Be concise and friendly.
"""

class OllamaProvider(BaseAIProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _is_ollama_alive(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(
                f"{self._base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def query(self, user_text: str, system_prompt: str, context: list[dict]) -> str:
        if not await self._is_ollama_alive():
            return "Ollama isn't running. Please start it first."

        # Build short message list — only keep last 3 turns to save memory
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for turn in context[-6:]:
            messages.append(turn)
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 60,     # Keep responses short — better for slow hardware
                "num_ctx": 512,        # Small context = faster on i5 650 / GT 740
                "top_p": 0.85,
                "repeat_penalty": 1.1,
            },
        }

        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),  # phi3 can be slow
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Ollama HTTP %d: %s", resp.status, body[:200])
                    return "Something went wrong with Ollama."

                data = await resp.json()
                raw = data.get("message", {}).get("content", "").strip()
                return self._clean(raw)

        except asyncio.TimeoutError:
            logger.warning("Ollama timed out for model %s", self._model)
            return "That took too long. Try a shorter question."
        except Exception as exc:
            logger.error("Ollama error: %s", exc)
            return "I had trouble connecting to Ollama."

    def _clean(self, text: str) -> str:
        """
        Return plain natural-language text.
        If the model returned JSON, extract the reply field.
        If it returned markdown fences, strip them.
        """
        if not text:
            return "I'm not sure about that."

        # 1. Strip markdown code fences
        text = re.sub(r"```[a-z]*\n?", "", text).strip("`").strip()

        # 2. Try to parse as JSON and pull out a reply field
        try:
            obj = json.loads(text)
            # Handle various shapes the model might return
            if isinstance(obj, dict):
                reply = (
                    obj.get("reply")
                    or obj.get("response")
                    or obj.get("text")
                    or (obj.get("params") or {}).get("reply")
                    or ""
                )
                if reply:
                    return str(reply).strip()
        except Exception:
            pass

        # 3. Look for JSON embedded somewhere in the text
        json_match = re.search(r'\{[^{}]+\}', text)
        if json_match:
            try:
                obj = json.loads(json_match.group())
                if isinstance(obj, dict):
                    reply = (
                        obj.get("reply")
                        or obj.get("response")
                        or obj.get("text")
                        or (obj.get("params") or {}).get("reply")
                        or ""
                    )
                    if reply:
                        return str(reply).strip()
            except Exception:
                pass

        # 4. Use raw text — strip leading labels like "Assistant:" or "Emi:"
        text = re.sub(r'^(assistant|emi|ai)\s*:\s*', '', text, flags=re.IGNORECASE)

        # 5. Trim to a reasonable length (2 sentences max)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return " ".join(sentences[:2]).strip() or "I'm not sure about that."

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
