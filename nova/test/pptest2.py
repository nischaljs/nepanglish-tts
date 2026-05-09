import wave

import numpy as np
import pyaudio
import webrtcvad

# Settings
RATE = 16000
FRAME_DURATION = 30
FRAME_SIZE = int(RATE * FRAME_DURATION / 1000)
VOLUME_THRESHOLD = 500
SILENCE_MARGIN = 2  # seconds of silence to end speech

# Derived values
silence_threshold_frames = int(SILENCE_MARGIN * 1000 / FRAME_DURATION)

#save audio to file
def save_audio(audio):

    wf = wave.open("speech.wav","wb")

    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)

    wf.writeframes(audio)
    wf.close()

    print("Saved speech.wav")

# Initialize
vad = webrtcvad.Vad(2)
pa = pyaudio.PyAudio()
stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=FRAME_SIZE)

speech_active = False
silence_frames = 0
audio_buffer = []

print("🎤 Listening... Speak into your microphone.")

try:
    while True:
        frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
        audio_data = np.frombuffer(frame, dtype=np.int16)
        volume = np.sqrt(np.mean(audio_data.astype(np.float32)**2)) if len(audio_data) > 0 else 0
        is_speech = vad.is_speech(frame, RATE) and volume > VOLUME_THRESHOLD

        if is_speech:
            audio_buffer.append(frame)
            silence_frames = 0
            if not speech_active:
                print("✅ Speech started!")
                speech_active = True
        else:
            if speech_active:
                silence_frames += 1
                audio_buffer.append(frame)  # still buffer a few silent frames
               

                if silence_frames > silence_threshold_frames:
                    print("🛑 Speech ended.")
                    print(f"Buffered {len(audio_buffer)} frames for STT/TTS.")
                    audio = b''.join(audio_buffer)
                    save_audio(audio)
                    # Reset buffer
                    audio_buffer = []
                    speech_active = False
                    silence_frames = 0
            # if speech not active, ignore silence

except KeyboardInterrupt:
    print("\n🛑 Stopped listening.")
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()

   

#     User speaks
#    ↓
# ESP32 + INMP441
#    ↓
# Audio sent to server (HTTP)
#    ↓
# Server converts speech → text
#    ↓
# Local AI model via Ollama
#    ↓
# AI returns structured response
#    ↓
# WebSocket sends command to ESP32
#    ↓
# ESP32 performs action (light on/off etc)