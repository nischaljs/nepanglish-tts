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
    daemon)
        [[ -f "$MARKER" ]] || setup
        shift
        echo ""
        echo "Starting Nepali TTS HTTP daemon (Ctrl-C to stop)."
        echo ""
        exec .venv/bin/python scripts/tts_daemon.py "$@" ;;
    nova)
        # End-to-end: install integration into Nova, start daemon if
        # needed, wait for it, run Nova, kill daemon on exit (if we
        # started it). One paste, one command.
        [[ -f "$MARKER" ]] || setup

        NOVA_DIR="${NOVA_DIR:-$HOME/Documents/welcome-bot/Nova-HomeAutomation}"
        if [[ ! -d "$NOVA_DIR" ]]; then
            echo "ERROR: Nova not found at $NOVA_DIR" >&2
            echo "Set NOVA_DIR env var: NOVA_DIR=/path bash run.sh nova" >&2
            exit 1
        fi

        echo ""
        echo "=== Installing nepali_tts integration into Nova ==="
        bash scripts/install_into_nova.sh "$NOVA_DIR"

        STARTED_DAEMON=false
        DAEMON_PID=""

        # Did someone already start the daemon? (curl returns 0 on /health)
        if curl -sf http://127.0.0.1:5555/health >/dev/null 2>&1; then
            echo ""
            echo "TTS daemon already running — reusing it."
        else
            echo ""
            echo "=== Starting TTS daemon in background ==="
            nohup .venv/bin/python scripts/tts_daemon.py \
                > /tmp/tts-daemon.log 2>&1 &
            DAEMON_PID=$!
            STARTED_DAEMON=true
            disown "$DAEMON_PID" 2>/dev/null || true

            echo "Waiting for daemon to load model..."
            for i in $(seq 1 30); do
                if curl -sf http://127.0.0.1:5555/health >/dev/null 2>&1; then
                    echo "Daemon ready (PID $DAEMON_PID, took ${i}s)."
                    break
                fi
                sleep 1
            done

            if ! curl -sf http://127.0.0.1:5555/health >/dev/null 2>&1; then
                echo "ERROR: daemon didn't come up in 30s." >&2
                echo "Last 30 lines of /tmp/tts-daemon.log:" >&2
                tail -30 /tmp/tts-daemon.log >&2 || true
                exit 1
            fi
        fi

        # Stop the daemon on exit ONLY if we started it. If a long-lived
        # daemon was already running (e.g. from `bash run.sh daemon`),
        # leave it alone.
        cleanup() {
            if [[ "$STARTED_DAEMON" == "true" && -n "$DAEMON_PID" ]]; then
                echo ""
                echo "Stopping TTS daemon (PID $DAEMON_PID)..."
                kill "$DAEMON_PID" 2>/dev/null || true
            fi
        }
        trap cleanup EXIT INT TERM

        echo ""
        echo "=== Running Nova ==="
        echo "Daemon logs:  tail -f /tmp/tts-daemon.log"
        echo ""
        cd "$NOVA_DIR"
        ./run_live_test_with_esp32_mimic.sh
        ;;
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
        echo "Usage: bash run.sh [setup | daemon [--port N] | nova | -- <cmd...>]" >&2
        exit 2 ;;
esac
