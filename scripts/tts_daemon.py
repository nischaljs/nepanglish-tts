"""Tiny HTTP daemon that exposes nepali_tts synthesis on localhost.

Designed for cross-venv use: a separate process (e.g. a Python 3.11 app
that can't share this venv) POSTs text and gets a WAV file back. The
daemon loads the Piper model once at startup, then serves any number of
requests.

Start (from the repo root):
    bash run.sh daemon                # foreground, Ctrl-C to stop
    nohup bash run.sh daemon > /tmp/tts-daemon.log 2>&1 & disown   # background

Stop:
    pkill -f tts_daemon.py

Endpoints:
    GET  /health   → 200 {"status": "ok"}
    POST /speak    → 200 {"status": "ok", "out_path": "...", "duration_ms": N}
                     body: {"text": "...", "out_path": "/abs/path/out.wav"}

The output file is a 16-bit mono PCM WAV at the synthesizer's target
sample rate (24 kHz by default — see nepali_tts/config.py).
"""

import argparse
import json
import logging
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

from nepali_tts import get_synthesizer

log = logging.getLogger("tts-daemon")

# The synthesizer isn't designed for parallel calls — sherpa-onnx wants
# one generate() at a time. We serialize via a lock so concurrent HTTP
# clients don't race.
_synth_lock = threading.Lock()
_synth = None


def _write_wav(path: str, audio: np.ndarray, sample_rate: int) -> None:
    """Write float32 audio as a 16-bit mono WAV. Stdlib only."""
    samples = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(samples.tobytes())


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info("%s %s", self.address_string(), format % args)

    def _reply(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"status": "ok"})
        else:
            self._reply(404, {"status": "error", "message": "not found"})

    def do_POST(self):
        if self.path != "/speak":
            self._reply(404, {"status": "error", "message": "use POST /speak"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(n))
            text = data["text"]
            out_path = data["out_path"]
        except Exception as e:
            self._reply(400, {"status": "error", "message": f"bad request: {e}"})
            return

        t0 = time.time()
        try:
            with _synth_lock:
                audio = _synth.synthesize(text)
                _write_wav(out_path, audio, _synth.output_sample_rate)
        except Exception as e:
            log.exception("synthesis failed")
            self._reply(500, {"status": "error", "message": str(e)})
            return

        ms = int((time.time() - t0) * 1000)
        log.info("synthesized %d chars → %s (%dms)", len(text), out_path, ms)
        self._reply(200, {"status": "ok", "out_path": out_path, "duration_ms": ms})


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    args = parser.parse_args()

    global _synth
    log.info("Loading Nepali TTS model (one-time, ~5s on Pi)...")
    _synth = get_synthesizer()
    log.info(
        "Model ready. native rate=%d Hz, output rate=%d Hz",
        _synth.native_sample_rate,
        _synth.output_sample_rate,
    )

    server = HTTPServer((args.host, args.port), _Handler)
    log.info("TTS daemon listening on http://%s:%d", args.host, args.port)
    log.info('POST /speak {"text": "...", "out_path": "/abs/path/out.wav"}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
