"""Manual posting, caption editing and quality checks, background tasks, video geometry and quality gates (version 1.2 features)."""
import json
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'worker' / 'app'))
sys.path.insert(0, str(ROOT / 'services' / 'agent'))
import core
import tasks as tasks_mod
import ui


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = core.Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def job(self, jid, state, **kw):
        cols = dict(id=jid, platform='douyin', source_id=jid, url='https://www.douyin.com/video/' + jid, country='CN', title='Tiêu đề ' + jid,
                    first_seen=1, last_seen=1, state=state, updated=time.time())
        cols.update(kw)
        with self.s.transaction() as db:
            db.execute('INSERT INTO jobs(%s) VALUES (%s)' % (','.join(cols), ','.join('?' * len(cols))), list(cols.values()))

    def ready(self, jid, **kw):
        self.job(jid, 'ready', output_file='/d/%s.mp4' % jid, output_hash='h', analysis=json.dumps({'kind': 'dialogue', 'caption_vi': 'Mô tả ' + jid, 'hashtags': ['a', 'b', 'c']}), **kw)


class ManualPublishTests(Base):
    def test_manual_click_waives_switch_window_limit_and_gap_but_not_safety_rails(self):
        self.ready('a'); self.ready('b')
        # switch off, outside the window: the scheduled path refuses...
        self.assertEqual(self.s.publish_claim()['status'], 'disabled')
        # ...but the owner's click on a specific video goes through
        r = self.s.publish_claim(job_id='b')
        self.assertEqual((r['status'], r['id'], r['manual']), ('claimed', 'b', True))
        self.assertEqual(self.s.publish_claim(job_id='a')['status'], 'blocked')        # one post in flight at a time
        self.s.publish_finish('b', r['lease'], 'published', 'https://www.tiktok.com/@u/video/1')
        self.assertEqual(self.s.publish_claim(job_id='a')['status'], 'claimed')        # no gap/limit for a manual click

    def test_manual_respects_challenge_pause_and_unconfirmed_posts(self):
        self.ready('a')
        self.s.set_challenge(True)
        self.assertEqual(self.s.publish_claim(job_id='a')['status'], 'blocked')
        self.s.set_challenge(False)
        self.job('u', 'publish_unknown')
        self.assertEqual(self.s.publish_claim(job_id='a')['status'], 'blocked')

    def test_manual_only_claims_the_chosen_ready_video(self):
        self.ready('a')
        self.job('p', 'published', output_file='/d/p.mp4')
        self.assertEqual(self.s.publish_claim(job_id='p')['status'], 'idle')
        self.assertEqual(self.s.publish_claim(job_id='nope')['status'], 'idle')
        self.job('w', 'awaiting_approval', output_file='/d/w.mp4')
        self.assertEqual(self.s.publish_claim(job_id='w')['status'], 'claimed')        # clicking Post also approves it

    def test_claim_uses_edited_caption_and_visibility(self):
        self.ready('a')
        self.s.update_settings({'visibility': 'self'})
        self.s.set_caption('a', 'Mô tả của chủ kênh #vui #haihuoc #giadinh')
        r = self.s.publish_claim(job_id='a')
        self.assertEqual(r['caption'], 'Mô tả của chủ kênh #vui #haihuoc #giadinh')
        self.assertEqual(r['visibility'], 'self')

    def test_parked_video_can_be_put_back_and_starts_with_a_clean_slate(self):
        out = Path(self.tmp.name) / 'jobs' / 'a' / 'final.mp4'
        out.parent.mkdir(parents=True)
        out.write_bytes(b'x' * 100)
        self.job('a', 'ready', output_file=str(out), output_hash='h', analysis=json.dumps({'caption_vi': 'Mô tả đủ dài', 'hashtags': ['a1', 'b2', 'c3']}))
        for _ in range(3):
            r = self.s.publish_claim(job_id='a')
            self.s.publish_finish('a', r['lease'], 'failed', reason='UI changed')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['needs_review'])
        self.assertIn('output_file', self.s.dashboard_data()['review'][0])
        self.s.decide('a', 'retry')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['ready'])
        r = self.s.publish_claim(job_id='a')
        self.s.publish_finish('a', r['lease'], 'failed', reason='again')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['ready'])          # one failure again, not instantly parked
        with self.assertRaises(ValueError):
            self.job('b', 'needs_review')
            self.s.decide('b', 'retry')                                                      # nothing rendered, nothing to put back

    def test_two_clicks_cannot_post_the_same_video_twice(self):
        self.ready('a')
        results = []
        barrier = threading.Barrier(6)

        def click():
            barrier.wait()
            results.append(self.s.publish_claim(job_id='a')['status'])
        ts = [threading.Thread(target=click) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count('claimed'), 1)

    def test_peek_can_target_a_video_without_changing_state(self):
        self.ready('a'); self.ready('b', meta=json.dumps({'score': 5}))
        self.assertEqual(self.s.publish_peek('a')['id'], 'a')
        self.assertEqual(self.s.publish_peek()['id'], 'b')                               # best score first
        self.assertEqual([j['state'] for j in self.s.status()['jobs']].count('ready'), 2)


