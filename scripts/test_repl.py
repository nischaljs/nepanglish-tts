"""Interactive REPL for hearing the TTS output.

Usage:
    python scripts/test_repl.py

Type Devanagari, English, or any Nepanglish mix; each line gets synthesized
and played through your default audio device.

Slash commands (handy for testing):
    /list          show available fillers
    /<name>        play a filler instantly (e.g. /hmm, /umm, /ah, /eh)
    /render        re-render all the fillers (after edits)
    /help          show this list
    quit / q       exit

'quit' / 'q' / Ctrl-C to exit.
"""

import logging
import os
import signal
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nepali_tts import get_synthesizer, play_filler, render_fillers, speak  # noqa: E402
from nepali_tts.fillers import list_fillers  # noqa: E402


# --- Ctrl-C escape hatch -----------------------------------------------
# During synthesis sherpa-onnx is doing C++ work in a worker thread and
# PortAudio's stream.write is blocking — sometimes the first Ctrl-C gets
# swallowed there before Python can raise KeyboardInterrupt. So we
# install a handler that on the *second* press hard-exits the process.
_sigint_count = 0


def _on_sigint(_sig, _frame):
    global _sigint_count
    _sigint_count += 1
    if _sigint_count >= 2:
        # os._exit skips Python finalizers — exactly what we want when
        # we're stuck in a C++ thread that's ignoring the signal.
        print("\nforce-quitting (Ctrl-C twice).")
        os._exit(130)
    print("\n(synthesis is busy — press Ctrl-C again to force-quit, "
          "or just type 'q' at the prompt)")
    raise KeyboardInterrupt


signal.signal(signal.SIGINT, _on_sigint)

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

Slash commands:
  /list          list available fillers
  /<name>        play a filler (e.g. /hmm)
  /render        re-render the filler wavs
  /help          show this help

'quit' / 'q' / Ctrl-C to exit.
"""


def _handle_command(line: str) -> None:
    """Dispatch a /-prefixed line. Pure side-effects; no return value."""
    cmd = line[1:].strip().lower()

    if cmd in {"help", "h", "?"}:
        print(BANNER)
        return

    if cmd == "list":
        names = list_fillers()
        if not names:
            print("  no fillers rendered yet — run /render to create them")
        else:
            print(f"  available fillers: {', '.join(names)}")
        return

    if cmd == "render":
        print("  rendering fillers (one-time, ~5s)...")
        render_fillers()
        print(f"  done. fillers: {', '.join(list_fillers())}")
        return

    # Otherwise treat it as a filler name.
    if not play_filler(cmd):
        print(f"  unknown command or missing filler: /{cmd}")
        print(f"  try /list or /help")


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
        # Reset the Ctrl-C counter every time we're back at a clean prompt.
        # This way "double Ctrl-C" only triggers when both presses happen
        # *during the same operation* — not across the lifetime of the REPL.
        global _sigint_count
        _sigint_count = 0

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

        # Slash commands branch off into the filler/help handlers; anything
        # else gets sent through the full TTS pipeline.
        if text.startswith("/"):
            try:
                _handle_command(text)
            except Exception as e:
                print(f"!! command failed: {e}")
            continue

        try:
            speak(text)
        except Exception as e:
            # Keep the REPL alive on bad input — much nicer than crashing
            # mid-test session.
            print(f"!! synthesis failed: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
