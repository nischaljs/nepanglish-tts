import asyncio
import wave
from collections import deque

import numpy as np
import webrtcvad
import websockets

# RATE = 16000
# FRAME_MS = 20
# FRAME_SIZE = int(RATE * FRAME_MS / 1000)

# vad = webrtcvad.Vad(3)

# VOLUME_THRESHOLD = 400
# SPEECH_CONFIRM_FRAMES = 5
# SILENCE_LIMIT = int(2000 / FRAME_MS)

# async def handler(ws):

#     print("ESP connected")

#     speech_active = False
#     silence_frames = 0
#     speech_frames = 0

#     audio_buffer = []
#     pre_buffer = deque(maxlen=25)

#     try:
#         async for message in ws:

#             frame = message

#             audio = np.frombuffer(frame, dtype=np.int16)

#             volume = np.sqrt(np.mean(audio.astype(np.float32)**2))

#             vad_result = vad.is_speech(frame, RATE)

#             is_speech = vad_result and volume > VOLUME_THRESHOLD

#             pre_buffer.append(frame)

#             if is_speech:

#                 speech_frames += 1

#                 if speech_frames >= SPEECH_CONFIRM_FRAMES and not speech_active:

#                     print("Speech started")

#                     speech_active = True
#                     audio_buffer.extend(pre_buffer)

#                 if speech_active:

#                     audio_buffer.append(frame)

#                 silence_frames = 0

#             else:

#                 speech_frames = 0

#                 if speech_active:

#                     silence_frames += 1
#                     audio_buffer.append(frame)

#                     if silence_frames > SILENCE_LIMIT:

#                         print("Speech ended")

#                         audio = b''.join(audio_buffer)
#                         save_audio(audio)

#                         await ws.send("stop_stream")

#                         speech_active = False
#                         silence_frames = 0
#                         audio_buffer = []

#     except websockets.exceptions.ConnectionClosed:

#         print("ESP disconnected")


# def save_audio(audio):

#     wf = wave.open("data/output_audio/speech.wav","wb")

#     wf.setnchannels(1)
#     wf.setsampwidth(2)
#     wf.setframerate(16000)

#     wf.writeframes(audio)
#     wf.close()

#     print("Saved speech.wav")


# async def main():

#     async with websockets.serve(handler,"0.0.0.0",8080):

#         print("Server started")

#         await asyncio.Future()


# asyncio.run(main())