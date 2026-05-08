"""Interactive REPL for hearing the TTS output.

Usage:
    python scripts/test_repl.py

Type Devanagari, English, or any Nepanglish mix; each line gets synthesized
and played through your default audio device. 'quit' or Ctrl-C to exit.
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nepali_tts import get_synthesizer, speak  # noqa: E402

# Millisecond wall-clock prefix makes streaming visible at a glance:
# you can see "synth chunk 1 ready" arrive *before* "play chunk 1" finishes.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d  %(message)s",
    datefmt="%H:%M:%S",
)

BANNER = """\
Nepali TTS test REPL
--------------------
Type some text and hit Enter to hear it.
Try Devanagari only:  नमस्ते, मेरो नाम नोवा हो।
Or mix in English:    यो robot को speed बढाउ।
'quit' / 'q' / Ctrl-C to exit.
"""


def main() -> int:
    print(BANNER)

    # Warm up before the first prompt so the user doesn't sit through a
    # multi-second hitch on their first input.
    print("Loading model... ", end="", flush=True)
    try:
        synth = get_synthesizer()
    except FileNotFoundError as e:
        print()
        print(f"!! {e}", file=sys.stderr)
        return 1
    # Touch the transliterator too so its model loads now, not on first
    # English-containing utterance.
    from nepali_tts.transliterator import warm_up

    warm_up()
    print(f"ready. (model rate: {synth.native_sample_rate} Hz, "
          f"output: {synth.output_sample_rate} Hz)\n")

    while True:
        try:
            text = input("text> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return 0

        if not text:
            continue
        if text.lower() in {"quit", "exit", "q"}:
            print("bye.")
            return 0

        try:
            speak(text)
        except Exception as e:
            # Keep the REPL alive on bad input — much nicer than crashing
            # mid-test session.
            print(f"!! synthesis failed: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
