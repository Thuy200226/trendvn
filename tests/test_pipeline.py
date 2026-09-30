"""Discovery parsers, engagement gates, publishing queue safety and topic/sensitivity checks."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'worker' / 'app'))
sys.path.insert(0, str(ROOT / 'services' / 'agent'))
from core import Store, build_caption, validate_analysis
import collector as c

TH = {'min_views': {'kuaishou': 1000000, 'tiktok': 1000000}, 'min_likes': {'douyin': 150000}, 'max_duration': 180}


class ParserTests(unittest.TestCase):
    def test_douyin_keeps_only_real_videos(self):
        video = {'aweme_id': '123456', 'aweme_type': 0, 'desc': 'hi', 'duration': 30000, 'statistics': {'digg_count': 200000},
                 'video': {'play_addr': {'url_list': ['http://v5.zjcdn.com/a.mp4']}}}
        payload = {'aweme_list': [video, dict(video, aweme_id='9', aweme_type=68), dict(video, aweme_id='8', is_ads=True),
                                  {'aweme_id': '7', 'aweme_type': 101}, dict(video, aweme_id='6', statistics={})]}
        items = c.parse_douyin(payload)
        self.assertEqual([i['source_id'] for i in items], ['123456'])
        self.assertTrue(items[0]['media']['url'].startswith('https://'))
        self.assertEqual(items[0]['url'], 'https://www.douyin.com/video/123456')

    def test_kuaishou_feed(self):
        feed = {'photo': {'id': '3xabc', 'caption': 'c', 'viewCount': '2000000', 'realLikeCount': 5, 'duration': 20000,
                          'photoUrl': 'https://v.kwaicdn.com/x.mp4'}}
        items = c.parse_kuaishou({'data': {'brilliantTypeData': {'feeds': [feed, {'photo': {'id': 'x/../y', 'photoUrl': 'u'}}, {}]}}})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['views'], 2000000)
        self.assertEqual(items[0]['duration'], 20.0)

    def test_tiktok_skips_ads_and_bad_ids(self):
        good = {'id': '7688988035727363348', 'desc': 'd', 'author': {'uniqueId': 'user.one'}, 'stats': {'playCount': 4400000, 'diggCount': 1},
                'video': {'duration': 13, 'playAddr': 'https://v16.tiktok.com/v.mp4'}}
        items = c.parse_tiktok({'itemList': [good, dict(good, isAd=True), dict(good, id='12'), dict(good, author={'uniqueId': 'a/b'})]})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['url'], 'https://www.tiktok.com/@user.one/video/7688988035727363348')

    def test_instagram_codes_deduplicated_in_order(self):
        text = '/reels/DdPgJ99Ps8d/ "code":"Ddz3t5_K43z" /reel/DdPgJ99Ps8d/ /reels/audio/ "code":"en_US"'
        self.assertEqual(c.parse_instagram_codes(text), ['DdPgJ99Ps8d', 'Ddz3t5_K43z'])  # locale tags are not reel codes


class GateTests(unittest.TestCase):
    def item(self, **kw):
        return dict({'duration': 30, 'views': 2000000, 'likes': 200000}, **kw)

    def test_long_video_rejected(self):
        self.assertFalse(c.qualifies('tiktok', self.item(duration=181), TH))

    def test_low_views_rejected(self):
        self.assertFalse(c.qualifies('kuaishou', self.item(views=999999), TH))

    def test_douyin_needs_likes(self):
        self.assertFalse(c.qualifies('douyin', self.item(views=None, likes=1000), TH))
        self.assertTrue(c.qualifies('douyin', self.item(views=None, likes=200000), TH))

    def test_unknown_views_rejected_where_required(self):
        self.assertFalse(c.qualifies('tiktok', self.item(views=None), TH))

    def test_instagram_unknown_duration_allowed(self):
        self.assertTrue(c.qualifies('instagram', {'duration': None, 'views': None, 'likes': 5}, TH))


class PublishQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ready(self, jid, first_seen=1):
        with self.s.transaction() as db:
            db.execute("INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,state,output_file,output_hash,analysis,route,updated) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (jid, 'douyin', jid, 'https://www.douyin.com/video/' + jid, 'CN', 'Tiêu đề', first_seen, 'ready',
                        '/data/jobs/%s/final.mp4' % jid, 'h', json.dumps({'kind': 'music', 'caption_vi': 'Bài hát hay'}), 'original', 1))

    def enable(self, **extra):
        with self.s.transaction() as db:
            db.execute("UPDATE settings SET value='true' WHERE key='publisher_enabled'")
            db.execute("UPDATE settings SET value='[]' WHERE key='post_windows'")   # tests run at any hour
            for k, v in extra.items():
                db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(v), k))

    def test_switch_off_by_default(self):
        self.ready('a')
        self.assertEqual(self.s.publish_claim()['status'], 'disabled')

    def test_claim_publish_and_daily_limit(self):
        for j in 'abc':
            self.ready(j)
        self.enable(min_publish_gap=0)
        first = self.s.publish_claim()
        self.assertEqual(first['status'], 'claimed')
        self.assertEqual(self.s.publish_claim()['status'], 'blocked')      # one in flight at a time
        self.s.publish_finish(first['id'], first['lease'], 'published', 'https://www.tiktok.com/@u/video/1')
        second = self.s.publish_claim()
        self.s.publish_finish(second['id'], second['lease'], 'published', 'https://www.tiktok.com/@u/video/2')
        self.assertEqual(self.s.publish_claim()['status'], 'limit')        # daily_limit is 2

    def test_gap_between_posts(self):
        self.ready('a'); self.ready('b')
        self.enable()
        first = self.s.publish_claim()
        self.s.publish_finish(first['id'], first['lease'], 'published', 'https://www.tiktok.com/@u/video/1')
        r = self.s.publish_claim()
        self.assertEqual(r['status'], 'wait')
        self.assertGreater(r['retry_after'], 3600)

    def test_unknown_outcome_blocks_and_never_requeues(self):
        self.ready('a'); self.ready('b')
        self.enable(min_publish_gap=0)
        c1 = self.s.publish_claim()
        self.s.publish_finish(c1['id'], c1['lease'], 'unknown', reason='clicked, unconfirmed')
        self.assertEqual(self.s.publish_claim()['status'], 'blocked')
        self.assertEqual(len(self.s.unresolved()), 1)
        self.s.resolve_unknown(c1['id'], 'published', 'https://www.tiktok.com/@u/video/9')
        self.assertEqual(self.s.publish_claim()['status'], 'claimed')

    def test_failed_before_post_returns_to_ready(self):
        self.ready('a')
        self.enable(min_publish_gap=0)
        c1 = self.s.publish_claim()
        self.s.publish_finish(c1['id'], c1['lease'], 'failed', reason='not logged in')
        self.assertEqual(self.s.publish_claim()['status'], 'idle')                      # cooling off for an hour, so one bad video cannot hammer TikTok
        self.assertEqual(self.s.publish_claim(now=time.time() + 4000)['status'], 'claimed')   # and is tried again afterwards

    def test_stale_lease_and_bad_url_rejected(self):
        self.ready('a')
        self.enable()
        c1 = self.s.publish_claim()
        with self.assertRaises(ValueError):
            self.s.publish_finish(c1['id'], 'wrong', 'published')
        with self.assertRaises(ValueError):
            self.s.publish_finish(c1['id'], c1['lease'], 'published', 'https://evil.example/x')

    def test_duplicate_outcome(self):
        self.ready('a')
        self.enable()
        c1 = self.s.publish_claim()
        self.s.publish_finish(c1['id'], c1['lease'], 'duplicate', reason='same caption')
        self.assertEqual(self.s.publish_claim()['status'], 'idle')

    def test_release_requeues_without_burning_an_attempt(self):
        now = time.time()
        b = lambda ts: {'platform': 'douyin', 'stream': 's', 'observed_at': ts, 'items': [
            {'source_id': '555', 'url': 'https://www.douyin.com/video/555', 'country': 'CN', 'title': 't', 'evidence_url': 'https://www.douyin.com/'}] if ts > now else []}
        self.s.ingest(b(now), now=now)
        jid = self.s.ingest(b(now + 1), now=now + 1)['candidates'][0]['id']
        (Path(self.tmp.name) / 'inbox' / 'r.mp4').write_bytes(b'fixture')
        self.s.attach(jid, 'r.mp4')
        job = self.s.claim()
        self.s.release(jid, job['lease'], 'rate limited')
        again = self.s.claim()
        self.assertEqual(again['id'], jid)
        self.assertEqual(again['attempts'], 0)   # value before this claim's increment
        with self.assertRaises(ValueError):
            self.s.release(jid, 'stale-lease', 'x')

    def test_peek_does_not_change_state(self):
        self.ready('a')
        self.assertEqual(self.s.publish_peek()['status'], 'ready')
        self.assertEqual(self.s.publish_peek()['status'], 'ready')

    def test_heartbeat_states(self):
        self.assertEqual(self.s.status()['discovery'], 'not_connected')
        self.s.heartbeat('discovery', True, {'douyin': 'ok'})
        self.assertEqual(self.s.status()['discovery'], 'connected')
        self.s.heartbeat('publisher', False, 'Chưa đăng nhập')
        self.assertEqual(self.s.status()['publisher'], 'error')
        with self.assertRaises(ValueError):
            self.s.heartbeat('other', True)

    def test_ingest_reports_candidates(self):
        now = time.time()
        batch = lambda ids, ts: {'platform': 'douyin', 'stream': 's', 'observed_at': ts, 'items': [
            {'source_id': i, 'url': 'https://www.douyin.com/video/' + i, 'country': 'CN', 'title': 't', 'rank': 1, 'evidence_url': 'https://www.douyin.com/'} for i in ids]}
        self.s.ingest(batch(['111'], now), now=now)
        r = self.s.ingest(batch(['111', '222'], now + 1), now=now + 1)
        self.assertEqual([x['source_id'] for x in r['candidates']], ['222'])
        self.assertEqual(self.s.candidates_without_media()[0]['source_id'], '222')


class SubtitleTests(unittest.TestCase):
    def test_long_sentence_is_split_not_rejected(self):
        from media import ass_subtitles
        seg = [{'start': 1.0, 'end': 9.0, 'vi': 'Đây là một câu rất dài ' * 8}, {'start': 9.5, 'end': 11.0, 'vi': 'Ngắn thôi'}]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'a.ass'
            ass_subtitles(seg, out, 720, 1280)
            events = [l for l in out.read_text(encoding='utf-8').splitlines() if l.startswith('Dialogue:')]
        self.assertGreater(len(events), 2)
        stamps = [(l.split(',')[1], l.split(',')[2]) for l in events]
        parse = lambda s: sum(float(x) * m for x, m in zip(s.split(':'), (3600, 60, 1)))
        for (a, b), (c, _) in zip(stamps, stamps[1:]):
            self.assertLessEqual(parse(a), parse(b))
            self.assertLessEqual(parse(b), parse(c) + 0.011)      # no overlap between consecutive captions
        for l in events:
            self.assertLessEqual(l.count('\\N'), 1)                # at most two lines per caption


class TopicTests(unittest.TestCase):
    def a(self, **kw):
        base = {'kind': 'music', 'confidence': .99, 'segments': [], 'topic': 'music', 'sensitive': False}
        return dict(base, **kw)

    def test_strict_requires_topic_fields(self):
        with self.assertRaises(ValueError):
            validate_analysis({'kind': 'music', 'confidence': .99, 'segments': []}, 10, strict=True)
        self.assertEqual(validate_analysis(self.a(), 10, strict=True), 'original')

    def test_off_topic_and_sensitive_held(self):
        with self.assertRaises(ValueError):
            validate_analysis(self.a(topic='other'), 10, strict=True)
        with self.assertRaises(ValueError):
            validate_analysis(self.a(sensitive=True), 10, strict=True)

    def test_caption_never_empty_and_bounded(self):
        cap = build_caption({'kind': 'dialogue', 'caption_vi': 'x' * 400}, 't')
        self.assertLessEqual(len(cap.split(' #')[0]), 150)
        self.assertTrue(build_caption({}, '#tag Tiêu đề gốc').startswith('Tiêu đề gốc #'))   # source hashtags are dropped, ours are appended


if __name__ == '__main__':
    unittest.main()
