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
import errno
import json
import logging
import socket
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

# Run-from-anywhere import: scripts/ isn't a package, so add the repo
# root to sys.path before importing nepali_tts. Same trick the other
# scripts in this folder use.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nepali_tts import get_synthesizer  # noqa: E402
from nepali_tts.player import play_stream  # noqa: E402
from nepali_tts.transliterator import warm_up as _warm_translit  # noqa: E402

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
            out_path = data.get("out_path")  # optional
            # When True (default), the daemon plays audio through its own
            # sounddevice output as it's being synthesized — first sentence
            # is audible after ~1s instead of waiting for the whole reply
            # to render. The caller should then *skip* re-playing the file.
            stream = bool(data.get("stream", True))
        except Exception as e:
            self._reply(400, {"status": "error", "message": f"bad request: {e}"})
            return

        t0 = time.time()
        try:
            with _synth_lock:
                if stream:
                    # Pipeline synth → playback. Tee chunks into a list so
                    # we can also write the WAV file at the end if asked.
                    chunks: list[np.ndarray] = []

                    def _tee():
                        for c in _synth.synthesize_stream(text):
                            chunks.append(c)
                            yield c

                    play_stream(_tee(), sample_rate=_synth.output_sample_rate)
                    audio = (
                        np.concatenate(chunks)
                        if chunks
                        else np.zeros(0, dtype=np.float32)
                    )
                else:
                    audio = _synth.synthesize(text)

                if out_path:
                    p = Path(out_path)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    _write_wav(str(p), audio, _synth.output_sample_rate)
        except Exception as e:
            log.exception("synthesis failed")
            self._reply(500, {"status": "error", "message": str(e)})
            return

        ms = int((time.time() - t0) * 1000)
        log.info(
            "synthesized %d chars (stream=%s) → %s (%dms)",
            len(text), stream, out_path or "(no file)", ms,
        )
        self._reply(200, {
            "status": "ok",
            "out_path": out_path,
            "duration_ms": ms,
            "played": stream,
        })


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

    # Pre-load the AI4Bharat transliteration model now so the first
    # request that hits an English word doesn't pay the ~3s lazy load
    # penalty mid-conversation.
    log.info("Pre-warming English→Devanagari transliterator...")
    try:
        _warm_translit()
        log.info("Transliterator ready.")
    except Exception as e:
        log.warning(
            "Transliterator warm-up failed (%s) — will lazy-load on first "
            "English token. Synthesis still works.", e,
        )

    # ThreadingHTTPServer handles each request in its own thread, so
    # /health and /speak don't block each other. The synthesizer itself
    # is still serialized via _synth_lock since sherpa-onnx isn't
    # thread-safe — but at least a hung synth doesn't make the daemon
    # appear dead to health checks.
    try:
        server = ThreadingHTTPServer((args.host, args.port), _Handler)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            log.error(
                "Port %d is already in use. Another daemon is probably "
                "running. Stop it with: pkill -9 -f tts_daemon.py",
                args.port,
            )
            return 1
        raise

    log.info("TTS daemon listening on http://%s:%d", args.host, args.port)
    log.info('POST /speak {"text": "...", "out_path": "/abs/path/out.wav"}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
