"""Record the pro Hamsa demo (voice, subtitles, taps, zooms) to demo/hamsa-demo-pro.mp4.

Does not overwrite demo/hamsa-demo.mp4 (the silent baseline).

    python demo/tts.py
    python demo/record.py
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from mix_audio import mix, mux_video

HERE = Path(__file__).resolve().parent
PAGE = (HERE / "hamsa-demo.html").as_uri()
TIMINGS = HERE / "_audio" / "timings.json"
NARRATION = HERE / "narration.json"
OUT = HERE / "hamsa-demo-pro.mp4"
VIDEO_TMP = HERE / "_video"
HIDE_CONTROLS = ".controls { display: none !important; }"

LAYOUT_CHECK = """
() => {
  const issues = [];
  const vw = innerWidth, vh = innerHeight;
  const r = (el) => el.getBoundingClientRect();
  const visible = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && r(el).width > 0; };
  const inside = (child, box, name) => {
    const a = r(child), b = r(box);
    if (a.left < b.left - 1 || a.right > b.right + 1) issues.push(`${name} overflows horizontally: ${child.className}`);
  };
  const bounds = document.getElementById('stageViewport') || document.querySelector('.app');
  const bb = r(bounds);
  const zoomed = (window.HAMSA_CAM_SCALE || 1) > 1.02;
  if (!zoomed) for (const el of [document.querySelector('.console'), document.querySelector('.phone')])
    if (el && r(el).bottom > bb.bottom + 2) issues.push(`${el.className} extends below the stage (${Math.round(r(el).bottom)} > ${Math.round(bb.bottom)})`);
  const app = document.querySelector('.app');
  if (r(app).bottom > vh + 1) issues.push(`app extends below the viewport (${Math.round(r(app).bottom)} > ${vh})`);
  if (document.documentElement.scrollWidth > vw + 1) issues.push('horizontal scroll');
  for (const el of document.querySelectorAll('.caption h1, .caption p, .chapter .lbl, .stat .v, .console-head h2'))
    if (visible(el) && el.scrollWidth > el.clientWidth + 1) issues.push(`text clipped: "${el.textContent.trim().slice(0, 40)}"`);
  const msgs = document.querySelector('#msgs');
  for (const el of msgs.children) if (visible(el)) inside(el, msgs, 'phone message');
  const feed = document.querySelector('#feed');
  for (const el of feed.children) if (visible(el)) inside(el, feed, 'feed card');
  for (const el of document.querySelectorAll('.bubble, .card'))
    for (const c of el.querySelectorAll('*')) if (visible(c) && c.scrollWidth > c.clientWidth + 2 && getComputedStyle(c).overflow === 'visible' && c.children.length === 0)
      issues.push(`content wider than box: "${c.textContent.trim().slice(0, 40)}"`);
  for (const list of [msgs, feed]) {
    const kids = [...list.children].filter(visible);
    for (let i = 1; i < kids.length; i++) if (r(kids[i]).top < r(kids[i - 1]).bottom - 1) issues.push(`overlap in ${list.id}`);
  }
  const phone = r(document.querySelector('.phone')), con = r(document.querySelector('.console'));
  const sideBySide = con.left >= phone.right - 1;
  if (!sideBySide && con.top < phone.bottom - 1) issues.push('phone and console overlap');
  return issues;
}
"""


def load_narration() -> list[str]:
    return json.loads(NARRATION.read_text(encoding="utf-8"))


def inject_init(timings: dict, lines: list[str]) -> str:
    ms = timings.get("ms", {})
    return f"window.HAMSA_TIMINGS = {json.dumps(ms)}; window.HAMSA_NARRATION = {json.dumps(lines)};"


def encode_video(webm: str, out: Path, start_s: float, duration_s: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start_s:.3f}", "-i", webm, "-t", f"{duration_s:.3f}",
         "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
         "-an", str(out)],
        check=True,
    )


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def extract_frames(video: Path, out_dir: Path, count: int = 5) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = probe_duration(video)
    paths = []
    for i in range(count):
        t = dur * (i + 0.5) / count
        p = out_dir / f"frame_{i:02d}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", str(p)],
            check=True,
        )
        paths.append(p)
    return paths


def record_pro(width: int, height: int, query: str, timings_path: Path, out_mp4: Path, label: str) -> tuple[float, list[str]]:
    if not timings_path.is_file():
        print(f"Missing {timings_path}; run demo/tts.py first.", file=sys.stderr)
        sys.exit(2)

    timings = json.loads(timings_path.read_text(encoding="utf-8"))
    lines = load_narration()
    problems: list[str] = []
    VIDEO_TMP.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": width, "height": height}, color_scheme="light",
            record_video_dir=tmp, record_video_size={"width": width, "height": height},
        )
        page = ctx.new_page()
        page.add_init_script(inject_init(timings, lines))
        t0 = time.monotonic()
        page.goto(PAGE + "?" + query)
        page.add_style_tag(content=HIDE_CONTROLS)
        page.wait_for_function("window.hamsaFontsReady === true", timeout=60_000)
        schedule = page.evaluate("window.hamsaDemo.schedule")
        demo_ms = page.evaluate("window.hamsaDemo.demoMs")
        total_ms = page.evaluate("window.hamsaDemo.totalMs")
        page.evaluate("window.hamsaDemo.restart()")
        lead = time.monotonic() - t0

        checkpoints = [int(demo_ms * x) for x in (0.15, 0.35, 0.55, 0.75, 0.92)]
        for at in checkpoints:
            page.wait_for_function(f"window.hamsaDemo.state().clock >= {at}", timeout=180_000, polling=50)
            issues = page.evaluate(LAYOUT_CHECK)
            if issues:
                problems += [f"{label} @{at}ms: {i}" for i in issues]

        page.wait_for_function("window.hamsaDemo.state().finished", timeout=300_000, polling=100)
        page.wait_for_timeout(4000)
        ctx.close()
        browser.close()
        webm = glob.glob(f"{tmp}/*.webm")[0]

        silent = VIDEO_TMP / f"{label}_silent.mp4"
        encode_video(webm, silent, max(0.5, lead), total_ms / 1000 + 0.35)
        audio = VIDEO_TMP / f"{label}_audio.m4a"
        mix(timings_path, schedule, audio)
        mux_video(silent, audio, out_mp4)

    dur = probe_duration(out_mp4)
    frames = extract_frames(out_mp4, VIDEO_TMP / f"{label}_frames")
    print(f"wrote {out_mp4.name} ({dur:.1f}s), frames in {frames[0].parent.relative_to(HERE)}")
    return dur, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found", file=sys.stderr)
        return 2
    dur, problems = record_pro(1600, 900, "autoplay=0&record=1", TIMINGS, OUT, "landscape_pro")
    if problems:
        print("\nLayout problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(f"Final duration: {dur:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
