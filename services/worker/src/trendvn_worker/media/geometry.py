"""Output geometry: 9:16 canvas, blurred-background reframing, where captions may sit."""

CANVAS = (1080, 1920)


def display_size(stream):
    """Size the viewer sees: phones often store portrait video as landscape pixels plus a 90-degree rotation flag."""
    w, h = stream["width"], stream["height"]
    rot = 0
    try:
        rot = int(float((stream.get("tags") or {}).get("rotate", 0)))
    except (TypeError, ValueError):
        pass
    for sd in stream.get("side_data_list") or []:
        if isinstance(sd, dict) and "rotation" in sd:
            try:
                rot = int(float(sd["rotation"]))
            except (TypeError, ValueError):
                pass
    return (h, w) if abs(rot) % 180 == 90 else (w, h)


def layout(width, height):
    """Output geometry. Portrait videos keep their pixels (capped at 1080x1920); wide or square ones go on a 1080x1920 canvas over a
    blurred copy of themselves, which is how they fill a phone screen instead of shrinking into a thin strip."""
    if width / height <= 0.7:
        k = min(1.0, CANVAS[0] / width, CANVAS[1] / height)
        return {"reframe": False, "w": max(2, int(width * k) // 2 * 2), "h": max(2, int(height * k) // 2 * 2)}
    fg_h = round(CANVAS[0] * height / width / 2) * 2
    return {"reframe": True, "w": CANVAS[0], "h": CANVAS[1], "fg_h": fg_h, "band_top": (CANVAS[1] + fg_h) // 2}


def caption_zone(geo):
    """Where Vietnamese captions go. TikTok draws the account name, caption and hashtags over roughly the lowest quarter of the screen
    (y above about 1450 of 1920 stays clear) and its tabs over the top ~130px, so captions sit in the free blurred band when there is
    one, otherwise above the lower overlay."""
    H = geo["h"]
    if not geo["reframe"]:
        return {"align": 2, "margin": round(H * 0.27), "box": True}
    top_h = (H - geo["fg_h"]) // 2
    if geo["band_top"] <= 1340:
        return {"align": 8, "margin": geo["band_top"] + round(H * 0.025), "box": False}  # wide video: band below the picture
    if top_h >= 260:
        return {"align": 8, "margin": max(140, top_h // 2 - 60), "box": False}  # square or 4:5: band above the picture
    return {"align": 8, "margin": top_h + 30, "box": True}  # 3:4: top of the picture


def fps_of(stream):
    try:
        n, d = stream.get("avg_frame_rate", "0/1").split("/")
        return float(n) / float(d) if float(d) else 0
    except Exception:
        return 0
