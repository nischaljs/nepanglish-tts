#!/usr/bin/env bash
# Linux / macOS / Raspberry Pi setup script for nepanglish-tts.
#
# Run from the repo root:
#     bash scripts/setup.sh
#
# Order matters: CPU-only torch must be installed BEFORE
# ai4bharat-transliteration, or pip pulls 2 GB of unused CUDA libs.

set -euo pipefail

echo ""
echo "=== nepanglish-tts setup ==="
echo "Repo path: $(pwd)"
echo ""

# 1. Find Python 3.10. README pins 3.10; newer Pythons can break some
#    transitive deps from fairseq.
PYTHON=""
for candidate in python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        ver=$("$candidate" --version 2>&1 || true)
        if [[ "$ver" == *"Python 3.10."* ]]; then
            PYTHON="$candidate"
            echo "Using: $candidate ($ver)"
            break
        fi
    fi
done
if [[ -z "$PYTHON" ]]; then
    echo "ERROR: Python 3.10 not found." >&2
    echo "On Debian/Ubuntu/Raspberry Pi OS:" >&2
    echo "    sudo apt install python3.10 python3.10-venv" >&2
    echo "On macOS:    brew install python@3.10" >&2
    echo "Or use mise: mise install python@3.10" >&2
    exit 1
fi

# 2. Create venv if missing.
if [[ ! -d ".venv" ]]; then
    echo "Creating .venv..."
    "$PYTHON" -m venv .venv
else
    echo ".venv already exists, reusing it."
fi

PIP=".venv/bin/pip"
VENV_PY=".venv/bin/python"

if [[ ! -x "$PIP" ]]; then
    echo "ERROR: venv creation failed (no .venv/bin/pip)." >&2
    exit 1
fi

# 3. Pin pip to a version that's permissive about fairseq's metadata
#    and bump the network timeout for big sdist downloads.
echo ""
echo "Pinning pip < 24.1 and raising network timeout to 300s..."
"$VENV_PY" -m pip install --upgrade "pip<24.1"
"$PIP" config set global.timeout 300

# 4. CPU-only torch FIRST — saves ~2 GB of unused CUDA libs.
echo ""
echo "Installing CPU-only torch (slow step, be patient)..."
"$PIP" install --default-timeout=300 --retries 5 -r requirements-cpu.txt

# 5. Project deps.
echo ""
echo "Installing project requirements..."
"$PIP" install --default-timeout=300 --retries 5 -r requirements.txt

# 6. Voice model.
echo ""
echo "Downloading the Nepali voice model (~60 MB)..."
"$VENV_PY" scripts/download_model.py

echo ""
echo "Done. Activate with:"
echo "    source .venv/bin/activate"
echo "Then try:"
echo "    python scripts/test_repl.py"
