"""The TTS engine itself: text in, audio out.

Wraps sherpa-onnx (the runtime) running a Piper VITS model (the voice).
Sherpa is dramatically faster than the standalone Piper Python package on
ARM CPUs because it executes the ONNX graph through optimized C++ with
NEON SIMD, and it's stable for long-lived processes.
"""

import logging

import numpy as np
import sherpa_onnx

from . import config
from .resampler import StreamingResampler
from .transliterator import nepanglish_to_devanagari

log = logging.getLogger(__name__)


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
    def _build_engine() -> sherpa_onnx.OfflineTts:
        if not config.ACOUSTIC_MODEL.exists():
            raise FileNotFoundError(
                f"Model not found at {config.ACOUSTIC_MODEL}.\n"
                f"Run `python scripts/download_model.py` first."
            )

        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(config.ACOUSTIC_MODEL),
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
            # Cap how many sentences sherpa will batch internally. Keeping
            # this small bounds memory use; we handle long inputs sentence
            # by sentence anyway.
            max_num_sentences=2,
            # Silence injected after sentence-final punctuation. Without
            # this, multi-sentence responses sound rushed.
            silence_scale=config.SILENCE_SCALE,
        )

        if not tts_config.validate():
            raise RuntimeError(
                "sherpa-onnx rejected the TTS config — model files may be "
                "corrupt or mismatched. Try re-running download_model.py."
            )

        log.info("loading Nepali TTS model from %s", config.MODEL_DIR)
        return sherpa_onnx.OfflineTts(tts_config)

    # ---- the actual synthesis -------------------------------------------

    @property
    def native_sample_rate(self) -> int:
        """Sample rate the underlying model emits (before resampling)."""
        return self._engine.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        """Render `text` into a 1-D float32 waveform at TARGET_SAMPLE_RATE.

        Steps: transliterate any English → Devanagari, run the VITS model,
        resample 22050 → 24000 so the output matches what the ESP32 expects.
        """
        if not text or not text.strip():
            return np.zeros(0, dtype=np.float32)

        clean_text = nepanglish_to_devanagari(text)
        log.debug("synth input  : %r", text)
        log.debug("synth cleaned: %r", clean_text)

        # sid=0 → first (and only) speaker for this single-speaker model.
        # speed=1.0 here because we already control pace via length_scale.
        result = self._engine.generate(clean_text, sid=0, speed=1.0)
        raw = np.asarray(result.samples, dtype=np.float32)

        # Resample to the rate the rest of the pipeline expects.
        resampler = StreamingResampler(
            in_rate=result.sample_rate,
            out_rate=config.TARGET_SAMPLE_RATE,
        )
        return resampler.resample_full(raw)
