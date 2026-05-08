"""Pre-rendered short phrases the robot can say *instantly*.

The motivating use case: the user finishes asking something. The LLM is
about to take 1-3 seconds to respond. The robot sits in awkward silence.

Solution: the moment the wake word fires, play a pre-rendered "हजुर?" or
"एक छिन है". By the time the filler finishes, the LLM has hopefully
answered and we can flow straight into the real reply. To the listener
the robot feels alert and continuous, even though the heavy lifting is
still happening in the background.

How it works:
  1. First call to render_fillers() synthesizes each phrase once and
     saves a wav alongside the model files.
  2. play_filler(name) loads the cached wav and plays it through
     sounddevice. No model touched, no transliteration, no resampler.
     Latency is dominated by PortAudio's setup time (~50ms).

Add or replace phrases by editing DEFAULT_FILLERS or passing your own
dict to render_fillers().
"""

import logging
import wave
from pathlib import Path
from typing import Mapping

import numpy as np

from . import config

log = logging.getLogger(__name__)

# Where the rendered wavs live. Sits next to the model so it travels
# with whichever user setup we're on.
FILLER_DIR = config.MODELS_DIR / "fillers"

# Default fillers are deliberately *non-committal* thinking sounds. We
# avoid pure vocalizations like "हम्म" / "उम्म" because TTS models are
# trained on words and tend to mispronounce non-word vocalizations
# (espeak's Nepali phonemizer reads "हम्म" as "ha-m-ma", which sounds
# like "amma"). The sounds below are real Nepali interjections the model
# has heard plenty of times in training, so they synthesize cleanly.
#
# A robot saying "हजुर?" or "एक छिन है" feels stiff/over-polite —
# something noncommittal like "अहँ" or "ओहो" works much better as a
# brief filler while the LLM thinks. Override or extend by passing your
# own dict to render_fillers().
DEFAULT_FILLERS: Mapping[str, str] = {
    "ah":  "अहँ...",        # "uhh" / "huh" — acknowledgement / hesitation
    "oh":  "ओहो...",        # "oh" — mild surprise / realizing
    "eh":  "एऽ...",         # casual hesitation
    "la":  "ल त...",        # "well so..." — common conversational filler
}

# Loaded wavs cached in memory so play_filler is microsecond-fast after
# the first call.
_loaded: dict[str, tuple[np.ndarray, int]] = {}


# ---- rendering -----------------------------------------------------------

def render_fillers(
    fillers: Mapping[str, str] = DEFAULT_FILLERS,
    *,
    overwrite: bool = False,
) -> Path:
    """Synthesize every filler that doesn't already exist on disk. Returns
    the directory the wavs live in.

    Skips work for fillers already rendered (unless overwrite=True), so
    calling this on every startup is cheap after the first run.
    """
    # Lazy import — render_fillers is the only path that needs the heavy
    # synthesizer; play_filler doesn't.
    from .synthesizer import NepaliSynthesizer

    FILLER_DIR.mkdir(parents=True, exist_ok=True)

    missing = {
        name: text
        for name, text in fillers.items()
        if overwrite or not (FILLER_DIR / f"{name}.wav").exists()
    }
    if not missing:
        return FILLER_DIR

    log.info("rendering %d filler(s) to %s", len(missing), FILLER_DIR)
    synth = NepaliSynthesizer()
    for name, text in missing.items():
        log.info("  filler %-10s : %s", name, text)
        audio = synth.synthesize(text)
        _save_wav(FILLER_DIR / f"{name}.wav", audio, synth.output_sample_rate)
    return FILLER_DIR


def _save_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write a float32 [-1, 1] array as a 16-bit PCM wav."""
    pcm = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def _load_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM wav back to a float32 [-1, 1] array."""
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767
    return pcm, rate


# ---- playback ------------------------------------------------------------

def play_filler(name: str) -> bool:
    """Play a pre-rendered filler. Returns True on success, False if the
    filler doesn't exist (caller can fall back to silence or to a real
    speak() call)."""
    path = FILLER_DIR / f"{name}.wav"
    if name not in _loaded:
        if not path.exists():
            log.warning(
                "filler %r not found at %s — run render_fillers() first",
                name, path,
            )
            return False
        _loaded[name] = _load_wav(path)

    audio, rate = _loaded[name]
    # Reuse the same playback path as real speech for consistency.
    from .player import play
    play(audio, sample_rate=rate)
    return True


def list_fillers() -> list[str]:
    """Names of fillers currently on disk."""
    if not FILLER_DIR.exists():
        return []
    return sorted(p.stem for p in FILLER_DIR.glob("*.wav"))
