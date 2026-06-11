"""
speech/stt.py — Speech-to-text using Google STT via SpeechRecognition.
Runs continuous microphone capture in a background thread.

FIXES:
- Added `timeout` to listen() so the mic never blocks indefinitely waiting
  for speech (was the cause of the long mic-off periods after TTS finished).
- Added post-error cooldown so a Google STT failure doesn't spam retries.
- Dynamic energy threshold is kept but capped to avoid runaway suppression.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Awaitable

import speech_recognition as sr

logger = logging.getLogger(__name__)

TranscriptCallback = Callable[[str], Awaitable[None]]

# How long (seconds) to wait for speech to start before looping again.
# Keeps the mic responsive; was None (block forever) before this fix.
_LISTEN_TIMEOUT = 3.0

# Max time for a single phrase — unchanged from original.
_PHRASE_TIME_LIMIT = 8.0

# Cooldown after a Google STT network error to avoid hammering the API.
_ERROR_COOLDOWN = 2.0


class SpeechToText:
    """
    Listens to the microphone and calls *on_transcript* with recognised text.
    Runs the blocking SR loop in a daemon thread; bridges back to asyncio.
    """

    def __init__(
        self,
        on_transcript: TranscriptCallback,
        loop: asyncio.AbstractEventLoop,
        energy_threshold: int = 300,
        pause_threshold: float = 0.8,
        phrase_time_limit: float | None = _PHRASE_TIME_LIMIT,
        listen_timeout: float = _LISTEN_TIMEOUT,
    ) -> None:
        self._on_transcript    = on_transcript
        self._loop             = loop
        self._energy_threshold = energy_threshold
        self._pause_threshold  = pause_threshold
        self._phrase_time_limit = phrase_time_limit
        self._listen_timeout   = listen_timeout

        self._recognizer = sr.Recognizer()
        self._recognizer.energy_threshold          = energy_threshold
        self._recognizer.pause_threshold           = pause_threshold
        self._recognizer.dynamic_energy_threshold  = True
        # Cap so a loud ambient burst doesn't silence the mic permanently.
        self._recognizer.dynamic_energy_adjustment_damping = 0.15
        self._recognizer.dynamic_energy_ratio              = 1.5

        self._running = False
        self._thread: threading.Thread | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._listen_loop, daemon=True, name="stt-thread"
        )
        self._thread.start()
        logger.info("STT listening started")

    def stop(self) -> None:
        self._running = False
        logger.info("STT listening stopped")

    # ── Internal ───────────────────────────────────────────────────────────────

    def _listen_loop(self) -> None:
        """Blocking loop — runs entirely in the worker thread."""
        with sr.Microphone() as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.info(
                "Microphone calibrated (energy=%s)", self._recognizer.energy_threshold
            )

            while self._running:
                try:
                    # FIX: `timeout` makes listen() return after _LISTEN_TIMEOUT
                    # seconds of silence instead of blocking forever.  This is
                    # what caused the mic to appear "off" for a long time after
                    # TTS finished speaking.
                    audio = self._recognizer.listen(
                        source,
                        timeout=self._listen_timeout,
                        phrase_time_limit=self._phrase_time_limit,
                    )
                    text = self._recognizer.recognize_google(audio)
                    if text:
                        logger.debug("STT recognised: %r", text)
                        asyncio.run_coroutine_threadsafe(
                            self._on_transcript(text),
                            self._loop,
                        )

                except sr.WaitTimeoutError:
                    # No speech detected within timeout — keep looping.
                    pass
                except sr.UnknownValueError:
                    # Unintelligible audio — keep looping.
                    pass
                except sr.RequestError as exc:
                    logger.error("Google STT request failed: %s", exc)
                    # Brief cooldown so we don't hammer the API on network issues.
                    time.sleep(_ERROR_COOLDOWN)
                except Exception as exc:
                    logger.exception("Unexpected STT error: %s", exc)
                    time.sleep(_ERROR_COOLDOWN)
