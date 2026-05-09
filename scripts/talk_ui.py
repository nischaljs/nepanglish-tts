"""Headless local entry point for Nova — webcam + press-to-talk.

Run from the repo root (or anywhere — paths are computed automatically):

    .venv/bin/python scripts/talk_ui.py

The webcam runs in a background thread (used for face recognition) but
no preview window is shown — saves CPU and avoids Qt/Wayland headaches.
Face state changes are logged to the terminal instead.

  ENTER → record N seconds, transcribe, reply, speak it back
  /3 /5 /7 → change recording length
  /face   → print current recognition snapshot
  /q      → quit

Single command, full local pipeline: camera + mic + STT + LLM + TTS.
No HTTP daemon, no ESP32, no Pi.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path

import cv2


# ── path setup so this script can be run from anywhere ─────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
NOVA_DIR = REPO_ROOT / "nova"
FACE_DIR = REPO_ROOT / "face-recognition"
sys.path.insert(0, str(NOVA_DIR))
sys.path.insert(0, str(FACE_DIR))
os.chdir(NOVA_DIR)


# ── Nova + face imports (after path setup) ─────────────────────────
from face_recognition_system.detector import detect_faces  # noqa: E402

from app.face.context import build_face_context  # noqa: E402
from app.face.face_tools import FrameBuffer, get_bridge  # noqa: E402
from app.llm.groq import get_active_model, groq_llm_json, set_face_context  # noqa: E402
from app.stt.whisper import transcribe_audio  # noqa: E402
from app.tts.tts_engine import play_audio, text_to_speech  # noqa: E402
from config.config import AUDIO_PATH  # noqa: E402


CYAN = "\033[1;36m"
YEL = "\033[1;33m"
GRN = "\033[0;32m"
GRY = "\033[0;90m"
NC = "\033[0m"


_running = True
_last_face_info: dict | None = None
_state_lock = threading.Lock()

# Set during a turn (recording → STT → LLM → TTS). The camera thread
# keeps grabbing frames (cheap) but skips the expensive face detection +
# recognition pass while busy. Frees ~30-50% of a CPU core for the
# audio pipeline at exactly the moments that matter.
_turn_busy = threading.Event()


def _face_state_key(info: dict | None) -> str:
    """Compact key for change-detection logging."""
    if not info:
        return "no-face"
    if info.get("unknown"):
        return "unknown"
    return f"known:{info.get('id', '?')}"


def _camera_loop():
    """Open the webcam, push frames to FrameBuffer, run recognition.

    Runs in a thread so the main thread can do voice I/O. No preview
    window — face state changes are printed to the terminal so the user
    still knows who Nova thinks it's looking at.
    """
    global _last_face_info

    cap = None
    for idx in (0, 1, 2, 3):
        c = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not c.isOpened():
            c.release()
            continue
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        good = False
        for _ in range(10):
            ok, fr = c.read()
            if ok and fr is not None and fr.mean() > 4:
                good = True
                break
            time.sleep(0.05)
        if good:
            cap = c
            print(f"{GRN}[CAM]{NC} using /dev/video{idx} (V4L2, headless)")
            break
        c.release()

    if cap is None:
        print(f"{YEL}[CAM]{NC} no working webcam found — voice still works")
        return

    bridge = get_bridge()
    last_recog = 0.0
    last_logged = "no-face"

    while _running:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        FrameBuffer().update(frame)

        now = time.time()
        # While a turn is in flight, frames keep flowing into FrameBuffer
        # (so anything Nova-internal that reads the buffer still sees a
        # live image), but we skip the CPU-heavy detect/recognize work.
        # Resumes the moment the turn finishes.
        if _turn_busy.is_set():
            time.sleep(0.03)
            continue

        if now - last_recog > 0.5:
            try:
                faces = detect_faces(frame) or []
                if faces:
                    info = bridge.recognize(frame)
                else:
                    info = None
                with _state_lock:
                    _last_face_info = info

                key = _face_state_key(info)
                if key != last_logged:
                    if key == "no-face":
                        print(f"{GRY}[FACE] gone{NC}")
                    elif key == "unknown":
                        print(f"{YEL}[FACE] unknown person{NC}")
                    else:
                        name = info.get("name", "?") if info else "?"
                        conf = info.get("confidence", 0.0) if info else 0.0
                        print(f"{GRN}[FACE] {name}{NC} ({int(conf * 100)}%)")
                    last_logged = key
            except Exception:
                pass
            last_recog = now

    cap.release()


# ── Voice I/O (main thread, async) ────────────────────────────────


async def _record_vad(max_seconds: int = 8, silence_ms: int = 500) -> str:
    """Record from the mic, auto-stop when the speaker pauses.

    Streams 30 ms frames through webrtcvad. Stops when we've seen at
    least min_speech_ms of voice followed by silence_ms of non-voice,
    or when we hit max_seconds (failsafe). Saves the trimmed clip to
    data/output_audio/speech.wav so the rest of the pipeline is
    untouched.
    """
    import queue

    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    import webrtcvad

    rate = 16000
    frame_ms = 30
    frame_len = int(rate * frame_ms / 1000)
    max_frames = int(max_seconds * 1000 / frame_ms)
    silence_frames = int(silence_ms / frame_ms)
    min_speech_frames = int(300 / frame_ms)  # require ~300 ms of voice before silence can stop us

    # Aggressiveness 3 (most strict) — only counts confident-voice frames
    # as speech. With 2, fan/keyboard/breath noise was tagged as speech
    # and the auto-stop never fired, so every clip ran the full 8s and
    # Whisper hallucinated extra words from the trailing silence.
    vad = webrtcvad.Vad(3)
    q: queue.Queue[bytes] = queue.Queue()

    def cb(indata, frames, time_info, status):
        q.put(bytes(indata))

    print(f"  {CYAN}● listening — speak (auto-stop on silence, max {max_seconds}s){NC}")
    collected: list[bytes] = []
    silent_run = 0
    speech_seen = 0

    with sd.RawInputStream(
        samplerate=rate, blocksize=frame_len, channels=1, dtype="int16", callback=cb,
    ):
        for _ in range(max_frames):
            data = q.get()
            collected.append(data)
            if vad.is_speech(data, rate):
                speech_seen += 1
                silent_run = 0
            else:
                silent_run += 1
                if speech_seen >= min_speech_frames and silent_run >= silence_frames:
                    break

    audio = np.frombuffer(b"".join(collected), dtype=np.int16).reshape(-1, 1)
    out_dir = "data/output_audio"
    os.makedirs(out_dir, exist_ok=True)
    out = f"{out_dir}/speech.wav"
    sf.write(out, audio, rate)
    duration = len(audio) / rate
    print(f"  {GRY}({duration:.1f}s captured){NC}")
    return out


def _maybe_register_face(name: str) -> dict | None:
    """If there's an unknown face on screen, save it under `name`.

    Called when the LLM emits `type: "register"` with a captured name.
    Pulls the latest frame from FrameBuffer (kept fresh by the camera
    thread), hands it to the bridge, and returns the new identity dict
    so we can switch the LLM context over to it for the next turn.
    """
    if not name or not name.strip():
        return None
    frame = FrameBuffer().get_frame()
    if frame is None:
        print(f"  {YEL}[FACE]{NC} can't register {name!r} — no camera frame")
        return None
    bridge = get_bridge()
    # Only register if the face we see right now is actually unknown —
    # otherwise we'd duplicate an existing identity under a new name.
    with _state_lock:
        current = _last_face_info
    if current and not current.get("unknown"):
        print(f"  {YEL}[FACE]{NC} face already known as {current.get('name')!r} — skipping register")
        return None
    try:
        result = bridge.register(frame, name)
    except Exception as e:
        print(f"  {YEL}[FACE]{NC} register failed: {e}")
        return None
    if not result:
        print(f"  {YEL}[FACE]{NC} register returned nothing (face not detected in frame?)")
        return None
    # bridge.register returns either a bare id string or a dict like
    # {"id": "...", "name": "..."} depending on the wrapper layer —
    # normalize to a plain string id either way.
    identity_id = result["id"] if isinstance(result, dict) else str(result)
    print(f"  {GRN}[FACE]{NC} registered {name!r} as id {identity_id}")
    return {"id": identity_id, "name": name, "confidence": 1.0, "unknown": False}


async def _chat_once(user_text: str):
    with _state_lock:
        info = _last_face_info
    face_ctx = ""
    face_id = None
    if info and not info.get("unknown"):
        face_ctx = build_face_context(info)
        face_id = info.get("id")
    set_face_context(face_ctx, face_id)

    print(f"  {GRY}thinking…{NC}")
    t0 = time.time()
    resp = await groq_llm_json(user_text)
    t_llm = time.time() - t0

    text = resp.get("response", "")
    print(f"  {YEL}Nova{NC} [{get_active_model()}, {t_llm * 1000:.0f} ms]: {text!r}")

    # If the LLM captured a name in a register intent, persist the face
    # → name mapping NOW so subsequent turns recognize this person and
    # the LLM can greet them by name. Also push the new identity into
    # face context immediately, so the very next turn already personal.
    if resp.get("type") == "register" and resp.get("name"):
        new_info = await asyncio.to_thread(_maybe_register_face, resp["name"])
        if new_info:
            with _state_lock:
                globals()["_last_face_info"] = new_info
            set_face_context(build_face_context(new_info), new_info["id"])

    if not text:
        return
    t0 = time.time()
    f = await text_to_speech(text, out_path=AUDIO_PATH)
    await play_audio(f)
    print(f"  {GRY}(spoken in {(time.time() - t0) * 1000:.0f} ms){NC}")


async def _voice_loop(max_seconds: int = 8):
    seconds = max_seconds
    print()
    print(f"{YEL}Press ENTER to talk to Nova{NC} (auto-stop on silence, max {seconds}s).")
    print(f"  {GRY}LLM: {get_active_model()}  (auto-falls-back to 8B on rate limit){NC}")
    print(f"  /5 /8 /12 → change max recording length")
    print(f"  /face    → show current face recognition")
    print(f"  /q       → quit")
    print()

    loop = asyncio.get_running_loop()

    while _running:
        try:
            line = await loop.run_in_executor(None, input, f"{CYAN}you{NC} (ENTER to talk): ")
        except (EOFError, KeyboardInterrupt):
            return
        line = line.strip()

        if line in ("/q", "/quit", "/exit"):
            return
        if line == "/face":
            with _state_lock:
                info = _last_face_info
            print(f"  face: {info!r}")
            continue
        if line in ("/5", "/8", "/12"):
            seconds = int(line[1:])
            print(f"  max recording length set to {seconds}s")
            continue
        if line.startswith("/"):
            print(f"  unknown command — try /q to quit")
            continue

        # Pause face recognition for the duration of this turn so the
        # camera thread isn't burning a CPU core while we're recording,
        # transcribing, talking to the LLM, and synthesizing audio.
        _turn_busy.set()
        try:
            wav = await _record_vad(max_seconds=seconds)
            text = await asyncio.to_thread(transcribe_audio)
            print(f"  you said: {text!r}")
            if text and len(text.strip()) >= 2:
                await _chat_once(text)
            else:
                print(f"  (didn't catch that — try again)")
        except Exception as e:
            print(f"  ERROR: {e.__class__.__name__}: {e}")
        finally:
            _turn_busy.clear()


def main():
    print(f"{YEL}Nova local{NC} — camera (headless) + voice, all on this laptop")
    print(f"  loading models...")

    # Pre-warm the AI4Bharat English→Devanagari transliterator now, in a
    # background thread. Otherwise the very first reply that contains a
    # Latin word ("exhibition", "music", etc) blocks ~20 s while torch +
    # the multilingual model load synchronously inside text_to_speech().
    def _warm_translit():
        try:
            from nepali_tts.transliterator import warm_up
            warm_up()
            print(f"{GRY}[warm] transliterator ready{NC}")
        except Exception as e:
            print(f"{YEL}[warm]{NC} transliterator pre-warm failed: {e}")

    threading.Thread(target=_warm_translit, name="warm-translit", daemon=True).start()

    cam_thread = threading.Thread(target=_camera_loop, name="nova-cam", daemon=True)
    cam_thread.start()

    try:
        asyncio.run(_voice_loop())
    except KeyboardInterrupt:
        pass
    finally:
        globals()["_running"] = False
        cam_thread.join(timeout=2.0)
        print(f"{GRY}bye.{NC}")


if __name__ == "__main__":
    main()
