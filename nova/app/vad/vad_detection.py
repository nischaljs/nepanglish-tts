from collections import deque

import numpy as np
import webrtcvad

from app.orchestration.event_bus import EventBus
from app.pipeline.process_audio import process_audio
from app.audio.utils import save_audio

speech_active = False
silence_frames = 0
speech_frames = 0
audio_buffer = []

pre_buffer = deque(maxlen=25)
RATE = 16000
FRAME_MS = 20
FRAME_SIZE = int(RATE * FRAME_MS / 1000)

vad = webrtcvad.Vad(3)

VOLUME_THRESHOLD = 600
SPEECH_CONFIRM_FRAMES = 5
# Silence threshold to consider speech ended. 4000ms made every turn
# wait an extra ~2.5s after the user finished talking. 1500ms still
# tolerates natural pauses but cuts most of the dead air.
SILENCE_LIMIT = int(1500 / FRAME_MS)

no_speech_frames = 0
NO_SPEECH_LIMIT = int(6000 / FRAME_MS)

_frame_count = 0

_event_bus = EventBus()


async def detect_speech(audio_data):
    global speech_active
    global silence_frames
    global speech_frames
    global audio_buffer
    global no_speech_frames
    global _frame_count

    frame = audio_data
    audio = np.frombuffer(frame, dtype=np.int16)

    _frame_count += 1
    volume = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
    vad_result = vad.is_speech(frame, RATE)

    is_speech = vad_result and volume > VOLUME_THRESHOLD

    pre_buffer.append(frame)

    if _frame_count % 10 == 0:
        print(f"[VAD] frame#{_frame_count} volume={volume:.0f} vad={int(vad_result)} is_speech={int(is_speech)}"
              f" speech_active={int(speech_active)} speech_frames={speech_frames} silence_frames={silence_frames}")

    if is_speech:
        no_speech_frames = 0
        speech_frames += 1

        if speech_frames >= SPEECH_CONFIRM_FRAMES and not speech_active:
            print(f"[VAD] ✓ SPEECH STARTED (volume={volume:.0f} > {VOLUME_THRESHOLD}, "
                  f"vad={int(vad_result)}, confirm_frames={speech_frames})")
            print(f"[VAD] Pre-buffer has {len(pre_buffer)} frames ({len(pre_buffer) * FRAME_MS}ms context)")
            speech_active = True
            audio_buffer.extend(pre_buffer)
            await _event_bus.publish("speech_started", {})

        if speech_active:
            audio_buffer.append(frame)

        silence_frames = 0

    else:
        speech_frames = 0

        if not speech_active:
            no_speech_frames += 1

            if no_speech_frames > NO_SPEECH_LIMIT:
                print(f"[VAD] ⏰ NO SPEECH TIMEOUT ({no_speech_frames * FRAME_MS}ms silence) → stopping stream")
                from app.communication.websocket import send_websocket_message
                await send_websocket_message("stop_stream")
                no_speech_frames = 0
                _frame_count = 0
                return

        if speech_active:
            silence_frames += 1
            audio_buffer.append(frame)

            if silence_frames > SILENCE_LIMIT:
                total_ms = len(audio_buffer) * FRAME_MS
                print(f"[VAD] ⏹ SPEECH ENDED ({silence_frames * FRAME_MS}ms silence)"
                      f" — total audio captured: {total_ms}ms ({len(audio_buffer)} frames)")

                audio = b"".join(audio_buffer)
                save_audio(audio)

                from app.communication.websocket import send_websocket_message
                await send_websocket_message("stop_stream")

                await process_audio()

                speech_active = False
                silence_frames = 0
                audio_buffer = []
                _frame_count = 0