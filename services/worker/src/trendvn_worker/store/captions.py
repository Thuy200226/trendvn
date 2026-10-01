"""The caption the owner will post: edit, reset, and the list of videos ready to post."""

import json
import re
import time
import unicodedata

from ..domain.captions import build_caption, lint_caption


class CaptionMixin:
    """Caption editing and the ready-to-post list."""

    def set_caption(self, jid, caption):
        """Owner's edit of the caption/hashtags that will be posted. Validated, never silently altered."""
        caption = unicodedata.normalize("NFC", str(caption)).replace("\r\n", "\n").replace("\r", "\n")
        caption = "\n".join(line.rstrip() for line in re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", caption).split("\n")).strip()
        if not caption:
            raise ValueError("Mô tả không được để trống")
        if len(caption) > 2200:
            raise ValueError("Mô tả quá dài (tối đa 2200 ký tự)")
        with self.transaction() as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] not in ("ready", "awaiting_approval"):
                raise ValueError("Chỉ sửa được mô tả của video sẵn sàng đăng")
            cur = db.execute("SELECT caption_user,analysis,title FROM jobs WHERE id=?", (jid,)).fetchone()
            effective = cur["caption_user"] or build_caption(json.loads(cur["analysis"] or "{}"), cur["title"])
            if caption == effective:
                return  # nothing changed: no event, no churn
            db.execute("UPDATE jobs SET caption_user=?,updated=? WHERE id=?", (caption, time.time(), jid))
            self.event(db, jid, "caption_edited", caption[:200])

    def reset_caption(self, jid):
        with self.transaction() as db:
            db.execute(
                "UPDATE jobs SET caption_user=NULL,updated=? WHERE id=? AND state IN ('ready','awaiting_approval')", (time.time(), jid)
            )

    def ready_list(self, limit=30):
        """Everything that has been rendered and can be posted, best first, with the caption that would be used and its quality check."""
        with self.connect() as db:
            rows = db.execute(
                """SELECT id,platform,title,state,route,meta,analysis,caption_user,output_info,duration,updated,first_seen
                FROM jobs WHERE state IN ('ready','awaiting_approval') AND output_file IS NOT NULL
                ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                a = json.loads(d.pop("analysis") or "{}")
            except ValueError:
                a = {}
            try:
                d["caption"] = d["caption_user"] or build_caption(a, d["title"])
            except Exception:
                d["caption"] = d["caption_user"] or (d["title"] or "")[:110]
            d["caption_edited"] = bool(d["caption_user"])
            d["lint"] = lint_caption(d["caption"])
            d["kind"] = a.get("kind")
            d["info"] = json.loads(d["output_info"] or "{}")
            out.append(d)
        return out
