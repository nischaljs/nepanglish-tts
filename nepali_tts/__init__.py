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


def speak(text: str, *, filler: str | None = None) -> None:
    """Synthesize `text` and play it through the default audio device.

    Streams: the first sentence starts playing as soon as it's synthesized,
    while later sentences are still being generated. So the time-to-first-
    sound is the synthesis time of sentence 1, not of the whole utterance.

    Accepts pure Nepali, pure English, or any Nepanglish mix — Latin tokens
    get phonetically transliterated to Devanagari before they reach the
    acoustic model.

    If `filler` is given (e.g. "ah", "oh", "eh", "la"), the matching pre-
    rendered filler wav plays first as a brief thinking sound, then the
    real synthesis. Useful for making a robot sound less abrupt:
        speak("नमस्ते मेरो नाम नोवा हो।", filler="ah")
    Use `nepali_tts.fillers.list_fillers()` to see what's rendered.
    """
    from .player import play_stream

    if filler:
        # Best-effort: a missing filler shouldn't block real speech.
        try:
            from .fillers import play_filler
            play_filler(filler)
        except Exception:
            pass

    synth = get_synthesizer()
    play_stream(
        synth.synthesize_stream(text),
        sample_rate=synth.output_sample_rate,
    )


__all__ = [
    "speak",
    "get_synthesizer",
    "NepaliSynthesizer",
    # Filler audio: pre-rendered short phrases for instant playback.
    "render_fillers",
    "play_filler",
]


def render_fillers(*args, **kwargs):
    """Lazy re-export — see nepali_tts.fillers.render_fillers."""
    from .fillers import render_fillers as _impl
    return _impl(*args, **kwargs)


def play_filler(*args, **kwargs):
    """Lazy re-export — see nepali_tts.fillers.play_filler."""
    from .fillers import play_filler as _impl
    return _impl(*args, **kwargs)
