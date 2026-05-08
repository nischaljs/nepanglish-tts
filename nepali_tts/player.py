"""Local audio playback — only used by the test harness.

In production, audio leaves the Pi over a WebSocket binary frame and the
ESP32 plays it. This module exists so we can hear the same audio on a
laptop while developing.
"""

import logging
from typing import Iterable

import numpy as np
import sounddevice as sd

from . import config

log = logging.getLogger(__name__)


def play(audio: np.ndarray, sample_rate: int = config.TARGET_SAMPLE_RATE) -> None:
    """Play a complete 1-D float32 waveform and block until it finishes."""
    if audio.size == 0:
        return
    sd.play(audio, samplerate=sample_rate, blocking=True)


def play_stream(
    chunks: Iterable[np.ndarray],
    sample_rate: int = config.TARGET_SAMPLE_RATE,
) -> None:
    """Play audio chunks the moment they arrive.

    Opens a sounddevice OutputStream, then writes each chunk into it as the
    iterator produces them. The first chunk starts playing almost
    immediately; later chunks queue up behind the audio currently playing.

    If the synthesizer falls behind playback (RTF > 1 with too-small
    chunks) you'd hear a gap. With sentence-sized chunks from sherpa,
    sentence 1 is usually long enough to mask the synth time of sentence 2.
    """
    # blocksize=0 lets PortAudio pick its own; channels=1 because the
    # Piper Nepali model is mono. dtype must match what we feed in.
    chunks_played = 0
    with sd.OutputStream(
        samplerate=sample_rate, channels=1, dtype="float32"
    ) as stream:
        for chunk in chunks:
            if not chunk.size:
                continue
            chunks_played += 1
            log.info(
                "player chunk %d playing  %.2fs of audio",
                chunks_played,
                chunk.size / sample_rate,
            )
            stream.write(chunk)
        log.info("player draining")
        # `with` block triggers stream.stop() which drains any audio
        # still queued in the device buffer before returning.
