"""
brain/emotions.py — Expression and emotion manager for Emi OS v5.
Fixed: SPEAKING no longer hard-codes HAPPY; expressions vary by tone.
"""
from __future__ import annotations

import asyncio
import logging
import random
from enum import Enum
from typing import Callable, Awaitable

from config import Expression

logger = logging.getLogger(__name__)

Broadcaster = Callable[[dict], Awaitable[None]]


class EmotionState(str, Enum):
    IDLE      = "idle"
    LISTENING = "listening"
    WORKING   = "working"
    SPEAKING  = "speaking"
    SLEEPING  = "sleeping"
    REACTING  = "reacting"


class EmotionManager:
    def __init__(self, broadcaster: Broadcaster) -> None:
        self._broadcast = broadcaster
        self._current_expression: Expression = Expression.IDLE
        self._current_state: EmotionState    = EmotionState.IDLE
        self._blink_task: asyncio.Task | None = None

    async def set_expression(self, expression: Expression) -> None:
        self._current_expression = expression
        await self._broadcast({"type": "expression", "value": expression.value})
        logger.debug("Expression → %s", expression.value)

    async def blink(self) -> None:
        await self._broadcast({"type": "blink"})

    async def listen(self) -> None:
        self._current_state = EmotionState.LISTENING
        await self.set_expression(Expression.LISTENING)

    async def work(self) -> None:
        self._current_state = EmotionState.WORKING
        await self.set_expression(Expression.WORKING)

    async def sleep(self) -> None:
        self._current_state = EmotionState.SLEEPING
        await self.set_expression(Expression.SLEEPING)
        self._stop_blink_loop()

    async def idle(self) -> None:
        self._current_state = EmotionState.IDLE
        await self.set_expression(Expression.IDLE)
        self._start_blink_loop()

    async def speak(self, tone: str = "neutral") -> None:
        """
        Enter speaking state with tone-appropriate expression.
        tone: "neutral" | "happy" | "blush" | "annoyed" | "sleepy"
        """
        self._current_state = EmotionState.SPEAKING
        tone_map = {
            "neutral":  Expression.WORKING,   # focused / engaged
            "happy":    Expression.HAPPY,
            "blush":    Expression.BLUSH,
            "annoyed":  Expression.TSUNDERE,
            "sleepy":   Expression.SLEEPING,
        }
        expr = tone_map.get(tone, Expression.WORKING)
        await self.set_expression(expr)

    async def blush(self) -> None:
        prev = self._current_expression
        await self.set_expression(Expression.BLUSH)
        await asyncio.sleep(2.0)
        await self.set_expression(prev)

    async def tsundere(self) -> None:
        prev = self._current_expression
        await self.set_expression(Expression.TSUNDERE)
        await asyncio.sleep(2.5)
        await self.set_expression(prev)

    async def show_speech_bubble(self, text: str) -> None:
        await self._broadcast({"type": "speech_bubble", "text": text})

    async def hide_speech_bubble(self) -> None:
        await self._broadcast({"type": "speech_bubble", "text": ""})

    # ── Blink loop ─────────────────────────────────────────────────────────
    def _start_blink_loop(self) -> None:
        if self._blink_task is None or self._blink_task.done():
            self._blink_task = asyncio.create_task(self._blink_loop())

    def _stop_blink_loop(self) -> None:
        if self._blink_task and not self._blink_task.done():
            self._blink_task.cancel()
            self._blink_task = None

    async def _blink_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(3.5 + random.uniform(0, 3.0))
                if self._current_state in (EmotionState.IDLE, EmotionState.SPEAKING):
                    await self.blink()
        except asyncio.CancelledError:
            pass

    @property
    def current_expression(self) -> Expression:
        return self._current_expression

    @property
    def current_state(self) -> EmotionState:
        return self._current_state
