#!/usr/bin/env bash
# Install the nepali_tts integration into a Nova-HomeAutomation checkout.
#
# Usage:
#   bash scripts/install_into_nova.sh
#       (defaults to ~/Documents/welcome-bot/Nova-HomeAutomation)
#   bash scripts/install_into_nova.sh /path/to/Nova-HomeAutomation
#
# What it does:
#   1. Backs up the current app/tts/tts_engine.py (once) to .bak.
#   2. Replaces it with the HTTP-client version that talks to the
#      nepali_tts daemon on localhost:5555.
#   3. Removes a stray "v" line in app/pipeline/process_audio.py if
#      it's actually on disk (a paste artefact some users hit).
#   4. Sanity-checks both files parse as valid Python.
#
# Idempotent — safe to re-run.

set -euo pipefail

NOVA_DIR="${1:-$HOME/Documents/welcome-bot/Nova-HomeAutomation}"

if [[ ! -d "$NOVA_DIR" ]]; then
    echo "ERROR: Nova directory not found: $NOVA_DIR" >&2
    echo "Pass the correct path:  bash $0 /path/to/Nova-HomeAutomation" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/nova_tts_engine.py"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template missing: $TEMPLATE" >&2
    echo "Did you 'git pull' the latest nepanglish-tts?" >&2
    exit 1
fi

DEST="$NOVA_DIR/app/tts/tts_engine.py"
PIPELINE="$NOVA_DIR/app/pipeline/process_audio.py"

# 1. Back up the existing tts_engine.py once.
if [[ -f "$DEST" && ! -f "$DEST.bak" ]]; then
    cp "$DEST" "$DEST.bak"
    echo "Backed up old tts_engine.py → $DEST.bak"
fi

# 2. Drop in the new file.
cp "$TEMPLATE" "$DEST"
echo "Wrote new tts_engine.py to $DEST"

# 3. Remove stray 'v' line if present.
if [[ -f "$PIPELINE" ]] && grep -qE '^v\s*$' "$PIPELINE"; then
    sed -i '/^v\s*$/d' "$PIPELINE"
    echo "Removed stray 'v' line from $PIPELINE"
fi

# 4. Sanity-check both files parse.
python3 -c "import ast; ast.parse(open('$DEST').read())" \
    && echo "[OK] $DEST parses"
if [[ -f "$PIPELINE" ]]; then
    python3 -c "import ast; ast.parse(open('$PIPELINE').read())" \
        && echo "[OK] $PIPELINE parses"
fi

cat <<EOF

Done. Next steps:

  1. Start the TTS daemon in the background:
       cd $REPO_ROOT
       nohup bash run.sh daemon > /tmp/tts-daemon.log 2>&1 & disown

  2. Confirm the daemon is up (wait a few seconds for model load):
       curl http://127.0.0.1:5555/health

  3. Run Nova as before:
       cd $NOVA_DIR
       ./run_live_test_with_esp32_mimic.sh

EOF