class PublishFailureTests(Base):
    def test_failed_manual_click_on_an_unapproved_video_does_not_approve_it(self):
        self.job('w', 'awaiting_approval', output_file='/d/w.mp4', output_hash='h')
        r = self.s.publish_claim(job_id='w')
        self.s.publish_finish('w', r['lease'], 'failed', reason='Chrome did not start')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['awaiting_approval'])
        self.s.update_settings({'publisher_enabled': True, 'post_windows': [], 'min_publish_gap': 0})
        self.assertEqual(self.s.publish_claim(now=time.time() + 9000)['status'], 'idle')     # the scheduler still will not post it

    def test_resolving_an_unknown_post_as_not_posted_restores_the_prior_state(self):
        self.job('w', 'awaiting_approval', output_file='/d/w.mp4', output_hash='h')
        r = self.s.publish_claim(job_id='w')
        self.s.publish_finish('w', r['lease'], 'unknown', reason='?')
        self.s.resolve_unknown('w', 'failed')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['awaiting_approval'])

    def test_deferred_outcome_is_not_counted_as_the_videos_fault(self):
        self.ready('a')
        for _ in range(5):
            r = self.s.publish_claim(job_id='a')
            self.s.publish_finish('a', r['lease'], 'deferred', reason='TikTok asked for verification')
        self.assertEqual(self.s.ready_list()[0]['id'], 'a')
        self.assertEqual(self.s.publish_claim(job_id='a')['status'], 'claimed')

    def test_three_failures_park_the_video_for_review(self):
        self.ready('a')
        sent = []
        self.s.notifier = lambda kind, text, key: sent.append(kind)
        for n in range(3):
            r = self.s.publish_claim(job_id='a')
            self.s.publish_finish('a', r['lease'], 'failed', reason='UI changed')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['needs_review'])
        self.assertIn('review', sent)

    def test_a_failing_video_does_not_block_the_next_one(self):
        self.ready('bad', meta=json.dumps({'score': 99})); self.ready('good', meta=json.dumps({'score': 1}))
        self.s.update_settings({'publisher_enabled': True, 'post_windows': [], 'min_publish_gap': 0})
        r = self.s.publish_claim()
        self.assertEqual(r['id'], 'bad')
        self.s.publish_finish('bad', r['lease'], 'failed', reason='x')
        self.assertEqual(self.s.publish_claim()['id'], 'good')                               # the best video is cooling off, the next one goes

    def test_housekeeping_gives_a_slow_publish_45_minutes(self):
        self.ready('a')
        r = self.s.publish_claim(job_id='a')
        with self.s.transaction() as db:
            db.execute('UPDATE jobs SET updated=? WHERE id=?', (time.time() - 1500, 'a'))     # 25 minutes: still a live publish
        self.s.housekeeping()
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['publishing'])
        with self.s.transaction() as db:
            db.execute('UPDATE jobs SET updated=? WHERE id=?', (time.time() - 3000, 'a'))
        self.s.housekeeping()
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['publish_unknown'])


class RobustnessTests(Base):
    def test_malformed_model_output_cannot_break_captions_or_the_list(self):
        for bad in (5, True, 'haihuoc', {'a': 1}, [None, 7, ['x'], 'ok1']):
            c = core.build_caption({'kind': 'dialogue', 'caption_vi': 'Một câu mô tả đầy đủ', 'hashtags': bad}, 't')
            self.assertIn('#xuhuong', c)
        self.job('a', 'ready', output_file='/d/a.mp4', output_hash='h', analysis='{not json')
        self.assertEqual(len(self.s.ready_list()), 1)

    def test_caption_line_breaks_and_unicode_are_normalised(self):
        self.ready('a')
        self.s.set_caption('a', 'Dòng một  \r\nDòng hai\r\n#a1 #b2 #c3')
        self.assertEqual(self.s.ready_list()[0]['caption'], 'Dòng một\nDòng hai\n#a1 #b2 #c3')
        again = self.s.ready_list()[0]['caption']
        self.s.set_caption('a', again.replace('\n', '\r\n'))
        self.assertEqual(len([e for e in self.s.recent_events(50) if e['event'] == 'caption_edited']), 1)   # re-saving the same text is not an edit
        self.s.set_caption('a', 'Vie\u0302\u0323t Nam #vie\u0302\u0323t #a2 #b3')
        self.assertIn('Việt Nam', self.s.ready_list()[0]['caption'])                                          # decomposed accents become normal letters

    def test_partial_settings_update_never_erases_other_thresholds(self):
        self.s.update_settings({'min_views': {'tiktok': 7}})
        self.s.update_settings({'min_likes': {'douyin': 9}})
        cfg = self.s.settings()
        self.assertEqual((cfg['min_views']['tiktok'], cfg['min_views']['kuaishou'], cfg['min_likes']['douyin']), (7, 1000000, 9))


