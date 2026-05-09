#!/usr/bin/env bash
# One-shot bootstrap. Works on a fresh Linux laptop or a freshly-imaged
# Raspberry Pi. After this completes, the project is fully self-contained:
# Python 3.10, all deps, voice model, face model, Nova, face-recognition
# code — everything inside the nepanglish-tts/ folder. Delete the folder
# = clean uninstall.
#
# Usage:
#   git clone https://github.com/nischaljs/nepanglish-tts.git
#   cd nepanglish-tts
#   bash scripts/bootstrap_pi.sh
#
# Idempotent — safe to re-run after pulls.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NOVA_DIR="$REPO_ROOT/nova"
NOVA_REPO_URL="${NOVA_REPO_URL:-https://github.com/yubraj525/Nova-HomeAutomation.git}"
NOVA_BRANCH="${NOVA_BRANCH:-face-integration}"
VENV="$REPO_ROOT/.venv"

cd "$REPO_ROOT"

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   nepanglish-tts unified bootstrap                        ║"
echo "║   Project root: $REPO_ROOT"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Base nepali_tts setup (uv + python 3.10 + venv + deps + voice model) ──
echo "==> [1/7] Base setup (uv, Python 3.10, voice model)"
bash run.sh setup

# ── 2. Clone Nova if missing ──
if [[ ! -d "$NOVA_DIR" ]]; then
    echo ""
    echo "==> [2/7] Cloning Nova ($NOVA_BRANCH branch)"
    git clone --branch "$NOVA_BRANCH" --single-branch "$NOVA_REPO_URL" "$NOVA_DIR"
else
    echo ""
    echo "==> [2/7] Nova already at $NOVA_DIR — skipping clone"
fi

# ── 3. Install Nova deps + face recognition deps into the SAME venv ──
echo ""
echo "==> [3/7] Installing Nova + face-recognition deps into the venv"
PIP="$VENV/bin/pip install --quiet"
$PIP --upgrade pip >/dev/null 2>&1 || true
# Nova's own requirements.txt currently mirrors nepanglish-tts deps
# (sherpa-onnx, soxr, etc) — already installed by run.sh setup. We
# install the Nova-side deps explicitly. Note: Whisper transcription
# goes through Groq's hosted model, so no local openai-whisper.
$PIP groq python-dotenv pygame soundfile pydub edge-tts \
     webrtcvad-wheels PyAudio
# Face recognition (InsightFace + onnxruntime as the runtime dep).
$PIP insightface onnxruntime
# OpenCV: scrub any headless variant a transitive dep may have pulled in
# and force the GUI build. The headless one breaks cv2.imshow, which
# scripts/talk_ui.py uses for the camera preview window.
"$VENV/bin/pip" uninstall -y opencv-python opencv-python-headless >/dev/null 2>&1 || true
$PIP opencv-python

# ── 4. Make `nepali_tts` importable from anywhere in this venv ──
echo ""
echo "==> [4/7] Wiring nepali_tts into venv import path"
echo "$REPO_ROOT" > "$VENV/lib/python3.10/site-packages/nepali_tts.pth"

# ── 5. Patch Nova's tts_engine.py with the in-process variant ──
echo ""
echo "==> [5/7] Patching Nova's tts_engine.py (in-process — no HTTP daemon)"
DEST="$NOVA_DIR/app/tts/tts_engine.py"
if [[ -f "$DEST" && ! -f "$DEST.bootstrap_bak" ]]; then
    cp "$DEST" "$DEST.bootstrap_bak"
fi
cp "$REPO_ROOT/scripts/nova_tts_engine_inproc.py" "$DEST"

# ── 6. Persist runtime env vars so `source .venv/bin/activate` is enough ──
echo ""
echo "==> [6/7] Persisting PYTHONPATH and runtime config in venv activate"
ACTIVATE="$VENV/bin/activate"
if ! grep -q "^export PYTHONPATH=" "$ACTIVATE"; then
    echo "export PYTHONPATH=\"$NOVA_DIR\"" >> "$ACTIVATE"
fi
if ! grep -q "^export TTS_STREAM=" "$ACTIVATE"; then
    echo "export TTS_STREAM=0" >> "$ACTIVATE"
fi
# .env template for Nova (Groq API key)
if [[ ! -f "$NOVA_DIR/.env" ]]; then
    cat > "$NOVA_DIR/.env" <<EOF
# Required for Nova's LLM (groq) and STT (whisper-large-v3-turbo on Groq).
# Get a key at https://console.groq.com/
GROQ=YOUR_GROQ_KEY_HERE
EOF
    echo "    Created template: $NOVA_DIR/.env"
fi

# ── 7. Sanity check: every critical module imports ──
echo ""
echo "==> [7/7] Smoke-testing imports"
"$VENV/bin/python" - <<'PYEOF'
import os, sys
# Suppress noisy imports' chatter.
os.environ.setdefault("GROQ", "DUMMY_FOR_IMPORT_TEST")
nova = os.environ.get("PYTHONPATH", "").split(":")[0]
sys.path.insert(0, nova)
sys.path.insert(0, os.path.join(os.path.dirname(nova), "face-recognition"))
import importlib
errs = []
for m in ("nepali_tts", "app.tts.tts_engine", "app.face.face_tools",
         "face_recognition_system"):
    try:
        importlib.import_module(m)
    except Exception as e:
        errs.append(f"{m}: {e.__class__.__name__}: {e}")
if errs:
    print("  IMPORT ERRORS:")
    for e in errs:
        print(f"    {e}")
    sys.exit(1)
print("  All imports OK.")
PYEOF

cat <<EOF

╔═══════════════════════════════════════════════════════════╗
║   Bootstrap complete.                                     ║
╚═══════════════════════════════════════════════════════════╝

Next steps:

  1. Set your Groq API key in $NOVA_DIR/.env
     (replace YOUR_GROQ_KEY_HERE with the real key)

  2. Activate the venv (sets PYTHONPATH and TTS_STREAM automatically):
       source $VENV/bin/activate

  3. Test the LLM + TTS pipeline by typing messages:
       cd $NOVA_DIR
       python chat.py

     Type a Nepali or English message at the 'you:' prompt — Nova replies
     in Devanagari (per the new prompt) and you'll hear the female voice.
     Use /v inside chat.py to record from your laptop mic.

To uninstall everything: just delete the $REPO_ROOT folder.
EOF
