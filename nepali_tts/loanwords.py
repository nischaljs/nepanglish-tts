"""Curated English → Devanagari pronunciations for common Nepanglish loanwords.

The transliterator has three layers, in priority order:

  1. This file — hand-checked, won't drift over time, trumps everything.
  2. The on-disk cache (`models/translit_cache.json`) — built up at runtime
     from ai4bharat output for words we don't have here.
  3. The ai4bharat IndicXlit model — heavy fallback for novel words.

Layer 1 exists because:
  - The ai4bharat model sometimes produces shaky transliterations for short
    or ambiguous words (e.g. it might give "AC" as "अस" instead of "एसी").
  - Words you say a lot should sound the same every time, not drift if the
    model gives different beam-search outputs.
  - Lookups are O(1) — no neural model needed for the top ~120 loanwords
    that cover the bulk of real conversation.

Edit this file to add or fix entries. Keys are lower-case; the lookup
lower-cases its input so 'Robot', 'robot', and 'ROBOT' all hit the same
entry.
"""

SEED_LOANWORDS: dict[str, str] = {
    # --- Tech / electronics --------------------------------------------
    "robot":      "रोबोट",
    "computer":   "कम्प्युटर",
    "laptop":     "ल्यापटप",
    "tablet":     "ट्याब्लेट",
    "mobile":     "मोबाइल",
    "phone":      "फोन",
    "screen":     "स्क्रिन",
    "speaker":    "स्पिकर",
    "headphone":  "हेडफोन",
    "headphones": "हेडफोन्स",
    "charger":    "चार्जर",
    "battery":    "ब्याट्री",
    "camera":     "क्यामेरा",
    "tv":         "टिभी",
    "ac":         "एसी",
    "fan":        "फ्यान",
    "light":      "लाइट",
    "switch":     "स्विच",
    "bulb":       "बल्ब",

    # --- Internet / software -------------------------------------------
    "internet":   "इन्टरनेट",
    "wifi":       "वाइफाइ",
    "bluetooth":  "ब्लुटुथ",
    "email":      "इमेल",
    "website":    "वेबसाइट",
    "online":     "अनलाइन",
    "offline":    "अफलाइन",
    "browser":    "ब्राउजर",
    "google":     "गुगल",
    "youtube":    "युट्युब",
    "facebook":   "फेसबुक",
    "instagram":  "इन्स्टाग्राम",
    "whatsapp":   "ह्वाट्सएप",
    "social":     "सोसल",
    "media":      "मिडिया",
    "app":        "एप",
    "software":   "सफ्टवेयर",
    "hardware":   "हार्डवेयर",
    "code":       "कोड",
    "data":       "डाटा",
    "file":       "फाइल",
    "video":      "भिडियो",
    "audio":      "अडियो",
    "music":      "म्युजिक",
    "movie":      "मुभी",
    "photo":      "फोटो",
    "download":   "डाउनलोड",
    "upload":     "अपलोड",

    # --- Common actions ------------------------------------------------
    "on":         "अन",
    "off":        "अफ",
    "open":       "ओपन",
    "close":      "क्लोज",
    "start":      "स्टार्ट",
    "stop":       "स्टप",
    "play":       "प्ले",
    "pause":      "पज",
    "send":       "सेन्ड",
    "call":       "कल",
    "check":      "चेक",
    "update":     "अपडेट",
    "save":       "सेभ",
    "delete":     "डिलिट",
    "scroll":     "स्क्रोल",
    "click":      "क्लिक",
    "manage":     "म्यानेज",
    "control":    "कन्ट्रोल",
    "test":       "टेस्ट",

    # --- Daily life / places -------------------------------------------
    "school":     "स्कुल",
    "college":    "कलेज",
    "office":     "अफिस",
    "hospital":   "हस्पिटल",
    "doctor":     "डाक्टर",
    "teacher":    "टिचर",
    "student":    "स्टुडेन्ट",
    "friend":     "फ्रेन्ड",
    "bike":       "बाइक",
    "car":        "कार",
    "bus":        "बस",

    # --- Adjectives / qualifiers ---------------------------------------
    "good":       "गुड",
    "bad":        "ब्याड",
    "nice":       "नाइस",
    "cool":       "कुल",
    "super":      "सुपर",
    "smart":      "स्मार्ट",
    "easy":       "इजी",
    "hard":       "हार्ड",
    "busy":       "बिजी",
    "free":       "फ्री",
    "fast":       "फास्ट",
    "slow":       "स्लो",
    "common":     "कमन",
    "special":    "स्पेसल",

    # --- Common nouns in conversation ----------------------------------
    "time":       "टाइम",
    "date":       "डेट",
    "year":       "इयर",
    "month":      "मन्थ",
    "week":       "विक",
    "speed":      "स्पीड",
    "size":       "साइज",
    "level":      "लेभल",
    "problem":    "प्रब्लम",
    "problems":   "प्रब्लम्स",
    "issue":      "इस्यु",
    "idea":       "आइडिया",
    "plan":       "प्लान",
    "project":    "प्रोजेक्ट",
    "system":     "सिस्टम",
    "service":    "सर्भिस",
    "product":    "प्रोडक्ट",
    "customer":   "कस्टमर",
    "company":    "कम्पनी",
    "business":   "बिजनेस",
    "meeting":    "मिटिङ",
    "career":     "क्यारियर",
    "life":       "लाइफ",
    "health":     "हेल्थ",
    "growth":     "ग्रोथ",
    "focus":      "फोकस",
    "personal":   "पर्सनल",
    "productivity": "प्रोडक्टिभिटी",
    "conversation": "कन्भर्सेसन",

    # --- Greetings / interjections -------------------------------------
    "hello":      "हेलो",
    "hi":         "हाई",
    "bye":        "बाइ",
    "ok":         "ओके",
    "okay":       "ओके",
    "yes":        "यस",
    "no":         "नो",
    "thanks":     "थ्याङ्क्स",
    "please":     "प्लिज",
    "sorry":      "सरी",

    # --- Common abbreviations / acronyms -------------------------------
    # We spell these out letter-by-letter the way Nepali speakers say them.
    "ai":         "एआई",
    "ml":         "एमएल",
    "tts":        "टीटीएस",
    "stt":        "एसटीटी",
    "llm":        "एलएलएम",
    "usb":        "युएसबी",
    "pdf":        "पीडीएफ",
    "led":        "एलईडी",
    "url":        "युआरएल",
    "id":         "आइडी",
}
