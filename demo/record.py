"""Record demo/hamsa-demo.html to MP4 (landscape 1600x900 and vertical 1080x1920).

    pip install playwright && playwright install chromium   # plus ffmpeg on PATH
    python demo/record.py                 # both videos
    python demo/record.py --only landscape

While recording, screenshots are taken at 10 s, 30 s and 50 s of demo time and the layout is checked for
overflowing or overlapping elements. The script exits non-zero if a check fails.
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

HERE = Path(__file__).resolve().parent
PAGE = (HERE / "hamsa-demo.html").as_uri()
SHOTS_AT_S = (10, 30, 50)
HIDE_CONTROLS = ".controls { display: none !important; }"

LAYOUT_CHECK = """
() => {
  const issues = [];
  const vw = innerWidth, vh = innerHeight;
  const r = (el) => el.getBoundingClientRect();  // already in zoomed viewport pixels
  const visible = (el) => { const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden' && r(el).width > 0; };
  const inside = (child, box, name) => {
    const a = r(child), b = r(box);
    if (a.left < b.left - 1 || a.right > b.right + 1) issues.push(`${name} overflows horizontally: ${child.className}`);
  };
  const app = document.querySelector('.app');
  for (const el of [app, document.querySelector('.console'), document.querySelector('.phone')])
    if (r(el).bottom > vh + 1) issues.push(`${el.className} extends below the viewport (${Math.round(r(el).bottom)} > ${vh})`);
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
  // siblings in the phone list / feed must not overlap each other
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


def record(name: str, width: int, height: int, out: Path, shots_dir: Path) -> list[str]:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": width, "height": height}, color_scheme="light",
            record_video_dir=tmp, record_video_size={"width": width, "height": height},
        )
        page = ctx.new_page()
        t_page = time.monotonic()
        page.goto(PAGE + "?autoplay=0")
        page.add_style_tag(content=HIDE_CONTROLS)
        page.wait_for_function("window.hamsaFontsReady === true", timeout=60_000)
        total_ms = page.evaluate("window.hamsaDemo.totalMs")
        page.evaluate("window.hamsaDemo.restart()")
        lead = time.monotonic() - t_page

        for at in SHOTS_AT_S:
            # Screenshots don't pause the page, so the recording stays continuous.
            page.wait_for_function(f"window.hamsaDemo.state().clock >= {at * 1000}", timeout=120_000, polling=50)
            shot = shots_dir / f"{name}_{at:02d}s.png"
            page.screenshot(path=str(shot))
            issues = page.evaluate(LAYOUT_CHECK)
            print(f"[{name}] {at:>2}s  {shot.relative_to(HERE.parent)}  {'OK' if not issues else issues}")
            problems += [f"{name} @{at}s: {i}" for i in issues]

        page.wait_for_function("window.hamsaDemo.state().finished", timeout=120_000, polling=100)
        page.wait_for_timeout(400)
        ctx.close()
        browser.close()
        webm = glob.glob(f"{tmp}/*.webm")[0]
        encode(webm, out, lead, total_ms)
    return problems


def encode(webm: str, out: Path, lead_s: float, total_ms: int) -> None:
    """Trim the blank lead-in (page load + font wait) and encode H.264 for sharing."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", webm],
                           capture_output=True, text=True, check=True)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    start = max(0.6, lead_s)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", webm, "-t", f"{total_ms / 1000 + 0.4:.2f}",
           "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
           "-an", str(out)]
    subprocess.run(cmd, check=True)
    print(f"wrote {out.relative_to(HERE.parent)} (source {duration:.1f}s, demo {total_ms / 1000:.1f}s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["landscape", "vertical"])
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 2
    shots = HERE / "screenshots"
    shots.mkdir(exist_ok=True)
    jobs = [("landscape", 1600, 900, HERE / "hamsa-demo.mp4"), ("vertical", 1080, 1920, HERE / "hamsa-demo-vertical.mp4")]
    problems: list[str] = []
    for name, w, h, out in jobs:
        if args.only in (None, name):
            problems += record(name, w, h, out, shots)
    if problems:
        print("\nLayout problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
