"""One-pass render to a TikTok-ready MP4, its quality check and the dashboard poster."""

from ..domain.hardsubs import hard_subtitle_band
from .ffmpeg import decode_check, ffmpeg, probe
from .geometry import caption_zone, display_size, fps_of, layout
from .subtitles import ass_subtitles, subtitles

# H.264 high profile, 8-bit 4:2:0 (what every phone decodes), capped bitrate; AAC stereo.
# veryfast/crf 24 measured against a crf 12 reference on real clips: SSIM 0.992 (invisible loss), 40% smaller and 40% faster than fast/crf 23.
VIDEO_ENCODER = "-c:v libx264 -preset veryfast -crf 24 -profile:v high -pix_fmt yuv420p -maxrate 4M -bufsize 8M".split()
AUDIO_ENCODER = "-c:a aac -b:a 160k -ac 2".split()
LOUDNESS = "loudnorm=I=-14:TP=-1.0:LRA=13,aresample=44100"  # TikTok's sweet spot; dynamic mode keeps music natural at this range
QUIET_LUFS = -35  # a render quieter than this is flagged on the dashboard
BLUR_MAX_RADIUS = 20


def render(path, folder, a, route, duration, voice=None):
    """One ffmpeg pass: reframe to 9:16, blur out the source's own burned-in subtitles and burn Vietnamese ones when the route needs
    them, mix the voice-over, level the sound, drop the source's metadata, and write a web-friendly MP4 (H.264 high, yuv420p, AAC,
    faststart). Returns the path of the finished file."""
    out = folder / "final.mp4"
    _, meta = probe(path)
    vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in meta["streams"])
    geo = layout(*display_size(vs))
    chain, last = _picture_chain(geo, fps_of(vs), a, route, folder)
    inputs = ["-i", str(path)]
    if voice:
        inputs += ["-i", str(voice["wav"])]
    audio, amap = _audio_chain(has_audio, voice)
    ffmpeg(
        *inputs, "-filter_complex", ";".join(chain + audio), "-map", "[%s]" % last, *amap, "-t", "%.3f" % duration,
        *VIDEO_ENCODER, *AUDIO_ENCODER, "-map_metadata", "-1", "-movflags", "+faststart", str(out),
        timeout=900,
    )  # fmt: skip
    final_duration, _ = probe(out)
    if abs(final_duration - duration) > 1:
        raise ValueError("Rendered duration mismatch")
    return out


def covered_hard_subtitles(a, route):
    """The band of the source picture that render() blurs out (its burned-in subtitles), or None. Only videos that get our own captions
    are touched: a music video that stays as it is keeps its lyrics."""
    return hard_subtitle_band(a) if route != "original" else None


def _picture_chain(geo, fps, a, route, folder):
    """The video part of the filter graph. Returns (filters, label of the final video stream)."""
    if geo["reframe"]:
        chain = [
            "[0:v]split=2[bgs][fgs];[bgs]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=8:2,eq=brightness=-0.08,"
            "scale=%d:%d:flags=bilinear[bg];[fgs]scale=%d:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]" % (geo["w"], geo["h"], geo["w"])
        ]  # blur a tiny copy, then enlarge: same look, ~4x faster
    else:
        chain = ["[0:v]scale=%d:%d[v0]" % (geo["w"], geo["h"])]
    last = "v0"
    band = covered_hard_subtitles(a, route)
    if band:
        chain.append(_blur_band(geo, band, last, "v1"))
        last = "v1"
    if route != "original":
        subtitles(a["segments"], folder / "vi.srt")
        ass = folder / "vi.ass"
        ass_subtitles(a["segments"], ass, geo["w"], geo["h"], zone=caption_zone(geo))
        label = "v%d" % (int(last[1:]) + 1)
        chain.append("[%s]ass=%s[%s]" % (last, ass, label))  # folder is a generated UUID path, never user-controlled filter text
        last = label
    if fps > 30.5:
        label = "v%d" % (int(last[1:]) + 1)
        chain.append("[%s]fps=30[%s]" % (last, label))
        last = label
    return chain, last


def _blur_band(geo, band, source, label):
    """Blur the strip of the picture where the source carries its own subtitles, so they do not show through ours."""
    top, bottom = band
    if geo["reframe"]:  # the picture is the middle of the canvas, the rest is blurred backdrop
        picture_top, picture_height = (geo["h"] - geo["fg_h"]) // 2, geo["fg_h"]
    else:
        picture_top, picture_height = 0, geo["h"]
    y = picture_top + int(top * picture_height) // 2 * 2
    height = min(max(8, int((bottom - top) * picture_height) // 2 * 2), geo["h"] - y)
    radius = max(1, min(BLUR_MAX_RADIUS, height // 4 - 1))  # the chroma planes are half as tall and cap the radius
    return "[%s]split=2[hsa][hsb];[hsb]crop=%d:%d:0:%d,boxblur=%d:3,eq=brightness=-0.12[hsc];[hsa][hsc]overlay=0:%d[%s]" % (
        source,
        geo["w"],
        height,
        y,
        radius,
        y,
        label,
    )


def _audio_chain(has_audio, voice):
    """The audio part of the filter graph. Returns (filters, -map arguments)."""
    if voice:
        delay = int(voice["delay"] * 1000)
        chain = ["[1:a]atempo=%.3f,adelay=%d|%d[vo]" % (voice["tempo"], delay, delay)]
        if has_audio:
            chain.append("[0:a]volume=0.18[bg_a];[bg_a][vo]amix=inputs=2:duration=first:normalize=0[mix]")
            source = "mix"
        else:
            source = "vo"
        chain.append("[%s]%s[a]" % (source, LOUDNESS))
        return chain, ["-map", "[a]"]
    if has_audio:
        return ["[0:a]%s[a]" % LOUDNESS], ["-map", "[a]"]
    return [], []


def qc(out, source_has_audio):
    """Quality report of the rendered file: facts for the dashboard plus blocking problems. Returns (info, problems).
    Also decodes the whole file, so a damaged render raises here instead of reaching TikTok."""
    duration, meta = probe(out)
    v = next(s for s in meta["streams"] if s["codec_type"] == "video")
    audio = [s for s in meta["streams"] if s["codec_type"] == "audio"]
    loudness = decode_check(out, bool(audio))
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
    if loudness:
        info["lufs"] = round(loudness["lufs"], 1)
        info["peak"] = loudness["peak"]
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
    elif loudness and loudness["lufs"] < QUIET_LUFS:
        info["warning"] = "Âm thanh rất nhỏ hoặc im lặng (%.0f LUFS)" % loudness["lufs"]  # a silent source is legitimate, so only a warning
    return info, problems


def make_poster(video, out, duration):
    """Small still for the dashboard so phones do not download the whole video just to show a card."""
    ffmpeg(
        "-ss", "%.2f" % min(1.5, max(0.0, duration / 3)), "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(out)
    )
