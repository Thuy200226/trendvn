"""Settings, golden-hour publishing, approval, feedback loop, notifications, dashboard rendering, scoring, voice-over."""
import json
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'worker' / 'app'))
sys.path.insert(0, str(ROOT / 'services' / 'agent'))
import core
import notify
import prompts
import ui
import collector as c

TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def at(hour, minute=0):
    return datetime(2026, 9, 30, hour, minute, tzinfo=TZ).timestamp()


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


class SettingsTests(Base):
    def test_valid_patch_is_saved(self):
        self.s.update_settings({'daily_limit': 3, 'post_windows': [[9, 12]], 'min_views': {'tiktok': 5}, 'target': '@my.account'})
        cfg = self.s.settings()
        self.assertEqual((cfg['daily_limit'], cfg['post_windows'], cfg['min_views']['tiktok'], cfg['target']), (3, [[9, 12]], 5, 'my.account'))
        self.assertEqual(cfg['min_views']['kuaishou'], 1000000)      # a partial update keeps the other sources' thresholds

    def test_bad_values_rejected(self):
        for bad in ({'daily_limit': 0}, {'daily_limit': 2.5}, {'daily_limit': True}, {'post_windows': [[14, 11]]}, {'post_windows': [[0, 25]]},
                    {'min_views': {'evil': 1}}, {'target': 'a b'}, {'audio_confidence': 2}, {'timezone': 'x'}, {'hb_discovery': {}}, {'voice': '../x'}):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.s.update_settings(bad)

    def test_processing_needs_key(self):
        with self.assertRaises(ValueError):
            self.s.update_settings({'processing_enabled': True})
        (Path(self.tmp.name) / 'gemini.key').write_text('x' * 30)
        self.s.update_settings({'processing_enabled': True})
        self.assertTrue(self.s.settings()['processing_enabled'])


class WindowTests(Base):
    def test_window_state(self):
        self.assertEqual(self.s.window_state(now=at(12)), (True, ''))
        self.assertEqual(self.s.window_state(now=at(19, 30)), (True, ''))
        self.assertEqual(self.s.window_state(now=at(15)), (False, '19:00 hôm nay'))
        self.assertEqual(self.s.window_state(now=at(23, 30)), (False, '11:00 ngày mai'))
        self.assertEqual(self.s.window_state(now=at(3)), (False, '11:00 hôm nay'))

    def test_claim_respects_window(self):
        self.job('a', 'ready', output_file='/data/a.mp4', output_hash='h')
        self.s.update_settings({'publisher_enabled': True, 'min_publish_gap': 0})
        self.assertEqual(self.s.publish_claim(now=at(15))['status'], 'wait')
        self.assertEqual(self.s.publish_claim(now=at(20))['status'], 'claimed')

    def test_best_score_first(self):
        self.job('low', 'ready', output_file='/d/l.mp4', output_hash='h', meta=json.dumps({'score': 10}), first_seen=1)
        self.job('high', 'ready', output_file='/d/h.mp4', output_hash='h', meta=json.dumps({'score': 999}), first_seen=2)
        self.s.update_settings({'publisher_enabled': True})
        self.assertEqual(self.s.publish_claim(now=at(20))['id'], 'high')


