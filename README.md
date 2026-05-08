# Nepanglish TTS

[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Offline, low-latency Nepali text-to-speech that handles code-switching
("Nepanglish") gracefully — runs on CPU, ships to a Raspberry Pi.**

You give it a sentence in Nepali, English, or any mix of the two, and it
speaks it back in a natural Nepali voice. English words get phonetically
transliterated to Devanagari first so they sound like a Nepali speaker
saying them, not like a confused phonemizer.

Designed to be the speech stage of a robotic voice assistant running on a
Raspberry Pi 4 (no GPU, 4 GB RAM), but the same code runs anywhere Python
runs. Audio is streamed sentence-by-sentence so the time-to-first-word is
short even on slow hardware.

```python
from nepali_tts import speak

speak("नमस्ते, मेरो नाम नोवा हो।")
speak("यो robot को speed बढाउ।")        # mixed scripts — handled
speak("Hello, how are you?")           # pure English — also fine
```

## Why this exists

Most usable Nepali TTS today is cloud-based (Google, Azure, etc.) — fine
for desktop apps but a non-starter when:

- you're on an edge device with no internet (robot at an exhibition, kiosk,
  rural deployment),
- you can't afford per-request API fees,
- privacy / data-locality matters,
- or your input is **Nepanglish** — Nepali grammar with English nouns
  sprinkled in, the way most Nepalis actually speak — which most cloud
  TTS engines mangle.

This project stitches together open-source pieces (Piper voice model,
Sherpa-ONNX runtime, AI4Bharat transliteration, soxr) into a small
streamable library that does the right thing on a CPU.

## How to use it

### Quickest way — try it interactively

```bash
source .venv/bin/activate
python scripts/test_repl.py
```

Type a sentence, hit Enter, hear it. Type `quit` (or `q`) to exit. The
REPL also supports a few slash-commands while testing:

| Command          | What it does                                      |
|------------------|---------------------------------------------------|
| `/list`          | List the rendered fillers                         |
| `/<filler-name>` | Play a filler instantly (e.g. `/ah`, `/oh`)       |
| `/render`        | Re-render fillers after editing them              |
| `/help`          | Show the command list                             |

Press `Ctrl-C` once to interrupt synthesis, or twice quickly to force-quit
(useful when the C++ engine is mid-step and the first signal gets eaten).

### From your own Python code — one function

```python
from nepali_tts import speak

speak("नमस्ते, कस्तो छ?")           # pure Nepali
speak("Robot को speed बढाउ")        # mixed English + Nepali — works too
```

That's the whole API. `speak(text)` is the function you asked for.

#### Optional: prefix with a filler

A "filler" is a short pre-rendered thinking sound the robot can say
instantly — useful for making the robot feel responsive while a slower
operation (LLM call, etc.) finishes in the background.

```python
from nepali_tts import speak, play_filler, render_fillers

# Once, after install — generates the filler wavs:
render_fillers()

# Then either play one on its own:
play_filler("ah")          # "अहँ..."  — uhh / hesitation
play_filler("oh")          # "ओहो..."  — oh / realizing
play_filler("la")          # "ल त..."  — well so...

# ...or attach one to a speak() call (filler plays first, then the text):
speak("तपाईंको प्रश्नको जवाफ यो हो।", filler="ah")
```

The intended pattern for hiding LLM latency in a robot pipeline:

```python
play_filler("ah")              # blocks ~0.5s — hides the next gap
response = llm.generate(...)   # 1-3 seconds, runs in parallel-ish
speak(response)                # streaming kicks in here
```

Available default fillers: `ah`, `oh`, `eh`, `la`. Edit
`nepali_tts/fillers.py` (or pass your own dict to `render_fillers`) to
add or change them.

If you ever need just the raw audio (without playing it — e.g. to send it
somewhere else), there are two ways:

```python
from nepali_tts import get_synthesizer
synth = get_synthesizer()

# Single-shot — wait for the whole reply, get one big numpy array.
audio = synth.synthesize("कस्तो छ?")

# Streaming — get chunks as the model finishes each sentence.
# This is what the production WebSocket path will use.
for chunk in synth.synthesize_stream("कस्तो छ?"):
    send_to_esp32(chunk)   # or whatever you want to do per-chunk
```

