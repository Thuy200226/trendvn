"""The caption the owner will post: edit, reset, and the list of videos ready to post."""

import re
import time
import unicodedata

from ..domain.captions import build_caption, lint_caption
from ..jsonsafe import loads


class CaptionMixin:
    """Caption editing and the ready-to-post list."""

    def set_caption(self, jid, caption):
        """Owner's edit of the caption/hashtags that will be posted. Validated, never silently altered."""
        caption = unicodedata.normalize("NFC", str(caption)).replace("\r\n", "\n").replace("\r", "\n")
        caption = "\n".join(line.rstrip() for line in re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", caption).split("\n")).strip()
        if not caption:
            raise ValueError("M\u00f4 t\u1ea3 kh\u00f4ng \u0111\u01b0\u1ee3c \u0111\u1ec3 tr\u1ed1ng")
        if len(caption) > 2200:
            raise ValueError("M\u00f4 t\u1ea3 qu\u00e1 d\u00e0i (t\u1ed1i \u0111a 2200 k\u00fd t\u1ef1)")
        with self.transaction() as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] not in ("ready", "awaiting_approval"):
                raise ValueError("Ch\u1ec9 s\u1eeda \u0111\u01b0\u1ee3c m\u00f4 t\u1ea3 c\u1ee7a video s\u1eb5n s\u00e0ng \u0111\u0103ng")
            cur = db.execute("SELECT caption_user,analysis,title FROM jobs WHERE id=?", (jid,)).fetchone()
            effective = cur["caption_user"] or build_caption(loads(cur["analysis"], {}), cur["title"])
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
                """SELECT id,platform,title,state,route,topic,meta,analysis,caption_user,output_info,duration,updated,first_seen,last_publish_fail
                FROM jobs WHERE state IN ('ready','awaiting_approval') AND output_file IS NOT NULL
                ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            a = loads(d.pop("analysis"), {})  # damaged, or JSON of the wrong kind: no analysis
            try:
                d["caption"] = d["caption_user"] or build_caption(a, d["title"])
            except Exception:
                d["caption"] = d["caption_user"] or (d["title"] or "")[:110]
            d["caption_edited"] = bool(d["caption_user"])
            d["lint"] = lint_caption(d["caption"])
            d["kind"] = a.get("kind")
            d["info"] = loads(d["output_info"], {})
            out.append(d)
        return out