class ApprovalTests(Base):
    def test_approve_and_reject(self):
        self.job('a', 'awaiting_approval')
        self.job('b', 'awaiting_approval')
        self.s.decide('a', 'approve')
        self.s.decide('b', 'reject')
        states = {j['id']: j['state'] for j in self.s.status()['jobs']}
        self.assertEqual(states, {'a': 'ready', 'b': 'rejected'})

    def test_needs_review_requires_source_and_reprocesses_leniently(self):
        src = Path(self.tmp.name) / 'inbox' / 's.mp4'
        src.write_bytes(b'x')
        self.job('a', 'needs_review', source_file=str(src))
        self.job('gone', 'needs_review', source_file='/nope.mp4')
        with self.assertRaises(ValueError):
            self.s.decide('gone', 'approve')
        self.s.decide('a', 'approve')
        row = [j for j in self.s.status()['jobs'] if j['id'] == 'a'][0]
        self.assertEqual(row['state'], 'queued')
        self.assertEqual(self.s.claim()['approved'], 1)

    def test_cannot_approve_published(self):
        self.job('p', 'published')
        with self.assertRaises(ValueError):
            self.s.decide('p', 'approve')
        with self.assertRaises(ValueError):
            self.s.decide('p', 'reject')

    def test_lenient_waives_only_judgement_checks(self):
        a = {'kind': 'dialogue', 'confidence': 0.5, 'topic': 'other', 'sensitive': True,
             'segments': [{'start': 0, 'end': 2, 'vi': 'xin chào'}]}
        with self.assertRaises(ValueError):
            core.validate_analysis(a, 10, strict=True)
        self.assertEqual(core.validate_analysis(a, 10, strict=True, lenient=True), 'vietsub')
        bad = dict(a, segments=[{'start': 5, 'end': 6, 'vi': ''}])
        with self.assertRaises(ValueError):
            core.validate_analysis(bad, 10, strict=True, lenient=True)     # structural checks (empty translation) still apply
        junk = dict(a, segments=[{'start': 'x', 'end': 6, 'vi': 'y'}])
        with self.assertRaises(ValueError):
            core.validate_analysis(junk, 10, strict=True, lenient=True)

    def test_finish_awaiting_approval_state(self):
        self.job('q', 'queued', source_file='/x')
        job = self.s.claim()
        self.s.finish('q', job['lease'], 'awaiting_approval', reason='ok')
        self.assertEqual([j['state'] for j in self.s.status()['jobs']], ['awaiting_approval'])


class ChallengeTests(Base):
    def test_challenge_pauses_publishing_until_cleared(self):
        self.job('a', 'ready', output_file='/d/a.mp4', output_hash='h')
        self.s.update_settings({'publisher_enabled': True, 'post_windows': []})
        sent = []
        self.s.notifier = lambda kind, text, key: sent.append((kind, text))
        self.s.set_challenge(True)
        r = self.s.publish_claim()
        self.assertEqual(r['status'], 'blocked')
        self.assertIn('trust', r['reason'])
        self.assertTrue(self.s.status()['publisher_challenge'])
        self.assertTrue(any(k == 'urgent' and 'CAPTCHA' in m for k, m in sent))
        self.s.set_challenge(False)
        self.assertEqual(self.s.publish_claim()['status'], 'claimed')

    def test_dashboard_shows_the_challenge_and_counts_it(self):
        self.s.set_challenge(True)
        d = self.s.dashboard_data()
        d['notify_channels'] = []
        d['voice_sample'] = False
        html = ui.render(d, 'T')
        self.assertIn('yêu cầu xác minh', html)
        self.assertIn('./trendvn tiktok trust', html)

    def test_publisher_recognises_challenge_text(self):
        import publisher

        class Page:
            def __init__(self, text, sel=0):
                self.text, self.sel = text, sel

            def locator(self, s):
                outer = self
                return type('L', (), {'count': lambda self: outer.sel})()

            def inner_text(self, *a, **k):
                return self.text
        self.assertTrue(publisher.has_challenge(Page('Chọn 2 đối tượng có hình dạng giống nhau')))
        self.assertTrue(publisher.has_challenge(Page('bất kỳ', sel=1)))
        self.assertFalse(publisher.has_challenge(Page('Tải video lên')))


