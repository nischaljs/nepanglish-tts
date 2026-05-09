#!/usr/bin/env bash
# nepanglish-tts — single-command entry point (Linux / macOS / Pi).
#
#   bash run.sh              # opens the type-and-hear REPL (sets up first if needed)
#   bash run.sh setup        # only do the setup, don't launch the REPL
#   bash run.sh -- <args...> # run an arbitrary command inside the project venv
#
# Self-contained: no system Python required, no admin rights, no PATH
# changes outside the project. Everything — uv's downloaded interpreter,
# its package cache, the venv, the voice model — lives inside this
# folder. Delete the folder to uninstall.

set -euo pipefail
cd "$(dirname "$0")"

# Keep uv's caches inside the project so deleting the folder = clean wipe.
export UV_CACHE_DIR="$PWD/.uv/cache"
export UV_PYTHON_INSTALL_DIR="$PWD/.uv/python"

MARKER=".venv/.setup_complete"

setup() {
    echo ""
    echo "=== nepanglish-tts: first-time setup ==="
    echo "Everything stays inside this folder ($PWD)."
    echo ""

    # 1. uv = single-binary Python toolchain. Drops into ~/.local/bin,
    #    no admin needed. We only use it to fetch the project's Python
    #    and resolve packages; nothing system-wide changes.
    if ! command -v uv >/dev/null 2>&1; then
        echo "Installing uv (one-time, ~30 MB)..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        [[ -f "$HOME/.local/bin/env" ]] && source "$HOME/.local/bin/env"
        export PATH="$HOME/.local/bin:$PATH"
    fi
    echo "uv: $(uv --version)"

    # 2. Standalone Python 3.10 — pinned because fairseq (transitive
    #    dep of ai4bharat-transliteration) won't import on 3.11+.
    echo ""
    echo "Provisioning Python 3.10 into .uv/python ..."
    uv python install 3.10

    # 3. Project venv (skip if user already has one — keeps re-runs cheap).
    if [[ ! -d ".venv" ]]; then
        echo ""
        echo "Creating .venv ..."
        uv venv --python 3.10 .venv
    fi

    # 4. CPU-only torch FIRST — saves ~2 GB of unused CUDA libs.
    echo ""
    echo "Installing CPU-only torch ..."
    uv pip install --python .venv/bin/python -r requirements-cpu.txt

    # 5. Project deps.
    echo ""
    echo "Installing project requirements ..."
    uv pip install --python .venv/bin/python -r requirements.txt

    # 6. Voice model (~60 MB). Idempotent — script no-ops if already there.
    echo ""
    echo "Downloading the Nepali voice model ..."
    .venv/bin/python scripts/download_model.py

    touch "$MARKER"
    echo ""
    echo "Setup complete."
}

case "${1:-}" in
    setup)
        setup
        exit 0 ;;
    --)
        [[ -f "$MARKER" ]] || setup
        shift
        exec .venv/bin/python "$@" ;;
    "")
        [[ -f "$MARKER" ]] || setup
        echo ""
        echo "Launching the type-and-hear REPL — type a sentence, hit Enter."
        echo ""
        exec .venv/bin/python scripts/test_repl.py ;;
    *)
        echo "Usage: bash run.sh [setup | -- <cmd...>]" >&2
        exit 2 ;;
esac
