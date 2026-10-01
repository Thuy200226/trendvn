"""One-pass render to a TikTok-ready MP4, its quality check and the dashboard poster."""

from .ffmpeg import ffmpeg, probe
from .geometry import caption_zone, display_size, fps_of, layout
from .subtitles import ass_subtitles, subtitles

# H.264 high profile, 8-bit 4:2:0 (what every phone decodes), capped bitrate; AAC stereo
VIDEO_ENCODER = "-c:v libx264 -preset fast -crf 23 -profile:v high -pix_fmt yuv420p -maxrate 4M -bufsize 8M".split()
AUDIO_ENCODER = "-c:a aac -b:a 160k -ac 2".split()


def render(path, folder, a, route, duration, voice=None):
    """One ffmpeg pass: reframe to 9:16, burn Vietnamese subtitles when the route needs them, mix the voice-over, level the sound,
    drop the source's metadata, and write a web-friendly MP4 (H.264 high, yuv420p, AAC, faststart)."""
    out = folder / "final.mp4"
    _, meta = probe(path)
    vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in meta["streams"])
    geo = layout(*display_size(vs))
    chain = []
    if geo["reframe"]:
        chain.append(
            "[0:v]split=2[bgs][fgs];[bgs]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=8:2,scale=%d:%d:flags=bilinear,eq=brightness=-0.08[bg];"
            "[fgs]scale=%d:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]" % (geo["w"], geo["h"], geo["w"])
        )  # blur a tiny copy, then enlarge: same look, ~4x faster
    else:
        chain.append("[0:v]scale=%d:%d[v0]" % (geo["w"], geo["h"]))
    last = "v0"
    if route != "original":
        subtitles(a["segments"], folder / "vi.srt")
        ass = folder / "vi.ass"
        ass_subtitles(a["segments"], ass, geo["w"], geo["h"], zone=caption_zone(geo))
        chain.append("[%s]ass=%s[v1]" % (last, ass))
        last = "v1"  # folder is a generated UUID path, never user-controlled filter text
    if fps_of(vs) > 30.5:
        chain.append("[%s]fps=30[v2]" % last)
        last = "v2"
    chain.append("[%s]null[v]" % last)
    inputs = ["-i", str(path)]
    if voice:
        inputs += ["-i", str(voice["wav"])]
        delay = int(voice["delay"] * 1000)
        chain.append("[1:a]atempo=%.3f,adelay=%d|%d[vo]" % (voice["tempo"], delay, delay))
        if has_audio:
            chain.append("[0:a]volume=0.18[bg_a];[bg_a][vo]amix=inputs=2:duration=first:normalize=0[mix]")
            src = "mix"
        else:
            src = "vo"
        chain.append("[%s]loudnorm=I=-14:TP=-1.0:LRA=13,aresample=44100[a]" % src)
        amap = ["-map", "[a]"]
    elif has_audio:
        chain.append("[0:a]loudnorm=I=-14:TP=-1.0:LRA=13,aresample=44100[a]")
        amap = ["-map", "[a]"]
    else:
        amap = []
    ffmpeg(
        *inputs, "-filter_complex", ";".join(chain), "-map", "[v]", *amap, "-t", "%.3f" % duration,
        *VIDEO_ENCODER, *AUDIO_ENCODER, "-map_metadata", "-1", "-movflags", "+faststart", str(out),
        timeout=900,
    )  # fmt: skip
    final_duration, final_meta = probe(out)
    if abs(final_duration - duration) > 1:
        raise ValueError("Rendered duration mismatch")
    ffmpeg("-i", str(out), "-f", "null", "-")
    return out


def qc(out, source_has_audio):
    """Quality report of the rendered file: facts for the dashboard plus blocking problems. Returns (info, problems)."""
    duration, meta = probe(out)
    v = next(s for s in meta["streams"] if s["codec_type"] == "video")
    audio = [s for s in meta["streams"] if s["codec_type"] == "audio"]
    info = {
        "w": v["width"],
        "h": v["height"],
        "duration": round(duration, 1),
        "size": int(meta["format"].get("size", 0)),
        "codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
        "audio": bool(audio),
        "portrait": v["height"] > v["width"],
        "fps": round(fps_of(v)),
    }
    problems = []
    if v.get("codec_name") != "h264" or v.get("pix_fmt") != "yuv420p":
        problems.append("Định dạng video không phải H.264 yuv420p")
    if v["width"] % 2 or v["height"] % 2:
        problems.append("Kích thước hình lẻ")
    if source_has_audio and not audio:
        problems.append("Video gốc có tiếng nhưng bản dựng mất tiếng")
    if info["size"] < 20_000:
        problems.append("File dựng nhỏ bất thường")
    if min(v["width"], v["height"]) < 480:
        info["warning"] = "Độ phân giải thấp (%dx%d)" % (v["width"], v["height"])
    return info, problems


def make_poster(video, out, duration):
    """Small still for the dashboard so phones do not download the whole video just to show a card."""
    ffmpeg(
        "-ss", "%.2f" % min(1.5, max(0.0, duration / 3)), "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(out)
    )
