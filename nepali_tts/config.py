"""All the knobs in one place.

Tweak prosody and paths here without touching synthesis code. Anything that
might want to change between laptop testing and Pi deployment lives in this
file.
"""

import os
from pathlib import Path

# Layout: <project root>/models/<archive name>/...
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

# Pick a model variant. Available on the sherpa-onnx releases page
# (k2-fsa/sherpa-onnx, "tts-models" tag):
#   "vits-piper-ne_NP-chitwan-medium"      ← male voice, fp32 (laptop default)
#   "vits-piper-ne_NP-chitwan-medium-int8" ← male, quantized — fastest on Pi
#   "vits-piper-ne_NP-chitwan-medium-fp16" ← male, middle ground
#   "vits-piper-ne_NP-google-medium"       ← female (Google's Nepali TTS)
#
# Override at runtime without editing this file:
#   NEPALI_TTS_MODEL=vits-piper-ne_NP-chitwan-medium-int8 ./run.sh ...
MODEL_NAME = os.environ.get(
    "NEPALI_TTS_MODEL",
    "vits-piper-ne_NP-google-medium",
)
MODEL_DIR = MODELS_DIR / MODEL_NAME

# Sherpa-onnx archives put the .onnx alongside these two files. We
# discover the .onnx dynamically (it's named differently across variants)
# in the synthesizer at startup — see _find_acoustic_model().
TOKENS = MODEL_DIR / "tokens.txt"
ESPEAK_DATA = MODEL_DIR / "espeak-ng-data"

# Piper's chitwan-medium emits 22050 Hz. The ESP32 I2S DMA we eventually feed
# wants 24000 Hz, so we resample on the Pi side to keep the firmware dumb.
# We do the same resample on laptop too so the test exercises the real path.
NATIVE_SAMPLE_RATE = 22050
TARGET_SAMPLE_RATE = 24000

# --- Prosody knobs (VITS stochastic duration predictor) -------------------
# Higher = slower speech. 1.0 = native pace; 1.15 = ~15% slower —
# enough head-room for clarity in noisy halls without dragging.
LENGTH_SCALE = 1.15

# Generator noise. Controls timbre variation between syllables. 0.50 keeps
# the voice human-sounding (not the flat 0.35 robot setting) without
# costing any wall-clock — noise scale only affects timbre, not duration.
NOISE_SCALE = 0.50

# Phoneme-level pitch wobble. 0.45 is the upper limit before the model
# stutters on consonant clusters; gives the cadence prosodic life
# compared to a flat 0.40. No speed cost.
NOISE_W = 0.45

# Pause length at sentence boundaries. 0.25 = short, conversational beat.
SILENCE_SCALE = 0.25

# How many CPU threads sherpa-onnx may use. The Pi 4's Cortex-A72 has 4
# cores total — in production we'll want this at 2 to leave headroom for
# STT/LLM/VAD. On a laptop, 4 is a better default for snappier RTF.
NUM_THREADS = 4

# Soft cap on chunk length for streaming. If a single sentence (text up
# to a hard `।`/`.`/`?`/`!`) is longer than this, we'll insert extra
# splits at commas / colons so the listener hears the first chunk
# sooner. Set to 0 to disable.
MAX_CHUNK_CHARS = 100

# When True, transliterated English tokens get a pass that swaps bare
# फ → फ़ and ज → ज़ (nuqta-marked variants). espeak-ng phonemizes the
# nuqta forms with /f/ and /z/ on languages that support them, where the
# unmarked forms come out as /pʰ/ and /dʒ/. The voice is still Nepali,
# but words like "phone", "fast", "office", "zone", "zero" sound a touch
# more like a Nepali speaker code-switching to English than a Nepali
# reading English letter-by-letter. Set False if it sounds wrong on
# your model variant.
ENGLISH_LEAN_TRANSLIT = True