## What's happening under the hood (the simple version)

When you call `speak("यो robot को speed बढाउ")`, four things happen in
order:

```
  text ──► [1 fix English] ──► [2 speak] ──► [3 resize sound] ──► [4 play]
```

1. **Fix the English words.** The voice model only reads Devanagari letters
   (नेपाली script). So we sneak through the sentence and convert any
   English words into how they'd be spelled in Devanagari.
   Example: `robot` becomes `रोबोट`, `speed` becomes `स्पीड`.
   The Nepali speech engine then says them with a natural Nepali accent.

2. **Speak.** A pre-trained AI model (Piper, a Nepali voice) reads the
   cleaned-up text and produces raw sound waves.

3. **Resize the sound.** The model produces sound at one "rate" (22050 Hz),
   but the eventual robot speaker expects a different rate (24000 Hz). We
   convert it so it doesn't sound chipmunked. (On the laptop this step
   isn't strictly needed for playback, but we keep it in so the test
   matches what the Pi will actually do.)

4. **Play.** We send the sound to your laptop speakers.
   *(On the real robot, this step instead sends the sound over the network
   to the speaker — same code up to step 3, only the last step changes.)*

### The streaming part

Steps 2 → 4 don't run one-after-another for the whole reply. They run
**sentence by sentence**, in parallel:

```
  sentence 1: synth ───► resample ───► play (you hear it!)
                                              │
  sentence 2:    synth ───► resample ───► play (queued behind 1)
                                              │
  sentence 3:           synth ───► resample ───► play (queued behind 2)
```

So the robot starts speaking the first sentence the moment it's ready,
while the second is still being generated in the background. This shaves a
lot off the awkward "thinking silence" before the robot starts talking —
especially for longer multi-sentence replies.

If you want to see this happen with your own eyes, the test REPL prints
timestamped logs:

```
21:43:56.691  synth  chunk 1 ready
21:43:56.695  player chunk 1 playing      ← starts playing 4ms later
21:43:59.498  synth  chunk 2 ready        ← chunk 1 still being heard
21:43:59.503  player chunk 2 playing
```

If streaming wasn't on, you'd see all three `synth` lines first, then all
three `player` lines after.

## What's in the project folder

```
nepali_tts/                  ← the actual library
├── __init__.py              ← exposes speak(), play_filler(), render_fillers()
├── synthesizer.py           ← step 2: text → sound (with comma-splitting)
├── transliterator.py        ← step 1: English → Devanagari (+ disk cache)
├── resampler.py             ← step 3: 22050 Hz → 24000 Hz
├── player.py                ← step 4: send sound to speakers
├── fillers.py               ← pre-rendered "thinking" sounds
└── config.py                ← all the tunable settings in one place

scripts/
├── download_model.py        ← one-time: pulls the Nepali voice model
└── test_repl.py             ← the interactive "type & hear" tester

models/                      ← downloaded voice files (auto-created)
├── vits-piper-ne_NP-…/      ← the voice model itself
├── translit_cache.json      ← cached English→Devanagari lookups
└── fillers/                 ← rendered filler wavs (auto-created)
```

## The tools doing the heavy lifting

| Tool                       | What it does                                |
|----------------------------|---------------------------------------------|
| **Piper**                  | The Nepali voice model itself               |
| **Sherpa-ONNX**            | The engine that runs the Piper model fast   |
| **AI4Bharat Transliteration** | Converts English words → Devanagari      |
| **soxr**                   | Resamples the audio cleanly (no clicks)     |
| **sounddevice**            | Plays the audio through your speakers       |

You don't have to interact with any of these directly — `speak()` handles
everything.

## Tweaking the voice

All the dials are in `nepali_tts/config.py`. The interesting ones:

