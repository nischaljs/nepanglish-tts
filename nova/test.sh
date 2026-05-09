#!/usr/bin/env bash
# Nova welcome bot — easy test runner.
#
#   ./test.sh           same as `quick`
#   ./test.sh quick     fast offline tests: imports + VAD threshold + LLM JSON contract
#   ./test.sh vad       just the VAD threshold check
#   ./test.sh llm       just the LLM JSON contract test
#   ./test.sh pipeline  full STT→LLM→TTS run against a saved WAV (plays audio!)
#   ./test.sh all       quick + pipeline
#   ./test.sh chat      interactive REPL: type or speak to Nova, hear replies
#   ./test.sh live      start the full server (needs ESP32 + camera)

set -u
cd "$(dirname "$(readlink -f "$0")")"

if [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi
export PYTHONPATH=.

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
hdr()  { echo; echo -e "${YELLOW}=== $1 ===${NC}"; }


quick_imports_and_vad() {
  hdr "module imports + VAD threshold"
  python - <<'PY' || fail "imports/VAD failed"
import app.vad.vad_detection
import app.llm.groq
import app.pipeline.process_audio
import app.tts.tts_engine
import app.orchestration.orchestrator
from app.vad.vad_detection import SILENCE_LIMIT, FRAME_MS
ms = SILENCE_LIMIT * FRAME_MS
assert ms == 4000, f"expected 4000, got {ms}"
print(f"all modules import OK, VAD silence cutoff = {ms} ms")
PY
  ok "imports + VAD threshold"
}


llm_contract() {
  hdr "LLM JSON contract (calls Groq → needs internet + GROQ key)"
  python - <<'PY' || fail "LLM contract failed"
import asyncio, json
from app.llm.groq import groq_llm_json, set_face_context

async def main():
    set_face_context("", None)
    a = await groq_llm_json("My name is Yubraj")
    print("[register on name]", json.dumps(a, ensure_ascii=False))
    assert a["type"] == "register", f"expected register, got {a['type']}"
    assert a.get("name", "").lower() == "yubraj", f"expected name=Yubraj, got {a.get('name')!r}"

    set_face_context("You are talking to Yubraj. He has visited 2 times before.", "fake-face-1")
    b = await groq_llm_json("play some music")
    print("[known + command]", json.dumps(b, ensure_ascii=False))
    assert b["type"] == "command", f"expected command, got {b['type']}"
    assert b["target"] == "music", f"expected music, got {b['target']}"

    print("LLM contract OK")

asyncio.run(main())
PY
  ok "LLM contract"
}


pipeline_test() {
  hdr "full pipeline against a saved WAV  ⚠️  audio will play on Pi speaker"
  if [[ ! -f data/output_audio/speech.wav ]]; then
    src=""
    for f in "$HOME/Documents/2.wav" "$HOME/Documents/4.wav" "$HOME/Documents/9.wav" "$HOME/Documents/nova1.wav"; do
      [[ -f "$f" ]] && src="$f" && break
    done
    [[ -z "$src" ]] && fail "no data/output_audio/speech.wav and no fallback WAV in ~/Documents/"
    mkdir -p data/output_audio
    cp "$src" data/output_audio/speech.wav
    echo "(staged $src as data/output_audio/speech.wav)"
  fi
  python - <<'PY' || fail "pipeline failed"
import asyncio, time
from app.pipeline.process_audio import process_audio
t = time.time()
asyncio.run(process_audio())
print(f"pipeline wall time: {time.time()-t:.1f}s")
PY
  ok "pipeline"
}


live_server() {
  hdr "starting full server (Ctrl+C to stop)"
  exec python app/main.py
}


chat_repl() {
  hdr "interactive REPL — /h for help, /q to quit"
  exec python chat.py
}


case "${1:-quick}" in
  quick)    quick_imports_and_vad; llm_contract ;;
  vad)      quick_imports_and_vad ;;
  llm)      llm_contract ;;
  pipeline) pipeline_test ;;
  live)     live_server ;;
  chat)     chat_repl ;;
  all)      quick_imports_and_vad; llm_contract; pipeline_test ;;
  *) echo "usage: $0 {quick|vad|llm|pipeline|chat|live|all}"; exit 2 ;;
esac
