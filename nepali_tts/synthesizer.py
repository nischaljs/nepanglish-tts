"""The TTS engine itself: text in, audio out.

Wraps sherpa-onnx (the runtime) running a Piper VITS model (the voice).
Sherpa is dramatically faster than the standalone Piper Python package on
ARM CPUs because it executes the ONNX graph through optimized C++ with
NEON SIMD, and it's stable for long-lived processes.

Two synthesis APIs:
  - synthesize(text)           -> full audio array (single-shot)
  - synthesize_stream(text)    -> generator yielding chunks as they're ready

The streaming version is what production wants: it starts emitting audio
sentence-by-sentence as the model finishes each one, instead of making the
listener wait for the whole utterance.
"""

import logging
import queue
import re
import threading
from typing import Iterator

import numpy as np
import sherpa_onnx

from . import config
from .numbers import numbers_to_nepali
from .preprocess import normalize_punctuation
from .resampler import StreamingResampler
from .transliterator import nepanglish_to_devanagari

log = logging.getLogger(__name__)


# Sentence terminators sherpa-onnx already splits on. We split there too
# when probing whether a sentence is "long enough to need a sub-split".
_HARD_END = re.compile(r"(?<=[।.!?])\s+")
# Soft splits we'll promote to hard splits inside long sentences. Comma,
# semicolon, colon, em-dash, en-dash followed by whitespace. We *consume*
# the soft punctuation rather than keep it — leaving "X,।" looks weird.
_SOFT_SPLIT = re.compile(r"[,;:—–]\s+")


def _split_for_streaming(text: str, max_chars: int) -> str:
    """Return `text` rewritten so no contiguous sentence is longer than
    `max_chars`. We achieve that by replacing soft punctuation (commas,
    colons, dashes) inside over-long sentences with `। ` so the engine
    breaks the chunk earlier and the listener hears audio sooner.

    Trade-off: a comma-injected break gets a sentence-length pause, which
    can sound a touch heavier than a real comma. For a robot voice where
    fast-first-word matters more than literary rhythm, that's a fair price.

    Set max_chars to 0 to disable.
    """
    if not max_chars or max_chars <= 0:
        return text
    sentences = _HARD_END.split(text)
    out = []
    for s in sentences:
        if len(s) <= max_chars:
            out.append(s)
            continue
        # Sentence is over budget — promote its soft splits to hard ones.
        # We don't try to be clever about which commas to promote; every
        # one becomes a break, which over-splits some sentences but keeps
        # the logic dead simple and the audio still sounds natural.
        out.append(_SOFT_SPLIT.sub("। ", s))
    return " ".join(out)


