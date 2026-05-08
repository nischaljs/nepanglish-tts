"""Local audio playback — only used by the test harness.

In production, audio leaves the Pi over a WebSocket binary frame and the
ESP32 plays it. This module exists so we can hear the same audio on a
laptop while developing.
"""

import numpy as np
import sounddevice as sd

from . import config


def play(audio: np.ndarray, sample_rate: int = config.TARGET_SAMPLE_RATE) -> None:
    """Play a 1-D float32 waveform and block until it finishes.

    No normalization — Piper's output already sits comfortably in [-1, 1].
    If you ever pipe in louder audio, the audio stack will hard-clip it.
    """
    if audio.size == 0:
        return
    sd.play(audio, samplerate=sample_rate, blocking=True)
