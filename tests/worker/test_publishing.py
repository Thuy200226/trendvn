"""Publishing: claim rules (switch, window, limit, gap), manual posting, failures, approval, TikTok verification."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_agent.publisher.challenge import has_challenge
from trendvn_worker import ui
from trendvn_worker.domain.analysis import validate_analysis
from trendvn_worker.store import Store

ROOT = Path(__file__).resolve().parents[2]


class PublishQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ready(self, jid, first_seen=1):
        with self.s.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,state,output_file,output_hash,analysis,route,updated) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    "douyin",
                    jid,
                    "https://www.douyin.com/video/" + jid,
                    "CN",
                    "Tiêu đề",
                    first_seen,
                    "ready",
                    "/data/jobs/%s/final.mp4" % jid,
                    "h",
                    json.dumps({"kind": "music", "caption_vi": "Bài hát hay"}),
                    "original",
                    1,
                ),
            )

    def enable(self, **extra):
        with self.s.transaction() as db:
            db.execute("UPDATE settings SET value='true' WHERE key='publisher_enabled'")
            db.execute("UPDATE settings SET value='[]' WHERE key='post_windows'")  # tests run at any hour
            for k, v in extra.items():
                db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(v), k))

    def test_switch_off_by_default(self):
        self.ready("a")
        self.assertEqual(self.s.publish_claim()["status"], "disabled")

    def test_claim_publish_and_daily_limit(self):
        for j in "abc":
            self.ready(j)
        self.enable(min_publish_gap=0)
        first = self.s.publish_claim()
        self.assertEqual(first["status"], "claimed")
        self.assertEqual(self.s.publish_claim()["status"], "blocked")  # one in flight at a time
        self.s.publish_finish(first["id"], first["lease"], "published", "https://www.tiktok.com/@u/video/1")
        second = self.s.publish_claim()
        self.s.publish_finish(second["id"], second["lease"], "published", "https://www.tiktok.com/@u/video/2")
        self.assertEqual(self.s.publish_claim()["status"], "limit")  # daily_limit is 2

    def test_gap_between_posts(self):
        self.ready("a")
        self.ready("b")
        self.enable()
        first = self.s.publish_claim()
        self.s.publish_finish(first["id"], first["lease"], "published", "https://www.tiktok.com/@u/video/1")
        r = self.s.publish_claim()
        self.assertEqual(r["status"], "wait")
        self.assertGreater(r["retry_after"], 3600)

    def test_unknown_outcome_blocks_and_never_requeues(self):
        self.ready("a")
        self.ready("b")
        self.enable(min_publish_gap=0)
        c1 = self.s.publish_claim()
        self.s.publish_finish(c1["id"], c1["lease"], "unknown", reason="clicked, unconfirmed")
        self.assertEqual(self.s.publish_claim()["status"], "blocked")
        self.assertEqual(len(self.s.unresolved()), 1)
        self.s.resolve_unknown(c1["id"], "published", "https://www.tiktok.com/@u/video/9")
        self.assertEqual(self.s.publish_claim()["status"], "claimed")

    def test_failed_before_post_returns_to_ready(self):
        self.ready("a")
        self.enable(min_publish_gap=0)
        c1 = self.s.publish_claim()
        self.s.publish_finish(c1["id"], c1["lease"], "failed", reason="not logged in")
        self.assertEqual(self.s.publish_claim()["status"], "idle")  # cooling off for an hour, so one bad video cannot hammer TikTok
        self.assertEqual(self.s.publish_claim(now=time.time() + 4000)["status"], "claimed")  # and is tried again afterwards

    def test_stale_lease_and_bad_url_rejected(self):
        self.ready("a")
        self.enable()
        c1 = self.s.publish_claim()
        with self.assertRaises(ValueError):
            self.s.publish_finish(c1["id"], "wrong", "published")
        with self.assertRaises(ValueError):
            self.s.publish_finish(c1["id"], c1["lease"], "published", "https://evil.example/x")

    def test_duplicate_outcome(self):
        self.ready("a")
        self.enable()
        c1 = self.s.publish_claim()
        self.s.publish_finish(c1["id"], c1["lease"], "duplicate", reason="same caption")
        self.assertEqual(self.s.publish_claim()["status"], "idle")

    def test_release_requeues_without_burning_an_attempt(self):
        now = time.time()
        b = lambda ts: {
            "platform": "douyin",
            "stream": "s",
            "observed_at": ts,
            "items": (
                [
                    {
                        "source_id": "555",
                        "url": "https://www.douyin.com/video/555",
                        "country": "CN",
                        "title": "t",
                        "evidence_url": "https://www.douyin.com/",
                    }
                ]
                if ts > now
                else []
            ),
        }
        self.s.ingest(b(now), now=now)
        jid = self.s.ingest(b(now + 1), now=now + 1)["candidates"][0]["id"]
        (Path(self.tmp.name) / "inbox" / "r.mp4").write_bytes(b"fixture")
        self.s.attach(jid, "r.mp4")
        job = self.s.claim()
        self.s.release(jid, job["lease"], "rate limited")
        again = self.s.claim()
        self.assertEqual(again["id"], jid)
        self.assertEqual(again["attempts"], 0)  # value before this claim's increment
        with self.assertRaises(ValueError):
            self.s.release(jid, "stale-lease", "x")

    def test_peek_does_not_change_state(self):
        self.ready("a")
        self.assertEqual(self.s.publish_peek()["status"], "ready")
        self.assertEqual(self.s.publish_peek()["status"], "ready")

    def test_heartbeat_states(self):
        self.assertEqual(self.s.status()["discovery"], "not_connected")
        self.s.heartbeat("discovery", True, {"douyin": "ok"})
        self.assertEqual(self.s.status()["discovery"], "connected")
        self.s.heartbeat("publisher", False, "Chưa đăng nhập")
        self.assertEqual(self.s.status()["publisher"], "error")
        with self.assertRaises(ValueError):
            self.s.heartbeat("other", True)

    def test_ingest_reports_candidates(self):
        now = time.time()
        batch = lambda ids, ts: {
            "platform": "douyin",
            "stream": "s",
            "observed_at": ts,
            "items": [
                {
                    "source_id": i,
                    "url": "https://www.douyin.com/video/" + i,
                    "country": "CN",
                    "title": "t",
                    "rank": 1,
                    "evidence_url": "https://www.douyin.com/",
                }
                for i in ids
            ],
        }
        self.s.ingest(batch(["111"], now), now=now)
        r = self.s.ingest(batch(["111", "222"], now + 1), now=now + 1)
        self.assertEqual([x["source_id"] for x in r["candidates"]], ["222"])
        self.assertEqual(self.s.candidates_without_media()[0]["source_id"], "222")


class WindowTests(StoreCase):
    def test_window_state(self):
        self.assertEqual(self.s.window_state(now=at(12)), (True, ""))
        self.assertEqual(self.s.window_state(now=at(19, 30)), (True, ""))
        self.assertEqual(self.s.window_state(now=at(15)), (False, "19:00 hôm nay"))
        self.assertEqual(self.s.window_state(now=at(23, 30)), (False, "11:00 ngày mai"))
        self.assertEqual(self.s.window_state(now=at(3)), (False, "11:00 hôm nay"))

    def test_claim_respects_window(self):
        self.job("a", "ready", output_file="/data/a.mp4", output_hash="h")
        self.s.update_settings({"publisher_enabled": True, "min_publish_gap": 0})
        self.assertEqual(self.s.publish_claim(now=at(15))["status"], "wait")
        self.assertEqual(self.s.publish_claim(now=at(20))["status"], "claimed")

    def test_best_score_first(self):
        self.job("low", "ready", output_file="/d/l.mp4", output_hash="h", meta=json.dumps({"score": 10}), first_seen=1)
        self.job("high", "ready", output_file="/d/h.mp4", output_hash="h", meta=json.dumps({"score": 999}), first_seen=2)
        self.s.update_settings({"publisher_enabled": True})
        self.assertEqual(self.s.publish_claim(now=at(20))["id"], "high")


class ApprovalTests(StoreCase):
    def test_approve_and_reject(self):
        self.job("a", "awaiting_approval")
        self.job("b", "awaiting_approval")
        self.s.decide("a", "approve")
        self.s.decide("b", "reject")
        states = {j["id"]: j["state"] for j in self.s.status()["jobs"]}
        self.assertEqual(states, {"a": "ready", "b": "rejected"})

    def test_needs_review_requires_source_and_reprocesses_leniently(self):
        src = Path(self.tmp.name) / "inbox" / "s.mp4"
        src.write_bytes(b"x")
        self.job("a", "needs_review", source_file=str(src))
        self.job("gone", "needs_review", source_file="/nope.mp4")
        with self.assertRaises(ValueError):
            self.s.decide("gone", "approve")
        self.s.decide("a", "approve")
        row = [j for j in self.s.status()["jobs"] if j["id"] == "a"][0]
        self.assertEqual(row["state"], "queued")
        self.assertEqual(self.s.claim()["approved"], 1)

    def test_cannot_approve_published(self):
        self.job("p", "published")
        with self.assertRaises(ValueError):
            self.s.decide("p", "approve")
        with self.assertRaises(ValueError):
            self.s.decide("p", "reject")

    def test_lenient_waives_only_judgement_checks(self):
        a = {
            "kind": "dialogue",
            "confidence": 0.5,
            "topic": "other",
            "sensitive": True,
            "segments": [{"start": 0, "end": 2, "vi": "xin chào"}],
        }
        with self.assertRaises(ValueError):
            validate_analysis(a, 10, strict=True)
        self.assertEqual(validate_analysis(a, 10, strict=True, lenient=True), "vietsub")
        bad = dict(a, segments=[{"start": 5, "end": 6, "vi": ""}])
        with self.assertRaises(ValueError):
            validate_analysis(bad, 10, strict=True, lenient=True)  # structural checks (empty translation) still apply
        junk = dict(a, segments=[{"start": "x", "end": 6, "vi": "y"}])
        with self.assertRaises(ValueError):
            validate_analysis(junk, 10, strict=True, lenient=True)

    def test_finish_awaiting_approval_state(self):
        self.job("q", "queued", source_file="/x")
        job = self.s.claim()
        self.s.finish("q", job["lease"], "awaiting_approval", reason="ok")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["awaiting_approval"])


class ChallengeTests(StoreCase):
    def test_challenge_pauses_publishing_until_cleared(self):
        self.job("a", "ready", output_file="/d/a.mp4", output_hash="h")
        self.s.update_settings({"publisher_enabled": True, "post_windows": []})
        sent = []
        self.s.notifier = lambda kind, text, key: sent.append((kind, text))
        self.s.set_challenge(True)
        r = self.s.publish_claim()
        self.assertEqual(r["status"], "blocked")
        self.assertIn("trust", r["reason"])
        self.assertTrue(self.s.status()["publisher_challenge"])
        self.assertTrue(any(k == "urgent" and "CAPTCHA" in m for k, m in sent))
        self.s.set_challenge(False)
        self.assertEqual(self.s.publish_claim()["status"], "claimed")

    def test_dashboard_shows_the_challenge_and_counts_it(self):
        self.s.set_challenge(True)
        d = self.s.dashboard_data()
        d["notify_channels"] = []
        d["voice_sample"] = False
        html = ui.render(d, "T")
        self.assertIn("yêu cầu xác minh", html)
        self.assertIn("./trendvn tiktok trust", html)

    def test_publisher_recognises_challenge_text(self):
        class Page:
            def __init__(self, text, sel=0):
                self.text, self.sel = text, sel

            def locator(self, s):
                outer = self
                return type("L", (), {"count": lambda self: outer.sel})()

            def inner_text(self, *a, **k):
                return self.text

        self.assertTrue(has_challenge(Page("Chọn 2 đối tượng có hình dạng giống nhau")))
        self.assertTrue(has_challenge(Page("bất kỳ", sel=1)))
        self.assertFalse(has_challenge(Page("Tải video lên")))


class ManualPublishTests(StoreCase):
    def test_manual_click_waives_switch_window_limit_and_gap_but_not_safety_rails(self):
        self.ready("a")
        self.ready("b")
        # switch off, outside the window: the scheduled path refuses...
        self.assertEqual(self.s.publish_claim()["status"], "disabled")
        # ...but the owner's click on a specific video goes through
        r = self.s.publish_claim(job_id="b")
        self.assertEqual((r["status"], r["id"], r["manual"]), ("claimed", "b", True))
        self.assertEqual(self.s.publish_claim(job_id="a")["status"], "blocked")  # one post in flight at a time
        self.s.publish_finish("b", r["lease"], "published", "https://www.tiktok.com/@u/video/1")
        self.assertEqual(self.s.publish_claim(job_id="a")["status"], "claimed")  # no gap/limit for a manual click

    def test_manual_respects_challenge_pause_and_unconfirmed_posts(self):
        self.ready("a")
        self.s.set_challenge(True)
        self.assertEqual(self.s.publish_claim(job_id="a")["status"], "blocked")
        self.s.set_challenge(False)
        self.job("u", "publish_unknown")
        self.assertEqual(self.s.publish_claim(job_id="a")["status"], "blocked")

    def test_manual_only_claims_the_chosen_ready_video(self):
        self.ready("a")
        self.job("p", "published", output_file="/d/p.mp4")
        self.assertEqual(self.s.publish_claim(job_id="p")["status"], "idle")
        self.assertEqual(self.s.publish_claim(job_id="nope")["status"], "idle")
        self.job("w", "awaiting_approval", output_file="/d/w.mp4")
        self.assertEqual(self.s.publish_claim(job_id="w")["status"], "claimed")  # clicking Post also approves it

    def test_claim_uses_edited_caption_and_visibility(self):
        self.ready("a")
        self.s.update_settings({"visibility": "self"})
        self.s.set_caption("a", "Mô tả của chủ kênh #vui #haihuoc #giadinh")
        r = self.s.publish_claim(job_id="a")
        self.assertEqual(r["caption"], "Mô tả của chủ kênh #vui #haihuoc #giadinh")
        self.assertEqual(r["visibility"], "self")

    def test_parked_video_can_be_put_back_and_starts_with_a_clean_slate(self):
        out = Path(self.tmp.name) / "jobs" / "a" / "final.mp4"
        out.parent.mkdir(parents=True)
        out.write_bytes(b"x" * 100)
        self.job(
            "a",
            "ready",
            output_file=str(out),
            output_hash="h",
            analysis=json.dumps({"caption_vi": "Mô tả đủ dài", "hashtags": ["a1", "b2", "c3"]}),
        )
        for _ in range(3):
            r = self.s.publish_claim(job_id="a")
            self.s.publish_finish("a", r["lease"], "failed", reason="UI changed")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["needs_review"])
        self.assertIn("output_file", self.s.dashboard_data()["review"][0])
        self.s.decide("a", "retry")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["ready"])
        r = self.s.publish_claim(job_id="a")
        self.s.publish_finish("a", r["lease"], "failed", reason="again")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["ready"])  # one failure again, not instantly parked
        with self.assertRaises(ValueError):
            self.job("b", "needs_review")
            self.s.decide("b", "retry")  # nothing rendered, nothing to put back

    def test_two_clicks_cannot_post_the_same_video_twice(self):
        self.ready("a")
        results = []
        barrier = threading.Barrier(6)

        def click():
            barrier.wait()
            results.append(self.s.publish_claim(job_id="a")["status"])

        ts = [threading.Thread(target=click) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count("claimed"), 1)

    def test_peek_can_target_a_video_without_changing_state(self):
        self.ready("a")
        self.ready("b", meta=json.dumps({"score": 5}))
        self.assertEqual(self.s.publish_peek("a")["id"], "a")
        self.assertEqual(self.s.publish_peek()["id"], "b")  # best score first
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]].count("ready"), 2)


class PublishFailureTests(StoreCase):
    def test_failed_manual_click_on_an_unapproved_video_does_not_approve_it(self):
        self.job("w", "awaiting_approval", output_file="/d/w.mp4", output_hash="h")
        r = self.s.publish_claim(job_id="w")
        self.s.publish_finish("w", r["lease"], "failed", reason="Chrome did not start")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["awaiting_approval"])
        self.s.update_settings({"publisher_enabled": True, "post_windows": [], "min_publish_gap": 0})
        self.assertEqual(self.s.publish_claim(now=time.time() + 9000)["status"], "idle")  # the scheduler still will not post it

    def test_resolving_an_unknown_post_as_not_posted_restores_the_prior_state(self):
        self.job("w", "awaiting_approval", output_file="/d/w.mp4", output_hash="h")
        r = self.s.publish_claim(job_id="w")
        self.s.publish_finish("w", r["lease"], "unknown", reason="?")
        self.s.resolve_unknown("w", "failed")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["awaiting_approval"])

    def test_deferred_outcome_is_not_counted_as_the_videos_fault(self):
        self.ready("a")
        for _ in range(5):
            r = self.s.publish_claim(job_id="a")
            self.s.publish_finish("a", r["lease"], "deferred", reason="TikTok asked for verification")
        self.assertEqual(self.s.ready_list()[0]["id"], "a")
        self.assertEqual(self.s.publish_claim(job_id="a")["status"], "claimed")

    def test_three_failures_park_the_video_for_review(self):
        self.ready("a")
        sent = []
        self.s.notifier = lambda kind, text, key: sent.append(kind)
        for n in range(3):
            r = self.s.publish_claim(job_id="a")
            self.s.publish_finish("a", r["lease"], "failed", reason="UI changed")
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["needs_review"])
        self.assertIn("review", sent)

    def test_a_failing_video_does_not_block_the_next_one(self):
        self.ready("bad", meta=json.dumps({"score": 99}))
        self.ready("good", meta=json.dumps({"score": 1}))
        self.s.update_settings({"publisher_enabled": True, "post_windows": [], "min_publish_gap": 0})
        r = self.s.publish_claim()
        self.assertEqual(r["id"], "bad")
        self.s.publish_finish("bad", r["lease"], "failed", reason="x")
        self.assertEqual(self.s.publish_claim()["id"], "good")  # the best video is cooling off, the next one goes

    def test_housekeeping_gives_a_slow_publish_45_minutes(self):
        self.ready("a")
        self.s.publish_claim(job_id="a")
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET updated=? WHERE id=?", (time.time() - 1500, "a"))  # 25 minutes: still a live publish
        self.s.housekeeping()
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["publishing"])
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET updated=? WHERE id=?", (time.time() - 3000, "a"))
        self.s.housekeeping()
        self.assertEqual([j["state"] for j in self.s.status()["jobs"]], ["publish_unknown"])


if __name__ == "__main__":
    unittest.main()
