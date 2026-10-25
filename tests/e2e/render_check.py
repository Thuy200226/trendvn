"""Offline media integration test. Synthetic fixtures only; no uploads or AI calls."""

import json
from pathlib import Path
import sys

sys.path.insert(0, "/app")  # inside the worker image the package lives in /app
from trendvn_worker.media.ffmpeg import probe, run
from trendvn_worker.media.fingerprint import fingerprint, similar
from trendvn_worker.media.render import render

root = Path("/tmp/trendvn-render-check")
root.mkdir(exist_ok=True)
source = root / "synthetic.mp4"
run(
    [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=360x640:rate=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100",
        "-t",
        "6",
        "-vf",
        "drawtext=text='TEST ONLY - NOT A REAL TREND':fontcolor=white:fontsize=16:x=15:y=80",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(source),
    ]
)
duration, _ = probe(source)
assert abs(duration - 6) < 0.2
fp = fingerprint(source, duration)
analysis = {
    "kind": "dialogue",
    "confidence": 0.99,
    "segments": [
        {"start": 0.5, "end": 2.5, "vi": "\u0110\u00e2y l\u00e0 video ki\u1ec3m th\u1eed ph\u1ee5 \u0111\u1ec1 ti\u1ebfng Vi\u1ec7t."},
        {"start": 3, "end": 5.5, "vi": "Kh\u00f4ng ph\u1ea3i video th\u1ecbnh h\u00e0nh ho\u1eb7c b\u00e0i \u0111\u0103ng th\u1eadt."},
    ],
}
subdir = root / "subtitles"
subdir.mkdir(exist_ok=True)
out = render(source, subdir, analysis, "vietsub", duration)
assert out.stat().st_size > 1000
passthrough = root / "music"
passthrough.mkdir(exist_ok=True)
music = render(source, passthrough, {"segments": []}, "original", duration)
assert similar(fp, fingerprint(music, duration))
run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", str(out), "-frames:v", "1", str(root / "preview.png")])
print(
    json.dumps(
        {
            "media_decode": "passed",
            "duration": "passed",
            "subtitle_render": "passed",
            "original_audio_route": "passed",
            "fingerprint": "passed",
            "fixture": "synthetic only",
            "gemini_live": "not tested",
            "tiktok_publish": "not tested",
        }
    )
)
