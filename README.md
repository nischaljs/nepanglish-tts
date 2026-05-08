# Nepali TTS

A small project that turns Nepali (and Nepanglish) text into spoken audio.
You give it a sentence, you hear it. Built to eventually run on a Raspberry
Pi as the "voice" of a robot, but for now we test it on a laptop.

## How to use it

### Quickest way — try it interactively

```bash
source .venv/bin/activate
python scripts/test_repl.py
```

Type a sentence, hit Enter, hear it. Type `quit` to exit.

### From your own Python code — one function

```python
from nepali_tts import speak

speak("नमस्ते, कस्तो छ?")           # pure Nepali
speak("Robot को speed बढाउ")        # mixed English + Nepali — works too
```

That's the whole API. `speak(text)` is the function you asked for.

If you ever need just the raw audio (without playing it — e.g. to send it
somewhere else), use this instead:

```python
from nepali_tts import get_synthesizer

synth = get_synthesizer()
audio = synth.synthesize("कस्तो छ?")   # numpy array of sound samples
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

## What's in the project folder

```
nepali_tts/                  ← the actual library
├── __init__.py              ← exposes the speak() function
├── synthesizer.py           ← step 2: text → sound
├── transliterator.py        ← step 1: English → Devanagari
├── resampler.py             ← step 3: 22050 Hz → 24000 Hz
├── player.py                ← step 4: send sound to speakers
└── config.py                ← all the tunable settings in one place

scripts/
├── download_model.py        ← one-time: pulls the Nepali voice model
└── test_repl.py             ← the interactive "type & hear" tester

models/                      ← downloaded voice files (auto-created)
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

| Dial           | What it does                            | Try values  |
|----------------|------------------------------------------|-------------|
| `LENGTH_SCALE` | Speed — higher = slower speech           | 0.9 – 1.2   |
| `NOISE_SCALE`  | How much expression / variation          | 0.30 – 0.50 |
| `NOISE_W`      | Pitch wobble (more = livelier)           | 0.35 – 0.45 |
| `SILENCE_SCALE`| Pause length between sentences           | 0.2 – 0.4   |
| `NUM_THREADS`  | CPU cores to use (4 on laptop, 2 on Pi)  | 2 – 4       |

Change them, save the file, run the REPL again to compare.

## Setup (only needed once)

```bash
# Pin the Python version this project needs
mise install python@3.10

# Make a virtual env and install the libraries
python -m venv .venv
source .venv/bin/activate
pip install "pip<24.1"          # older pip, more permissive about old packages
pip install -r requirements.txt

# Download the Nepali voice model (~60 MB)
python scripts/download_model.py
```

Why the older pip? One of our libraries (`fairseq`, used for English →
Devanagari) has slightly broken metadata that newer pip refuses to install.
Older pip is more forgiving.

## Honest caveats

- **Speed.** On the laptop, generating 1 second of audio takes ~1.3 seconds
  of compute. On the Pi 4 it'll likely be slower. If it becomes a problem,
  we have a smaller "int8" version of the model we can swap in.
- **First English word is slow.** The English→Devanagari helper loads a
  little AI model the first time it sees an English word. Adds ~3 seconds
  to that very first sentence. After that, instant.
- **Big install.** The transliteration helper drags in PyTorch + a bunch of
  GPU libraries we don't actually use. Total install is ~3.8 GB. On the Pi
  we'll switch to the CPU-only PyTorch build to slim it down.
