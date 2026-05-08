"""Top-level convenience: `from nepali_tts import speak`.

The synthesizer is heavy to construct (loads ~70MB of model + espeak data),
so we lazy-load it on first use. Importing this package stays cheap.
"""

from .synthesizer import NepaliSynthesizer

_synthesizer: NepaliSynthesizer | None = None


def get_synthesizer() -> NepaliSynthesizer:
    """Return the process-wide synthesizer, building it if needed."""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = NepaliSynthesizer()
    return _synthesizer


def speak(text: str) -> None:
    """Synthesize `text` and play it through the default audio device.

    Accepts pure Nepali, pure English, or any Nepanglish mix — Latin tokens
    get phonetically transliterated to Devanagari before they reach the
    acoustic model.
    """
    from .player import play

    synth = get_synthesizer()
    audio = synth.synthesize(text)
    play(audio, sample_rate=synth.output_sample_rate)


__all__ = ["speak", "get_synthesizer", "NepaliSynthesizer"]
