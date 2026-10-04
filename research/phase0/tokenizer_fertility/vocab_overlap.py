"""Compares the Sarvam-30B and Gemma 4 vocabularies (overlap, shared IDs, per-script deltas)."""

from __future__ import annotations

import unicodedata
from collections import Counter

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

SENTENCEPIECE_SPACE = "\u2581"


def vocab(repo: str) -> dict[str, int]:
    return Tokenizer.from_file(hf_hub_download(repo, "tokenizer.json")).get_vocab()


def script_of(token: str) -> str:
    for ch in token.replace(SENTENCEPIECE_SPACE, ""):
        if ord(ch) > 0x2FF:
            try:
                return unicodedata.name(ch).split()[0]
            except ValueError:
                return "UNNAMED"
    return "LATIN/ASCII"


def main() -> None:
    sarvam, gemma = vocab("sarvamai/sarvam-30b"), vocab("google/gemma-4-E4B-it")
    shared = set(sarvam) & set(gemma)
    same_id = sum(1 for t in shared if sarvam[t] == gemma[t])
    print(f"sarvam={len(sarvam):,} gemma4={len(gemma):,} shared={len(shared):,} shared_with_same_id={same_id:,}")
    print("sarvam-only by script:", Counter(script_of(t) for t in set(sarvam) - shared).most_common(12))
    print("gemma4-only by script:", Counter(script_of(t) for t in set(gemma) - shared).most_common(12))


if __name__ == "__main__":
    main()
