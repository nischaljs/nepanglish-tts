#!/usr/bin/env bash
# Install the TTS daemon as a systemd USER service.
#
# After this, the daemon:
#   - auto-starts on every boot (with lingering enabled — see end)
#   - restarts itself if it crashes
#   - logs to the user journal (journalctl --user -u tts-daemon)
#
# Run from the repo root:
#     bash scripts/install_systemd_service.sh
#
# To uninstall later:
#     systemctl --user disable --now tts-daemon
#     rm ~/.config/systemd/user/tts-daemon.service
#     systemctl --user daemon-reload

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="tts-daemon"
USER_UNIT_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$USER_UNIT_DIR/$SERVICE_NAME.service"
TEMPLATE="$REPO_ROOT/scripts/systemd/$SERVICE_NAME.service"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: service template missing at $TEMPLATE" >&2
    echo "Did you 'git pull'?" >&2
    exit 1
fi

if [[ ! -x "$REPO_ROOT/.venv/bin/python" ]]; then
    echo "ERROR: $REPO_ROOT/.venv/bin/python not found." >&2
    echo "Run setup first:  bash run.sh setup" >&2
    exit 1
fi

# Stop any manually-started daemon so the new one can bind port 5555.
if pgrep -f tts_daemon.py >/dev/null 2>&1; then
    echo "Stopping currently-running tts_daemon.py instances..."
    pkill -f tts_daemon.py || true
    sleep 1
fi

mkdir -p "$USER_UNIT_DIR"
cp "$TEMPLATE" "$SERVICE_FILE"
echo "Wrote service unit to $SERVICE_FILE"

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME"
echo
echo "Service enabled and started. Status:"
systemctl --user --no-pager status "$SERVICE_NAME" || true
echo

# Lingering = user services keep running across logout, and start on
# boot even if the user never logs in. Without it, the daemon stops
# when the user logs out (e.g. after rebooting and not logging in).
LINGER_STATE="$(loginctl show-user "$USER" --property=Linger 2>/dev/null || true)"
if [[ "$LINGER_STATE" != *"Linger=yes"* ]]; then
    echo "──────────────────────────────────────────────────────────────"
    echo "ONE MORE STEP — enable lingering so the daemon survives reboot"
    echo "even when no one is logged in. This needs sudo:"
    echo
    echo "    sudo loginctl enable-linger $USER"
    echo "──────────────────────────────────────────────────────────────"
    echo
fi

cat <<EOF
Useful commands:
  systemctl --user status tts-daemon       # is it healthy?
  systemctl --user restart tts-daemon      # restart after code change
  systemctl --user stop tts-daemon         # stop until reboot
  journalctl --user -u tts-daemon -f       # tail logs

EOF
