#!/usr/bin/env bash
# Linux / macOS / Raspberry Pi setup for nepanglish-tts.
#
# Run from the repo root:
#     bash scripts/setup.sh
#
# This bootstraps everything end-to-end: installs `uv` (a single-binary
# Python toolchain), uses it to download a standalone Python 3.10 just
# for this project, creates the venv, and installs all deps in the right
# order (CPU torch first to avoid 2 GB of unused CUDA libs).
#
# Why 3.10 specifically: fairseq (transitive dep of
# ai4bharat-transliteration) fails to import on Python 3.11+ due to a
# stricter @dataclass mutable-default check. See mise.toml.

set -euo pipefail

echo ""
echo "=== nepanglish-tts setup ==="
echo "Repo path: $(pwd)"
echo ""

# 1. Install uv if missing. Drops a single binary into ~/.local/bin (or
#    ~/.cargo/bin on some setups). No admin rights, no system Python
#    changes.
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv (one-time, ~30 MB)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer prints a hint about sourcing its env; do it inline so
    # uv is on PATH for the rest of this script.
    if [[ -f "$HOME/.local/bin/env" ]]; then
        # shellcheck source=/dev/null
        source "$HOME/.local/bin/env"
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv: $(uv --version)"

# 2. Fetch a standalone Python 3.10 just for this project. uv caches it
#    under ~/.local/share/uv/python/ — no apt, brew, or admin needed.
echo ""
echo "Provisioning Python 3.10..."
uv python install 3.10

# 3. Create the venv pointing at that 3.10.
if [[ ! -d ".venv" ]]; then
    echo "Creating .venv..."
    uv venv --python 3.10 .venv
else
    echo ".venv already exists, reusing it."
fi

# 4. CPU-only torch FIRST — saves ~2 GB of unused CUDA libs. uv's
#    resolver is more forgiving of fairseq's broken metadata than modern
#    pip, so we don't need the pip<24.1 dance.
echo ""
echo "Installing CPU-only torch (slow step, be patient)..."
VIRTUAL_ENV=".venv" uv pip install -r requirements-cpu.txt

# 5. Project deps.
echo ""
echo "Installing project requirements..."
VIRTUAL_ENV=".venv" uv pip install -r requirements.txt

# 6. Voice model.
echo ""
echo "Downloading the Nepali voice model (~60 MB)..."
.venv/bin/python scripts/download_model.py

echo ""
echo "Done. Activate with:"
echo "    source .venv/bin/activate"
echo "Then try:"
echo "    python scripts/test_repl.py"
