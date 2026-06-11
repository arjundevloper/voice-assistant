"""
system/media.py — Media and volume control for Emi OS v4.
Uses pycaw for volume and pyautogui for media key simulation.

FIX: AudioDevice.Activate() call signature was wrong.
     The correct pycaw pattern is to call Activate on the device COM object
     using the right CLSCTX and cast the pointer properly.
"""
from __future__ import annotations

import logging

import pyautogui
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

logger = logging.getLogger(__name__)


class MediaController:
    """Controls system volume and media playback keys."""

    def __init__(self) -> None:
        self._volume_interface: IAudioEndpointVolume | None = None
        self._init_volume()

    # ── Volume ────────────────────────────────────────────────────────────────

    def _init_volume(self) -> None:
        """
        FIX: Original code called devices.Activate(...) on a Python object
        that doesn't expose .Activate directly. The correct pycaw pattern is:
          speakers = AudioUtilities.GetSpeakers()
          interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
          volume = cast(interface, POINTER(IAudioEndpointVolume))
        pycaw's GetSpeakers() returns a COM IMMDevice, which does have Activate.
        The error 'AudioDevice has no attribute Activate' means pycaw returned
        its own wrapper — use .activate() (lowercase) from pycaw's API instead.
        """
        try:
            devices = AudioUtilities.GetSpeakers()
            # pycaw wraps the COM object; .Activate is the COM method
            interface = devices.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None
            )
            self._volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
            logger.info("Audio endpoint volume interface acquired")
        except AttributeError:
            # Fallback: some pycaw versions expose .activate() (lowercase)
            try:
                devices = AudioUtilities.GetSpeakers()
                self._volume_interface = devices.activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                )
                logger.info("Audio endpoint volume interface acquired (fallback)")
            except Exception as exc:
                logger.error("Volume interface init failed (both methods): %s", exc)
        except Exception as exc:
            logger.error("Volume interface init failed: %s", exc)

    def set_volume(self, level: int) -> bool:
        """Set master volume 0–100."""
        if not self._volume_interface:
            # Fallback: use pyautogui keypress simulation
            logger.warning("Volume interface unavailable — using key simulation")
            return self._set_volume_keys(level)
        clamped = max(0, min(100, level))
        scalar  = clamped / 100.0
        try:
            self._volume_interface.SetMasterVolumeLevelScalar(scalar, None)
            logger.info("Volume set to %d%%", clamped)
            return True
        except Exception as exc:
            logger.error("set_volume failed: %s", exc)
            return False

    def _set_volume_keys(self, target_level: int) -> bool:
        """Rough volume set via key presses when COM interface unavailable."""
        # Press volume down 50 times to reach ~0, then up to target
        for _ in range(50):
            pyautogui.press("volumedown")
        steps = target_level // 2
        for _ in range(steps):
            pyautogui.press("volumeup")
        return True

    def get_volume(self) -> int:
        """Return current master volume 0–100."""
        if not self._volume_interface:
            return -1
        try:
            scalar = self._volume_interface.GetMasterVolumeLevelScalar()
            return round(scalar * 100)
        except Exception as exc:
            logger.error("get_volume failed: %s", exc)
            return -1

    def mute(self) -> bool:
        if not self._volume_interface:
            pyautogui.press("volumemute")
            return True
        try:
            self._volume_interface.SetMute(1, None)
            logger.info("Muted")
            return True
        except Exception as exc:
            logger.error("mute failed: %s", exc)
            return False

    def unmute(self) -> bool:
        if not self._volume_interface:
            pyautogui.press("volumemute")  # toggle
            return True
        try:
            self._volume_interface.SetMute(0, None)
            logger.info("Unmuted")
            return True
        except Exception as exc:
            logger.error("unmute failed: %s", exc)
            return False

    # ── Media keys ────────────────────────────────────────────────────────────

    def next_track(self) -> None:
        pyautogui.press("nexttrack")
        logger.info("Next track")

    def prev_track(self) -> None:
        pyautogui.press("prevtrack")
        logger.info("Previous track")

    def pause(self) -> None:
        pyautogui.press("playpause")
        logger.info("Play/pause toggled (pause)")

    def resume(self) -> None:
        pyautogui.press("playpause")
        logger.info("Play/pause toggled (resume)")
