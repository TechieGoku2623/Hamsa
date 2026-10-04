"""Script and language identification for short chat messages.

Native script is identified from Unicode blocks. Romanized Indic (Hinglish, Tanglish, ...)
is identified from high-frequency function words, which is enough to pick a reply language."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

_BLOCKS = [
    (0x0900, 0x097F, "Deva"),
    (0x0980, 0x09FF, "Beng"),
    (0x0A00, 0x0A7F, "Guru"),
    (0x0A80, 0x0AFF, "Gujr"),
    (0x0B00, 0x0B7F, "Orya"),
    (0x0B80, 0x0BFF, "Taml"),
    (0x0C00, 0x0C7F, "Telu"),
    (0x0C80, 0x0CFF, "Knda"),
    (0x0D00, 0x0D7F, "Mlym"),
    (0xABC0, 0xABFF, "Mtei"),
    (0x1C50, 0x1C7F, "Olck"),
]

SCRIPT_LANG = {
    "Beng": "bn", "Guru": "pa", "Gujr": "gu", "Orya": "or", "Taml": "ta",
    "Telu": "te", "Knda": "kn", "Mlym": "ml", "Mtei": "mni", "Olck": "sat",
}

_WORD = re.compile(r"[a-z]+")

_ROMAN_MARKERS = {
    "hi_latn": {
        "hai", "hain", "kya", "kitna", "kitne", "kitni", "chahiye", "mujhe", "bhejo", "bhej", "dena", "do", "karo",
        "kar", "nahi", "nahin", "haan", "bhai", "bhaiya", "aap", "hum", "mera", "meri", "kab", "kahan", "aur",
        "wala", "wali", "ka", "ki", "ke", "se", "ko", "bhi", "abhi", "diya", "gaya", "ho", "hoga", "milega",
        "dijiye", "bata", "batao", "dikhao", "acha", "accha", "theek", "thik", "shukriya", "dhanyavad", "kilo",
    },
    "ta_latn": {
        "venum", "vendum", "enna", "irukka", "irukku", "evlo", "evvalavu", "vilai", "anuppu", "anupunga", "romba",
        "nandri", "illa", "illai", "sari", "seri", "kudunga", "vaanga", "eppo", "varum", "podhum", "pothum", "naan",
        "unga", "enakku", "kadai", "vendam", "konjam", "aachu",
    },
    "te_latn": {
        "kavali", "kaavali", "enti", "entha", "undi", "ledu", "pampandi", "cheyyandi", "meeru", "naaku", "dhara",
        "ippudu", "eppudu", "vastundi", "ayyindi", "chalu", "dhanyavadalu", "andi",
    },
    "bn_latn": {
        "chai", "lagbe", "koto", "dam", "pathan", "pathiye", "ami", "amar", "apni", "ache", "nei", "kobe", "asbe",
        "dhonnobad", "hobe", "korun", "din", "bhalo", "na",
    },
}
# "chai" is tea in Hindi and "want" in Bengali; do not let it decide alone.
_AMBIGUOUS = {"chai", "do", "na", "din", "dam", "ho", "ka", "ki", "ke", "se", "ko"}

_MARATHI_MARKERS = {"आहे", "पाहिजे", "हवे", "हवं", "का?", "किती", "पाठवा", "नाही", "मला", "तुम्ही", "आणि", "झाले", "केव्हा"}
_HINDI_MARKERS = {"है", "चाहिए", "कितना", "कितने", "भेजो", "भेजिए", "मुझे", "नहीं", "और", "कब", "क्या", "दो", "दीजिए", "हैं"}


def script_counts(text: str) -> Counter:
    c: Counter = Counter()
    for ch in text:
        cp = ord(ch)
        if ch.isspace() or not ch.isalpha() and unicodedata.category(ch)[0] != "M":
            continue
        for lo, hi, name in _BLOCKS:
            if lo <= cp <= hi:
                c[name] += 1
                break
        else:
            if ch.isascii():
                c["Latn"] += 1
            else:
                c["Other"] += 1
    return c


def detect(text: str) -> str:
    """Return a reply-language code: en, hi, hi_latn, mr, ta, ta_latn, te, te_latn, bn, bn_latn, kn, ..."""
    counts = script_counts(text)
    if not counts:
        return "en"
    script, _ = counts.most_common(1)[0]
    if script == "Deva":
        words = set(text.split())
        if len(words & _MARATHI_MARKERS) > len(words & _HINDI_MARKERS):
            return "mr"
        return "hi"
    if script in SCRIPT_LANG:
        return SCRIPT_LANG[script]
    words = _WORD.findall(text.lower())
    scores = {lang: sum(1 for w in words if w in m and w not in _AMBIGUOUS) for lang, m in _ROMAN_MARKERS.items()}
    weak = {lang: sum(1 for w in words if w in m and w in _AMBIGUOUS) for lang, m in _ROMAN_MARKERS.items()}
    best = max(scores, key=lambda k: (scores[k], weak[k]))
    if scores[best] >= 1 or weak[best] >= 2:
        return best
    return "en"


_ENGLISH_MARKERS = {
    "i", "me", "my", "we", "you", "your", "the", "is", "are", "am", "want", "need", "please", "send", "give", "what",
    "how", "when", "where", "do", "does", "can", "have", "and", "of", "for", "to", "it", "this", "that", "show", "much",
    "order", "thanks", "thank", "hello", "hi", "hey", "yes", "no", "ok", "okay",
}


def detect_in_context(text: str, previous: str | None) -> str:
    """Like detect(), but a Latin-script message with no language evidence ("1 kg basmati", "confirm")
    keeps the conversation's previous language instead of flipping to English."""
    lang = detect(text)
    if lang != "en" or not previous:
        return lang
    words = set(_WORD.findall(text.lower()))
    return "en" if words & _ENGLISH_MARKERS else previous


def script_of(text: str) -> str:
    counts = script_counts(text)
    return counts.most_common(1)[0][0] if counts else "Latn"


def normalize_digits(text: str) -> str:
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except ValueError:
                pass
        out.append(ch)
    return "".join(out)
