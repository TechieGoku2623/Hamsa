"""Generate the Hamsa demo voiceover with edge-tts.

    python demo/tts.py
    python demo/tts.py --lang hi
    python demo/tts.py --voice en-IN-PrabhatNeural
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
NARRATION = {"en": HERE / "narration.json", "hi": HERE / "narration.hi.json"}
DEFAULT_VOICE = {"en": "en-IN-NeerjaNeural", "hi": "hi-IN-SwaraNeural"}
SILENCE_RE = re.compile(r"silence_(start|end): (-?[0-9.]+)")


def probe_ms(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return round(float(out) * 1000)


def tighten(path: Path, lead: float = 0.08, tail: float = 0.15, gap: float = 0.4) -> None:
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-45dB:d=0.12", "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    ).stderr
    total = probe_ms(path) / 1000
    spans, start = [], None
    for kind, value in SILENCE_RE.findall(log):
        if kind == "start":
            start = max(0.0, float(value))
        elif start is not None:
            spans.append((start, float(value)))
            start = None
    if start is not None:
        spans.append((start, total))
    cuts = []
    for a, b in spans:
        if a <= 0.01:
            keep_from = b - lead
            if keep_from > 0:
                cuts.append((0.0, keep_from))
        elif b >= total - 0.05:
            if b - a > tail:
                cuts.append((a + tail, total + 1))
        elif b - a > gap:
            mid = gap / 2
            cuts.append((a + mid, b - mid))
    if not cuts:
        return
    expr = "+".join(f"between(t,{a:.4f},{b:.4f})" for a, b in cuts)
    tmp = path.with_suffix(".tight.mp3")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
         "-af", f"aselect='not({expr})',asetpts=N/SR/TB", "-c:a", "libmp3lame", "-b:a", "128k", str(tmp)],
        check=True,
    )
    tmp.replace(path)


async def synth(text: str, voice: str, rate: str, path: Path) -> None:
    for attempt in range(4):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(path))
            if path.stat().st_size > 0:
                return
        except Exception as exc:
            if attempt == 3:
                raise
            print(f"  retry {attempt + 1}: {exc}", file=sys.stderr)
        await asyncio.sleep(2 ** (attempt + 1))


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", choices=sorted(NARRATION), default="en")
    ap.add_argument("--voice")
    ap.add_argument("--rate", default="+0%")
    ap.add_argument("--out", type=Path, default=HERE / "_audio")
    ap.add_argument("--keep-pauses", action="store_true")
    args = ap.parse_args()
    if not shutil.which("ffprobe"):
        print("ffprobe not found", file=sys.stderr)
        return 1

    voice = args.voice or DEFAULT_VOICE[args.lang]
    lines = json.loads(NARRATION[args.lang].read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("scene_*.mp3"):
        old.unlink()

    scenes = []
    for i, text in enumerate(lines):
        path = args.out / f"scene_{i:02d}.mp3"
        await synth(text, voice, args.rate, path)
        if not args.keep_pauses:
            tighten(path)
        ms = probe_ms(path)
        scenes.append({"scene": i, "file": path.name, "ms": ms, "text": text})
        print(f"scene {i}: {ms / 1000:5.2f} s  {text[:58]}")

    payload = {
        "lang": args.lang,
        "voice": voice,
        "rate": args.rate,
        "ms": {str(s["scene"]): s["ms"] for s in scenes},
        "scenes": scenes,
    }
    (args.out / "timings.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"total {sum(s['ms'] for s in scenes) / 1000:.2f} s -> {args.out / 'timings.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
