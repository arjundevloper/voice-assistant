"""
brain/scheduler.py — Idle timer and periodic task scheduler for Emi OS v4.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

Callback = Callable[[], Awaitable[None]]


class IdleTimer:
    """
    Resets on activity. Fires the callback after `timeout` seconds of inactivity.
    """

    def __init__(self, timeout: float, callback: Callback) -> None:
        self._timeout   = timeout
        self._callback  = callback
        self._task: asyncio.Task | None = None

    def reset(self) -> None:
        """Call this on any user activity to restart the timer."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self._timeout)
            logger.info("Idle timer fired after %.0fs", self._timeout)
            await self._callback()
        except asyncio.CancelledError:
            pass

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()


class Scheduler:
    """
    Manages multiple named timers and periodic tasks for Emi.
    """

    def __init__(self) -> None:
        self._timers: dict[str, IdleTimer] = {}
        self._periodic_tasks: list[asyncio.Task] = []

    def register_idle_timer(self, name: str, timeout: float, callback: Callback) -> IdleTimer:
        timer = IdleTimer(timeout, callback)
        self._timers[name] = timer
        return timer

    def reset_timer(self, name: str) -> None:
        if name in self._timers:
            self._timers[name].reset()

    def cancel_timer(self, name: str) -> None:
        if name in self._timers:
            self._timers[name].cancel()

    def add_periodic(self, interval: float, callback: Callback) -> None:
        """Register a coroutine to run every `interval` seconds."""
        async def _loop() -> None:
            while True:
                try:
                    await asyncio.sleep(interval)
                    await callback()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Periodic task error: %s", exc)

        task = asyncio.create_task(_loop())
        self._periodic_tasks.append(task)

    def cancel_all(self) -> None:
        for timer in self._timers.values():
            timer.cancel()
        for task in self._periodic_tasks:
            task.cancel()
        logger.info("All scheduled tasks cancelled")
