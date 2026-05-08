"""Cleanup steps that run on the raw input text before synthesis.

Two transformations live here:

  1. normalize_punctuation — convert pasted-from-anywhere weirdness
     (smart quotes, en/em dashes, ellipses, zero-width chars, exotic
     unicode spaces) into something the espeak phonemizer reliably
     understands. Without this, paste from Word/Google Docs/Slack can
     produce strange "the space"-style mispronunciations as the
     phonemizer falls back to spelling unfamiliar code points.

  2. (number conversion lives in `numbers.py` — kept separate so it can
      be tested and overridden independently)
"""

import re

# Smart-quotes and quote-likes → straight ASCII equivalents.
# Various unicode spaces → plain space.
# Ellipsis → single period (so the streaming engine sees one sentence
#   break, not three).
_PUNCT_MAP = {
    # Single quotes / apostrophes
    "‘": "'", "’": "'",  # ‘ ’
    "‚": "'", "‛": "'",  # ‚ ‛
    "′": "'",                  # ′ prime
    "`":      "'",                  # backtick — espeak reads it as "backquote"
    # Double quotes
    "“": '"', "”": '"',  # “ ”
    "„": '"', "‟": '"',  # „ ‟
    "«": '"', "»": '"',  # « »
    "″": '"',                  # ″ double prime
    # Unicode space variants
    " ": " ",  # non-breaking
    " ": " ",  # narrow non-breaking
    " ": " ",  # thin
    " ": " ",  # hair
    " ": " ", " ": " ",  # en, em space
    " ": " ", " ": " ",
    "　": " ",  # ideographic
    "\t":     " ",
    # Ellipsis → single period (one sentence break, not three)
    "…": ".",  # …
}

# Zero-width / invisible chars: just strip them. Common offenders that
# sneak in through copy-paste are ZWJ, ZWNJ, ZWSP, BOM, word-joiner.
# Em/en dashes are NOT stripped — synthesizer uses them as soft split
# points for streaming.
_INVISIBLE = re.compile(
    "["
    "​"  # zero-width space
    "‌"  # zero-width non-joiner
    "‍"  # zero-width joiner
    "⁠"  # word joiner
    "﻿"  # zero-width no-break space (BOM)
    "­"  # soft hyphen
    "]"
)

# Repeated whitespace → single space. After all the above we may have
# double spaces lying around; collapse them so the phonemizer sees clean
# token boundaries.
_MULTI_SPACE = re.compile(r" {2,}")


def normalize_punctuation(text: str) -> str:
    """Clean up text that came from a paste so the phonemizer doesn't
    trip over exotic unicode. See module docstring for the full list of
    transformations.

    >>> normalize_punctuation('She said “hello” — then left…')
    'She said "hello" — then left.'
    """
    if not text:
        return text
    text = _INVISIBLE.sub("", text)
    text = text.translate(str.maketrans(_PUNCT_MAP))
    text = _MULTI_SPACE.sub(" ", text)
    return text
