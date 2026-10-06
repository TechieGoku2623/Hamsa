"""9:16, ~30 s short cut with voice, subtitles and music -> demo/hamsa-demo-vertical.mp4."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from mix_audio import mix, mux_video
from record import encode_video, extract_frames, inject_init, load_narration, probe_duration

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "_audio" / "vertical"
TIMINGS = AUDIO / "timings.json"
OUT = HERE / "hamsa-demo-vertical.mp4"
VIDEO_TMP = HERE / "_video"
NARRATE_SCENES = {2, 3, 5, 7}


def ensure_tts() -> None:
    if TIMINGS.is_file():
        return
    print("Generating faster voiceover for the 30 s cut…")
    subprocess.run(
        [sys.executable, str(HERE / "tts.py"), "--rate", "+32%", "--out", str(AUDIO)],
        check=True,
        cwd=HERE.parent,
    )


def record_vertical() -> float:
    ensure_tts()
    from playwright.sync_api import sync_playwright
    import glob
    import tempfile
    import time

    from record import HIDE_CONTROLS, PAGE

    timings = json.loads(TIMINGS.read_text(encoding="utf-8"))
    lines = load_narration()
    query = "autoplay=0&record=1&layout=vertical&cut=short"
    VIDEO_TMP.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1080, "height": 1920}, color_scheme="light",
            record_video_dir=tmp, record_video_size={"width": 1080, "height": 1920},
        )
        page = ctx.new_page()
        page.add_init_script(inject_init(timings, lines))
        t0 = time.monotonic()
        page.goto(PAGE + "?" + query)
        page.add_style_tag(content=HIDE_CONTROLS)
        page.wait_for_function("window.hamsaFontsReady === true", timeout=60_000)
        schedule = page.evaluate("window.hamsaDemo.schedule")
        total_ms = page.evaluate("window.hamsaDemo.totalMs")
        demo_ms = page.evaluate("window.hamsaDemo.demoMs")
        print(f"short cut demo timeline: {demo_ms / 1000:.2f}s (+ 4s outro hold)")
        if demo_ms > 30_500:
            print(f"Warning: short cut body is {demo_ms / 1000:.2f}s (target ≤30s)", file=sys.stderr)
        page.evaluate("window.hamsaDemo.restart()")
        lead = time.monotonic() - t0
        page.wait_for_function("window.hamsaDemo.state().finished", timeout=180_000, polling=100)
        page.wait_for_timeout(4000)
        ctx.close()
        browser.close()
        webm = glob.glob(f"{tmp}/*.webm")[0]

        silent = VIDEO_TMP / "vertical_silent.mp4"
        encode_video(webm, silent, max(0.5, lead), total_ms / 1000 + 0.35)
        audio = VIDEO_TMP / "vertical_audio.m4a"
        mix(TIMINGS, schedule, audio, narration_only_scenes=NARRATE_SCENES)
        mux_video(silent, audio, OUT)

    dur = probe_duration(OUT)
    extract_frames(OUT, VIDEO_TMP / "vertical_frames")
    return dur


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found", file=sys.stderr)
        return 2
    dur = record_vertical()
    print(f"wrote {OUT.name} ({dur:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