class NepaliSynthesizer:
    """Loads the model once, then renders any number of utterances.

    Build it at startup; call .synthesize() per request.
    """

    def __init__(self):
        self._engine = self._build_engine()
        # Resampler is stateful — we want a fresh one per utterance so an
        # error mid-stream doesn't poison the next call's filter history.
        # `output_sample_rate` is a constant we expose for the player.
        self.output_sample_rate = config.TARGET_SAMPLE_RATE

    # ---- model construction ---------------------------------------------

    @staticmethod
    def _find_acoustic_model():
        """The fp32, int8 and fp16 archives all use slightly different
        .onnx filenames inside, so glob instead of hard-coding."""
        if not config.MODEL_DIR.exists():
            raise FileNotFoundError(
                f"Model directory missing at {config.MODEL_DIR}.\n"
                f"Run `python scripts/download_model.py` first."
            )
        candidates = sorted(config.MODEL_DIR.glob("*.onnx"))
        if not candidates:
            raise FileNotFoundError(
                f"No .onnx file found inside {config.MODEL_DIR} — the "
                f"archive may have unpacked incompletely. Try deleting "
                f"the directory and re-running download_model.py."
            )
        return candidates[0]

    @classmethod
    def _build_engine(cls) -> sherpa_onnx.OfflineTts:
        acoustic_model = cls._find_acoustic_model()

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(acoustic_model),
                    tokens=str(config.TOKENS),
                    data_dir=str(config.ESPEAK_DATA),
                    length_scale=config.LENGTH_SCALE,
                    noise_scale=config.NOISE_SCALE,
                    noise_scale_w=config.NOISE_W,
                ),
                num_threads=config.NUM_THREADS,
                provider="cpu",
                debug=False,
            ),
            # One sentence per internal batch. This is what makes streaming
            # responsive — sherpa fires our callback after each sentence
            # instead of bundling several together. Bigger values trade
            # latency for slightly better throughput; we want latency.
            max_num_sentences=1,
            # Silence injected after sentence-final punctuation. Without
            # this, multi-sentence responses sound rushed.
            silence_scale=config.SILENCE_SCALE,
        )

        if not tts_config.validate():
            raise RuntimeError(
                "sherpa-onnx rejected the TTS config — model files may be "
                "corrupt or mismatched. Try re-running download_model.py."
            )

        log.info(
            "loading Nepali TTS model from %s (%s)",
            config.MODEL_DIR,
            acoustic_model.name,
        )
        return sherpa_onnx.OfflineTts(tts_config)

    # ---- the actual synthesis -------------------------------------------

    @property
    def native_sample_rate(self) -> int:
        """Sample rate the underlying model emits (before resampling)."""
        return self._engine.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        """Single-shot: render `text` into a 1-D float32 waveform at
        TARGET_SAMPLE_RATE. Blocks until the whole thing is ready.

        Use this when you need the complete audio (saving to a file, etc).
        For playback or network streaming, prefer synthesize_stream().
        """
        chunks = list(self.synthesize_stream(text))
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

    def synthesize_stream(self, text: str) -> Iterator[np.ndarray]:
        """Streaming generator: yield resampled audio chunks as the model
        finishes each sentence. The first chunk is available as soon as
        sentence 1 is done — the listener doesn't wait for the whole reply.

        Each yielded chunk is a 1-D float32 array at TARGET_SAMPLE_RATE.
        Pass them straight to a sounddevice OutputStream, a WebSocket, or
        wherever they need to go.
        """
        if not text or not text.strip():
            return

        # The full preprocessing pipeline. Each step is one focused
        # transformation; order matters.
        #
        #   1. Normalize weird punctuation (smart quotes, ellipses,
        #      zero-width chars) — paste from anywhere becomes safe input.
        #   2. Spell out digit runs in Nepali — '2024' → 'दुई हजार चौबीस'.
        #   3. Phonetically transliterate Latin words to Devanagari —
        #      'robot' → 'रोबोट'.
        #   4. Split long sentences on soft punctuation so streaming
        #      starts emitting audio sooner.
        clean_text = normalize_punctuation(text)
        clean_text = numbers_to_nepali(clean_text)
        clean_text = nepanglish_to_devanagari(clean_text)
        clean_text = _split_for_streaming(clean_text, config.MAX_CHUNK_CHARS)
        log.debug("synth input  : %r", text)
        log.debug("synth cleaned: %r", clean_text)

        # Stateful per utterance — fresh phase, no carry-over from the
        # previous call.
        resampler = StreamingResampler(
            in_rate=self._engine.sample_rate,
            out_rate=config.TARGET_SAMPLE_RATE,
        )

        # The trick: sherpa.generate() blocks until done, but it fires our
        # callback from a background thread mid-synthesis. So we run
        # generate() in a thread and bridge to the main thread with a
        # queue. The main thread can pull chunks the moment they arrive.
        chunk_q: "queue.Queue[np.ndarray | object]" = queue.Queue(maxsize=32)
        DONE = object()  # sentinel — pushed when synthesis is finished

        chunk_idx = 0

        def _callback(samples, progress):
            nonlocal chunk_idx
            chunk = resampler.push(np.asarray(samples, dtype=np.float32))
            if chunk.size:
                chunk_idx += 1
                log.info(
                    "synth  chunk %d ready  %.2fs of audio  progress=%.2f",
                    chunk_idx,
                    chunk.size / config.TARGET_SAMPLE_RATE,
                    progress,
                )
                chunk_q.put(chunk)
            return 1  # 0 would abort the rest of the utterance

        def _run():
            try:
                self._engine.generate(clean_text, sid=0, speed=1.0, callback=_callback)
                tail = resampler.flush()
                if tail.size:
                    chunk_q.put(tail)
                log.info("synth  done")
            except Exception as e:
                log.exception("synthesis worker crashed: %s", e)
            finally:
                chunk_q.put(DONE)

        worker = threading.Thread(target=_run, name="tts-synth", daemon=True)
        worker.start()

        while True:
            item = chunk_q.get()
            if item is DONE:
                break
            yield item  # type: ignore[misc]
        worker.join()
