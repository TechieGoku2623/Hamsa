# Hamsa product demo

`hamsa-demo.html` is a self-playing animated demo of Hamsa (sample data). Open it in any browser:

* **Pause / Restart** buttons at the top, or press Space.
* Click a chapter (1–6) to jump; earlier scenes are replayed instantly so the state is correct.
* `?autoplay=0` loads it paused.
* `?subs=0` hides burned-in subtitles (used in pro recordings by default).
* `?layout=vertical` and `?cut=short` drive the 9:16, ~30 s vertical cut.
* It follows the system dark mode and `prefers-reduced-motion`, and stacks to one column under 860 px.

Silent baseline videos (unchanged by the pro pipeline): `hamsa-demo.mp4`, `hamsa-demo-vertical.mp4`.

## Pro video (voice, subtitles, taps, zooms, music)

Requires Python 3.10+, ffmpeg on `PATH`, Playwright Chromium, and network access (Google Fonts + edge-tts).

```bash
python -m venv demo/.venv && demo/.venv/bin/pip install playwright edge-tts
demo/.venv/bin/playwright install chromium
python demo/tts.py                  # English voiceover
python demo/tts.py --lang hi        # Hindi voiceover
python demo/record.py               # 16:9 pro video
python demo/record_vertical.py      # 9:16, 30 s cut
```

Outputs:

* `demo/hamsa-demo-pro.mp4` — 1600×900, narration, subtitles, tap ripples, camera zooms, optional music.
* `demo/hamsa-demo-vertical.mp4` — 1080×1920 short cut with the same audio pipeline.

Add optional background music at `demo/assets/music.mp3` (royalty-free; never downloaded automatically). Without it, the scripts print a note and export voice only.

During `record.py`, layout is checked at several points; extracted QA frames land in `demo/_video/`.