class CaptionTests(Base):
    def test_edit_validate_reset(self):
        self.ready('a')
        for bad in ('', '   ', 'x' * 2201):
            with self.assertRaises(ValueError):
                self.s.set_caption('a', bad)
        self.s.set_caption('a', 'Mô tả mới #a #b #c')
        self.assertTrue(self.s.ready_list()[0]['caption_edited'])
        self.s.reset_caption('a')
        self.assertFalse(self.s.ready_list()[0]['caption_edited'])

    def test_unchanged_caption_is_not_an_edit(self):
        self.ready('a')
        same = self.s.ready_list()[0]['caption']
        self.s.set_caption('a', same)
        self.assertFalse(self.s.ready_list()[0]['caption_edited'])
        self.assertEqual(len([e for e in self.s.recent_events(50) if e['event'] == 'caption_edited']), 0)

    def test_only_unposted_videos_can_be_edited(self):
        self.job('p', 'published')
        with self.assertRaises(ValueError):
            self.s.set_caption('p', 'x')

    def test_caption_quality_rules(self):
        self.assertTrue(core.lint_caption('Khoảnh khắc thú vị của bé #vui #haihuoc #giadinh')['ok'])
        self.assertIn('Nên có 3–5 hashtag', core.lint_caption('Khoảnh khắc thú vị của bé #vui')['issues'])
        self.assertIn('Quá nhiều hashtag (nên tối đa 5)', core.lint_caption('Mô tả dài đủ dùng #a1 #b2 #c3 #d4 #e5 #f6')['issues'])
        self.assertIn('Có hashtag bị lặp', core.lint_caption('Mô tả dài đủ dùng #Vui #vui #c3')['issues'])
        self.assertIn('Mô tả quá ngắn', core.lint_caption('Hi #a1 #b2 #c3')['issues'])
        self.assertTrue(core.lint_caption('Nhạc #nhac #xuhuong #hay với tiếng Việt có dấu đầy đủ')['tags'] == 3)

    def test_build_caption_properties(self):
        long = 'Một mô tả rất dài ' * 20
        c = core.build_caption({'kind': 'dialogue', 'caption_vi': long, 'hashtags': ['Hài', '#vui vẻ', 'x', 'haihuoc', 'haihuoc', 'a' * 40]}, 't')
        text = c.split(' #')[0]
        self.assertLessEqual(len(text), 110)
        self.assertFalse(text.endswith((',', ';', ':', '-')))
        tags = [t for t in c.split() if t.startswith('#')]
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(len(tags), 5)
        self.assertIn('#xuhuong', tags)
        self.assertTrue(core.lint_caption(c)['tags'] <= 5)
        self.assertEqual(core.build_caption({'kind': 'music', 'caption_vi': 'Hay quá', 'hashtags': []}, 't'), 'Hay quá #xuhuong #nhac')
        self.assertNotIn('##', core.build_caption({'caption_vi': '#a #b nội dung', 'hashtags': ['#c']}, 't'))

    def test_platform_names_and_filler_never_become_hashtags(self):
        c = core.build_caption({'kind': 'dialogue', 'caption_vi': 'Một câu mô tả đầy đủ', 'hashtags': ['tiktokgiaitri', 'douyinvn', 'fyp', 'viral', 'haihuoc', 'giadinh']}, 't')
        tags = [x for x in c.split() if x.startswith('#')]
        self.assertEqual(tags, ['#haihuoc', '#giadinh', '#xuhuong', '#giaitri'])

    def test_caption_with_emoji_and_diacritics_survives(self):
        self.ready('a')
        self.s.set_caption('a', 'Cười xỉu với cô bé này 😂😂 #hàihước #vui #xuhuong')
        self.assertIn('😂', self.s.ready_list()[0]['caption'])


class ReadyListTests(Base):
    def test_ready_list_orders_by_score_and_reports_quality(self):
        self.ready('low', meta=json.dumps({'score': 1}), output_info=json.dumps({'w': 1080, 'h': 1920}))
        self.ready('high', meta=json.dumps({'score': 99}))
        self.job('x', 'queued')
        lst = self.s.ready_list()
        self.assertEqual([j['id'] for j in lst], ['high', 'low'])
        self.assertEqual(lst[1]['info']['w'], 1080)
        self.assertIn('ok', lst[0]['lint'])


