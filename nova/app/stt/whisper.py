
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()


# def transcribe_audio():
#     print("Transcribing")r
#     whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
#     segments, _ = whisper_model.transcribe("speech.wav", language="en")
#     text = " ".join([seg.text for seg in segments])
#     return text


client = Groq(api_key=os.getenv("GROQ"))


# Domain prompt — primes Whisper's decoder so proper nouns and Nova-specific
# vocabulary are recognized correctly. Plain comma-separated text works best;
# the model treats it as "stuff that came right before this audio clip."
_NOVA_PROMPT = (
    "नोवा, युब्राज, निश्चल, काठमाडौं, नेपाल, "
    "लाइट, फ्यान, म्युजिक, फोन, कम्प्युटर, गीत, "
    "अन गर, अफ गर, बजाऊ, रोक, "
    "नमस्ते, धन्यवाद, कस्तो छ, के गर्दै छौ, "
    "मेरो नाम, तिम्रो नाम, भन्नुहोस्, सुन्नुहोस्। "
    "Nova, Yubraj, light, fan, music, play, stop."
)


def transcribe_audio(filepath="data/output_audio/speech.wav"):
    print("Transcribing...")
    with open(filepath, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            # Full large-v3 (not the distilled turbo) — turbo loses notable
            # accuracy on low-resource languages like Nepali. ~400 ms slower
            # but worth it: fewer "Sorry, didn't catch that" loops.
            model="whisper-large-v3",
            file=audio_file,
            # Force Nepali. Auto-detect on short clips frequently misroutes
            # Nepali → Hindi/Urdu (same script, related languages). Nepali
            # mode still handles code-switched English words correctly.
            language="ne",
            # Prime the decoder with Nova-specific vocabulary so names and
            # domain commands get transcribed accurately.
            prompt=_NOVA_PROMPT,
            # Greedy decoding — deterministic, no sampling jitter.
            temperature=0.0,
        )
    text = transcription.text
    print(f"Transcribed: {text}")
    return text


