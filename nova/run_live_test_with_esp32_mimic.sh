#!/usr/bin/env bash
# run_live_test_with_esp32_mimic.sh
#
# Starts the Nova production server, then lets you choose:
#   (m)ic  — ESP32 mimicker: speak into C920 mic, full production pipeline
#   (t)ext — Chat REPL:      type messages, hear Nova reply on speaker
#
# All logs (server + mimic/chat) stream to console in real-time.
#
# Usage:
#   ./run_live_test_with_esp32_mimic.sh
#
# Press Ctrl+C to stop everything.

set -u
cd "$(dirname "$(readlink -f "$0")")"

if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
fi
export PYTHONPATH=.
export PYTHONUNBUFFERED=1

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; GRAY='\033[0;90m'; NC='\033[0m'
info()  { echo -e "${CYAN}▸${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }

SERVER_LOG=$(mktemp /tmp/nova-server-XXXX.log)
SERVER_PID=""
TAIL_PID=""
cleanup() {
  echo
  info "Shutting down..."
  if [[ -n "$TAIL_PID" ]] && kill -0 "$TAIL_PID" 2>/dev/null; then
    kill "$TAIL_PID" 2>/dev/null; wait "$TAIL_PID" 2>/dev/null
  fi
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null
  fi
  rm -f "$SERVER_LOG"
  echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT INT TERM

echo
echo "╔══════════════════════════════════════════════╗"
echo "║   Nova HomeAutomation — Full Pipeline Test   ║"
echo "╚══════════════════════════════════════════════╝"
echo

# ── 1. Start server ───────────────────────────────────────────
info "Starting Nova production server (app/main.py) ..."
python -u app/main.py > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!

# ── 2. Wait for server ready ──────────────────────────────────
READY_TIMEOUT=30
for i in $(seq 1 "$READY_TIMEOUT"); do
  if grep -q "Nova is ready\." "$SERVER_LOG" 2>/dev/null; then
    ok "Nova server is ready (PID $SERVER_PID)"
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    err "Server failed to start. Full log:"
    cat "$SERVER_LOG"
    exit 1
  fi
  sleep 1
done
if ! grep -q "Nova is ready\." "$SERVER_LOG" 2>/dev/null; then
  err "Server did not become ready within ${READY_TIMEOUT}s. Full log:"
  cat "$SERVER_LOG"
  exit 1
fi

# ── 3. Stream logs to console in background ───────────────────
tail -f "$SERVER_LOG" &
TAIL_PID=$!
sleep 1  # let tail show the startup lines

# ── 4. Pick mode ──────────────────────────────────────────────
echo
echo "Choose input mode:"
echo "  ${CYAN}m${NC}  Mic — ESP32 mimicker (speak into C920 webcam)"
echo "  ${CYAN}t${NC}  Text — chat REPL (type messages, hear replies)"
echo -n "Mode (m/t): "
read -r mode
echo

case "$mode" in
  m|M|mic|Mic)
    info "Starting ESP32 mimicker (C920 mic → ws://localhost:8080)"
    info "Speak loudly to trigger wake, then talk to Nova."
    echo
    python -m test.esp32_mimicker.main
    ;;
  t|T|text|Text)
    info "Starting chat REPL. Type messages to talk to Nova."
    info "Try: ${GRAY}/v${NC} to record from mic, ${GRAY}/h${NC} for commands"
    echo
    python chat.py
    ;;
  *)
    warn "Unknown mode '$mode'. Starting text chat as fallback."
    python chat.py
    ;;
esac
