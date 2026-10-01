"""Perceptual fingerprint of a video, to spot look-alikes that have different bytes."""

from .ffmpeg import ffmpeg

SAMPLE_POINTS = (0.15, 0.35, 0.55, 0.75, 0.90)  # where in the video the frames are taken
GRID = (9, 8)  # a 9x8 grayscale thumbnail: 8 rows x 8 left/right comparisons = 64 bits
MAX_BIT_DIFFERENCE = 6  # frames whose hashes differ by at most this many bits count as the same picture
MIN_MATCHING_FRAMES = 4


def frame_hash(path, at_seconds):
    """64-bit difference hash of one frame, as 16 hex digits."""
    width, height = GRID
    frame = ffmpeg(
        "-ss", str(at_seconds), "-i", str(path), "-frames:v", "1", "-vf", "scale=%d:%d,format=gray" % GRID, "-f", "rawvideo", "-"
    )
    if len(frame) != width * height:
        raise ValueError("Cannot fingerprint frame")
    bits = [frame[y * width + x] > frame[y * width + x + 1] for y in range(height) for x in range(width - 1)]
    return format(sum(int(bit) << position for position, bit in enumerate(bits)), "016x")


def fingerprint(path, duration):
    """Five frame hashes spread across the video."""
    return [frame_hash(path, duration * point) for point in SAMPLE_POINTS]


def similar(a, b):
    """True when most sampled frames look alike (the same video re-encoded, trimmed a little, or re-uploaded)."""
    if not len(a) == len(b) == len(SAMPLE_POINTS):
        return False
    close = sum((int(x, 16) ^ int(y, 16)).bit_count() <= MAX_BIT_DIFFERENCE for x, y in zip(a, b))
    return close >= MIN_MATCHING_FRAMES
