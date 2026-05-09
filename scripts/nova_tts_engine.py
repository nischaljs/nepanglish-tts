"""TTS engine — streams synthesis through the local nepali_tts HTTP daemon.

This file is the drop-in replacement for Nova's app/tts/tts_engine.py;
the installer (scripts/install_into_nova.sh) copies it into Nova.

How it works:
  - text_to_speech(text, out_path) POSTs to the daemon with stream=true.
    The daemon synthesizes sentence-by-sentence and plays each sentence
    through its own sounddevice output as it becomes ready (so the first
    sentence is audible in ~1s instead of waiting for the whole reply).
    A WAV file is also written at out_path for compatibility with code
    that wants to replay or save it.

  - When the request returns, we mark out_path as "already played". The
    next play_audio(out_path) call sees the marker and becomes a no-op,
    so audio doesn't play twice. play_audio() still does its normal
    pygame thing for *other* paths (music, prerecorded greetings, etc.).

The daemon must be running on localhost:5555 — start it with:
    cd ~/Documents/nepanglish-tts && bash run.sh daemon
"""

import asyncio
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pygame

from config.config import AUDIO_PATH

TTS_DAEMON_URL = os.environ.get("TTS_DAEMON_URL", "http://127.0.0.1:5555")
TTS_TIMEOUT_S = 120  # streaming includes playback time, so be generous

# Set TTS_STREAM=0 to disable daemon-side streaming playback and fall
# back to "render whole WAV → pygame plays it" — useful if your audio
# device can't be shared between this process (pygame) and the daemon
# (sounddevice). Default is streaming on, because streaming makes the
# first sentence audible ~5s sooner on long replies.
TTS_STREAM_DEFAULT = os.environ.get("TTS_STREAM", "1") != "0"

executor = ThreadPoolExecutor()
music_paused = False
music_playing = False

# Tracks the path of audio the daemon just streamed/played for us, so
# the immediately-following play_audio(path) call can no-op.
_streamed_lock = threading.Lock()
_streamed_path: str | None = None


def _ensure_mixer():
    """Init pygame.mixer the first time it's actually needed.

    Why lazy: if we init at import, pygame grabs the audio device and
    the daemon's sounddevice can't open it for streaming playback.
    Init-on-demand means we hold the device only when music or
    fallback (non-streamed) playback actually runs.
    """
    if not pygame.mixer.get_init():
        pygame.mixer.init()


def _play_blocking(path):
    _ensure_mixer()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()


async def play_audio(path=AUDIO_PATH):
    """Play `path` through pygame, UNLESS the daemon just streamed it
    for us (in which case the audio already came out of the speakers
    and a pygame replay would double it up)."""
    abs_path = os.path.abspath(path)
    global _streamed_path
    with _streamed_lock:
        if _streamed_path == abs_path:
            _streamed_path = None
            print(f"[TTS] (already streamed by daemon — skipping pygame replay)")
            return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, _play_blocking, path)


def _post_to_daemon(text, out_path):
    # Resolve to absolute — Nova's CWD differs from the daemon's, so a
    # relative path would land in the wrong place (or fail to write).
    out_path = os.path.abspath(out_path)
    payload = json.dumps({
        "text": text,
        "out_path": out_path,
        "stream": TTS_STREAM_DEFAULT,  # daemon plays as it synthesizes
    }).encode()
    req = urllib.request.Request(
        f"{TTS_DAEMON_URL}/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT_S) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # Daemon WAS reachable but returned a non-2xx — surface its
        # actual error message rather than a generic "unreachable".
        try:
            body = json.loads(e.read())
            msg = body.get("message", str(e))
        except Exception:
            msg = str(e)
        raise RuntimeError(f"TTS daemon error ({e.code}): {msg}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"TTS daemon unreachable at {TTS_DAEMON_URL}. Start it with: "
            "cd ~/Documents/nepanglish-tts && bash run.sh daemon"
        ) from e


async def text_to_speech(text, emotion="friendly", out_path=None):
    out_path = out_path or AUDIO_PATH
    abs_out = os.path.abspath(out_path)
    print(f"[TTS] Streaming via daemon → {abs_out}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, _post_to_daemon, text, out_path)
    if result.get("status") != "ok":
        raise RuntimeError(f"TTS daemon error: {result}")
    # Mark the path so the upcoming play_audio() call skips the replay.
    if result.get("played"):
        global _streamed_path
        with _streamed_lock:
            _streamed_path = abs_out
    print(f"[TTS] Done in {result.get('duration_ms')}ms (played via daemon stream)")
    return out_path


def pause_music():
    global music_paused
    # Don't _ensure_mixer here — if mixer isn't inited, nothing can be playing.
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
