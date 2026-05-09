
import wave


def save_audio(audio):

    wf = wave.open("data/output_audio/speech.wav","wb")

    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)

    wf.writeframes(audio)
    wf.close()

    print("Saved speech.wav")