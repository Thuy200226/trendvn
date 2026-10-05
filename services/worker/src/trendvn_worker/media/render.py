"""One-pass render to a TikTok-ready MP4, its quality check and the dashboard poster."""

from ..domain.hardsubs import covered_spans, hard_subtitle_band
from .ffmpeg import decode_check, ffmpeg, probe
from .geometry import caption_zone, display_size, fps_of, layout
from .subtitles import ass_subtitles, caption_extent, subtitles

# H.264 high profile, 8-bit 4:2:0 (what every phone decodes), capped bitrate; AAC stereo.
# veryfast/crf 24 measured against a crf 12 reference on real clips: SSIM 0.992 (invisible loss), 40% smaller and 40% faster than fast/crf 23.
VIDEO_ENCODER = "-c:v libx264 -preset veryfast -crf 24 -profile:v high -pix_fmt yuv420p -maxrate 4M -bufsize 8M".split()
AUDIO_ENCODER = "-c:a aac -b:a 160k -ac 2".split()
LOUDNESS = "loudnorm=I=-14:TP=-1.0:LRA=13,aresample=44100"  # TikTok's sweet spot; dynamic mode keeps music natural at this range
UNLEVELLED = (
    "aresample=44100"  # for videos without sound worth levelling: loudnorm would boost hiss to -14 LUFS, and turns digital silence into NaN
)
QUIET_LUFS = -35  # a render quieter than this is flagged on the dashboard
BLUR_MAX_RADIUS = 20
COVER_SLACK = 0.015  # the strip counts as overlapped when our caption comes this close (fraction of the height), not only when it touches
# a voice-over mix has a different loudness shape over time (low under the voice, full outside it): the final levelling alone left peaks
# above 0 dBTP after AAC on loud music beds (measured by the independent review), so a limiter at -1.5 dBFS follows it
LIMITER = ",alimiter=limit=0.84:attack=3:release=40:level=disabled"
VOICE_LUFS = -16  # the voice-over is levelled on its own first, then the whole mix to -14: the voice always stands clear of the bed
BED_UNDER_VOICE = 0.14  # the original sound's gain while the voice speaks (about -17 dB); outside that window it is untouched
COPY_MAX_BITRATE = 6_000_000  # a source above this is re-encoded to the 4 Mb/s cap instead of being kept bit for bit


