"""All the knobs in one place.

Tweak prosody and paths here without touching synthesis code. Anything that
might want to change between laptop testing and Pi deployment lives in this
file.
"""

from pathlib import Path

# Layout: <project root>/models/<archive name>/...
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

# Pick a model variant. Three are available on the sherpa-onnx releases
# page (k2-fsa/sherpa-onnx, "tts-models" tag):
#   "vits-piper-ne_NP-chitwan-medium"        ← fp32, biggest, best on x86 laptops
#   "vits-piper-ne_NP-chitwan-medium-int8"   ← quantized, half the size — try
#                                              this on Pi 4 / ARM where the
#                                              int8 path is well-optimized
#   "vits-piper-ne_NP-chitwan-medium-fp16"   ← middle ground
# In our testing fp32 was actually faster than int8 on x86_64 (ORT's
# int8 dequant overhead can outweigh the wins on small VITS models),
# but on aarch64 with proper int8 kernels int8 should win.
MODEL_NAME = "vits-piper-ne_NP-chitwan-medium"
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
# Slightly slower than default. Exhibition halls are noisy; listeners need
# the extra parsing time. Drop to 1.0 for normal pace.
LENGTH_SCALE = 1.05

# Generator noise. 0.35 keeps the voice stable but not flat. The Piper
# default of 0.667 is too breathy for a robot persona.
NOISE_SCALE = 0.35

# Phoneme-level pitch wobble. Critical for Nepali's tonal cadence — much
# below 0.35 sounds monotone, much above 0.45 stutters.
NOISE_W = 0.40

# Pause length at sentence boundaries. Mimics breathing and gives listeners
# room to catch up between thoughts. The sherpa-onnx default is 0.2; the
# brief suggests 0.2-0.3 for natural conversational delivery.
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
