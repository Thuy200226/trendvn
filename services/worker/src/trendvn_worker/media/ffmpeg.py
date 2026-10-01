"""Thin wrappers over ffmpeg and ffprobe."""

import json
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