class FakeAgentHandler(BaseHTTPRequestHandler):
    hits = []
    code = 200
    body = {'report': {'douyin': {'status': 'ok', 'summary': {'jingxuan': {'seen': 5, 'qualified': 2, 'baseline': False, 'new': 1}, 'media': {'downloaded': 1}}}}}
    delay = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length', '0'))
        FakeAgentHandler.hits.append((self.path, json.loads(self.rfile.read(n) or b'{}'), self.headers.get('Authorization')))
        time.sleep(FakeAgentHandler.delay)
        body = json.dumps(FakeAgentHandler.body).encode()
        self.send_response(FakeAgentHandler.code)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TaskTests(Base):
    def setUp(self):
        super().setUp()
        FakeAgentHandler.hits.clear()
        FakeAgentHandler.code, FakeAgentHandler.delay = 200, 0
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), FakeAgentHandler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.real_url = tasks_mod.agent_url
        tasks_mod.agent_url = lambda: 'http://127.0.0.1:%d' % self.srv.server_address[1]
        self.lock = threading.Lock()
        self.processed = []
        self.t = tasks_mod.Tasks(self.s, 't' * 40, lambda store: self.processed.append(1) or {'status': 'idle'}, self.lock)

    def tearDown(self):
        tasks_mod.agent_url = self.real_url
        self.srv.shutdown()
        super().tearDown()

    def wait(self, tid, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            row = [x for x in self.s.tasks_recent(20) if x['id'] == tid][0]
            if row['state'] != 'running':
                return row
            time.sleep(0.05)
        self.fail('task still running')

    def test_collect_task_summarises_each_source_in_vietnamese(self):
        row = self.wait(self.t.start('collect'))
        self.assertEqual(row['state'], 'done')
        self.assertIn('Douyin', row['result'])
        self.assertEqual(FakeAgentHandler.hits[0][0], '/api/collect')
        self.assertEqual(FakeAgentHandler.hits[0][2], 'Bearer ' + 't' * 40)

    def test_update_runs_collect_then_process_and_survives_a_failed_step(self):
        FakeAgentHandler.code = 500
        row = self.wait(self.t.start('update'))
        self.assertEqual(len(row['steps']), 2)
        self.assertEqual(row['steps'][0]['state'], 'error')
        self.assertEqual(row['state'], 'done')                 # processing still ran, so the round is not a total failure
        self.assertTrue(self.processed)

    def test_agent_busy_and_agent_down_give_owner_readable_errors(self):
        FakeAgentHandler.code = 409
        row = self.wait(self.t.start('collect'))
        self.assertEqual(row['state'], 'error')
        self.assertIn('bận', row['error'] + row['result'])
        self.srv.shutdown()
        self.srv.server_close()
        row = self.wait(self.t.start('collect'))
        self.assertIn('agent', (row['error'] + row['result']).lower())

    def test_a_second_browser_task_is_refused_while_one_runs(self):
        FakeAgentHandler.delay = 1.0
        first = self.t.start('collect')
        with self.assertRaises(tasks_mod.TaskBusy):
            self.t.start('publish', 'a' * 32)
        with self.assertRaises(tasks_mod.TaskBusy):
            self.t.start('update')
        self.t.start('process')                                # processing does not need the browser, so it may run alongside
        self.wait(first)

    def test_process_shares_the_schedules_lock(self):
        self.lock.acquire()
        try:
            row = self.wait(self.t.start('process'))
            self.assertIn('lịch tự động', (row['error'] + row['result']))
            self.assertFalse(self.processed)
        finally:
            self.lock.release()

    def test_publish_and_dryrun_pass_the_chosen_video_to_the_agent(self):
        FakeAgentHandler.body = {'status': 'published', 'url': 'https://www.tiktok.com/@u/video/1'}
        row = self.wait(self.t.start('publish', 'b' * 32))
        self.assertEqual(FakeAgentHandler.hits[-1][:2], ('/api/publish', {'job_id': 'b' * 32}))
        self.assertIn('Đã đăng', row['result'])
        FakeAgentHandler.body = {'status': 'dry_run', 'screenshot': '/x.png'}
        row = self.wait(self.t.start('dryrun', 'b' * 32))
        self.assertEqual(FakeAgentHandler.hits[-1][0], '/api/dry-run')
        self.assertEqual(row['state'], 'done')
        FakeAgentHandler.body = {'status': 'challenge'}
        row = self.wait(self.t.start('publish', 'b' * 32))
        self.assertEqual(row['state'], 'error')
        self.assertIn('xác minh', row['result'])

    def test_bad_requests_are_rejected(self):
        for kind, job in (('nope', None), ('publish', None), ('dryrun', '')):
            with self.assertRaises(ValueError):
                self.t.start(kind, job)

    def test_leftover_running_tasks_are_reaped_after_a_restart(self):
        tid = self.s.task_create('collect')
        tasks_mod.Tasks(self.s, 't' * 40, lambda s: {}, self.lock)
        row = [x for x in self.s.tasks_recent(5) if x['id'] == tid][0]
        self.assertEqual(row['state'], 'error')
        self.assertFalse(self.s.tasks_running())

    def test_unexpected_exception_never_leaves_a_task_running(self):
        def boom(store):
            raise RuntimeError('kaboom')
        t = tasks_mod.Tasks(self.s, 't' * 40, boom, self.lock)
        row = self.wait(t.start('process'))
        self.assertNotEqual(row['state'], 'running')


class SegmentNormalisationTests(unittest.TestCase):
    """Regression for a real Gemini failure: on a 138 s video it listed 11 lines after the end and the whole video was rejected."""

    def norm(self, segs, dur=10.0):
        return core.normalize_segments([dict(s, vi='x') for s in segs], dur)

    def test_hallucinated_lines_past_the_end_are_dropped_and_the_rest_kept(self):
        segs = [{'start': i * 3.0, 'end': i * 3.0 + 3.0} for i in range(40)]      # a real 120 s video, but Gemini kept going to 120
        out = core.normalize_segments([dict(s, vi='x') for s in segs], 100.0)
        self.assertEqual(len(out), 34)
        self.assertLessEqual(out[-1]['end'], 100.0)

    def test_overlaps_are_trimmed_and_order_fixed(self):
        out = self.norm([{'start': 4.0, 'end': 7.0}, {'start': 0.0, 'end': 4.5}])
        self.assertEqual([(s['start'], s['end']) for s in out], [(0.0, 4.0), (4.0, 7.0)])

    def test_zero_length_and_tiny_lines_are_dropped(self):
        out = self.norm([{'start': 1.0, 'end': 1.0}, {'start': 2.0, 'end': 2.1}, {'start': 3.0, 'end': 5.0}])
        self.assertEqual(len(out), 1)

    def test_last_line_is_cut_at_the_video_end(self):
        out = self.norm([{'start': 8.0, 'end': 14.0}])
        self.assertEqual(out[0]['end'], 10.0)

    def test_unreliable_output_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.norm([{'start': 20.0, 'end': 25.0}, {'start': 25.0, 'end': 30.0}, {'start': 1.0, 'end': 2.0}])
        for bad in ([{'start': True, 'end': 2.0}], [{'start': 0, 'end': float('nan')}], ['x']):
            with self.assertRaises(ValueError):
                self.norm(bad)

    def test_validate_analysis_persists_the_repaired_segments(self):
        a = {'kind': 'dialogue', 'confidence': .99, 'topic': 'entertainment', 'sensitive': False,
             'segments': [{'start': 0.0, 'end': 4.0, 'vi': 'a'}, {'start': 3.5, 'end': 7.0, 'vi': 'b'}, {'start': 12.0, 'end': 15.0, 'vi': 'c'}]}
        self.assertEqual(core.validate_analysis(a, 10.0, strict=True), 'vietsub')
        self.assertEqual([(s['start'], s['end']) for s in a['segments']], [(0.0, 3.5), (3.5, 7.0)])


class SummaryTests(unittest.TestCase):
    def test_process_summaries(self):
        self.assertIn('TẮT', tasks_mod.summarize_process([{'status': 'disabled'}]))
        self.assertIn('Không có video', tasks_mod.summarize_process([{'status': 'idle'}]))
        self.assertIn('2 sẵn sàng đăng', tasks_mod.summarize_process([{'status': 'ready'}, {'status': 'ready'}, {'status': 'idle'}]))

    def test_collect_summary_handles_skipped_and_first_scan(self):
        text = tasks_mod.summarize_collect({'tiktok': {'status': 'skipped', 'reason': 'Cần IP US'},
                                            'douyin': {'status': 'ok', 'summary': {'s': {'seen': 10, 'qualified': 3, 'baseline': True, 'new': 3}}},
                                            'kuaishou': {'status': 'error', 'reason': 'hết thời gian'}})
        self.assertIn('bỏ qua', text)
        self.assertIn('lần đầu', text)
        self.assertIn('lỗi', text)


class GeometryAndQualityTests(unittest.TestCase):
    def test_layout_rules(self):
        import media
        self.assertEqual(media.layout(1080, 1920), {'reframe': False, 'w': 1080, 'h': 1920})
        self.assertEqual(media.layout(721, 1281), {'reframe': False, 'w': 720, 'h': 1280})   # odd sizes made even
        wide = media.layout(1920, 1080)
        self.assertTrue(wide['reframe'] and (wide['w'], wide['h']) == (1080, 1920) and wide['fg_h'] == 608 and wide['band_top'] == 1264)
        sq = media.layout(1080, 1080)
        self.assertTrue(sq['reframe'] and sq['fg_h'] == 1080)
        self.assertTrue(media.layout(1280, 720)['reframe'])
        self.assertFalse(media.layout(1080, 1350)['reframe'] is False)                        # 4:5 goes on the canvas too

    def test_subtitles_sit_in_the_band_when_reframed(self):
        import media
        seg = [{'start': 0.5, 'end': 3.0, 'vi': 'Xin chào các bạn'}]
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.ass', Path(d) / 'b.ass'
            media.ass_subtitles(seg, a, 1080, 1920)
            media.ass_subtitles(seg, b, 1080, 1920, band_top=1264)
            style_a = [l for l in a.read_text().splitlines() if l.startswith('Style:')][0].split(',')
            style_b = [l for l in b.read_text().splitlines() if l.startswith('Style:')][0].split(',')
        self.assertEqual(style_a[18], '2')          # bottom-centre over the picture
        self.assertEqual(style_b[18], '8')          # top-centre inside the free band
        self.assertGreater(int(style_b[21]), 1264)  # margin pushes the text below the picture

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'needs ffmpeg/ffprobe (runs in the worker image)')
    def test_real_render_portrait_wide_and_silent(self):
        import subprocess
        import media
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)

            def make(name, size, audio=True, rate=30):
                out = d / name
                cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=%s:d=4:r=%d' % (size, rate)]
                if audio:
                    cmd += ['-f', 'lavfi', '-i', 'sine=frequency=300:duration=4']
                cmd += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p'] + (['-c:a', 'aac'] if audio else []) + [str(out)]
                subprocess.run(cmd, check=True)
                return out
            analysis = {'kind': 'dialogue', 'segments': [{'start': 0.5, 'end': 3.0, 'vi': 'Xin chào các bạn, đây là bản thử'}]}
            for name, size, audio, rate, expect_wh in (('p.mp4', '720x1280', True, 30, (720, 1280)), ('w.mp4', '1920x1080', True, 60, (1080, 1920)),
                                                      ('s.mp4', '1080x1080', False, 25, (1080, 1920))):
                src = make(name, size, audio, rate)
                folder = d / name.split('.')[0]
                folder.mkdir()
                dur, meta = media.probe(src)
                out = media.render(src, folder, analysis, 'vietsub', dur)
                info, problems = media.qc(out, audio)
                self.assertEqual((info['w'], info['h']), expect_wh, name)
                self.assertEqual(problems, [], name)
                self.assertEqual(info['audio'], audio, name)
                self.assertLessEqual(info['fps'], 30, name)
                self.assertAlmostEqual(info['duration'], 4.0, delta=0.5, msg=name)
                media.make_poster(out, folder / 'poster.jpg', dur)
                self.assertGreater((folder / 'poster.jpg').stat().st_size, 500, name)
            # metadata of the source is not carried over
            tagged = d / 'tag.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(d / 'p.mp4'), '-metadata', 'comment=SOURCE-SECRET', '-c', 'copy', str(tagged)], check=True)
            folder = d / 'tag'
            folder.mkdir()
            out = media.render(tagged, folder, analysis, 'vietsub', media.probe(tagged)[0])
            self.assertNotIn(b'SOURCE-SECRET', out.read_bytes())


