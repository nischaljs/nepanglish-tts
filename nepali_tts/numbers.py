"""Convert digit sequences in text to spelled-out Nepali words.

Without this step, '2024' gets handed to espeak verbatim — the Nepali
phonemizer either reads it as English digits or mispronounces it
character-by-character. With it, '2024' becomes 'दुई हजार चौबीस' before
synthesis sees it, and the model produces clean Nepali speech.

Handles:
  - ASCII digits (0-9)
  - Devanagari digits (०-९)
  - Numbers up to crores (10^7) — recurses for higher

Out of scope (TODO if needed):
  - Decimals (3.14)
  - Phone numbers / IDs (read digit-by-digit)
  - Ordinals (1st, 2nd)
  - Currency, percentages
"""

import re

# Standard Nepali words for 0-99. Spelling follows the most common
# everyday forms — there are minor variants in use, override entries
# here if you find a number that sounds wrong.
_TABLE: dict[int, str] = {
    0: "शून्य",     1: "एक",         2: "दुई",         3: "तीन",         4: "चार",
    5: "पाँच",      6: "छ",           7: "सात",         8: "आठ",          9: "नौ",
    10: "दश",       11: "एघार",       12: "बाह्र",       13: "तेह्र",       14: "चौध",
    15: "पन्ध्र",    16: "सोह्र",       17: "सत्र",       18: "अठार",       19: "उन्नाइस",
    20: "बीस",      21: "एक्काइस",    22: "बाइस",       23: "तेइस",       24: "चौबीस",
    25: "पच्चिस",   26: "छब्बिस",     27: "सत्ताइस",    28: "अठ्ठाइस",    29: "उनन्तीस",
    30: "तीस",      31: "एकत्तीस",    32: "बत्तीस",     33: "तेत्तीस",     34: "चौँतीस",
    35: "पैँतीस",   36: "छत्तीस",     37: "सैँतीस",     38: "अठतीस",      39: "उनन्चालीस",
    40: "चालीस",    41: "एकचालीस",   42: "बयालीस",    43: "त्रिचालीस",   44: "चवालीस",
    45: "पैँतालीस", 46: "छयालीस",     47: "सत्चालीस",  48: "अठचालीस",    49: "उनन्चास",
    50: "पचास",     51: "एकाउन्न",    52: "बाउन्न",     53: "त्रिपन्न",    54: "चवन्न",
    55: "पच्पन्न",  56: "छपन्न",      57: "सन्ताउन्न",  58: "अन्ठाउन्न",   59: "उनन्साठी",
    60: "साठी",     61: "एकसट्ठी",    62: "बैसट्ठी",    63: "त्रिसट्ठी",   64: "चौसट्ठी",
    65: "पैंसट्ठी", 66: "छयासट्ठी",   67: "सत्सट्ठी",   68: "अठसट्ठी",    69: "उनन्सत्तरी",
    70: "सत्तरी",   71: "एकहत्तर",    72: "बहत्तर",     73: "त्रिहत्तर",   74: "चौहत्तर",
    75: "पचहत्तर",  76: "छयहत्तर",    77: "सतहत्तर",    78: "अठहत्तर",    79: "उनासी",
    80: "असी",      81: "एकासी",      82: "बयासी",      83: "त्रियासी",   84: "चौरासी",
    85: "पचासी",    86: "छयासी",      87: "सतासी",      88: "अठासी",      89: "उनान्नब्बे",
    90: "नब्बे",    91: "एकान्नब्बे", 92: "बयान्नब्बे", 93: "त्रियान्नब्बे", 94: "चौरान्नब्बे",
    95: "पन्चान्नब्बे", 96: "छयान्नब्बे", 97: "सत्तान्नब्बे", 98: "अन्ठान्नब्बे", 99: "उनान्सय",
}

_DEV_DIGITS = "०१२३४५६७८९"


def _to_int(s: str) -> int:
    """Parse a digit string. Accepts ASCII digits, Devanagari digits, or
    a mix — useful because LLM output sometimes mixes both scripts."""
    out = 0
    for ch in s:
        if ch in _DEV_DIGITS:
            out = out * 10 + _DEV_DIGITS.index(ch)
        else:
            out = out * 10 + int(ch)
    return out


def number_to_words(n: int) -> str:
    """Spell `n` in Nepali. Handles negatives and recurses for huge
    numbers above one crore.

    >>> number_to_words(2024)
    'दुई हजार चौबीस'
    >>> number_to_words(100000)
    'एक लाख'
    >>> number_to_words(0)
    'शून्य'
    """
    if n < 0:
        return "ऋण " + number_to_words(-n)

    if n < 100:
        return _TABLE[n]

    # Indian/Nepali grouping: hundred (सय) → thousand (हजार) → lakh
    # → crore. Each "level" is the count of times its unit fits, plus
    # whatever's left over recursively.
    if n < 1000:
        unit, rem = divmod(n, 100)
        out = _TABLE[unit] + " सय"
    elif n < 100_000:
        unit, rem = divmod(n, 1000)
        out = number_to_words(unit) + " हजार"
    elif n < 10_000_000:
        unit, rem = divmod(n, 100_000)
        out = number_to_words(unit) + " लाख"
    else:
        unit, rem = divmod(n, 10_000_000)
        out = number_to_words(unit) + " करोड"

    if rem:
        out += " " + number_to_words(rem)
    return out


# Match runs of digits in either script. We don't try to detect dotted
# decimals or grouped numbers like "1,234" — phone numbers and IDs
# would be misread anyway. Keep scope tight.
_NUMBER_RUN = re.compile(r"[0-9०-९]+")


def numbers_to_nepali(text: str) -> str:
    """Replace every digit run in `text` with its Nepali spelling.

    >>> numbers_to_nepali('आज २०२४ साल हो।')
    'आज दुई हजार चौबीस साल हो।'
    >>> numbers_to_nepali('Room 101 मा छु।')
    'Room एक सय एक मा छु।'
    """
    if not text:
        return text
    return _NUMBER_RUN.sub(
        lambda m: number_to_words(_to_int(m.group(0))),
        text,
    )
