#!/usr/bin/env bash
# Run Nova-HomeAutomation while tailing the TTS daemon's logs in the
# same terminal. Each daemon log line is prefixed [TTS-DAEMON] so it's
# distinguishable from Nova's own output. Ctrl-C exits both cleanly.
#
# Usage:
#   bash scripts/run_nova_with_logs.sh
#       (defaults to ~/Documents/welcome-bot/Nova-HomeAutomation)
#   NOVA_DIR=/path bash scripts/run_nova_with_logs.sh

set -uo pipefail

NOVA_DIR="${NOVA_DIR:-$HOME/Documents/welcome-bot/Nova-HomeAutomation}"

if [[ ! -d "$NOVA_DIR" ]]; then
    echo "ERROR: Nova not found at $NOVA_DIR" >&2
    echo "Set NOVA_DIR env var: NOVA_DIR=/path bash $0" >&2
    exit 1
fi

# Confirm the daemon's actually running before we bother tailing.
if ! systemctl --user is-active --quiet tts-daemon; then
    echo "WARNING: tts-daemon service is not running."
    echo "Start it:  systemctl --user start tts-daemon"
    echo "Continuing anyway — Nova will fail TTS calls until the daemon is up."
    echo
fi

# Start the journal tail in the background, prefixing every line so it
# stands out from Nova's. -n 0 means "don't replay history; show only
# new events from now on." -f means follow.
journalctl --user -u tts-daemon -f -n 0 --output=cat --no-pager 2>/dev/null \
    | sed -u 's/^/\x1b[36m[TTS-DAEMON]\x1b[0m /' &
JOURNAL_PID=$!

# Make sure the background tail dies when this script exits.
cleanup() {
    if kill -0 "$JOURNAL_PID" 2>/dev/null; then
        kill "$JOURNAL_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

cd "$NOVA_DIR"
# shellcheck source=/dev/null
source venv/bin/activate

echo
echo "════════════════════════════════════════════════════════════════"
echo "Running Nova. Daemon log lines appear with a cyan [TTS-DAEMON]"
echo "prefix; everything else is Nova's own output. Ctrl-C to stop."
echo "════════════════════════════════════════════════════════════════"
echo

exec python app/main.py
