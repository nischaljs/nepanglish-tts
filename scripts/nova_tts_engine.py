"""TTS engine — talks to the local nepali_tts HTTP daemon for synthesis,
plays the resulting WAV via pygame. Music controls unchanged.

This file is the drop-in replacement for Nova's app/tts/tts_engine.py.
The installer (scripts/install_into_nova.sh) copies it into Nova.

The daemon must be running on localhost:5555 — start it with:
    cd ~/Documents/nepanglish-tts && bash run.sh daemon
"""

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pygame

from config.config import AUDIO_PATH

TTS_DAEMON_URL = os.environ.get("TTS_DAEMON_URL", "http://127.0.0.1:5555")
TTS_TIMEOUT_S = 60  # generous — Pi can take a while on long replies

executor = ThreadPoolExecutor()
music_paused = False
music_playing = False

pygame.mixer.init()


def _play_blocking(path):
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()


async def play_audio(path=AUDIO_PATH):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(executor, _play_blocking, path)


def _post_to_daemon(text, out_path):
    payload = json.dumps({"text": text, "out_path": out_path}).encode()
    req = urllib.request.Request(
        f"{TTS_DAEMON_URL}/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TTS_TIMEOUT_S) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"TTS daemon unreachable at {TTS_DAEMON_URL}. Start it with: "
            "cd ~/Documents/nepanglish-tts && bash run.sh daemon"
        ) from e


async def text_to_speech(text, emotion="friendly", out_path=None):
    out_path = out_path or AUDIO_PATH
    print(f"[TTS] Asking daemon to synthesize → {out_path}")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, _post_to_daemon, text, out_path)
    if result.get("status") != "ok":
        raise RuntimeError(f"TTS daemon error: {result}")
    print(f"[TTS] Render done in {result.get('duration_ms')}ms")
    return out_path


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
