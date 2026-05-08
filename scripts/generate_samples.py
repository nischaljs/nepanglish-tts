"""Generate the audio demos that get embedded in the README.

Produces a small set of representative wavs in `samples/` so anyone
landing on the GitHub repo can hear what this thing sounds like *before*
deciding to install it. That's the single biggest factor in TTS-repo
adoption.

Run once:
    python scripts/generate_samples.py

Re-run any time you change voice settings or the seed dict and want to
refresh the demos.
"""

import sys
import wave
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nepali_tts import get_synthesizer  # noqa: E402

SAMPLES_DIR = PROJECT_ROOT / "samples"

# Each entry: (filename, text, one-line description shown in the README)
SAMPLES: list[tuple[str, str, str]] = [
    (
        "01_basic.wav",
        "नमस्ते, मेरो नाम नोवा हो। म एउटा robot हुँ।",
        "Basic Nepali greeting + a transliterated English word",
    ),
    (
        "02_nepanglish.wav",
        "यो robot को speed बढाउ। AC अन गर र light off गर।",
        "Mixed-script Nepanglish — English nouns inside Nepali grammar",
    ),
    (
        "03_pure_english.wav",
        "Hello, how are you doing today?",
        "Pure English read with a Nepali speaker's accent",
    ),
    (
        "04_numbers.wav",
        "आज २०२४ साल हो। मसँग 1500 रुपैयाँ छ।",
        "Numerals (both Devanagari and Latin) spoken naturally",
    ),
    (
        "05_streaming_long.wav",
        (
            "नेपाली र अङ्ग्रेजी शब्दहरू मिसाएर बोलिने भाषालाई प्रायः "
            "Neplish भनिन्छ, जुन आजभोलि हाम्रो दैनिक conversation मा "
            "एकदमै common भइसकेको छ। यदि हामीले आफ्नो time लाई सही "
            "तरिकाले manage गरेनौं भने, भविष्यमा धेरै problems फेस "
            "गर्नुपर्ने हुन सक्छ।"
        ),
        "Long real-world Nepanglish paragraph — streamed sentence by sentence",
    ),
    (
        "06_punctuation.wav",
        "She said “hello” — then left… नमस्ते।",
        "Smart quotes / em dashes / ellipses get cleaned up before synthesis",
    ),
]


def _save_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    pcm = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def main() -> int:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating samples into {SAMPLES_DIR}")

    synth = get_synthesizer()

    for filename, text, description in SAMPLES:
        out_path = SAMPLES_DIR / filename
        print(f"  {filename:30}  {description}")
        audio = synth.synthesize(text)
        _save_wav(out_path, audio, synth.output_sample_rate)

    print(f"\nDone. {len(SAMPLES)} sample(s) in {SAMPLES_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
