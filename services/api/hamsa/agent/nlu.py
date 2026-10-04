"""Rules tier: intent keywords + catalog mention extraction with quantities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz
from rapidfuzz.distance import DamerauLevenshtein

from .lang import normalize_digits
from .lexicon import GROCERY_SYNONYMS, INTENT_KEYWORDS, NUMBER_WORDS, PAST_MARKERS, UNIT_WORDS

_TOKEN = re.compile(r"[^\s,;:!?()\[\]{}\"'|/]+")
_NUM_UNIT = re.compile(r"^(\d+(?:\.\d+)?)([^\d.]+)?$")
# Words that are numbers but also articles/verbs after a noun ("cheeni de do" = "give sugar").
_VERB_LIKE_NUMBERS = {"a", "an", "do", "ek", "दो", "एक", "ஒரு", "ఒక", "এক"}
_NUM_PREFIX = re.compile(r"^\d+(?:\.\d+)?")
_NAME_STOPWORDS = {"and", "the", "with", "for", "pack", "kg", "gm", "ml", "ltr"} | set(UNIT_WORDS)


def _is_latin(s: str) -> bool:
    return all(ord(c) < 0x250 for c in s)


@lru_cache(maxsize=4096)
def _word_re(kw: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])")


def prepare(text: str) -> str:
    return normalize_digits(text).lower().strip()


def keyword_hits(text: str, keywords: list[str]) -> list[tuple[int, int, str]]:
    hits = []
    for kw in keywords:
        if _is_latin(kw):
            for m in _word_re(kw).finditer(text):
                hits.append((m.start(), m.end(), kw))
        else:
            start = text.find(kw)
            while start != -1:
                hits.append((start, start + len(kw), kw))
                start = text.find(kw, start + 1)
    return hits


def detect_intents(text: str) -> set[str]:
    t = prepare(text)
    found = {intent for intent, kws in INTENT_KEYWORDS.items() if keyword_hits(t, kws)}
    # "payment done" / "payment kar diya" is a claim, not a request to pay.
    if "pay" in found and keyword_hits(t, PAST_MARKERS):
        found.add("paid")
    if "paid" in found:
        found.discard("pay")
    return found


@dataclass
class CatalogEntry:
    sku: str
    name: str
    unit: str
    price_paise: int
    aliases: list[str] = field(default_factory=list)
    stock: int | None = None

    def all_aliases(self) -> list[str]:
        out = {self.name.lower(), *(a.lower() for a in self.aliases if a)}
        for word in re.findall(r"[a-z]+", self.name.lower()):
            # Single words ("rice" in "Basmati Rice") match too; overlap resolution prefers longer aliases.
            if len(word) >= 3 and word not in _NAME_STOPWORDS:
                out.add(word)
            for syn in GROCERY_SYNONYMS.get(word, []):
                out.add(syn.lower())
        return sorted(out, key=len, reverse=True)


@dataclass
class Mention:
    sku: str
    start: int
    end: int
    alias: str
    score: float
    qty: float = 1.0
    qty_unit: str | None = None
    qty_explicit: bool = False


def _tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(text)]


def _number(tok: str) -> tuple[float, str | None] | None:
    m = _NUM_UNIT.match(tok)
    if m:
        unit = UNIT_WORDS.get(m.group(2)) if m.group(2) else None
        if m.group(2) and unit is None and m.group(2) not in {"x"}:
            return None
        return float(m.group(1)), unit
    if tok.startswith("x") and tok[1:].isdigit():
        return float(tok[1:]), None
    if tok in NUMBER_WORDS:
        return float(NUMBER_WORDS[tok]), None
    return None


def _qty_near(tokens: list[tuple[int, int, str]], start: int, end: int) -> tuple[float, str | None] | None:
    before = [t for t in tokens if t[1] <= start][-3:]
    after = [t for t in tokens if t[0] >= end][:3]
    # "2 kg sugar", "do kilo cheeni"
    for i in range(len(before) - 1, -1, -1):
        tok = before[i][2]
        if tok in UNIT_WORDS and i > 0:
            n = _number(before[i - 1][2])
            if n:
                return n[0], UNIT_WORDS[tok]
        n = _number(tok)
        if n and (i == len(before) - 1 or before[i + 1][2] in UNIT_WORDS):
            return n
    # "sugar 2 kg", "சர்க்கரை 2 கிலோ", "cheeni x2"
    for i, (_, _, tok) in enumerate(after[:2]):
        n = _number(tok)
        if n:
            unit = n[1]
            if unit is None and i + 1 < len(after) and after[i + 1][2] in UNIT_WORDS:
                unit = UNIT_WORDS[after[i + 1][2]]
            if tok in _VERB_LIKE_NUMBERS and unit is None:
                continue
            return n[0], unit
    return None


def find_mentions(text: str, catalog: list[CatalogEntry]) -> list[Mention]:
    t = prepare(text)
    tokens = _tokens(t)
    raw: list[Mention] = []
    for item in catalog:
        best: Mention | None = None
        for alias in item.all_aliases():
            if len(alias) < 2:
                continue
            hits = keyword_hits(t, [alias])
            if hits:
                s, e, _ = hits[0]
                cand = Mention(item.sku, s, e, alias, 100.0)
            elif _is_latin(alias) and len(alias) >= 5 and " " not in alias:
                cand = None
                for s, e, tok in tokens:
                    tok = _NUM_PREFIX.sub("", tok)
                    if abs(len(tok) - len(alias)) <= 2 and _is_latin(tok) and tok[:1] == alias[:1]:
                        max_edits = 1 if len(alias) <= 7 else 2
                        if DamerauLevenshtein.distance(tok, alias) <= max_edits:
                            r = fuzz.ratio(tok, alias)
                            if cand is None or r > cand.score:
                                cand = Mention(item.sku, s, e, alias, r)
            else:
                cand = None
            if cand and (best is None or (cand.score, len(cand.alias)) > (best.score, len(best.alias))):
                best = cand
        if best:
            raw.append(best)

    # Keep the most specific item per overlapping span; equal specificity stays ambiguous.
    raw.sort(key=lambda m: (m.start, -(m.end - m.start)))
    for m in raw:
        q = _qty_near(tokens, m.start, m.end)
        if q:
            m.qty, m.qty_unit, m.qty_explicit = q[0], q[1], True
    return raw


def group_overlaps(mentions: list[Mention]) -> list[list[Mention]]:
    groups: list[list[Mention]] = []
    for m in sorted(mentions, key=lambda m: m.start):
        for g in groups:
            if any(m.start < o.end and o.start < m.end for o in g):
                g.append(m)
                break
        else:
            groups.append([m])
    resolved = []
    for g in groups:
        top_len = max(len(m.alias) for m in g)
        top_score = max(m.score for m in g if len(m.alias) == top_len)
        resolved.append([m for m in g if len(m.alias) == top_len and m.score == top_score])
    return resolved


def convert_qty(qty: float, said_unit: str | None, item_unit: str) -> float:
    if said_unit == "g" and item_unit == "kg":
        return qty / 1000
    if said_unit == "ml" and item_unit == "l":
        return qty / 1000
    if said_unit == "kg" and item_unit == "g":
        return qty * 1000
    return qty


def clean_qty(qty: float, item_unit: str) -> float:
    if item_unit in {"kg", "l"}:
        return max(0.25, round(qty * 4) / 4)
    return float(max(1, round(qty)))