class FeedbackTests(Base):
    def published(self, jid, platform, vid, views, age_days=3):
        self.job(jid, 'published', platform=platform, publish_url='https://www.tiktok.com/@u/video/%s' % vid, published_at=time.time() - age_days * 86400)
        self.s.record_stats([{'video_id': vid, 'views': views, 'likes': views // 10}])

    def test_stats_matched_by_video_id(self):
        self.published('a', 'douyin', '7690000000000000001', 500)
        r = self.s.record_stats([{'video_id': '7690000000000000001', 'views': 900}, {'video_id': '7699999999999999999', 'views': 1}, {'video_id': 'zz', 'views': 1}])
        self.assertEqual(r['matched'], 1)
        self.assertEqual(self.s.performance()[0]['views'], 900)

    def test_weights_need_evidence_then_move(self):
        self.assertEqual(self.s.platform_weights(), {p: 1.0 for p in core.PLATFORMS})
        for i in range(4):
            self.published('d%d' % i, 'douyin', '76900000000000%05d' % i, 10000)
        for i in range(4):
            self.published('k%d' % i, 'kuaishou', '76910000000000%05d' % i, 1000)
        w = self.s.platform_weights()
        self.assertGreater(w['douyin'], 1.0)
        self.assertLess(w['kuaishou'], 1.0)
        self.assertEqual(w['tiktok'], 1.0)
        self.assertTrue(0.6 <= w['kuaishou'] <= w['douyin'] <= 1.5)


class NotifyTests(Base):
    def test_validation(self):
        for bad in ({'webhook': 'http://example.com/x'}, {'webhook': 'https://127.0.0.1/x'}, {'ntfy': 'https://192.168.1.5/t'}, {'webhook': 'https://localhost/x'},
                    {'telegram_token': 'abc', 'telegram_chat': '123456'}, {'telegram_token': '123456789:' + 'A' * 35, 'telegram_chat': 'x y'}):
            with self.assertRaises(ValueError, msg=str(bad)):
                notify.validate(bad)
        ok = notify.validate({'webhook': 'https://discord.com/api/webhooks/1/a', 'telegram_token': '123456789:' + 'A' * 35, 'telegram_chat': '-100123456'})
        self.assertEqual(notify.channels(ok), ['Telegram', 'Webhook (Discord/Slack)'])

    def test_config_file_is_private_and_never_returned(self):
        notify.save_config(self.tmp.name, {'ntfy': 'https://ntfy.sh/private-topic-xyz'})
        f = Path(self.tmp.name) / 'notify.json'
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('private-topic-xyz', json.dumps(self.s.status()))

    def test_throttle_and_emit_hooks(self):
        sent = []
        real_send, real_load = notify.send, notify.load_config
        notify.send = lambda cfg, text: sent.append(text) or {'x': True}
        notify.load_config = lambda root: {'ntfy': 'https://ntfy.sh/t'}
        try:
            self.s.notifier = notify.Notifier(self.s)
            self.s.emit('component', 'a', 'discovery')
            self.s.emit('component', 'a', 'discovery')      # throttled
            self.s.emit('review', 'r1', 'j1')
            self.s.emit('review', 'r1', 'j1')               # review is never throttled
            self.assertEqual(len(sent), 3)
            self.job('q', 'queued', source_file='/x', title='Video X')
            job = self.s.claim()
            self.s.finish('q', job['lease'], 'needs_review', reason='Off-topic')
            self.assertTrue(any('Cần bạn duyệt' in m and 'Video X' in m for m in sent))
        finally:
            notify.send, notify.load_config = real_send, real_load

    def test_notifier_failure_never_breaks_queue(self):
        def boom(kind, text, key):
            raise RuntimeError('network down')
        self.s.notifier = boom
        self.s.heartbeat('publisher', False, 'x')       # must not raise


class UiTests(Base):
    def render(self):
        d = self.s.dashboard_data()
        d['notify_channels'] = []
        d['voice_sample'] = False
        return ui.render(d, 'CSRFTOKEN', ('ok', 'Đã lưu'))

    def test_empty_dashboard_renders(self):
        html = self.render()
        self.assertIn('TrendVN', html)
        self.assertIn('CSRFTOKEN', html)

    def test_html_is_escaped(self):
        evil = '<script>alert(1)</script>'
        self.job('e', 'awaiting_approval', title=evil, reason=evil, route='vietsub')
        self.job('f', 'published', title=evil, publish_url='https://www.tiktok.com/@u/video/7690000000000000009', published_at=time.time())
        self.job('g', 'needs_review', title=evil, reason='<img src=x onerror=1>', source_file='/x')
        html = self.render()
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('<img src=x', html)

    def test_reason_translation_and_labels(self):
        self.assertIn('nhạy cảm', ui.vi_reason('Sensitive content (politics) needs review'))
        self.assertEqual(ui.vi_reason('unknown reason'), 'unknown reason')
        self.assertEqual(ui.ago(None), '—')
        self.assertEqual(ui.num(1234567), '1.234.567')

    def test_server_settings_patch_roundtrip(self):
        import os
        os.environ['TRENDVN_DATA'] = self.tmp.name
        os.environ['TRENDVN_TOKEN'] = 'x' * 40
        import importlib.util
        spec = importlib.util.spec_from_file_location('worker_server', ROOT / 'services' / 'worker' / 'app' / 'server.py')
        server_stub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server_stub)
        patch = server_stub.settings_patch({'daily_limit': ['3'], 'gap_hours': ['2.5'], 'post_windows': ['11-14, 19-23'], 'views_tiktok': ['2000000'],
                                            'views_douyin': ['0'], 'views_kuaishou': ['5'], 'views_instagram': ['0'], 'likes_douyin': ['100'],
                                            'processing_enabled': ['false'], 'require_approval': ['true']})
        self.assertEqual(patch['min_publish_gap'], 9000)
        self.assertEqual(patch['post_windows'], [[11, 14], [19, 23]])
        self.s.update_settings(patch)
        with self.assertRaises(ValueError):
            server_stub.parse_windows('abc')


class ScoringTests(unittest.TestCase):
    def test_fresh_beats_stale_and_weight_applies(self):
        now = time.time()
        fresh = {'views': 2_000_000, 'created': now - 10 * 3600}
        stale = {'views': 2_000_000, 'created': now - 100 * 3600}
        self.assertGreater(c.score('tiktok', fresh, None, now), 2 * c.score('tiktok', stale, None, now))
        self.assertGreater(c.score('tiktok', fresh, {'tiktok': 1.5}, now), c.score('tiktok', fresh, {'tiktok': 1.0}, now))

    def test_age_gate(self):
        now = time.time()
        th = {'max_age_days': 7, 'min_views': {'tiktok': 1}}
        self.assertTrue(c.qualifies('tiktok', {'views': 5, 'duration': 20, 'created': now - 3 * 86400}, th, now))
        self.assertFalse(c.qualifies('tiktok', {'views': 5, 'duration': 20, 'created': now - 9 * 86400}, th, now))
        self.assertTrue(c.qualifies('tiktok', {'views': 5, 'duration': 20, 'created': None}, th, now))   # unknown age is not held against it

    def test_parsers_carry_creation_time(self):
        d = c.parse_douyin({'aweme_list': [{'aweme_id': '1', 'aweme_type': 0, 'create_time': 1700000000, 'duration': 5000, 'statistics': {'digg_count': 1},
                                            'video': {'play_addr': {'url_list': ['https://a.zjcdn.com/x']}}}]})
        self.assertEqual(d[0]['created'], 1700000000)
        k = c.parse_kuaishou({'data': {'brilliantTypeData': {'feeds': [{'photo': {'id': 'abc', 'photoUrl': 'https://x', 'timestamp': 1700000000123, 'duration': 5000}}]}}})
        self.assertEqual(k[0]['created'], 1700000000)


class GeminiResilienceTests(Base):
    """Regression tests for problems found by calling the real Gemini API."""

    def setUp(self):
        super().setUp()
        (Path(self.tmp.name) / 'gemini.key').write_text('x' * 30)
        import media
        self.media = media
        self.real_gemini, self.real_sleep = media.gemini, media.time.sleep
        media.time.sleep = lambda s: None

    def tearDown(self):
        self.media.gemini, self.media.time.sleep = self.real_gemini, self.real_sleep
        super().tearDown()

    def test_retired_model_in_settings_is_upgraded(self):
        with self.s.transaction() as db:
            db.execute("UPDATE settings SET value='\"gemini-2.5-flash\"' WHERE key='model'")
            db.execute("UPDATE settings SET value='\"gemini-2.5-flash-preview-tts\"' WHERE key='tts_model'")
        cfg = core.Store(self.tmp.name).settings()
        self.assertEqual((cfg['model'], cfg['tts_model']), (core.DEFAULTS['model'], core.DEFAULTS['tts_model']))

    def test_404_falls_back_and_remembers_working_model(self):
        calls = []

        def fake(store, model, body):
            calls.append(model)
            if model != 'gemini-flash-latest':
                raise ValueError('Gemini HTTP 404 (%s): no longer available to new users' % model)
            return {'ok': model}
        self.media.gemini = fake
        cfg = self.s.settings()
        r = self.media.generate(self.s, cfg, [{'text': 'x'}])
        self.assertEqual(r, {'ok': 'gemini-flash-latest'})
        self.assertEqual(self.s.settings()['model'], 'gemini-flash-latest')     # next call goes straight to it
        calls.clear()
        self.media.generate(self.s, self.s.settings(), [{'text': 'x'}])
        self.assertEqual(calls, ['gemini-flash-latest'])

    def test_overload_retries_then_requeues_instead_of_breaking_the_job(self):
        self.media.gemini = lambda store, model, body: (_ for _ in ()).throw(ValueError('Gemini HTTP 503 (%s): high demand' % model))
        with self.assertRaises(self.media.Transient):
            self.media.generate(self.s, self.s.settings(), [{'text': 'x'}])
        self.assertTrue(issubclass(self.media.Transient, self.media.RateLimited))   # process_one re-queues RateLimited

    def test_overload_recovers_on_second_round(self):
        state = {'n': 0}

        def flaky(store, model, body):
            state['n'] += 1
            if state['n'] <= len(core.MODEL_FALLBACKS):
                raise ValueError('Gemini HTTP 503 (%s): high demand' % model)
            return {'ok': True}
        self.media.gemini = flaky
        self.assertEqual(self.media.generate(self.s, self.s.settings(), [{'text': 'x'}]), {'ok': True})

    def test_timeout_is_transient_and_not_counted(self):
        import urllib.request
        real = urllib.request.urlopen

        def hang(req, timeout=0):
            raise TimeoutError('read timed out')
        urllib.request.urlopen = hang
        try:
            self.media.gemini = self.real_gemini
            with self.assertRaises(ValueError) as cm:
                self.media.gemini(self.s, 'gemini-3.8-flash', {})
            self.assertIn('HTTP 504', str(cm.exception))
            with self.s.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM api_calls').fetchone()[0], 0)
        finally:
            urllib.request.urlopen = real

    def test_total_time_budget_is_respected(self):
        real_time = self.media.time.time
        clock = {'now': 1000.0}
        self.media.time.time = lambda: clock['now']
        calls = []

        def slow(store, model, body):
            calls.append(model)
            clock['now'] += 100          # every attempt burns 100 s
            raise ValueError('Gemini HTTP 504 (%s): no response in time' % model)
        self.media.gemini = slow
        try:
            with self.assertRaises(self.media.Transient):
                self.media.generate(self.s, self.s.settings(), [{'text': 'x'}])
        finally:
            self.media.time.time = real_time
        self.assertLessEqual(len(calls), 4)      # the 240 s budget stops the retry loop long before rounds x models

    def test_other_errors_are_not_swallowed(self):
        self.media.gemini = lambda store, model, body: (_ for _ in ()).throw(ValueError('Gemini HTTP 401 (x): bad key'))
        with self.assertRaises(ValueError):
            self.media.generate(self.s, self.s.settings(), [{'text': 'x'}])

    def test_rejected_requests_do_not_use_the_daily_allowance(self):
        import io
        import urllib.error
        import urllib.request
        real = urllib.request.urlopen

        def reject(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 404, 'nf', {}, io.BytesIO(b'{"error":{"message":"gone"}}'))
        urllib.request.urlopen = reject
        try:
            self.media.gemini = self.real_gemini
            with self.assertRaises(ValueError) as cm:
                self.media.gemini(self.s, 'gemini-3.8-flash', {})
            self.assertIn('gone', str(cm.exception))
            with self.s.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM api_calls').fetchone()[0], 0)
        finally:
            urllib.request.urlopen = real

    def test_tts_accepts_wav_pcm_and_reports_duration(self):
        import base64
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(b'\x00\x00' * 48000)
        wav = buf.getvalue()
        out = Path(self.tmp.name) / 'v.wav'
        for mime, payload in (('audio/wav', wav), ('audio/L16;codec=pcm;rate=24000', b'\x00\x00' * 48000)):
            self.media.gemini = lambda store, model, body, m=mime, p=payload: {'candidates': [{'content': {'parts': [
                {'inlineData': {'mimeType': m, 'data': base64.b64encode(p).decode()}}]}}]}
            self.assertAlmostEqual(self.media.tts(self.s, self.s.settings(), 'Xin chào', out), 2.0, places=2)


class VersionTests(unittest.TestCase):
    def test_single_version_everywhere(self):
        import version
        self.assertEqual(version.VERSION, (ROOT / 'VERSION').read_text().strip())
        self.assertIn('## %s ' % version.VERSION, (ROOT / 'CHANGELOG.md').read_text())


class PromptTests(unittest.TestCase):
    def test_schema_matches_validator(self):
        props = prompts.ANALYSIS_SCHEMA['properties']
        self.assertEqual(set(props['kind']['enum']), {'music', 'dialogue', 'narration', 'mixed', 'silent', 'uncertain'})
        self.assertEqual(set(props['topic']['enum']), {'entertainment', 'music', 'other'})
        for key in prompts.ANALYSIS_SCHEMA['required']:
            self.assertIn(key, props)
        for word in ('UNTRUSTED', 'segments', 'hashtags', 'sensitive', 'narration_vi', 'caption_vi'):
            self.assertIn(word, prompts.ANALYSIS_PROMPT)
        self.assertRegex(prompts.PROMPT_VERSION, r'^\d{4}-\d\d-\d\d\.\d+$')


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg/ffprobe not installed (runs inside the worker image)')
class VoiceoverTests(Base):
    def test_mix_and_subtitle_render(self):
        import subprocess
        import media
        folder = Path(self.tmp.name) / 'jobs' / 'j'
        folder.mkdir(parents=True)
        src = folder / 'src.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=360x640:d=8:r=15', '-f', 'lavfi', '-i', 'sine=frequency=300:duration=8',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(src)], check=True)
        analysis = {'kind': 'narration', 'confidence': .95, 'topic': 'entertainment', 'sensitive': False, 'narration_vi': 'Xin chào các bạn',
                    'segments': [{'start': 1.0, 'end': 5.0, 'vi': 'Xin chào các bạn'}]}

        def fake_tts(store, cfg, text, out):
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=600:duration=4.4', str(out)], check=True)
            return 4.4
        real = media.tts
        media.tts = fake_tts
        try:
            voice = media.make_voice(self.s, self.s.settings(), analysis, folder)
            self.assertAlmostEqual(voice['tempo'], 1.1, places=2)
            self.assertEqual(voice['delay'], 1.0)
            out = media.render(src, folder, analysis, 'voiceover', 8.0, voice)
            dur, meta = media.probe(out)
            self.assertAlmostEqual(dur, 8.0, delta=0.6)
            self.assertTrue(any(s['codec_type'] == 'audio' for s in meta['streams']))
            media.tts = lambda *a: 20.0                      # voice far longer than the speech window: refuse, subtitles remain
            with self.assertRaises(media.VoiceoverUnfit):
                media.make_voice(self.s, self.s.settings(), analysis, folder)
        finally:
            media.tts = real


if __name__ == '__main__':
    unittest.main()
