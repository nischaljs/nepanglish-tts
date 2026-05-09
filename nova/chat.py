"""Interactive REPL for the Nova welcome bot.

Type a message and hit Enter — Nova replies through the Pi speaker.
Commands:
  /v                    record 5s from the Pi mic, transcribe, get a reply
  /known <name>         pretend a known visitor (sets face context + id)
  /unknown              pretend nobody is recognized
  /face                 show current face context
  /q  /quit  /exit      quit
"""

import asyncio
import builtins
import datetime
import sys

import cv2

_original_print = builtins.print
def _ts_print(*args, **kwargs):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    _original_print(f"{ts}", *args, **kwargs)
builtins.print = _ts_print

from app.face.face_tools import FrameBuffer, get_bridge
from app.llm.groq import groq_llm_json, set_face_context
from app.tts.tts_engine import play_audio, text_to_speech
from config.config import AUDIO_PATH


CYAN = "\033[1;36m"
YEL = "\033[1;33m"
GRN = "\033[0;32m"
GRY = "\033[0;90m"
NC = "\033[0m"


async def speak(text: str):
    f = await text_to_speech(text, out_path=AUDIO_PATH)
    await play_audio(f)


async def chat_once(user_text: str, face_ctx: str, face_id: str | None):
    set_face_context(face_ctx, face_id)
    resp = await groq_llm_json(user_text)
    meta = (
        f"type={resp.get('type')} target={resp.get('target')} "
        f"action={resp.get('action')} name={resp.get('name')!r}"
    )
    print(f"  {GRY}{meta}{NC}")

    if resp.get("type") == "register":
        name = (resp.get("name") or "").strip()
        if name:
            fb = FrameBuffer()
            frame, _ = fb.get()
            if frame is not None:
                small = cv2.resize(frame, None, fx=0.5, fy=0.5)
                result = get_bridge().register(small, name)
                if result:
                    face_id = result["id"]
                    face_ctx = f"You are talking to {name}. They have visited before."
                    print(f"  {GRN}✓ Face registered{NC}: {name} (id={face_id})")

    if resp.get("response"):
        print(f"  {YEL}Nova{NC}: {resp['response']}")
        await speak(resp["response"])
    if resp.get("convo"):
        print(f"  {YEL}Nova{NC}: ({resp['convo']})")
        await speak(resp["convo"])
    return face_ctx, face_id


async def cmd_voice(face_ctx: str, face_id: str | None, seconds: int = 5):
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError as e:
        print(f"  voice mode needs sounddevice + soundfile — pip install missing: {e}")
        return
    rate = 16000
    print(f"  ● Recording {seconds}s … speak now")
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=1, dtype="int16")
    sd.wait()
    out = "data/output_audio/speech.wav"
    sf.write(out, audio, rate)
    print(f"  ● Saved {out}, transcribing …")
    from app.stt.whisper import transcribe_audio
    text = await asyncio.to_thread(transcribe_audio)
    print(f"  ● Transcribed: {text!r}")
    if text and len(text.strip()) >= 2:
        await chat_once(text, face_ctx, face_id)
    else:
        print("  (empty / too short — skipping)")


def help_text() -> str:
    return __doc__ or ""


async def main():
    print()
    print(f"{YEL}Nova interactive REPL{NC}  —  /q to quit, /h for commands")
    print()
    face_ctx = ""
    face_id = None

    while True:
        try:
            line = input(f"{CYAN}you{NC}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not line:
            continue
        low = line.lower()

        if low in ("/q", "/quit", "/exit"):
            return
        if low in ("/h", "/help", "?"):
            print(help_text())
            continue
        if low == "/v":
            await cmd_voice(face_ctx, face_id)
            continue
        if low == "/face":
            print(f"  context={face_ctx!r}  face_id={face_id!r}")
            continue
        if low == "/unknown":
            face_ctx, face_id = "", None
            print("  face context cleared (unknown visitor)")
            continue
        if low.startswith("/known "):
            name = line[len("/known "):].strip()
            if not name:
                print("  usage: /known <Name>")
                continue
            face_id = f"manual-{name.lower()}"
            fb = FrameBuffer()
            frame, _ = fb.get()
            if frame is not None:
                small = cv2.resize(frame, None, fx=0.5, fy=0.5)
                result = get_bridge().register(small, name)
                if result:
                    face_id = result["id"]
                    print(f"  {GRN}✓ Face registered from camera{NC}: {name}")
            face_ctx = (
                f"You are talking to {name}. "
                f"They have visited 2 times before."
            )
            print(f"  face context set → {name} (id={face_id})")
            continue
        if line.startswith("/"):
            print(f"  unknown command. Try /h for help.")
            continue

        face_ctx, face_id = await chat_once(line, face_ctx, face_id) or (face_ctx, face_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
