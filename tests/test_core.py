import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services'/'worker'/'app'))
from core import Store,canonical_url,validate_analysis
from media import similar,subtitles

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name);self.now=time.time()
    def tearDown(self):self.tmp.cleanup()
    def batch(self,ids,ts=None):
        return {'platform':'douyin','stream':'hot_music','observed_at':ts or self.now,'items':[
          {'source_id':i,'url':'https://www.douyin.com/video/'+i,'country':'CN','title':'Video '+i,'rank':n+1,
           'views':1000,'evidence_url':'https://www.douyin.com/hot'} for n,i in enumerate(ids)]}
    def candidate(self,ids=('123',)):
        self.s.ingest(self.batch([]),now=self.now)
        return self.s.ingest(self.batch(ids,self.now+1),now=self.now+1)['candidate_ids']
    def test_baseline_not_new(self):
        result=self.s.ingest(self.batch(['123']),now=self.now)
        self.assertTrue(result['baseline']);self.assertEqual(result['candidate_ids'],[])
    def test_subsequent_new_only(self):
        self.s.ingest(self.batch(['123']),now=self.now)
        r=self.s.ingest(self.batch(['123','456'],self.now+1),now=self.now+1)
        self.assertEqual(r['existing'],1);self.assertEqual(len(r['candidate_ids']),1)
    def test_stale_scan_rejected(self):
        self.s.ingest(self.batch(['123']),now=self.now)
        with self.assertRaises(ValueError):self.s.ingest(self.batch(['456']),now=self.now)
    def test_batch_transaction_no_partial(self):
        b=self.batch(['123','456']);b['items'][1]['country']='US'
        with self.assertRaises(ValueError):self.s.ingest(b,now=self.now)
        self.assertEqual(self.s.status()['counts'],{})
    def test_fake_domain_blocked(self):
        for u in ['https://douyin.com.evil.test/video/123','https://x@douyin.com/video/123','http://douyin.com/video/123']:
            with self.assertRaises(ValueError):canonical_url('douyin',u)
    def test_encoded_short_link_blocked(self):
        with self.assertRaises(ValueError):canonical_url('tiktok','https://vm.tiktok.com/123')
    def test_file_hash_dedup(self):
        ids=self.candidate(('123','456'));p=Path(self.tmp.name)/'inbox'/'test.mp4';p.write_bytes(b'fixture only')
        self.assertEqual(self.s.attach(ids[0],'test.mp4')['state'],'queued')
        self.assertEqual(self.s.attach(ids[1],'test.mp4')['state'],'duplicate')
    def test_traversal_rejected(self):
        jid=self.candidate()[0]
        with self.assertRaises(ValueError):self.s.attach(jid,'../../secret')
    def test_atomic_claim(self):
        jid=self.candidate()[0];(Path(self.tmp.name)/'inbox'/'x.mp4').write_bytes(b'fixture')
        self.s.attach(jid,'x.mp4')
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:res=list(ex.map(lambda _:self.s.claim(),range(5)))
        self.assertEqual(sum(x is not None for x in res),1)
    def test_stale_lease_cannot_finish(self):
        jid=self.candidate()[0];(Path(self.tmp.name)/'inbox'/'x.mp4').write_bytes(b'fixture');self.s.attach(jid,'x.mp4');j=self.s.claim()
        with self.assertRaises(ValueError):self.s.finish(jid,'wrong','ready')
        self.s.finish(jid,j['lease'],'needs_review',reason='test')
    def test_crash_publish_does_not_requeue(self):
        jid=self.candidate()[0]
        with self.s.transaction() as db:db.execute("UPDATE jobs SET state='publishing',updated=? WHERE id=?",(time.time()-3000,jid))
        self.s.housekeeping()
        self.assertEqual(self.s.status()['jobs'][0]['state'],'publish_unknown');self.assertIsNone(self.s.claim())

class AudioTests(unittest.TestCase):
    def a(self,kind='dialogue'):
        return {'kind':kind,'confidence':0.99,'segments':[{'start':0,'end':2,'vi':'Xin chào Việt Nam!'}]}
    def test_music_route(self):self.assertEqual(validate_analysis({'kind':'music','confidence':.99,'segments':[]},10),'original')
    def test_mixed_route(self):self.assertEqual(validate_analysis(self.a('mixed'),10),'vietsub')
    def test_music_with_speech_rejected(self):
        with self.assertRaises(ValueError):validate_analysis(self.a('music'),10)
    def test_low_confidence_held(self):
        a=self.a();a['confidence']=.5
        with self.assertRaises(ValueError):validate_analysis(a,10)
    def test_segment_running_past_the_video_is_cut_not_rejected(self):
        a=self.a();validate_analysis(a,1)
        self.assertEqual(a['segments'][0]['end'],1)
    def test_mostly_outside_video_is_held(self):
        a=self.a();a['segments']=[{'start':50,'end':60,'vi':'x'},{'start':60,'end':70,'vi':'y'}]
        with self.assertRaises(ValueError):validate_analysis(a,10)
    def test_nan_held(self):
        a=self.a();a['confidence']=float('nan')
        with self.assertRaises(ValueError):validate_analysis(a,10)
    def test_visual_duplicate(self):
        self.assertTrue(similar(['0'*16]*5,['0'*15+'1']*5));self.assertFalse(similar(['0'*16]*5,['f'*16]*5))
    def test_subtitle_injection_sanitized(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'vi.srt';a=self.a();a['segments'][0]['vi']='<b>Xin</b> {\\pos(0,0)}\nchào'
            subtitles(a['segments'],p);s=p.read_text();self.assertNotIn('<b>',s);self.assertNotIn('{',s)

if __name__=='__main__':unittest.main(verbosity=2)
