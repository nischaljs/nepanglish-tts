"""Stateful 22050 → 24000 Hz resampler.

Why not scipy.signal.resample? Two reasons:
  1. It's slow on ARM — no NEON path.
  2. Resampling sequential chunks independently produces audible clicks at
     every chunk boundary, because each call has no memory of the previous
     waveform's filter phase.

soxr.ResampleStream maintains its filter state across calls, so chunk
boundaries are mathematically continuous. The 'HQ' quality is the sweet
spot for speech — sounds clean, runs comfortably under realtime on a
Cortex-A72 thanks to NEON SIMD.

We currently call this in single-shot mode for the laptop test, but the
streaming API is the same one we'll use over WebSocket later.
"""

import numpy as np
import soxr

from . import config


class StreamingResampler:
    def __init__(
        self,
        in_rate: int = config.NATIVE_SAMPLE_RATE,
        out_rate: int = config.TARGET_SAMPLE_RATE,
    ):
        # When the rates match there's nothing to do — fast-path returns
        # incoming chunks unchanged. Saves ~5-10ms/chunk and avoids
        # creating a soxr stream we'd never use.
        self._passthrough = in_rate == out_rate
        self._stream = None
        if not self._passthrough:
            self._stream = soxr.ResampleStream(
                in_rate=in_rate,
                out_rate=out_rate,
                num_channels=1,
                dtype="float32",
                quality="HQ",
            )

    def push(self, chunk: np.ndarray) -> np.ndarray:
        """Feed a chunk in, get the corresponding resampled output. The
        stream remembers phase across calls so consecutive pushes line up."""
        if self._passthrough:
            return chunk
        return self._stream.resample_chunk(chunk, last=False)

    def flush(self) -> np.ndarray:
        """Drain the filter's tail. Call once after the final push()."""
        if self._passthrough:
            return np.zeros(0, dtype=np.float32)
        return self._stream.resample_chunk(
            np.zeros(0, dtype=np.float32), last=True
        )

    def resample_full(self, audio: np.ndarray) -> np.ndarray:
        """Single-shot helper: resample one complete utterance. Equivalent
        to push() + flush() concatenated."""
        if self._passthrough:
            return audio
        body = self.push(audio)
        tail = self.flush()
        return np.concatenate([body, tail]) if tail.size else body
