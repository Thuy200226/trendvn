"""Ask Gemini what a video contains and turn the answer into a route."""

import base64
import json

from ..domain.analysis import validate_analysis
from ..media.ffmpeg import ffmpeg
from .gemini import generate
from .prompts import ANALYSIS_SCHEMA, analysis_prompt


def analyze(store, path, duration, cfg, folder, lenient=False):
    proxy = folder / "analysis.mp4"
    # Gemini looks at one frame per second whatever the file's frame rate, so 1 fps loses nothing and halves the file and the work
    ffmpeg(
        "-i", str(path), "-vf", "scale=384:-2,fps=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-c:a", "aac", "-b:a", "48k", "-movflags", "+faststart", str(proxy),
    )  # fmt: skip
    if proxy.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("Analysis proxy exceeds 12MB")
    parts = [
        {"text": analysis_prompt(cfg.get("caption_style", "hook")) + "\nVideo length: %.1f seconds." % duration},
        {"inline_data": {"mime_type": "video/mp4", "data": base64.b64encode(proxy.read_bytes()).decode()}},
    ]
    data = generate(store, cfg, parts, ANALYSIS_SCHEMA)
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    try:
        a = json.loads(text)
    except Exception:
        raise ValueError("Gemini did not return valid analysis JSON") from None
    if isinstance(a, list) and a:
        a = a[0]
    route = validate_analysis(a, duration, cfg["audio_confidence"], strict=True, lenient=lenient, accepted_topics=store.wanted_topics())
    return a, route