def render(path, folder, a, route, duration, voice=None, mask="auto"):
    """One ffmpeg pass: reframe to 9:16, blur out the source's own burned-in subtitles and burn Vietnamese ones when the route needs
    them, mix the voice-over, level the sound, drop the source's metadata, and write a web-friendly MP4 (H.264 high, yuv420p, AAC,
    faststart). Returns the path of the finished file."""
    out = folder / "final.mp4"
    _, meta = probe(path)
    vs = next(s for s in meta["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in meta["streams"])
    geo = layout(*display_size(vs))
    if can_copy_video(vs, geo, route):
        chain, picture = [], ["-map", "0:v:0", "-c:v", "copy"]  # the picture is already what we would make: keep it bit for bit
    else:
        chain, last = _picture_chain(geo, fps_of(vs), a, route, folder, duration, mask)
        picture = ["-map", "[%s]" % last, *VIDEO_ENCODER]
    inputs = ["-i", str(path)]
    if voice:
        inputs += ["-i", str(voice["wav"])]
    for levelled in (True, False) if a.get("kind") != "silent" else (False,):
        audio, amap = _audio_chain(has_audio, voice, levelled)
        graph = ["-filter_complex", ";".join(chain + audio)] if chain or audio else []
        try:
            ffmpeg(
                *inputs, *graph, *picture, *amap, "-t", "%.3f" % duration,
                *AUDIO_ENCODER, "-map_metadata", "-1", "-movflags", "+faststart", str(out),
                timeout=900,
            )  # fmt: skip
            break
        except ValueError as error:
            if not levelled or "NaN" not in str(error):
                raise  # only "loudnorm met digital silence" is retried, once, without levelling
    final_duration, _ = probe(out)
    if abs(final_duration - duration) > 1:
        raise ValueError("Rendered duration mismatch")
    return out


def can_copy_video(stream, geo, route):
    """True when a video that stays as it is (music, no speech) already has the picture we would produce: portrait H.264 8-bit 4:2:0 that
    needs no scaling, rotation or frame-rate change, at an ordinary bitrate. Then only the sound is levelled and the picture is copied:
    no quality lost, a few seconds of work instead of a minute."""
    if route != "original" or geo["reframe"]:
        return False
    if stream.get("codec_name") != "h264" or stream.get("pix_fmt") != "yuv420p":
        return False
    if (stream["width"], stream["height"]) != (geo["w"], geo["h"]) or _has_rotation(stream):
        return False
    try:
        bit_rate = int(stream.get("bit_rate") or 0)
    except (TypeError, ValueError):
        return False
    return fps_of(stream) <= 30.5 and 0 < bit_rate <= COPY_MAX_BITRATE


def _has_rotation(stream):
    """Any rotation, flip or display matrix on the stream (even 0 or 180 degrees): such a picture is re-encoded, which bakes it in."""
    try:
        if float((stream.get("tags") or {}).get("rotate", 0)) % 360:
            return True
    except (TypeError, ValueError):
        return True
    return any(
        isinstance(data, dict) and ("rotation" in data or "display" in str(data.get("side_data_type", "")).lower())
        for data in stream.get("side_data_list") or []
    )


def covered_hard_subtitles(a, route, geo=None, mask="always"):
    """The band of the source picture that render() blurs out (its burned-in subtitles), or None. Only videos that get our own captions
    are touched: a music video that stays as it is keeps its lyrics. `mask` is the owner's choice: "off" never, "always" whenever the
    band is known, "auto" only when our captions would sit on top of it (a wide video's captions go below the picture, nothing to hide)."""
    band = hard_subtitle_band(a) if route != "original" else None
    if not band or mask == "off":
        return None
    if mask == "auto" and geo is not None and not _overlaps_caption(geo, band):
        return None
    return band


def _band_pixels(geo, band):
    """(y, height) in output pixels of the strip `band` (fractions of the picture) occupies."""
    top, bottom = band
    if geo["reframe"]:  # the picture is the middle of the canvas, the rest is blurred backdrop
        picture_top, picture_height = (geo["h"] - geo["fg_h"]) // 2, geo["fg_h"]
    else:
        picture_top, picture_height = 0, geo["h"]
    height = min(max(8, int((bottom - top) * picture_height) // 2 * 2), geo["h"])
    y = min(picture_top + int(top * picture_height) // 2 * 2, geo["h"] - height)  # a band at the very edge still gets its full height
    return y, height


def _overlaps_caption(geo, band):
    """Would a caption drawn in our caption zone cover part of the source's own subtitle strip?"""
    y, height = _band_pixels(geo, band)
    caption_top, caption_bottom = caption_extent(geo["w"], geo["h"], caption_zone(geo))
    slack = COVER_SLACK * geo["h"]
    return caption_top - slack < y + height and y < caption_bottom + slack


def _picture_chain(geo, fps, a, route, folder, duration, mask="auto"):
    """The video part of the filter graph. Returns (filters, label of the final video stream)."""
    if geo["reframe"]:
        chain = [
            "[0:v]split=2[bgs][fgs];[bgs]scale=108:192:force_original_aspect_ratio=increase,crop=108:192,boxblur=8:2,eq=brightness=-0.08,"
            "scale=%d:%d:flags=bilinear[bg];[fgs]scale=%d:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]" % (geo["w"], geo["h"], geo["w"])
        ]  # blur a tiny copy, then enlarge: same look, ~4x faster
    else:
        chain = ["[0:v]scale=%d:%d[v0]" % (geo["w"], geo["h"])]
    last = "v0"
    band = covered_hard_subtitles(a, route, geo, mask)
    spans = covered_spans(a.get("segments") or [], duration) if band else []
    if band and spans:
        chain.append(_blur_band(geo, band, last, "v1", spans))
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


def _blur_band(geo, band, source, label, spans):
    """Blur the strip of the picture where the source carries its own subtitles, so they do not show through ours; only during `spans`
    (the seconds our own lines are on screen), the rest of the time the picture is left alone."""
    y, height = _band_pixels(geo, band)
    radius = max(1, min(BLUR_MAX_RADIUS, height // 4 - 1))  # the chroma planes are half as tall and cap the radius
    when = "+".join("between(t,%.2f,%.2f)" % span for span in spans)  # quoted below: the commas belong to the expression
    return "[%s]split=2[hsa][hsb];[hsb]crop=%d:%d:0:%d,boxblur=%d:3,eq=brightness=-0.12[hsc];[hsa][hsc]overlay=0:%d:enable='%s'[%s]" % (
        source,
        geo["w"],
        height,
        y,
        radius,
        y,
        when,
        label,
    )


def _audio_chain(has_audio, voice, levelled=True):
    """The audio part of the filter graph. Returns (filters, -map arguments).
    With a voice-over: the voice is sped up only as much as ai/tts.py decided, levelled on its own (-16 LUFS) and delayed to where the
    speech began; the original sound is turned down to BED_UNDER_VOICE only while the voice speaks, eased in and out (0.3 s, 0.5 s), and
    left alone before and after (an intro, a pause, music at the end); the mix is then levelled to -14 like everything else."""
    level = LOUDNESS if levelled else UNLEVELLED
    if voice:
        start = float(voice["delay"])
        delay = int(start * 1000)
        end = float(
            voice.get("until", start + float(voice.get("seconds", 10**6)))
        )  # to the end of the speech window; unknown: the whole video
        own = "loudnorm=I=%d:TP=-1.5:LRA=7," % VOICE_LUFS if levelled else ""
        chain = ["[1:a]atempo=%.3f,%saresample=44100,adelay=%d|%d[vo]" % (voice["tempo"], own, delay, delay)]
        if has_audio:
            gain = "1-%.2f*clip((t-%.2f)/0.3,0,1)*clip((%.2f-t)/0.5,0,1)" % (1 - BED_UNDER_VOICE, max(0.0, start - 0.3), end + 0.5)
            chain.append("[0:a]volume='%s':eval=frame[bg_a];[bg_a][vo]amix=inputs=2:duration=first:normalize=0[mix]" % gain)
            source = "mix"
        else:
            source = "vo"
        chain.append("[%s]%s%s[a]" % (source, level, LIMITER if levelled else ""))
        return chain, ["-map", "[a]"]
    if has_audio:
        return ["[0:a]%s[a]" % level], ["-map", "[a]"]
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
