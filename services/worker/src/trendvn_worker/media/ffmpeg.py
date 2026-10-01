"""Thin wrappers over ffmpeg and ffprobe."""

import json
import re
import subprocess

DEFAULT_TIMEOUT = 300


def run(args, timeout=DEFAULT_TIMEOUT):
    """Run a command and return its stdout; a non-zero exit raises ValueError carrying the tail of stderr."""
    process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if process.returncode:
        raise ValueError("Media operation failed: " + process.stderr.decode(errors="replace")[-700:])
    return process.stdout


def ffmpeg(*args, timeout=DEFAULT_TIMEOUT):
    """`ffmpeg -v error -y <args>`: quiet, overwrite the output. Returns stdout (raw frames when the output is `-`)."""
    return run(["ffmpeg", "-v", "error", "-y", *args], timeout=timeout)


def probe(path):
    """(duration in seconds, ffprobe's full JSON). Raises ValueError when the file has no video stream."""
    result = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))
    duration = float(result["format"]["duration"])
    if not any(stream["codec_type"] == "video" for stream in result["streams"]):
        raise ValueError("No video stream")
    return duration, result


def decode_check(path, with_audio):
    """Decode every frame and sample of a finished file (a damaged one fails here) and measure its loudness on the way
    (ebur128 rides on the same pass, so it costs almost nothing). Returns {"lufs": integrated loudness, "peak": true peak in dBFS},
    or {} when the file has no audio."""
    args = ["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(path)]
    process = subprocess.run(
        args + (["-af", "ebur128=peak=true"] if with_audio else []) + ["-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=DEFAULT_TIMEOUT,
    )
    report = process.stderr.decode(errors="replace")
    if process.returncode:
        raise ValueError("Media operation failed: " + report[-700:])
    summary = report[report.rfind("Summary:") :] if "Summary:" in report else ""
    lufs = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary)
    if not (with_audio and lufs):
        return {}
    return {"lufs": -120.0 if lufs.group(1) == "-inf" else float(lufs.group(1)), "peak": float(peak.group(1)) if peak else None}
