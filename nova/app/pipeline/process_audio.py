import asyncio
import os
import time

import cv2

from app.audio.player import download_and_play
from app.face.context import build_face_context
from app.face.face_tools import FrameBuffer, get_bridge
from app.llm.groq import groq_llm_json, set_face_context
from app.orchestration.event_bus import EventBus
from app.orchestration.interaction_lock import InteractionLock
from app.pipeline.process_transcript import handle_command
from app.stt.whisper import transcribe_audio
from app.tts.tts_engine import (
    pause_music,
    play_audio,
    resume_music,
    stop_music,
    text_to_speech,
)
from config.config import AUDIO_PATH

CONVO_AUDIO_PATH = os.path.join(os.path.dirname(AUDIO_PATH), "convo.wav")

_CURRENT_FACE = None


def update_face_context(face_info: dict | None):
    global _CURRENT_FACE
    _CURRENT_FACE = face_info
    ctx = build_face_context(face_info) if face_info else ""
    face_id = face_info.get("id") if face_info else None
    print(f"[PIPELINE] Face context → ctx='{ctx}' face_id={face_id}")
    set_face_context(ctx, face_id)


def _recognize_snapshot():
    t0 = time.time()
    frame, ts = FrameBuffer().get()
    if frame is None:
        print(f"[PIPELINE] Face snapshot: no frame available (took {time.time()-t0:.2f}s)")
        return None
    result = get_bridge().recognize(frame)
    elapsed = time.time() - t0
    if not result or result.get("unknown"):
        print(f"[PIPELINE] Face snapshot: unknown or no face (took {elapsed:.2f}s)")
        return None
    print(f"[PIPELINE] Face snapshot → {result.get('name')} "
          f"conf={result.get('confidence')} id={result.get('id')} (took {elapsed:.2f}s)")
    return result


def _register_sync(frame, name) -> bool:
    t0 = time.time()
    small = cv2.resize(frame, None, fx=0.5, fy=0.5)
    ok = bool(get_bridge().register(small, name))
    print(f"[PIPELINE] Face register({name}) → {'✓' if ok else '✗'} (took {time.time()-t0:.2f}s)")
    return ok


async def _register_face(name: str) -> bool:
    if not name:
        print("[PIPELINE] Face register skipped: empty name")
        return False
    try:
        t0 = time.time()
        frame, ts = FrameBuffer().get()
        if frame is None:
            print("[PIPELINE] Face register failed: no frame from camera")
            return False
        print(f"[PIPELINE] Registering face for '{name}' from camera frame (age={time.time()-ts:.1f}s)")
        ok = await asyncio.to_thread(_register_sync, frame, name)
        print(f"[PIPELINE] Register '{name}' → {'✓' if ok else '✗'} (took {time.time()-t0:.1f}s)")
        return ok
    except Exception as e:
        print(f"[PIPELINE] Face registration error: {e}")
        return False


async def _speak(text: str, out_path: str = AUDIO_PATH):
    event_bus = EventBus()
    await event_bus.publish("tts_started", {"text": text})
    t0 = time.time()
    print(f"[PIPELINE] TTS start: '{text[:80]}'")
    file = await text_to_speech(text, out_path=out_path)
    print(f"[PIPELINE] TTS render done ({time.time()-t0:.1f}s) → playing...")
    await play_audio(file)
    print(f"[PIPELINE] TTS playback done (total {time.time()-t0:.1f}s)")
    await event_bus.publish("tts_finished", {"text": text})


async def process_audio():
    lock = InteractionLock()
    event_bus = EventBus()

    await lock.release("speech")

    if lock.is_active and not lock.is_inactive:
        print(f"[PIPELINE] Interaction lock active — pipeline paused")
        return

    await lock.acquire("pipeline")

    print("[PIPELINE] ═══════ STARTING PIPELINE ═══════")
    t_pipeline = time.time()

    face_info = _CURRENT_FACE
    print(f"[PIPELINE] Cached face context: {face_info}")

    await event_bus.publish("speech_ended", {"face_info": face_info})

    text = await asyncio.to_thread(transcribe_audio)
    print(f"[PIPELINE] STT result: '{text}' (took {time.time()-t_pipeline:.1f}s)")

    if not text or len(text.strip()) < 2:
        print(f"[PIPELINE] ✗ Empty/invalid transcription — skipping ({time.time()-t_pipeline:.1f}s)")
        await lock.release("pipeline")
        return

    print("[PIPELINE] Calling LLM...")
    t_llm = time.time()
    response = await groq_llm_json(text)
    print(f"[PIPELINE] LLM response ({time.time()-t_llm:.1f}s): {response}")

    reply = response.get("response", "")
    convo_reply = response.get("convo", "")

    if reply.strip():
        print(f"[PIPELINE] Nova says: '{reply}'")
        await _speak(reply)

    rtype = response.get("type")

    if rtype == "command":
        target = response.get("target")
        action = response.get("action")
        print(f"[PIPELINE] Command: target={target} action={action}")

        if target == "music":
            if action == "play":
                song = response.get("song", text)
                print(f"[PIPELINE] Playing music: {song}")
                asyncio.create_task(download_and_play(song))
            elif action == "pause":
                print("[PIPELINE] Music pause")
                pause_music()
            elif action == "resume":
                print("[PIPELINE] Music resume")
                resume_music()
            elif action == "stop":
                print("[PIPELINE] Music stop")
                stop_music()
        else:
            result = handle_command(response)
            print(f"[PIPELINE] IoT command result: {result}")
            try:
                from app.communication.websocket import broadcast
                await broadcast({"type": "command", "payload": result})
            except Exception as e:
                print(f"[PIPELINE] Error broadcasting command: {e}")

    elif rtype == "register":
        name = (response.get("name") or "").strip()
        if name:
            ok = await _register_face(name)
            if ok:
                print(f"[PIPELINE] ✓ Registered: {name}")
                await event_bus.publish("user_registered", {"name": name})
            else:
                print(f"[PIPELINE] ✗ Failed to register {name}")
        else:
            print(f"[PIPELINE] Register type but no name in response")

    elif rtype in ("conversation_continue", "followup_question"):
        print(f"[PIPELINE] Continuing conversation: type={rtype}")

    elif rtype == "session_end":
        print(f"[PIPELINE] Session end requested")
    total = time.time() - t_pipeline
    print(f"[PIPELINE] ═══════ PIPELINE DONE ({total:.1f}s) ═══════")
    try:
        from app.communication.websocket import send_websocket_message
        await send_websocket_message("start_stream")
        print("[PIPELINE] Sent: start_stream → ready for next utterance")
    except Exception as e:
        print(f"[PIPELINE] Error sending start_stream: {e}")

    await event_bus.publish("pipeline_complete", {"duration": total})
    await lock.release("pipeline")