| Dial              | What it does                                     | Try values  |
|-------------------|--------------------------------------------------|-------------|
| `MODEL_NAME`      | Which voice model variant to load (fp32/int8/fp16) | see file  |
| `LENGTH_SCALE`    | Speed — higher = slower speech                   | 0.9 – 1.2   |
| `NOISE_SCALE`     | How much expression / variation                  | 0.30 – 0.50 |
| `NOISE_W`         | Pitch wobble (more = livelier)                   | 0.35 – 0.45 |
| `SILENCE_SCALE`   | Pause length between sentences                   | 0.2 – 0.4   |
| `NUM_THREADS`     | CPU cores to use (4 on laptop, 2 on Pi)          | 2 – 4       |
| `MAX_CHUNK_CHARS` | Force splitting long sentences on `,`/`;`/`:` so streaming starts sooner. 0 disables. | 80 – 150 |

Change them, save the file, run the REPL again to compare.

## Setup (only needed once)

```bash
# 1. Pin the Python version this project needs
mise install python@3.10

# 2. Make a virtual env
python -m venv .venv
source .venv/bin/activate
pip install "pip<24.1"               # older pip — more permissive about
                                     # fairseq's slightly-broken metadata

# 3. Install CPU-only PyTorch first (saves ~2 GB of unused CUDA libs)
pip install -r requirements-cpu.txt

# 4. Then the project itself
pip install -r requirements.txt

# 5. Download the Nepali voice model (~60 MB)
python scripts/download_model.py
```

**Order matters in steps 3–4.** If you skip `requirements-cpu.txt` and
just `pip install -r requirements.txt`, pip will pull the default CUDA
build of PyTorch alongside fairseq — that's ~2 GB of NVIDIA libraries
your CPU-only box will never use.

If you already installed without the CPU index and want to slim down:

```bash
pip uninstall -y torch torchaudio nvidia-* triton
pip install -r requirements-cpu.txt
```

(Alternatively keep what you have — it'll work fine, it's just bigger.)

## Honest caveats

- **Speed.** On a laptop, generating 1 second of audio takes ~1.3 seconds
  of compute (real-time factor ~1.3). On the Pi 4 it'll likely be slower.
  If it becomes a problem, smaller `-int8` and `-fp16` quantized variants
  of the same Piper model exist on the [sherpa-onnx releases page][rel].
- **First English word is slow.** The English→Devanagari helper loads a
  small neural model the first time it sees an English token. Adds ~3
  seconds to that very first sentence. After that, instant — and cached.
- **Big install.** `ai4bharat-transliteration` drags in PyTorch + a bunch
  of CUDA libraries we don't actually use on CPU. Total install is ~3.8
  GB. On the Pi, switch to the CPU-only PyTorch build (and the int8
  Piper variant) to slim it down.
- **Sentence boundaries matter.** The streaming engine splits on `।`
  (Devanagari danda), `.`, `?`, `!`. If a single sentence is longer than
  `MAX_CHUNK_CHARS`, we *also* split on `,` / `;` / `:` to keep streaming
  responsive — so most well-punctuated text streams smoothly. Text with
  no punctuation at all becomes one big chunk.

[rel]: https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models

## Acknowledgements

This project stands entirely on top of these open-source tools:

- [**Piper**](https://github.com/rhasspy/piper) — the underlying VITS
  voice model, including the Nepali `chitwan-medium` and `google-medium`
  voices.
- [**Sherpa-ONNX**](https://github.com/k2-fsa/sherpa-onnx) — the C++
  runtime that runs the Piper model fast on CPUs (including ARM).
- [**AI4Bharat IndicXlit**](https://github.com/AI4Bharat/IndicXlit) — the
  English → Indic transliteration model that makes the Nepanglish path
  sound natural.
- [**soxr**](https://github.com/dofuuz/python-soxr) — phase-preserving
  streaming resampling.
- [**sounddevice**](https://python-sounddevice.readthedocs.io/) — the
  PortAudio Python bindings used for local playback.

If you build something cool with this, ping me — I'd love to see it.

## License

[MIT](LICENSE) — do whatever you want, just don't blame me when your
robot becomes self-aware.
