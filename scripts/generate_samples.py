"""Generate the audio demos that get embedded in the README.

Produces a small set of representative wavs in `samples/` plus a
companion .mp4 of each. The .wav is the source of truth; the .mp4 (an
AAC audio track in an mp4 container) is what we embed in the README,
because GitHub's markdown renderer plays `<video>`-tagged mp4 files
inline but doesn't render `<audio>` tags or auto-preview wavs.

Run once:
    python scripts/generate_samples.py

Re-run after editing prosody / loanword spellings to refresh the demos.

Requires `ffmpeg` on PATH (Arch: `sudo pacman -S ffmpeg`).
"""

import shutil
import subprocess
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


def _wav_to_mp4(wav_path: Path, mp4_path: Path) -> None:
    """Encode a wav to an audio-only mp4 (AAC). Smaller than the wav and
    — critically — plays inline in GitHub READMEs via the `<video>` tag.
    """
    if not shutil.which("ffmpeg"):
        print("  !! ffmpeg not found — skipping mp4 conversion", file=sys.stderr)
        return
    subprocess.run(
        [
            "ffmpeg",
            "-y",                    # overwrite without asking
            "-loglevel", "error",
            "-i", str(wav_path),
            "-c:a", "aac",
            "-b:a", "96k",           # plenty for speech
            "-movflags", "+faststart",  # let players start before full download
            str(mp4_path),
        ],
        check=True,
    )


def main() -> int:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating samples into {SAMPLES_DIR}")

    synth = get_synthesizer()

    for filename, text, description in SAMPLES:
        wav_path = SAMPLES_DIR / filename
        mp4_path = wav_path.with_suffix(".mp4")
        print(f"  {filename:30}  {description}")
        audio = synth.synthesize(text)
        _save_wav(wav_path, audio, synth.output_sample_rate)
        _wav_to_mp4(wav_path, mp4_path)

    print(f"\nDone. {len(SAMPLES)} sample(s) in {SAMPLES_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
