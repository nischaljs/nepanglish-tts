"""Turn 'Nepanglish' into pure Devanagari before it hits the TTS engine.

The Piper Nepali model's phonemizer (espeak-ng with the ne locale) only
understands Devanagari. If we hand it raw Latin text like 'robot', it tries
to pronounce each letter under Nepali phonetic rules and you get nonsense.

The ideal backend is ai4bharat's IndicXlit (XlitEngine) — a neural model
trained specifically for English → Indic phonetic transliteration. Rule-
based tools handle the *opposite* direction well (Romanized Nepali →
Devanagari) but butcher non-phonetic English like 'robot'.

ai4bharat depends on fairseq, which doesn't build cleanly on every Python
version. So this module tries to load it lazily and falls back to a
passthrough if it isn't available — Latin text will sound rough but the
Devanagari portions of the input still synthesize fine.
"""

import json
import logging
import re
import threading
from functools import lru_cache
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

# Latin-letter runs only. Devanagari, digits, punctuation, whitespace pass
# through unchanged — sherpa-onnx is fine with all of those.
_LATIN_RUN = re.compile(r"[A-Za-z]+")

_engine = None
_engine_unavailable = False  # set once we know it can't be loaded

# Persistent disk cache: { english_word_lowercase: devanagari_form }.
# Survives process restarts, so once you've said "conversation" once,
# every future session pronounces it instantly without touching the
# heavy XlitEngine again. Stored next to the models so it travels with
# any user's setup.
CACHE_PATH = config.MODELS_DIR / "translit_cache.json"
_disk_cache: dict[str, str] = {}
_disk_cache_loaded = False
_disk_cache_dirty = False
_cache_lock = threading.Lock()


def _load_disk_cache():
    """Read the cache from disk into memory. Idempotent."""
    global _disk_cache, _disk_cache_loaded
    if _disk_cache_loaded:
        return
    _disk_cache_loaded = True
    if not CACHE_PATH.exists():
        return
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            _disk_cache = json.load(f)
        log.info("loaded %d cached transliterations from %s",
                 len(_disk_cache), CACHE_PATH)
    except Exception as e:
        log.warning("transliteration cache load failed (%s) — starting fresh", e)
        _disk_cache = {}


def _save_disk_cache():
    """Write the cache atomically. Called after each new word is learned —
    cheap because the cache stays small (hundreds of entries, not millions)."""
    global _disk_cache_dirty
    if not _disk_cache_dirty:
        return
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_disk_cache, f, ensure_ascii=False, indent=2, sort_keys=True)
        tmp.replace(CACHE_PATH)
        _disk_cache_dirty = False
    except Exception as e:
        log.warning("transliteration cache save failed: %s", e)


def _patch_torch_load_for_fairseq():
    """fairseq's checkpoints predate PyTorch 2.6, which flipped torch.load's
    `weights_only` default to True for security. Old fairseq checkpoints
    contain non-tensor objects (argparse.Namespace, OmegaConf configs) that
    the strict loader rejects.

    We trust the ai4bharat checkpoint source, so we flip the default back.
    Idempotent — safe to call repeatedly."""
    import torch

    if getattr(torch.load, "_patched_for_fairseq", False):
        return
    original = torch.load

    def patched(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original(*args, **kwargs)

    patched._patched_for_fairseq = True  # type: ignore[attr-defined]
    torch.load = patched  # type: ignore[assignment]


def _silence_fairseq_logs():
    """fairseq prints a flood of INFO lines on every translit call (batch
    sampler timings, dataset loads, etc). Useful in research, noise here.
    Bump it to WARNING so only real problems break through."""
    for name in (
        "fairseq",
        "fairseq.tasks.translation_multi_simple_epoch",
        "fairseq.data.multilingual.multilingual_data_manager",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


def _load_engine():
    """First call pays the model load cost (~1-2s plus a one-time download
    on the very first run). Returns None if ai4bharat isn't installed; the
    caller is expected to fall back to passthrough in that case."""
    global _engine, _engine_unavailable
    if _engine is not None or _engine_unavailable:
        return _engine
    try:
        _patch_torch_load_for_fairseq()
        _silence_fairseq_logs()
        from ai4bharat.transliteration import XlitEngine
    except ImportError:
        log.warning(
            "ai4bharat-transliteration not installed — English tokens will "
            "be passed through unchanged and may sound poor. Install the "
            "package to enable Nepanglish transliteration."
        )
        _engine_unavailable = True
        return None
    # beam_width is the quality/speed trade-off. 4 is a sweet spot; higher
    # gives marginal gains for noticeable latency.
    # rescore=False skips downloading the ~800MB language-model dicts. The
    # rescorer slightly improves rare-word transliteration but costs a lot
    # of disk and load time. Set to True if you need that last bit of
    # quality and have the storage.
    _engine = XlitEngine("ne", beam_width=4, rescore=False)
    return _engine


@lru_cache(maxsize=2048)
def _transliterate_word(word: str) -> str:
    """Per-word lookup with two layers of caching:

    1. lru_cache (this decorator) — in-process, super fast.
    2. JSON file on disk — survives restarts, so the second time you ever
       run this project you don't pay the XlitEngine cost for words you've
       already used.

    Loanwords like 'robot' / 'AC' / 'project' recur constantly in real
    Nepanglish, so even a few hundred cached entries hit ~100% of repeat
    traffic.
    """
    global _disk_cache_dirty
    key = word.lower()

    # --- layer 2: disk cache --------------------------------------------
    _load_disk_cache()
    cached = _disk_cache.get(key)
    if cached is not None:
        return cached

    # --- layer 3: actually run the model --------------------------------
    engine = _load_engine()
    if engine is None:
        return word
    try:
        result = engine.translit_word(key, topk=1)
    except Exception as e:
        # Don't kill synthesis just because one word's transliteration
        # blew up — the raw word will sound ugly but the sentence still
        # gets spoken.
        log.warning("transliteration failed for %r: %s", word, e)
        return word

    # XlitEngine returns {lang_code: [candidates]}. Pick the top one.
    translit = word
    if isinstance(result, dict):
        candidates = result.get("ne") or next(iter(result.values()), [])
        if candidates:
            translit = candidates[0]
    elif isinstance(result, str):
        translit = result

    # Save the answer for next time.
    with _cache_lock:
        _disk_cache[key] = translit
        _disk_cache_dirty = True
    _save_disk_cache()

    return translit


def nepanglish_to_devanagari(text: str) -> str:
    """Replace every Latin-letter run in `text` with its Devanagari phonetic
    form, leaving everything else alone.

    >>> nepanglish_to_devanagari('यो Robot को speed बढाउ')
    'यो रोबोट को स्पिड बढाउ'
    """
    if not text:
        return text
    return _LATIN_RUN.sub(lambda m: _transliterate_word(m.group(0)), text)


def warm_up() -> None:
    """Load the transliteration model now instead of on first use. Useful
    at server start so the first user-visible response isn't laggy. No-op
    if ai4bharat isn't installed."""
    _load_engine()