class RotationZonesAndSizeTests(unittest.TestCase):
    def test_displayed_size_follows_rotation(self):
        import media
        self.assertEqual(media.display_size({'width': 1280, 'height': 720}), (1280, 720))
        self.assertEqual(media.display_size({'width': 1280, 'height': 720, 'tags': {'rotate': '90'}}), (720, 1280))
        self.assertEqual(media.display_size({'width': 720, 'height': 1280, 'side_data_list': [{'rotation': -90}]}), (1280, 720))
        self.assertEqual(media.display_size({'width': 720, 'height': 1280, 'side_data_list': [{'rotation': 180}]}), (720, 1280))
        self.assertEqual(media.display_size({'width': 720, 'height': 1280, 'tags': {'rotate': 'x'}}), (720, 1280))

    def test_oversized_portrait_is_scaled_to_fit_and_small_is_left_alone(self):
        import media
        big = media.layout(2160, 3840)
        self.assertEqual((big['w'], big['h']), (1080, 1920))
        tall = media.layout(1080, 2400)
        self.assertLessEqual(tall['h'], 1920)
        self.assertEqual(tall['w'] % 2 + tall['h'] % 2, 0)
        self.assertEqual((media.layout(320, 568)['w'], media.layout(320, 568)['h']), (320, 568))

    def test_captions_stay_clear_of_tiktoks_lower_overlay(self):
        import media
        portrait = media.caption_zone(media.layout(1080, 1920))
        self.assertEqual(portrait['align'], 2)
        self.assertLessEqual(1920 - portrait['margin'], 1440 + 1)                 # text bottom edge above the overlay
        wide = media.caption_zone(media.layout(1920, 1080))
        self.assertEqual((wide['align'], wide['box']), (8, False))
        self.assertLess(wide['margin'], 1400)
        square = media.caption_zone(media.layout(1080, 1080))                      # its bottom band starts at 1500: too low, so the top band is used
        self.assertEqual(square['align'], 8)
        self.assertLess(square['margin'], 400)
        self.assertGreaterEqual(square['margin'], 140)                            # below TikTok's top tabs
        four_five = media.caption_zone(media.layout(1080, 1350))
        self.assertLess(four_five['margin'] + 130, (1920 - 1350) // 2 + 1)        # two caption lines fit inside the top band
        three_four = media.caption_zone(media.layout(1080, 1440))
        self.assertTrue(three_four['box'])


class PublisherOutcomeTests(unittest.TestCase):
    """publish_one must never raise and must never turn a pre-click error into 'unknown' or a post-click error into 'failed'."""

    def setUp(self):
        import publisher
        self.p = publisher
        self.tmp = tempfile.TemporaryDirectory()
        self.real = (publisher.RUNTIME, publisher.chrome)
        publisher.RUNTIME = Path(self.tmp.name)
        folder = Path(self.tmp.name) / 'jobs' / 'j1'
        folder.mkdir(parents=True)
        (folder / 'final.mp4').write_bytes(b'x' * 100)
        self.job = {'id': 'j1', 'output_hash': publisher.sha256(folder / 'final.mp4'), 'caption': 'Mô tả #a1 #b2 #c3', 'target': 'u', 'visibility': 'public'}

    def tearDown(self):
        self.p.RUNTIME, self.p.chrome = self.real
        self.tmp.cleanup()

    def test_chrome_failing_to_start_is_a_plain_failure(self):
        def boom(*a, **k):
            raise RuntimeError('Chrome crashed')
        self.p.chrome = boom
        outcome, url, reason = self.p.publish_one(self.job, dry_run=False)
        self.assertEqual(outcome, 'failed')
        self.assertIn('Chrome crashed', reason)

    def test_missing_or_changed_file_is_refused_before_any_browser(self):
        self.p.chrome = lambda *a, **k: (_ for _ in ()).throw(AssertionError('browser must not start'))
        self.assertEqual(self.p.publish_one(dict(self.job, output_hash='other'), False)[0], 'failed')
        self.assertEqual(self.p.publish_one(dict(self.job, id='nope'), False)[0], 'failed')

    def test_error_after_the_post_click_is_unknown_never_failed(self):
        state = {'clicked': False}
        orig = self.p._publish_one

        def clicked_then_boom(job, dry_run, st):
            st['clicked'] = True
            raise RuntimeError('network died while verifying')
        self.p._publish_one = clicked_then_boom
        try:
            outcome, _, reason = self.p.publish_one(self.job, dry_run=False)
        finally:
            self.p._publish_one = orig
        self.assertEqual(outcome, 'unknown')
        self.assertIn('network died', reason)

    def test_run_publish_always_reports_back_to_the_worker(self):
        calls = []
        real_worker = self.p.worker
        self.p.worker = lambda path, payload=None, timeout=900: calls.append((path, payload)) or (
            {'status': 'claimed', 'id': 'j1', 'lease': 'L', **{k: self.job[k] for k in ('output_hash', 'caption', 'target', 'visibility')}}
            if path.endswith('/claim') else {'ok': True})
        self.p.chrome = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('no display'))
        try:
            res = self.p.run_publish('j1')
        finally:
            self.p.worker = real_worker
        self.assertEqual(res['status'], 'failed')
        finish = [c for c in calls if c[0].endswith('/finish')]
        self.assertEqual(len(finish), 1)
        self.assertEqual((finish[0][1]['outcome'], finish[0][1]['lease']), ('failed', 'L'))
        self.assertEqual(calls[0][1], {'job_id': 'j1'})


