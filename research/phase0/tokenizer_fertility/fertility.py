"""Tokenizer fertility harness for Hamsa Phase 0.

Measures, for each candidate tokenizer:
  1. Fertility (tokens per whitespace word) on native-script and romanized text
     for the 22 scheduled Indian languages (AI4Bharat Bhasha-Abhijnaanam).
  2. Tokens per message and parity vs. English on a parallel probe set of
     code-mixed business chat messages (probe_business_codemixed.jsonl).

Only tokenizer files are downloaded, never model weights.

Usage:
  python fertility.py --max-per-lang 400 --out results
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path

from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

HERE = Path(__file__).resolve().parent

CANDIDATES: dict[str, str] = {
    "qwen3.5": "Qwen/Qwen3.5-4B",
    "gemma4": "google/gemma-4-E4B-it",
    "sarvam-30b": "sarvamai/sarvam-30b",
    "sarvam-105b": "sarvamai/sarvam-105b",
    "sarvam-1": "sarvamai/sarvam-1",
    "gpt-oss": "openai/gpt-oss-20b",
    "deepseek-v4": "deepseek-ai/DeepSeek-V4-Flash",
    "ministral-3": "mistralai/Ministral-3-8B-Instruct-2512",
    "phi-4-mini": "microsoft/Phi-4-mini-instruct",
    "lfm2": "LiquidAI/LFM2-2.6B",
    "krutrim-2": "krutrim-ai-labs/Krutrim-2-instruct",
    "param-1": "bharatgenai/Param-1-2.9B-Instruct",
    "indictok-256k": "vivekvar/indictok-256k",
}

SCHEDULED = {
    "Assamese", "Bangla", "Bodo", "Dogri", "Gujarati", "Hindi", "Kannada",
    "Kashmiri", "Konkani", "Maithili", "Malayalam", "Manipuri", "Marathi",
    "Nepali", "Oriya", "Punjabi", "Sanskrit", "Santali", "Sindhi", "Tamil",
    "Telugu", "Urdu",
}


def load_tokenizer(repo: str) -> Tokenizer:
    path = hf_hub_download(repo, "tokenizer.json")
    return Tokenizer.from_file(path)


def load_bhasha(max_per_lang: int, seed: int) -> dict[tuple[str, str, str], list[str]]:
    """Returns {(language, script, form): [sentences]} where form is native|romanized."""
    zpath = hf_hub_download("ai4bharat/Bhasha-Abhijnaanam", "bhasha-abhijnaanam.zip", repo_type="dataset")
    with zipfile.ZipFile(zpath) as zf:
        rows = json.loads(zf.read("bhasha-abhijnaanam.json"))["data"]
    buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for r in rows:
        if r["language"] not in SCHEDULED:
            continue
        if r.get("native sentence"):
            buckets[(r["language"], r["script"], "native")].append(r["native sentence"].strip())
        if r.get("romanized sentence"):
            buckets[(r["language"], r["script"], "romanized")].append(r["romanized sentence"].strip())
    rng = random.Random(seed)
    out = {}
    for k, sents in buckets.items():
        sents = [s for s in sents if len(s.split()) >= 3]
        rng.shuffle(sents)
        out[k] = sents[:max_per_lang]
    return out


def fertility(tok: Tokenizer, sents: list[str]) -> float:
    n_tok = sum(len(e.ids) for e in tok.encode_batch(sents, add_special_tokens=False))
    n_words = sum(len(s.split()) for s in sents)
    return n_tok / max(n_words, 1)


def load_probe() -> dict[str, dict[int, str]]:
    probe: dict[str, dict[int, str]] = defaultdict(dict)
    for line in (HERE / "probe_business_codemixed.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            probe[r["variant"]][r["id"]] = r["text"]
    return probe


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-per-lang", type=int, default=400)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--out", type=Path, default=HERE / "results")
    ap.add_argument("--only", nargs="*", help="subset of candidate keys")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    corpus = load_bhasha(args.max_per_lang, args.seed)
    probe = load_probe()
    keys = args.only or list(CANDIDATES)

    toks: dict[str, Tokenizer] = {}
    vocab: dict[str, int] = {}
    for k in keys:
        try:
            toks[k] = load_tokenizer(CANDIDATES[k])
            vocab[k] = toks[k].get_vocab_size()
        except Exception as e:  # noqa: BLE001
            print(f"skip {k}: {type(e).__name__}: {e}")

    fert: dict[str, dict[str, float]] = {}
    for k, tok in toks.items():
        fert[k] = {}
        for (lang, script, form), sents in sorted(corpus.items()):
            if sents:
                fert[k][f"{lang}|{script}|{form}"] = round(fertility(tok, sents), 3)

    probe_tokens: dict[str, dict[str, float]] = {}
    probe_parity: dict[str, dict[str, float]] = {}
    for k, tok in toks.items():
        en = probe["en"]
        en_counts = {i: len(tok.encode(t, add_special_tokens=False).ids) for i, t in en.items()}
        probe_tokens[k], probe_parity[k] = {}, {}
        for variant, msgs in probe.items():
            counts = [len(tok.encode(msgs[i], add_special_tokens=False).ids) for i in sorted(msgs)]
            ratios = [len(tok.encode(msgs[i], add_special_tokens=False).ids) / en_counts[i] for i in sorted(msgs)]
            probe_tokens[k][variant] = round(statistics.mean(counts), 2)
            probe_parity[k][variant] = round(statistics.mean(ratios), 2)

    summary = {}
    for k in toks:
        native = [v for kk, v in fert[k].items() if kk.endswith("|native")]
        roman = [v for kk, v in fert[k].items() if kk.endswith("|romanized")]
        indic_probe = [v for var, v in probe_tokens[k].items() if var != "en"]
        summary[k] = {
            "repo": CANDIDATES[k],
            "vocab_size": vocab[k],
            "native_fertility_mean": round(statistics.mean(native), 3),
            "native_fertility_worst": round(max(native), 3),
            "native_worst_lang": max((v, kk) for kk, v in fert[k].items() if kk.endswith("|native"))[1],
            "romanized_fertility_mean": round(statistics.mean(roman), 3),
            "probe_en_tokens_per_msg": probe_tokens[k]["en"],
            "probe_indic_tokens_per_msg_mean": round(statistics.mean(indic_probe), 2),
        }

    meta = {
        "corpus": "ai4bharat/Bhasha-Abhijnaanam (native + romanized, 22 scheduled languages)",
        "max_per_lang": args.max_per_lang,
        "seed": args.seed,
        "word_definition": "whitespace split",
        "special_tokens": "excluded",
    }
    (args.out / "fertility_by_language.json").write_text(json.dumps(fert, indent=2, ensure_ascii=False))
    (args.out / "probe_tokens_per_message.json").write_text(json.dumps(probe_tokens, indent=2))
    (args.out / "probe_parity_vs_english.json").write_text(json.dumps(probe_parity, indent=2))
    (args.out / "summary.json").write_text(json.dumps({"meta": meta, "tokenizers": summary}, indent=2))
    write_markdown(args.out / "RESULTS.md", meta, summary, fert, probe_tokens, probe_parity)
    print((args.out / "RESULTS.md").read_text())


def write_markdown(path, meta, summary, fert, probe_tokens, probe_parity) -> None:
    order = sorted(summary, key=lambda k: summary[k]["native_fertility_mean"])
    lines = ["# Tokenizer fertility results (generated by fertility.py)", ""]
    lines += [f"- Corpus: {meta['corpus']}, up to {meta['max_per_lang']} sentences per language/script/form, seed {meta['seed']}",
              "- Fertility = tokens / whitespace word, special tokens excluded. Lower is cheaper.",
              "- Probe = 12 parallel business chat messages per variant; parity = tokens(variant) / tokens(English) with the same tokenizer.", ""]
    lines += ["## Summary", "",
              "| tokenizer | vocab | native fert. (mean) | native fert. (worst) | worst language | romanized fert. | probe EN tok/msg | probe Indic tok/msg |",
              "|---|---:|---:|---:|---|---:|---:|---:|"]
    for k in order:
        s = summary[k]
        lines.append(f"| {k} | {s['vocab_size']:,} | {s['native_fertility_mean']} | {s['native_fertility_worst']} | "
                     f"{s['native_worst_lang'].split('|')[0]} ({s['native_worst_lang'].split('|')[1]}) | {s['romanized_fertility_mean']} | "
                     f"{s['probe_en_tokens_per_msg']} | {s['probe_indic_tokens_per_msg_mean']} |")
    langs = sorted({kk for k in fert for kk in fert[k] if kk.endswith("|native")})
    lines += ["", "## Native-script fertility by language", "", "| language (script) | " + " | ".join(order) + " |",
              "|---|" + "---:|" * len(order)]
    for l in langs:
        name, script, _ = l.split("|")
        lines.append(f"| {name} ({script}) | " + " | ".join(str(fert[k].get(l, "")) for k in order) + " |")
    variants = list(next(iter(probe_tokens.values())).keys())
    lines += ["", "## Business probe: tokens per message", "", "| variant | " + " | ".join(order) + " |", "|---|" + "---:|" * len(order)]
    for v in variants:
        lines.append(f"| {v} | " + " | ".join(str(probe_tokens[k][v]) for k in order) + " |")
    lines += ["", "## Business probe: parity vs. English (same tokenizer)", "", "| variant | " + " | ".join(order) + " |", "|---|" + "---:|" * len(order)]
    for v in variants:
        lines.append(f"| {v} | " + " | ".join(str(probe_parity[k][v]) for k in order) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
