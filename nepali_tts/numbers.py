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
# How long a continuous digit run has to be before we read it digit-by-
# digit instead of as a single number. A Nepali mobile number is 10
# digits, so 10 is the natural cutoff. Reading 1,234,567 (1.2 million)
# digit-by-digit would be wrong, but a hyphenated 9841-123456 is almost
# always a phone — that case is handled separately.
_LONG_NUMBER_DIGITS = 10


def _digit_value(ch: str) -> int:
    """Single-character digit lookup. Works for ASCII or Devanagari."""
    if ch in _DEV_DIGITS:
        return _DEV_DIGITS.index(ch)
    return int(ch)


def _to_int(s: str) -> int:
    """Parse a digit string. Accepts ASCII digits, Devanagari digits, or
    a mix — useful because LLM output sometimes mixes both scripts."""
    out = 0
    for ch in s:
        out = out * 10 + _digit_value(ch)
    return out


def _digits_one_by_one(s: str) -> str:
    """Read each digit individually: '9841' → 'नौ आठ चार एक'.
    Anything that isn't a digit (hyphens, plus signs, etc.) is dropped.
    Used for phone numbers and long IDs where the value is meaningless."""
    return " ".join(_TABLE[_digit_value(c)] for c in s if c.isdigit() or c in _DEV_DIGITS)


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


# Match a number-ish token: integers, decimals (1.5), and hyphenated
# digit sequences (phone numbers like 9841-123456 or +977-9841-123456).
# Anatomy:
#   \+?                         optional leading + (country codes)
#   [0-9०-९]+                   first run of digits
#   (?:[-.][0-9०-९]+)*           zero or more more runs joined by - or .
_NUMBER_TOKEN = re.compile(r"\+?[0-9०-९]+(?:[-.][0-9०-९]+)*")


def _convert_token(s: str) -> str:
    """Decide how to read one matched token. Three cases:
    1. Phone-like (has hyphens, or 10+ contiguous digits): one-by-one.
    2. Decimal (has a single '.', no hyphens): X दशमलव d d d.
    3. Plain integer: convert to Nepali words.
    """
    plus = s.startswith("+")
    body = s[1:] if plus else s

    has_hyphen = "-" in body
    digits_only = "".join(c for c in body if c.isdigit() or c in _DEV_DIGITS)

    # Case 1: phone / long ID — read each digit. Hyphenated tokens always
    # qualify; un-hyphenated tokens qualify if they're 10+ digits long.
    if has_hyphen or len(digits_only) >= _LONG_NUMBER_DIGITS:
        words = _digits_one_by_one(body)
        return ("प्लस " + words) if plus else words

    # Case 2: decimal. Whole part as a number, fractional as digits.
    if "." in body:
        whole, frac = body.split(".", 1)
        whole_words = number_to_words(_to_int(whole)) if whole else "शून्य"
        frac_words = _digits_one_by_one(frac)
        return f"{whole_words} दशमलव {frac_words}"

    # Case 3: plain integer.
    return number_to_words(_to_int(body))


def numbers_to_nepali(text: str) -> str:
    """Replace every numeric token in `text` with its Nepali spelling.

    >>> numbers_to_nepali('आज २०२४ साल हो।')
    'आज दुई हजार चौबीस साल हो।'
    >>> numbers_to_nepali('मेरो number 9841-123456 हो।')
    'मेरो number नौ आठ चार एक एक दुई तीन चार पाँच छ हो।'
    >>> numbers_to_nepali('यो 3.14 हो।')
    'यो तीन दशमलव एक चार हो।'
    """
    if not text:
        return text
    return _NUMBER_TOKEN.sub(lambda m: _convert_token(m.group(0)), text)