class LoggingNeverBreaksJobsTests(unittest.TestCase):
    def test_log_survives_an_unwritable_log_file(self):
        import common
        real = common.DATA
        try:
            common.DATA = Path('/proc/nonexistent-dir')            # cannot be created or written
            common.log('still fine')
        finally:
            common.DATA = real


class UiHtmlTests(Base):
    def render(self, **extra):
        d = self.s.dashboard_data()
        d.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=self.s.tasks_recent(6))
        d.update(extra)
        return ui.render(d, 'CSRFX')

    def test_publish_tab_has_the_four_buttons_and_the_confirm_text(self):
        self.ready('a' * 32)
        html = self.render()
        for needle in ('Đăng ngay', 'Xem thử, không đăng', 'Lưu mô tả', 'Bỏ video', 'data-confirm=', 'Chế độ hiển thị'.replace('Chế độ hiển thị', 'CHỈ MÌNH TÔI' if False else 'CÔNG KHAI')):
            self.assertIn(needle, html)

    def test_buttons_are_disabled_while_a_task_runs_or_tiktok_asks_for_verification(self):
        self.ready('a' * 32)
        self.s.task_create('collect')
        html = self.render()
        self.assertIn('Đang có việc khác chạy', html)
        self.assertRegex(html, r'<button class="go big"[^>]*disabled')
        self.s.tasks_reap()
        self.s.set_challenge(True)
        html = self.render()
        self.assertIn('TikTok đang đòi xác minh', html)

    def test_user_text_is_escaped_in_the_caption_box_and_task_output(self):
        self.ready('a' * 32)
        self.s.set_caption('a' * 32, '</textarea><script>alert(1)</script> #a1 #b2 #c3')
        tid = self.s.task_create('publish', 'a' * 32)
        self.s.task_update(tid, steps=[{'name': '<b>x</b>', 'state': 'error', 'detail': '<img src=x onerror=alert(2)>'}], state='error', error='<script>3</script>')
        html = self.render()
        self.assertNotIn('<script>alert', html)
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('<script>3', html)

    def test_approve_button_only_for_unapproved_videos_and_quick_switches_ask_first(self):
        (Path(self.tmp.name) / 'gemini.key').write_text('x' * 30)
        self.ready('a' * 32)
        self.job('w' * 32, 'awaiting_approval', output_file='/d/w.mp4', output_hash='h', analysis=json.dumps({'caption_vi': 'Mô tả đủ dài để qua kiểm tra', 'hashtags': ['a1', 'b2', 'c3']}))
        html = self.render()
        self.assertEqual(html.count('Duyệt cho lịch tự đăng'), 1)
        self.assertEqual(len(re.findall(r'data-confirm="Bật tự đăng\?', html)), 1)
        self.assertEqual(len(re.findall(r'data-confirm="Bật xử lý video\?', html)), 2)     # the home switch and the Hàng đợi tab card; both ask first
        self.assertNotRegex(html, r'<button class="go big">\s*✔ Bật xử lý video')
        self.s.update_settings({'publisher_enabled': True})
        self.assertNotIn('data-confirm="Bật tự đăng', self.render())              # turning it OFF stays one tap

    def test_screenshot_name_becomes_a_link_but_arbitrary_paths_do_not(self):
        tid = self.s.task_create('dryrun', 'a' * 32)
        self.s.task_update(tid, steps=[{'name': 'x', 'state': 'done', 'detail': 'Xong. Xem ảnh chụp: /media/shot/shot_1790000000.png và /media/shot/../../etc/passwd'}], state='done')
        html = ui.task_panel(self.s.tasks_recent(3))
        self.assertIn('href="/media/shot/shot_1790000000.png"', html)
        self.assertNotIn('href="/media/shot/../', html)

    def queued(self, jid, state='queued', n=1):
        self.job(jid, state, url='https://x/' + jid, title='Video chờ ' + jid[:4], first_seen=time.time() - n)

    def test_publish_tab_explains_why_it_is_empty(self):
        html = self.render()
        self.assertIn('Chưa có video nào xử lý xong', html)
        self.assertIn('Chưa có video nào để xử lý', html)                                  # nothing anywhere: tells you to update
        self.queued('q' * 32)
        html = self.render()
        self.assertIn('1 video đang chờ xử lý</b> nhưng công tắc', html)                   # waiting but processing OFF: says so
        self.assertIn('Chưa có khóa Gemini', html)                                          # no key yet: points at the settings instead of a button that would fail
        (Path(self.tmp.name) / 'gemini.key').write_text('x' * 30)
        html = self.render()
        self.assertRegex(html, r'name="next" value="publish"><input type="hidden" name="processing_enabled" value="true"')   # key present: the switch is one tap
        self.s.update_settings({'processing_enabled': True})
        html = self.render()
        self.assertIn('Xử lý ngay (1)', html)                                              # waiting and ON: one button to process now
        self.assertNotIn('nhưng công tắc', html)

    def test_queue_tab_lists_what_waits_in_processing_order_and_has_its_own_nav_entry(self):
        self.queued('a' * 32, n=30)
        self.queued('b' * 32, n=10)
        self.queued('c' * 32, 'processing', n=5)
        self.queued('d' * 32, 'candidate', n=1)
        html = self.render()
        self.assertIn('<section data-tab="queue" id="queue"', html)
        body = html.split('<section data-tab="queue" id="queue"')[1].split('</section>')[0]
        self.assertLess(body.index('Video chờ cccc'), body.index('Video chờ aaaa'))         # being processed first
        self.assertLess(body.index('Video chờ aaaa'), body.index('Video chờ bbbb'))         # then oldest first, as claim() takes them
        self.assertIn('Ứng viên chưa tải về (1)', body)
        self.assertEqual(html.count('data-go="queue"'), 2)                                 # top nav and bottom nav
        self.assertNotIn('Hàng đợi (đang chờ xử lý)', html)                                 # no longer buried under Thêm
        d = self.s.dashboard_data()
        self.assertEqual([j['state'] for j in d['queue']], ['processing', 'queued', 'queued'])

    def test_status_pills_are_one_card_not_a_scrolling_row(self):
        html = self.render()
        self.assertIn('class="card pills"', html)
        self.assertNotIn('overflow-x:auto;scroll-snap', html)
        self.assertNotIn('white-space:nowrap}.chip', html)

    def test_old_finished_task_panels_are_hidden_on_other_tabs_but_running_ones_stay(self):
        tid = self.s.task_create('process')
        self.s.task_update(tid, steps=[{'name': 'x', 'state': 'done', 'detail': 'ok'}], state='done')
        tasks = self.s.tasks_recent(3)
        now = tasks[0]['started']
        self.assertIn('taskpanel', ui.task_panel(tasks, now + 60, ('process',)))
        self.assertEqual(ui.task_panel(tasks, now + 3 * 3600, ('process',)), '')
        self.assertIn('taskpanel', ui.task_panel(tasks, now + 3 * 3600))                    # the home panel always shows the latest
        self.s.task_create('collect')
        self.assertIn('data-running="1"', ui.task_panel(self.s.tasks_recent(3), now + 3 * 3600, ('collect',)))

    def test_no_element_ids_are_duplicated(self):
        import re
        self.ready('a' * 32)
        ids = re.findall(r'\sid="([^"]+)"', self.render())
        self.assertEqual(len(ids), len(set(ids)), [i for i in ids if ids.count(i) > 1])


if __name__ == '__main__':
    unittest.main()
