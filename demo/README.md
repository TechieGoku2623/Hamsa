# Hamsa product demo

`hamsa-demo.html` is a self-playing, ~57 s animated demo of Hamsa (sample data). Open it in any browser:

* **Pause / Restart** buttons at the top, or press Space.
* Click a chapter (1–6) to jump; earlier scenes are replayed instantly so the state is correct.
* `?autoplay=0` loads it paused.
* It follows the system dark mode and `prefers-reduced-motion`, and stacks to one column under 860 px.

## Re-record the videos

Requires Python 3.10+, ffmpeg on `PATH`, and network access (Google Fonts).

```bash
pip install playwright && playwright install chromium
python demo/record.py                  # hamsa-demo.mp4 (1600x900) + hamsa-demo-vertical.mp4 (1080x1920)
python demo/record.py --only landscape
```

The page is recorded at 1600x900 (and 1080x1920 for the vertical cut) with the Pause/Restart controls hidden. The
recorder trims the lead-in (page load and font wait) and encodes H.264, 30 fps, yuv420p, faststart.

During each recording it saves screenshots at 10 s, 30 s and 50 s to `demo/screenshots/` and checks the layout:
nothing extends past the viewport, no clipped text, and no overlapping messages, cards, phone or console. It exits
non-zero if a check fails.
