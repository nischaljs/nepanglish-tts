"""In-process TTS engine for Nova.

Imports nepali_tts directly instead of going through the HTTP daemon.
Same Python process holds Nova AND the synthesizer, so:

  - No HTTP roundtrip per request
  - No JSON serialization
  - Streaming chunks pipe straight from synth to sounddevice — first
    sentence is audible in ~1s, while the rest is still being made
  - WAV file is still written (so play_audio() stays a no-op for
    code paths that only want to *re-play* the last reply)

Use this on systems where you can run a single Python 3.10 venv with
both Nova's and nepali_tts's deps merged (typically a dev laptop).

On the Pi, where Nova's venv is 3.11 and fairseq won't import on
3.11+, you can't share a process — use scripts/nova_tts_engine.py
(the HTTP-daemon variant) instead.
"""

import asyncio
import os
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pygame

from config.config import AUDIO_PATH
from nepali_tts import get_synthesizer
from nepali_tts.player import play_stream

executor = ThreadPoolExecutor(max_workers=2)
music_paused = False
music_playing = False

# Lazy-init pygame.mixer so it doesn't grab the audio device at import
# time. sounddevice opens the device for streaming TTS playback; if
# pygame had it locked, sounddevice would block. Init pygame only when
# actual music playback (or fallback file replay) needs it.
def _ensure_mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.init()


print("[TTS] Loading Nepali TTS model (one-time)...")
_synth = get_synthesizer()
print(f"[TTS] Model ready (output rate: {_synth.output_sample_rate} Hz).")

# Tracks paths the synth-stream just played, so the immediately-following
# play_audio(path) call can no-op (audio is already out the speakers).
_streamed_lock = threading.Lock()
_streamed_path: str | None = None


# ─── audio file I/O ────────────────────────────────────────────────


def _write_wav(path: str, audio: np.ndarray, sample_rate: int) -> None:
    """Stdlib-only 16-bit mono WAV writer."""
    samples = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(samples.tobytes())


def _play_blocking(path):
    _ensure_mixer()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()


async def play_audio(path=AUDIO_PATH):
    """Play a wav via pygame UNLESS we just streamed it through sounddevice
    during text_to_speech (in which case audio is already out)."""
    abs_path = os.path.abspath(path)
    global _streamed_path
    with _streamed_lock:
        if _streamed_path == abs_path:
            _streamed_path = None
            print("[TTS] (already streamed in-process — skipping pygame replay)")
            return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, _play_blocking, path)


# ─── synthesis ─────────────────────────────────────────────────────


def _synth_stream_and_write(text: str, out_path: str) -> None:
    """Pipeline synth → sounddevice playback (chunk-by-chunk), AND tee
    each chunk into a list so we can write the full WAV at the end.

    The blocking is in stream.write() inside play_stream — it returns
    only after all chunks have been queued + drained, so by the time
    this function returns, audio has finished playing.
    """
    chunks: list[np.ndarray] = []

    def _tee():
        for c in _synth.synthesize_stream(text):
            chunks.append(c)
            yield c

    play_stream(_tee(), sample_rate=_synth.output_sample_rate)

    audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    _write_wav(out_path, audio, _synth.output_sample_rate)


async def text_to_speech(text, emotion="friendly", out_path=None):
    """Render `text` and play it streamingly. Returns out_path so callers
    that wanted a file path still get one.

    `emotion` is accepted for API compatibility with Nova's previous
    cloud-based TTS but ignored here — the Piper voice has a single
    timbre. Tweak nepali_tts/config.py (LENGTH_SCALE, NOISE_SCALE,
    NOISE_W) for global prosody changes.
    """
    out_path = out_path or AUDIO_PATH
    abs_out = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(abs_out) or ".", exist_ok=True)
    print(f"[TTS] In-process streaming → {abs_out}")
    t0 = time.time()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, _synth_stream_and_write, text, abs_out)
    # Mark so the upcoming play_audio() doesn't replay what we just streamed.
    global _streamed_path
    with _streamed_lock:
        _streamed_path = abs_out
    print(f"[TTS] Done in {(time.time()-t0)*1000:.0f}ms (streamed)")
    return out_path


# ─── music controls (unchanged from Nova's original) ───────────────


def pause_music():
    global music_paused
    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
        pygame.mixer.music.pause()
        music_paused = True
        print("Music paused!")
    else:
        print("Nothing playing to pause!")


def resume_music():
    global music_paused
    if pygame.mixer.get_init() and music_paused:
        pygame.mixer.music.unpause()
        music_paused = False
        print("Music resumed!")
    else:
        print(f"Cannot resume! init={pygame.mixer.get_init()}, paused={music_paused}")


def stop_music():
    global music_paused, music_playing
    if pygame.mixer.get_init():
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        music_paused = False
        music_playing = False
        print("Music stopped!")
    else:
        print("Nothing to stop!")
