"""Processing several queued videos at once: Gemini's latency dominates a video's time, so two at a time nearly doubles throughput."""

import itertools
import threading
import time
from pathlib import Path
from unittest import mock

from tests.support import StoreCase
from trendvn_worker import pipeline
from trendvn_worker.files import file_hash

ANALYSIS = {"kind": "dialogue", "caption_vi": "Mô tả", "hashtags": ["a", "b", "c"], "segments": [], "topic": "pets"}


class ProcessManyTests(StoreCase):
    def test_runs_the_requested_number_with_the_requested_overlap(self):
        active, peak, calls = [0], [0], []
        lock = threading.Lock()

        def slow(store):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                calls.append(1)
            time.sleep(0.15)
            with lock:
                active[0] -= 1
            return {"status": "ready"}

        with mock.patch.object(pipeline, "process_one", slow):
            started = time.time()
            results = pipeline.process_many(self.s, 4, parallel=2)
            took = time.time() - started
        self.assertEqual((len(results), len(calls), peak[0]), (4, 4, 2))
        self.assertLess(took, 0.5)  # four 0.15 s jobs, two at a time: about 0.3 s, not 0.6 s

    def test_a_terminal_status_stops_handing_out_work(self):
        statuses = iter(["ready", "idle"] + ["ready"] * 20)
        lock = threading.Lock()

        def process_one(store):
            with lock:
                status = next(statuses)
            time.sleep(0.05)
            return {"status": status}

        with mock.patch.object(pipeline, "process_one", process_one):
            results = pipeline.process_many(self.s, 8, parallel=2)
        self.assertLessEqual(len(results), 4)  # the two in flight may finish, nothing new starts after "idle"
        self.assertIn("idle", [r["status"] for r in results])

    def test_one_run_that_raises_is_reported_and_the_others_finish(self):
        outcomes = itertools.cycle([RuntimeError("boom"), {"status": "ready"}])
        lock = threading.Lock()

        def process_one(store):
            with lock:
                outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(pipeline, "process_one", process_one):
            results = pipeline.process_many(self.s, 4, parallel=2)
        self.assertEqual(sorted(r["status"] for r in results), ["error", "error", "ready", "ready"])
        self.assertIn("boom", [r for r in results if r["status"] == "error"][0]["reason"])

    def test_counts_are_clamped(self):
        with mock.patch.object(pipeline, "process_one", lambda store: {"status": "ready"}):
            self.assertEqual(len(pipeline.process_many(self.s, 1, parallel=5)), 1)
            self.assertEqual(len(pipeline.process_many(self.s, 3, parallel=0)), 3)
            self.assertEqual(pipeline.process_many(self.s, 0, parallel=2), [])


class RealJobsInParallelTests(StoreCase):
    def test_every_queued_video_is_processed_exactly_once(self):
        source = Path(self.tmp.name) / "source.mp4"
        source.write_bytes(b"video")
        (self.s.root / "gemini.key").write_text("key")
        self.s.update_settings({"processing_enabled": True, "require_approval": False})
        for i in range(5):
            self.job("j%d" % i, "queued", source_file=str(source), content_hash=file_hash(source), first_seen=i)
        counter, lock = itertools.count(), threading.Lock()

        def unique_fingerprint(path, duration):
            with lock:
                return [next(counter)]

        analyzed = []

        def analyze(store, path, duration, cfg, folder, lenient=False):
            analyzed.append(folder.name)
            time.sleep(0.05)
            return dict(ANALYSIS), "vietsub"

        def render(path, folder, analysis, route, duration, voice=None):
            out = folder / "final.mp4"
            out.write_bytes(b"rendered " + folder.name.encode())
            return out

        with mock.patch.multiple(
            pipeline,
            probe=lambda path: (30.0, {"streams": [{"codec_type": "video", "width": 720, "height": 1280}]}),
            fingerprint=unique_fingerprint,
            similar=lambda a, b: a == b,
            analyze=analyze,
            render=render,
            qc=lambda out, audio: ({"w": 720, "h": 1280, "duration": 30.0}, []),
            make_poster=lambda out, poster, duration: None,
        ):
            results = pipeline.process_many(self.s, 5, parallel=3)
        self.assertEqual(sorted(r["status"] for r in results), ["ready"] * 5)
        self.assertEqual(sorted(analyzed), ["j%d" % i for i in range(5)])  # each job analysed once, none twice
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE state='ready'").fetchone()[0], 5)
            self.assertEqual(db.execute("SELECT count(DISTINCT output_hash) FROM jobs").fetchone()[0], 5)
