"""Mix narration MP3s (and optional music) for demo videos."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUSIC = HERE / "assets" / "music.mp3"
OUTRO_PAD_S = 4.0


def load_timings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def scene_starts_ms(schedule: list[dict]) -> list[tuple[int, int]]:
    """(scene_index, start_ms) in playback order."""
    return [(e["scene"], e["start"]) for e in schedule]


def build_schedule(order: list[int], scenes_dur: dict[int, int]) -> list[dict]:
    acc = 0
    out = []
    for scene in order:
        dur = scenes_dur[scene]
        out.append({"scene": scene, "start": acc, "duration": dur})
        acc += dur
    return out


def mix(
    timings_path: Path,
    schedule: list[dict],
    out_audio: Path,
    *,
    narration_only_scenes: set[int] | None = None,
) -> float:
    """Return total timeline length in seconds (demo + outro pad)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")

    data = load_timings(timings_path)
    total_ms = sum(e["duration"] for e in schedule) + int(OUTRO_PAD_S * 1000)
    total_s = total_ms / 1000

    chains: list[str] = []
    inputs: list[str] = []
    idx = 0
    ms_map = {int(k): v for k, v in data["ms"].items()}
    audio_dir = timings_path.parent

    for scene, start in scene_starts_ms(schedule):
        if narration_only_scenes is not None and scene not in narration_only_scenes:
            continue
        file_ms = ms_map.get(scene)
        mp3 = audio_dir / f"scene_{scene:02d}.mp3"
        if not file_ms or not mp3.is_file():
            continue
        inputs.extend(["-i", str(mp3)])
        delay = int(start)
        chains.append(f"[{idx}:a]adelay={delay}|{delay},apad=whole_dur={total_s}[v{idx}]")
        idx += 1

    if not chains:
        raise RuntimeError("no narration tracks to mix")

    mix_in = "".join(f"[v{i}]" for i in range(idx))
    voice_chain = ";".join(chains) + f";{mix_in}amix=inputs={idx}:duration=longest:dropout_transition=0[voice]"

    if MUSIC.is_file():
        inputs.extend(["-i", str(MUSIC)])
        music_i = idx
        filt = (
            f"{voice_chain};"
            f"[{music_i}:a]volume=-24dB,afade=t=in:st=0:d=2,afade=t=out:st={max(0, total_s - 3):.3f}:d=3[music];"
            f"[voice][music]sidechaincompress=threshold=0.02:ratio=8:attack=5:release=250:makeup=2[ducked];"
            f"[ducked]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        )
    else:
        print(
            "Note: demo/assets/music.mp3 not found — skipping background music. "
            "Add a royalty-free track (YouTube Audio Library or Pixabay Music).",
            file=sys.stderr,
        )
        filt = f"{voice_chain};[voice]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"

    out_audio.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", filt, "-map", "[aout]",
           "-t", f"{total_s:.3f}", "-c:a", "aac", "-b:a", "192k", str(out_audio)]
    subprocess.run(cmd, check=True)
    return total_s


def mux_video(video: Path, audio: Path, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)],
        check=True,
    )
