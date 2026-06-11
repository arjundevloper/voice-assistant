"""
speech/tts.py — Text-to-speech using Microsoft Edge-TTS.
Async, non-blocking, streams audio via edge-tts and plays with pygame.
"""
from __future__ import annotations

import asyncio
import io
import logging
import tempfile
from pathlib import Path

import edge_tts
import pygame

logger = logging.getLogger(__name__)

# Initialise pygame mixer once at import time
pygame.mixer.init()


class TextToSpeech:
    """
    Synthesises and plays speech using Edge-TTS.
    Exposes a single `speak(text)` coroutine.
    """

    def __init__(
        self,
        voice: str  = "en-US-AriaNeural",
        volume: str = "+0%",
        rate: str   = "+0%",
        pitch: str  = "+0Hz",
    ) -> None:
        self.voice  = voice
        self.volume = volume
        self.rate   = rate
        self.pitch  = pitch
        self._lock  = asyncio.Lock()   # prevent overlapping speech

    # ── Public API ─────────────────────────────────────────────────────────────

    async def speak(self, text: str) -> None:
        """Synthesise *text* and play audio. Awaitable; won't overlap itself."""
        if not text.strip():
            return
        async with self._lock:
            await self._synthesise_and_play(text)

    async def stop(self) -> None:
        """Interrupt current playback."""
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _synthesise_and_play(self, text: str) -> None:
        tmp_path: Path | None = None
        try:
            communicate = edge_tts.Communicate(
                text,
                voice=self.voice,
                volume=self.volume,
                rate=self.rate,
                pitch=self.pitch,
            )

            # Write to a temp file (pygame needs a seekable stream)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            import aiofiles  # type: ignore
            async with aiofiles.open(tmp_path, "wb") as out:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        await out.write(chunk["data"])

            # Play synchronously inside executor to avoid blocking event loop
            await asyncio.get_event_loop().run_in_executor(None, self._play_file, tmp_path)

        except Exception as exc:
            logger.error("TTS error: %s", exc)
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _play_file(path: Path) -> None:
        """Blocking play — called in executor thread."""
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as exc:
            logger.error("Audio playback error: %s", exc)
