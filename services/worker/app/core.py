"""TrendVN queue. No TikTok API, browser cookies, or prior-project access."""
import hashlib
import json
import math
import re
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PLATFORMS = {'douyin': ('douyin.com',), 'kuaishou': ('kuaishou.com',),
             'tiktok': ('tiktok.com',), 'instagram': ('instagram.com',)}
COUNTRIES = {'douyin': 'CN', 'kuaishou': 'CN', 'tiktok': 'US', 'instagram': 'US'}
DEFAULTS = {'target': 'user5706026522362', 'topics': ['entertainment', 'music'],
            'daily_limit': 2, 'timezone': 'Asia/Ho_Chi_Minh', 'max_duration': 180,
            'model': 'gemini-3.8-flash', 'tts_model': 'gemini-3.8-flash-tts',
            'voice': 'Kore', 'audio_confidence': 0.90, 'processing_enabled': False,
            'discovery_connected': False, 'publisher_connected': False,
            'publisher_enabled': False, 'min_publish_gap': 3 * 3600, 'max_candidates_per_scan': 3, 'max_backlog': 4,
            'min_views': {'douyin': 0, 'kuaishou': 1000000, 'tiktok': 1000000, 'instagram': 0},
            'min_likes': {'douyin': 150000},
            'post_windows': [[11, 14], [19, 23]], 'max_age_days': 7,
            'require_approval': False, 'voiceover_enabled': False, 'gemini_daily_limit': 12, 'publisher_challenge': False,
            'visibility': 'public'}
HEARTBEAT_MAX_AGE = 30 * 3600
# Google retires Gemini models on a rolling basis ("no longer available to new users"). Stored settings that name a retired
# model are upgraded automatically, and media.py falls back through these chains when a call returns 404.
RETIRED_MODELS = {'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'}
RETIRED_TTS = {'gemini-2.5-flash-preview-tts', 'gemini-2.5-pro-preview-tts'}
MODEL_FALLBACKS = ['gemini-3.8-flash', 'gemini-flash-latest', 'gemini-3.5-flash', 'gemini-3.7-flash']
TTS_FALLBACKS = ['gemini-3.8-flash-tts', 'gemini-3.1-flash-tts-preview', 'gemini-2.5-flash-preview-tts']
STATES = ('baseline', 'candidate', 'queued', 'processing', 'awaiting_approval', 'ready', 'publishing', 'published',
          'needs_review', 'publish_unknown', 'duplicate', 'failed', 'rejected')


def _int(v, lo, hi, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and not math.isfinite(v)) or v != int(v) or not lo <= v <= hi:
        raise ValueError('%s must be an integer between %s and %s' % (name, lo, hi))
    return int(v)


def validate_settings(patch):
    """Only these keys can be changed from the dashboard, each with a strict range."""
    if not isinstance(patch, dict): raise ValueError('Settings must be an object')
    out = {}
    for k, v in patch.items():
        if k in ('processing_enabled', 'publisher_enabled', 'require_approval', 'voiceover_enabled'):
            if not isinstance(v, bool): raise ValueError(k + ' must be true or false')
            out[k] = v
        elif k == 'daily_limit': out[k] = _int(v, 1, 10, k)
        elif k == 'gemini_daily_limit': out[k] = _int(v, 1, 500, k)
        elif k == 'min_publish_gap': out[k] = _int(v, 0, 24 * 3600, k)
        elif k == 'max_age_days': out[k] = _int(v, 1, 60, k)
        elif k == 'max_duration': out[k] = _int(v, 10, 600, k)
        elif k == 'max_candidates_per_scan': out[k] = _int(v, 1, 10, k)
        elif k == 'max_backlog': out[k] = _int(v, 1, 20, k)
        elif k == 'audio_confidence':
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.5 <= v <= 0.99: raise ValueError('audio_confidence must be 0.5-0.99')
            out[k] = float(v)
        elif k in ('min_views', 'min_likes'):
            if not isinstance(v, dict) or set(v) - set(PLATFORMS): raise ValueError(k + ' needs per-platform numbers')
            out[k] = {p: _int(n, 0, 10**10, k + '.' + p) for p, n in v.items()}
        elif k == 'post_windows':
            if not isinstance(v, list) or len(v) > 6: raise ValueError('post_windows: at most 6 windows')
            wins = []
            for w in v:
                if not isinstance(w, (list, tuple)) or len(w) != 2: raise ValueError('post_windows entries are [start, end]')
                s, e = _int(w[0], 0, 23, 'window start'), _int(w[1], 1, 24, 'window end')
                if s >= e: raise ValueError('window start must be before end')
                wins.append([s, e])
            out[k] = wins
        elif k == 'target':
            if not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9._]{2,40}', v.lstrip('@')): raise ValueError('Invalid TikTok username')
            out[k] = v.lstrip('@')
        elif k == 'visibility':
            if v not in ('public', 'friends', 'self'): raise ValueError('visibility must be public, friends or self')
            out[k] = v
        elif k in ('model', 'tts_model'):
            if not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9._-]{3,60}', v): raise ValueError('Invalid model name')
            out[k] = v
        elif k == 'voice':
            if not isinstance(v, str) or not re.fullmatch(r'[A-Za-z]{3,20}', v): raise ValueError('Invalid voice name')
            out[k] = v
        else:
            raise ValueError('Setting cannot be changed here: ' + str(k))
    return out

def canonical_url(platform, value):
    if platform not in PLATFORMS: raise ValueError('Unsupported platform')
    u = urlsplit(value)
    host = (u.hostname or '').lower()
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError('HTTPS source URL required')
    if not any(host == d or host.endswith('.' + d) for d in PLATFORMS[platform]):
        raise ValueError('Source domain does not match platform')
    if not u.path or u.path == '/': raise ValueError('A video URL is required')
    # Share redirects are not stable IDs; resolve in the collector before ingest.
    if host in ('vm.tiktok.com', 'vt.tiktok.com', 'v.douyin.com', 'v.kuaishou.com'):
        raise ValueError('Resolve short share link to canonical video URL first')
    return urlunsplit(('https', host, u.path.rstrip('/'), '', ''))

def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def normalize_segments(segments, duration):
    """Gemini's timestamps vary run to run: it can list unsorted or overlapping lines, and on long videos it sometimes keeps 'transcribing'
    past the end of the video. Repair what is repairable (sort, trim overlaps, cut at the video's length, drop lines that lie outside the
    video or are too short to read) and report how many lines were dropped. Structural garbage still raises."""
    items = []
    for s in segments:
        if not isinstance(s, dict): raise ValueError('Invalid segments')
        start, finish = s.get('start'), s.get('end')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, finish)):
            raise ValueError('Invalid subtitle time')
        items.append(dict(s, start=float(start), end=float(finish)))
    items.sort(key=lambda s: (s['start'], s['end']))
    out, outside = [], 0
    for s in items:
        start, finish = max(0.0, s['start']), min(s['end'], duration)
        if start >= duration - 0.3:
            outside += 1                      # beyond the end of the video: the signature of a model that kept inventing lines
            continue
        if finish - start < 0.25:
            continue                          # too short to read; harmless
        if out and start < out[-1]['end']:
            if start - out[-1]['start'] >= 0.3: out[-1]['end'] = round(start, 2)      # trim the earlier line
            else: start = out[-1]['end']                                              # or start the later one after it
            if finish - start < 0.25:
                continue
        s['start'], s['end'] = round(start, 2), round(finish, 2)
        out.append(s)
    if items and outside > len(items) / 2: raise ValueError('Subtitle timestamps unreliable (%d of %d lines outside the video)' % (outside, len(items)))
    return out


def validate_analysis(a, duration, confidence=0.90, strict=False, lenient=False):
    """lenient=True is a human approval: it waives confidence/topic/sensitivity, never the structural checks."""
    allowed = ('music', 'dialogue', 'narration', 'mixed', 'silent', 'uncertain')
    if not isinstance(a, dict) or a.get('kind') not in allowed:
        raise ValueError('Invalid audio classification')
    c = a.get('confidence')
    if isinstance(c, bool) or not isinstance(c, (float, int)) or not math.isfinite(c) or not 0 <= c <= 1:
        raise ValueError('Invalid confidence')
    if not lenient and (c < confidence or a['kind'] == 'uncertain'): raise ValueError('Audio needs review')
    if strict and not lenient and (a.get('topic') not in ('entertainment', 'music', 'other') or not isinstance(a.get('sensitive'), bool)):
        raise ValueError('Topic/sensitivity missing from analysis')
    if not lenient and a.get('sensitive') is True: raise ValueError('Sensitive content (politics, violence, tragedy, adult or medical claims) needs review')
    if not lenient and a.get('topic') == 'other': raise ValueError('Off-topic for an entertainment and music channel')
    segments = a.get('segments', [])
    if not isinstance(segments, list) or len(segments) > 500: raise ValueError('Invalid segments')
    segments = a['segments'] = normalize_segments(segments, duration) if segments else []
    end = 0
    for s in segments:
        start, finish = s.get('start'), s.get('end')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, finish)):
            raise ValueError('Invalid subtitle time')
        if not end <= start < finish <= duration + 0.1: raise ValueError('Subtitle timestamps outside video or overlap')
        if not isinstance(s.get('vi'), str) or not s['vi'].strip() or len(s['vi']) > 350:
            raise ValueError('Invalid translated segment')
        end = finish
    if a['kind'] in ('dialogue', 'narration', 'mixed') and not segments:
        raise ValueError('Speech detected without transcript')
    if a['kind'] == 'music' and segments: raise ValueError('Music-only classification conflicts with speech')
    if a['kind'] == 'uncertain': a = dict(a, kind='silent' if not segments else 'mixed')
    if a['kind'] in ('dialogue', 'mixed'): return 'vietsub'
    if a['kind'] == 'narration': return 'voiceover'
    if a.get('requires_text_translation') and not segments:
        raise ValueError('On-screen information requires translation')
    return 'vietsub' if segments else 'original'

class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.notifier = None   # callable(kind, text, key) set by the server; failures never affect the queue
        self.root.mkdir(parents=True, exist_ok=True)
        for p in ('inbox', 'jobs', 'exports'): (self.root / p).mkdir(exist_ok=True)
        self.db = self.root / 'trendvn.sqlite3'
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS streams (name TEXT PRIMARY KEY, last_scan REAL);
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, platform TEXT, source_id TEXT, url TEXT, country TEXT,
              title TEXT, first_seen REAL, last_seen REAL, state TEXT, reason TEXT,
              source_file TEXT, content_hash TEXT, fingerprint TEXT, duration REAL,
              analysis TEXT, route TEXT, output_file TEXT, output_hash TEXT,
              lease TEXT, attempts INTEGER DEFAULT 0, target TEXT, publish_url TEXT,
              updated REAL, UNIQUE(platform,source_id), UNIQUE(url));
            CREATE TABLE IF NOT EXISTS observations (
              job_id TEXT, stream TEXT, observed REAL, rank INTEGER, views INTEGER,
              evidence TEXT, PRIMARY KEY(job_id,stream,observed));
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, at REAL, job_id TEXT, event TEXT, detail TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS api_calls (at REAL, model TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS post_stats (job_id TEXT, at REAL, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER);
            CREATE TABLE IF NOT EXISTS notif_log (kind TEXT, key TEXT, at REAL);
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, kind TEXT, job_id TEXT, state TEXT, started REAL, finished REAL,
                                              steps TEXT, result TEXT, error TEXT);
            CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
            CREATE INDEX IF NOT EXISTS idx_jobs_ps ON jobs(platform,state);
            CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated);
            CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
            CREATE INDEX IF NOT EXISTS idx_stats_job ON post_stats(job_id,at);
            CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);
            ''')
            for col in ('published_at REAL','caption TEXT','publish_lease TEXT','approved INTEGER DEFAULT 0','meta TEXT','caption_user TEXT','output_info TEXT','prev_state TEXT','publish_fails INTEGER DEFAULT 0','last_publish_fail REAL'):
                if col.split()[0] not in {r[1] for r in db.execute('PRAGMA table_info(jobs)')}:
                    db.execute('ALTER TABLE jobs ADD COLUMN '+col)
            for k,v in DEFAULTS.items(): db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,json.dumps(v)))
            for key,retired in (('model',RETIRED_MODELS),('tts_model',RETIRED_TTS)):
                row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
                if row and json.loads(row[0]) in retired:
                    db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(DEFAULTS[key]),key))

    def connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally: db.close()

    def settings(self):
        with self.connect() as db: return {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}

    def event(self, db, jid, name, detail=''):
        db.execute('INSERT INTO events(at,job_id,event,detail) VALUES(?,?,?,?)', (time.time(),jid,name,detail[:1000]))

    def emit(self, kind, text, key=''):
        if self.notifier:
            try: self.notifier(kind, text, key)
            except Exception: pass

    def update_settings(self, patch):
        clean = validate_settings(patch)
        if clean.get('processing_enabled') and not (self.root / 'gemini.key').exists():
            raise ValueError('Gemini key is required to enable processing')
        with self.transaction() as db:
            for k, v in clean.items():
                if k in ('min_views', 'min_likes'):        # a partial form must never erase the other sources' thresholds
                    row = db.execute('SELECT value FROM settings WHERE key=?', (k,)).fetchone()
                    v = {**(json.loads(row['value']) if row else {}), **v}
                    clean[k] = v
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (k, json.dumps(v)))
            self.event(db, '', 'settings', ', '.join(sorted(clean)))
        return clean

    def local_now(self, now=None):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(now or time.time(), ZoneInfo(self.settings()['timezone']))

    def window_state(self, cfg=None, now=None):
        """(inside_window, human text of the next opening). No windows configured means any time."""
        cfg = cfg or self.settings()
        wins = cfg.get('post_windows') or []
        d = self.local_now(now)
        hour = d.hour + d.minute / 60
        if not wins: return True, ''
        if any(s <= hour < e for s, e in wins): return True, ''
        later = sorted(s for s, _ in wins if s > hour)
        nxt = later[0] if later else sorted(s for s, _ in wins)[0]
        return False, '%02d:00 %s' % (nxt, 'hôm nay' if later else 'ngày mai')

    def ingest(self, batch, now=None):
        now = now or time.time()
        if not isinstance(batch,dict) or not isinstance(batch.get('items'),list) or len(batch['items']) > 100:
            raise ValueError('Batch must have at most 100 items')
        platform = batch.get('platform')
        if platform not in PLATFORMS: raise ValueError('Unknown platform')
        stream = batch.get('stream','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',stream): raise ValueError('Invalid stream')
        stream = platform + ':' + stream
        observed = batch.get('observed_at')
        if isinstance(observed,bool) or not isinstance(observed,(int,float)) or not math.isfinite(observed):
            raise ValueError('observed_at must be Unix timestamp')
        if not now-86400 <= observed <= now+60: raise ValueError('Stale/future batch')
        prepared=[]
        for v in batch['items']:
            source_id = str(v.get('source_id',''))
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',source_id): raise ValueError('Invalid source_id')
            url = canonical_url(platform,v.get('url',''))
            if source_id not in urlsplit(url).path.split('/'): raise ValueError('source_id must match canonical video URL')
            if v.get('country') != COUNTRIES[platform]: raise ValueError('Wrong source country')
            rank = v.get('rank')
            if rank is not None and (type(rank) is not int or rank < 1): raise ValueError('Invalid rank')
            views = v.get('views')
            if views is not None and (type(views) is not int or views < 0): raise ValueError('Invalid views')
            evidence = v.get('evidence_url','')
            if not isinstance(evidence,str) or not evidence.startswith('https://'): raise ValueError('Evidence URL required')
            title = str(v.get('title',''))[:500]
            meta = v.get('meta') if isinstance(v.get('meta'), dict) else {}
            meta = {k: meta[k] for k in ('score','likes','views','age_h','created') if isinstance(meta.get(k), (int, float)) and not isinstance(meta.get(k), bool) and math.isfinite(meta[k])}
            prepared.append((source_id,url,rank,views,evidence,title,json.dumps(meta) if meta else None))
        result={'baseline':False,'new':0,'existing':0,'candidate_ids':[],'candidates':[]}
        with self.transaction() as db:
            scan=db.execute('SELECT * FROM streams WHERE name=?',(stream,)).fetchone()
            if scan and observed <= scan['last_scan']: raise ValueError('Scan already ingested or older than last scan')
            baseline = scan is None
            result['baseline']=baseline
            for source_id,url,rank,views,evidence,title,meta in prepared:
                row=db.execute('SELECT * FROM jobs WHERE platform=? AND source_id=?',(platform,source_id)).fetchone()
                if row:
                    jid=row['id']; result['existing']+=1
                    db.execute('UPDATE jobs SET last_seen=?,updated=?,meta=COALESCE(?,meta) WHERE id=?',(observed,now,meta,jid))
                else:
                    jid=uuid.uuid4().hex
                    state='baseline' if baseline else 'candidate'
                    db.execute('''INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated,meta)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(jid,platform,source_id,url,COUNTRIES[platform],title,observed,observed,state,
                               'Initial observation only' if baseline else 'New in monitored source; validate evidence before processing',now,meta))
                    result['new']+=1
                    if not baseline: result['candidate_ids'].append(jid);result['candidates'].append({'id':jid,'source_id':source_id})
                    self.event(db,jid,state)
                db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',(jid,stream,observed,rank,views,evidence))
            db.execute('INSERT OR REPLACE INTO streams VALUES(?,?)',(stream,observed))
        return result

    def attach(self,jid,filename):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,150}',filename): raise ValueError('Invalid file name')
        p=(self.root/'inbox'/filename).resolve()
        if p.parent != self.root/'inbox' or not p.is_file(): raise ValueError('Source file missing')
        digest=file_hash(p)
        with self.transaction() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if not row or row['state'] not in ('candidate','awaiting_media'): raise ValueError('Job not eligible for media')
            dup=db.execute('SELECT id FROM jobs WHERE content_hash=? AND id<>?',(digest,jid)).fetchone()
            state='duplicate' if dup else 'queued'
            db.execute('UPDATE jobs SET source_file=?,content_hash=?,state=?,reason=?,updated=? WHERE id=?',
                       (str(p),digest,state,'Duplicate of '+dup['id'] if dup else '',time.time(),jid))
            self.event(db,jid,state)
        return {'id':jid,'state':state}

    def claim(self):
        with self.transaction() as db:
            row=db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY first_seen LIMIT 1").fetchone()
            if not row:return None
            token=uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='processing',lease=?,attempts=attempts+1,updated=? WHERE id=?",(token,time.time(),row['id']))
            self.event(db,row['id'],'processing')
            return dict(row)|{'lease':token}

    def finish(self,jid,lease,state,**fields):
        if state not in ('ready','awaiting_approval','needs_review','failed','duplicate'): raise ValueError('Invalid processing terminal state')
        allowed={'reason','analysis','route','output_file','output_hash','fingerprint','duration','output_info'}
        if set(fields)-allowed: raise ValueError('Invalid fields')
        with self.transaction() as db:
            query='UPDATE jobs SET state=?,lease=NULL,updated=?'+''.join(', '+k+'=?' for k in fields)+" WHERE id=? AND lease=? AND state='processing'"
            changed=db.execute(query,[state,time.time(),*fields.values(),jid,lease]).rowcount
            if changed!=1: raise ValueError('Stale lease')
            self.event(db,jid,state,str(fields.get('reason','')))
            title=(db.execute('SELECT title FROM jobs WHERE id=?',(jid,)).fetchone() or ['?'])[0][:60]
        reason=str(fields.get('reason',''))
        if state=='needs_review': self.emit('review','⚠️ Cần bạn duyệt: %s\nLý do: %s'%(title,reason),jid)
        elif state=='awaiting_approval': self.emit('approval','🎬 Video đã dựng, chờ bạn duyệt đăng: %s'%title,jid)
        elif state=='failed': self.emit('error','❌ Xử lý thất bại: %s\n%s'%(title,reason),jid)

    def decide(self,jid,action):
        """Human decision from the dashboard. approve on needs_review re-runs processing with the checks waived."""
        if action not in ('approve','reject','retry'): raise ValueError('Invalid action')
        with self.transaction() as db:
            row=db.execute('SELECT state,source_file,output_file FROM jobs WHERE id=?',(jid,)).fetchone()
            if not row: raise ValueError('Job not found')
            now=time.time()
            if action=='retry':
                # a video parked after repeated posting failures: the rendered file is fine, so put it back in the list of postable videos
                if row['state']!='needs_review' or not row['output_file'] or not Path(row['output_file']).is_file(): raise ValueError('Video này chưa có bản dựng để đăng lại')
                db.execute("UPDATE jobs SET state='ready',publish_fails=0,last_publish_fail=NULL,reason='Bạn đưa về sẵn sàng đăng',updated=? WHERE id=?",(now,jid))
            elif action=='reject':
                if row['state'] not in ('awaiting_approval','needs_review','ready','candidate','queued'): raise ValueError('Job cannot be rejected in this state')
                db.execute("UPDATE jobs SET state='rejected',reason='Rejected by operator',updated=? WHERE id=?",(now,jid))
            elif row['state']=='awaiting_approval':
                db.execute("UPDATE jobs SET state='ready',reason='Approved by operator',updated=? WHERE id=?",(now,jid))
            elif row['state']=='needs_review':
                if not row['source_file'] or not Path(row['source_file']).is_file(): raise ValueError('Source file is gone; cannot reprocess')
                db.execute("UPDATE jobs SET state='queued',approved=1,publish_fails=0,last_publish_fail=NULL,reason='Approved by operator; reprocessing',updated=? WHERE id=?",(now,jid))
            else: raise ValueError('Nothing to approve in this state')
            self.event(db,jid,'operator_'+action)

    def release(self,jid,lease,reason):
        """Put a claimed job back in the queue untouched (e.g. rate limit); does not count as an attempt."""
        with self.transaction() as db:
            changed=db.execute("UPDATE jobs SET state='queued',lease=NULL,attempts=MAX(attempts-1,0),reason=?,updated=? WHERE id=? AND lease=? AND state='processing'",
                               (reason[:700],time.time(),jid,lease)).rowcount
            if changed!=1: raise ValueError('Stale lease')
            self.event(db,jid,'released',reason)

    def housekeeping(self):
        now=time.time()
        with self.transaction() as db:
            processing=db.execute("UPDATE jobs SET state='needs_review',reason='Processing interrupted; inspect before retry',lease=NULL WHERE state='processing' AND updated<?",(now-1800,)).rowcount
            unknown=db.execute("UPDATE jobs SET state='publish_unknown',reason='Publishing confirmation missing; never retry automatically' WHERE state='publishing' AND updated<?",(now-2700,)).rowcount
        if unknown: self.emit('urgent','🚨 Có %d bài đăng chưa xác nhận. Hệ thống đã dừng đăng để tránh trùng; mở bảng điều khiển để xác nhận.'%unknown,'unknown')
        return {'interrupted_processing':processing,'uncertain_publishing':unknown}

    def heartbeat(self, component, ok, detail=None):
        if component not in ('discovery', 'publisher'): raise ValueError('Unknown component')
        value = {'at': time.time(), 'ok': bool(ok), 'detail': detail if isinstance(detail, (dict, list, str)) else None}
        with self.transaction() as db:
            prev = db.execute('SELECT value FROM settings WHERE key=?', ('hb_' + component,)).fetchone()
            before = (json.loads(prev['value']).get('detail') if prev else None)
            if isinstance(value['detail'], dict) and isinstance(before, dict):
                value['detail'] = {**before, **value['detail']}   # a partial run must not erase what other sources last reported
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('hb_' + component, json.dumps(value, ensure_ascii=False)[:8000]))
        if not ok:
            names = {'discovery': 'Bộ thu thập', 'publisher': 'Trình đăng TikTok'}
            self.emit('component', '🔌 %s cần chú ý: %s' % (names[component], detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)[:300]), component)

    def component_state(self, component, cfg=None):
        cfg = cfg or self.settings()
        hb = cfg.get('hb_' + component)
        if not hb: return 'not_connected'
        if time.time() - hb['at'] > HEARTBEAT_MAX_AGE: return 'stale'
        return 'connected' if hb['ok'] else 'error'

    def day_start(self, now=None):
        """Start of the current local day in the configured timezone, as Unix seconds."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(self.settings()['timezone'])
        d = datetime.fromtimestamp(now or time.time(), tz)
        return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    def published_today(self, db=None, now=None):
        start = self.day_start(now)
        q = "SELECT count(*) FROM jobs WHERE state IN ('published','publishing','publish_unknown') AND COALESCE(published_at,updated)>=?"
        if db is not None: return db.execute(q, (start,)).fetchone()[0]
        with self.connect() as c: return c.execute(q, (start,)).fetchone()[0]

    def publish_claim(self, now=None, job_id=None):
        """Reserve a rendered video for publishing.
        Scheduled use (job_id=None): honours the switch, posting window, daily limit and spacing, and picks the best-scored video.
        Manual use (job_id given, from the dashboard button): the owner's click is the consent for that one video, so the switch,
        window, limit and spacing are waived; the safety rails that protect the account (one post in flight, unconfirmed posts,
        TikTok verification pause) still apply."""
        now = now or time.time()
        cfg = self.settings()
        manual = job_id is not None
        if not manual and not cfg['publisher_enabled']: return {'status': 'disabled', 'reason': 'Publishing switch is off'}
        if cfg.get('publisher_challenge'):
            return {'status': 'blocked', 'reason': 'TikTok is asking for human verification; solve it once with `./trendvn tiktok trust`'}
        with self.transaction() as db:
            if db.execute("SELECT count(*) FROM jobs WHERE state IN ('publishing','publish_unknown')").fetchone()[0]:
                return {'status': 'blocked', 'reason': 'A previous publish is unconfirmed; resolve it before publishing again'}
            if not manual:
                inside, nxt = self.window_state(cfg, now)
                if not inside:
                    return {'status': 'wait', 'reason': 'Ngoài giờ vàng; lần tới lúc ' + nxt, 'next_window': nxt}
                if self.published_today(db, now) >= cfg['daily_limit']:
                    return {'status': 'limit', 'reason': 'Daily limit reached'}
                last = db.execute("SELECT max(published_at) FROM jobs WHERE state='published'").fetchone()[0]
                if last and now - last < cfg['min_publish_gap']:
                    return {'status': 'wait', 'reason': 'Minimum gap between posts not reached', 'retry_after': int(last + cfg['min_publish_gap'] - now)}
                row = db.execute("SELECT * FROM jobs WHERE state='ready' AND output_file IS NOT NULL AND COALESCE(last_publish_fail,0)<? ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 1", (now - 3600,)).fetchone()
            else:
                row = db.execute("SELECT * FROM jobs WHERE id=? AND state IN ('ready','awaiting_approval') AND output_file IS NOT NULL", (job_id,)).fetchone()
                if not row: return {'status': 'idle', 'reason': 'Video này không còn ở trạng thái sẵn sàng đăng'}
            if not row: return {'status': 'idle', 'reason': 'No rendered video is waiting'}
            token = uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='publishing',publish_lease=?,prev_state=?,updated=? WHERE id=?", (token, row['state'], now, row['id']))
            self.event(db, row['id'], 'publishing', 'thủ công' if manual else '')
            a = json.loads(row['analysis']) if row['analysis'] else {}
            caption = row['caption_user'] or build_caption(a, row['title'])
            db.execute('UPDATE jobs SET caption=? WHERE id=?', (caption, row['id']))
            return {'status': 'claimed', 'id': row['id'], 'lease': token, 'caption': caption, 'route': row['route'], 'manual': manual,
                    'output_file': row['output_file'], 'output_hash': row['output_hash'], 'target': cfg['target'], 'visibility': cfg['visibility']}

    def publish_peek(self, job_id=None):
        """A rendered video for rehearsals (the next one, or a chosen one); changes nothing and ignores the publishing switch."""
        cfg = self.settings()
        with self.connect() as db:
            if job_id:
                row = db.execute("SELECT * FROM jobs WHERE id=? AND state IN ('ready','awaiting_approval') AND output_file IS NOT NULL", (job_id,)).fetchone()
            else:
                row = db.execute("SELECT * FROM jobs WHERE state='ready' AND output_file IS NOT NULL ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 1").fetchone()
        if not row: return {'status': 'idle', 'reason': 'No rendered video is waiting'}
        a = json.loads(row['analysis']) if row['analysis'] else {}
        return {'status': 'ready', 'id': row['id'], 'caption': row['caption_user'] or build_caption(a, row['title']), 'route': row['route'],
                'output_file': row['output_file'], 'output_hash': row['output_hash'], 'target': cfg['target'], 'visibility': cfg['visibility']}

    def set_caption(self, jid, caption):
        """Owner's edit of the caption/hashtags that will be posted. Validated, never silently altered."""
        caption = unicodedata.normalize('NFC', str(caption)).replace('\r\n', '\n').replace('\r', '\n')
        caption = '\n'.join(line.rstrip() for line in re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', caption).split('\n')).strip()
        if not caption: raise ValueError('Mô tả không được để trống')
        if len(caption) > 2200: raise ValueError('Mô tả quá dài (tối đa 2200 ký tự)')
        with self.transaction() as db:
            row = db.execute('SELECT state FROM jobs WHERE id=?', (jid,)).fetchone()
            if not row or row['state'] not in ('ready', 'awaiting_approval'): raise ValueError('Chỉ sửa được mô tả của video sẵn sàng đăng')
            cur = db.execute('SELECT caption_user,analysis,title FROM jobs WHERE id=?', (jid,)).fetchone()
            effective = cur['caption_user'] or build_caption(json.loads(cur['analysis'] or '{}'), cur['title'])
            if caption == effective: return                       # nothing changed: no event, no churn
            db.execute('UPDATE jobs SET caption_user=?,updated=? WHERE id=?', (caption, time.time(), jid))
            self.event(db, jid, 'caption_edited', caption[:200])

    def reset_caption(self, jid):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET caption_user=NULL,updated=? WHERE id=? AND state IN ('ready','awaiting_approval')", (time.time(), jid))

    def ready_list(self, limit=30):
        """Everything that has been rendered and can be posted, best first, with the caption that would be used and its quality check."""
        with self.connect() as db:
            rows = db.execute("""SELECT id,platform,title,state,route,meta,analysis,caption_user,output_info,duration,updated,first_seen
                FROM jobs WHERE state IN ('ready','awaiting_approval') AND output_file IS NOT NULL
                ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT ?""", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try: a = json.loads(d.pop('analysis') or '{}')
            except ValueError: a = {}
            try: d['caption'] = d['caption_user'] or build_caption(a, d['title'])
            except Exception: d['caption'] = d['caption_user'] or (d['title'] or '')[:110]
            d['caption_edited'] = bool(d['caption_user'])
            d['lint'] = lint_caption(d['caption'])
            d['kind'] = a.get('kind')
            d['info'] = json.loads(d['output_info'] or '{}')
            out.append(d)
        return out

    # ------------------------------------------------------------------ background tasks (dashboard buttons)
    def task_create(self, kind, job_id=None):
        tid = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", (tid, kind, job_id, 'running', time.time(), None, '[]', '', ''))
        return tid

    def task_update(self, tid, steps=None, state=None, result=None, error=None):
        with self.transaction() as db:
            sets, vals = [], []
            if steps is not None: sets.append('steps=?'); vals.append(json.dumps(steps, ensure_ascii=False))
            if state: sets.append('state=?'); vals.append(state); sets.append('finished=?'); vals.append(time.time() if state != 'running' else None)
            if result is not None: sets.append('result=?'); vals.append(result[:1500])
            if error is not None: sets.append('error=?'); vals.append(error[:800])
            if sets: db.execute('UPDATE tasks SET %s WHERE id=?' % ','.join(sets), (*vals, tid))

    def tasks_recent(self, limit=8):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY started DESC LIMIT ?', (limit,))]
        for r in rows: r['steps'] = json.loads(r['steps'] or '[]')
        return rows

    def tasks_running(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,kind,job_id,started FROM tasks WHERE state='running'")]

    def tasks_reap(self):
        """After a restart nothing is really running: mark leftovers as interrupted so the buttons become usable again."""
        with self.transaction() as db:
            db.execute("UPDATE tasks SET state='error',finished=?,error='Bị gián đoạn (worker khởi động lại)' WHERE state='running'", (time.time(),))
            db.execute('DELETE FROM tasks WHERE started<?', (time.time() - 14 * 86400,))

    def publish_finish(self, jid, lease, outcome, url='', reason=''):
        """outcome: published (confirmed on the account), failed (nothing was posted; counted), deferred (nothing was posted and it is
        not the video's fault, e.g. TikTok verification; not counted), unknown (may have posted), duplicate."""
        states = {'published': 'published', 'failed': 'ready', 'deferred': 'ready', 'unknown': 'publish_unknown', 'duplicate': 'duplicate'}
        if outcome not in states: raise ValueError('Invalid publish outcome')
        if url and not re.fullmatch(r'https://[A-Za-z0-9.-]+\.tiktok\.com/[^\s"<>]{1,300}', url): raise ValueError('Invalid publish URL')
        parked = False
        with self.transaction() as db:
            row = db.execute('SELECT attempts,publish_lease,state,prev_state,publish_fails FROM jobs WHERE id=?', (jid,)).fetchone()
            if not row or row['state'] != 'publishing' or row['publish_lease'] != lease: raise ValueError('Stale publish lease')
            now = time.time()
            state = states[outcome]
            fails, last_fail = row['publish_fails'] or 0, None
            if outcome in ('failed', 'deferred') and row['prev_state'] == 'awaiting_approval':
                state = 'awaiting_approval'                     # a failed manual click must not silently approve the video for the scheduler
            if outcome == 'failed':
                fails, last_fail = fails + 1, now
                if fails >= 3:
                    state, parked = 'needs_review', True          # a video that keeps failing stops blocking the queue
                    reason = 'Đăng thất bại %d lần liên tiếp, cần bạn xem: %s' % (fails, reason)
            db.execute("UPDATE jobs SET state=?,publish_lease=NULL,publish_url=?,reason=?,published_at=?,updated=?,publish_fails=?,last_publish_fail=COALESCE(?,last_publish_fail) WHERE id=?",
                       (state, url or None, reason[:700], now if outcome == 'published' else None, now, fails, last_fail, jid))
            self.event(db, jid, 'publish_' + outcome, reason)
            title = (db.execute('SELECT title FROM jobs WHERE id=?', (jid,)).fetchone() or ['?'])[0][:60]
        if outcome == 'published': self.emit('published', '✅ Đã đăng: %s\n%s' % (title, url), jid)
        elif outcome == 'unknown': self.emit('urgent', '🚨 Đã bấm Đăng nhưng chưa xác nhận được: %s\nHệ thống dừng đăng. %s' % (title, reason), jid)
        elif parked: self.emit('review', '⚠️ Video đăng lỗi nhiều lần, đã chuyển sang Cần xem: %s\n%s' % (title, reason), jid)
        elif outcome == 'failed': self.emit('publish_failed', '⚠️ Đăng chưa thành công (sẽ thử lại sau): %s' % reason, 'publish_failed')

    def set_challenge(self, active):
        """TikTok asked for human verification. Publishing pauses (no retries that would keep triggering it) until the owner clears it."""
        with self.transaction() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('publisher_challenge', json.dumps(bool(active))))
            self.event(db, '', 'challenge_on' if active else 'challenge_off', '')
        if active:
            self.emit('urgent', '🧩 TikTok đang yêu cầu xác minh (CAPTCHA). Đăng bài tạm dừng. Hãy giải một lần: chạy `./trendvn tiktok trust` (Mac: nhấp đúp macos/Xac-minh-TikTok.command).', 'challenge')

    def resolve_unknown(self, jid, outcome, url=''):
        """Operator/agent verified the account: mark an uncertain publish as published or as not posted."""
        if outcome not in ('published', 'failed'): raise ValueError('Invalid outcome')
        with self.transaction() as db:
            row = db.execute('SELECT state,prev_state FROM jobs WHERE id=?', (jid,)).fetchone()
            if not row or row['state'] != 'publish_unknown': raise ValueError('Job is not awaiting confirmation')
            now = time.time()
            back = 'awaiting_approval' if row['prev_state'] == 'awaiting_approval' else 'ready'
            db.execute('UPDATE jobs SET state=?,publish_url=?,published_at=?,reason=?,updated=? WHERE id=?',
                       ('published' if outcome == 'published' else back, url or None, now if outcome == 'published' else None,
                        'Confirmed by account check', now, jid))
            self.event(db, jid, 'resolved_' + outcome)

    def unresolved(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,title,caption,updated FROM jobs WHERE state='publish_unknown'")]

    def candidates_without_media(self, limit=20):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,platform,source_id,url,title FROM jobs WHERE state='candidate' ORDER BY first_seen DESC LIMIT ?", (limit,))]

    def mark_media_failed(self, jid, reason):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state=CASE WHEN attempts>=2 THEN 'failed' ELSE state END,attempts=attempts+1,reason=?,updated=? WHERE id=? AND state='candidate'",
                       (reason[:700], time.time(), jid))
            self.event(db, jid, 'media_failed', reason)

    # ------------------------------------------------------------------ feedback loop
    def record_stats(self, items):
        """Views/likes read from our own TikTok profile, matched to jobs by the video id in publish_url."""
        if not isinstance(items, list) or len(items) > 200: raise ValueError('items must be a list of at most 200')
        now, matched = time.time(), 0
        with self.transaction() as db:
            for it in items:
                vid = str(it.get('video_id', ''))
                if not re.fullmatch(r'\d{6,25}', vid): continue
                nums = []
                for k in ('views', 'likes', 'comments', 'shares'):
                    v = it.get(k, 0)
                    nums.append(v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10**12 else 0)
                row = db.execute("SELECT id FROM jobs WHERE state='published' AND publish_url LIKE ?", ('%/video/' + vid,)).fetchone()
                if row:
                    db.execute('INSERT INTO post_stats VALUES (?,?,?,?,?,?)', (row['id'], now, *nums))
                    matched += 1
        return {'matched': matched}

    def performance(self, limit=30):
        with self.connect() as db:
            rows = db.execute("""SELECT j.id,j.platform,j.title,j.route,j.publish_url,j.published_at,j.meta,
                (SELECT views FROM post_stats s WHERE s.job_id=j.id ORDER BY at DESC LIMIT 1) views,
                (SELECT likes FROM post_stats s WHERE s.job_id=j.id ORDER BY at DESC LIMIT 1) likes
                FROM jobs j WHERE j.state='published' ORDER BY j.published_at DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def platform_weights(self):
        """Nudge source priority toward platforms whose reposts actually performed. Needs evidence before it moves at all."""
        with self.connect() as db:
            rows = db.execute("""SELECT j.platform p,
                (SELECT views FROM post_stats s WHERE s.job_id=j.id ORDER BY at DESC LIMIT 1) v
                FROM jobs j WHERE j.state='published' AND j.published_at<? """, (time.time() - 24 * 3600,)).fetchall()
        data = [(r['p'], r['v']) for r in rows if r['v'] is not None]
        weights = {p: 1.0 for p in PLATFORMS}
        if len(data) < 8: return weights
        overall = sum(v for _, v in data) / len(data) or 1
        for p in PLATFORMS:
            vs = [v for q, v in data if q == p]
            if len(vs) >= 3: weights[p] = round(min(1.5, max(0.6, (sum(vs) / len(vs)) / overall)), 2)
        return weights

    # ------------------------------------------------------------------ reporting
    def recent_events(self, limit=40):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT e.at,e.event,e.detail,e.job_id,COALESCE(j.title,'') title,COALESCE(j.platform,'') platform
                FROM events e LEFT JOIN jobs j ON j.id=e.job_id WHERE e.event<>'baseline' ORDER BY e.id DESC LIMIT ?""", (limit,))]

    def summary_text(self, now=None):
        st = self.status()
        c = st['counts']
        best = [p for p in self.performance(10) if p['views']]
        best = max(best, key=lambda p: p['views'], default=None)
        lines = ['📊 TrendVN hôm nay: đã đăng %d/%d' % (st['published_today'], st['daily_limit']),
                 'Hàng chờ: %d chờ xử lý, %d đã dựng, %d chờ duyệt' % (c.get('queued', 0) + c.get('processing', 0), c.get('ready', 0), c.get('awaiting_approval', 0) + c.get('needs_review', 0))]
        if st['unresolved_publishes']: lines.append('🚨 %d bài đăng chưa xác nhận' % st['unresolved_publishes'])
        if st['discovery'] != 'connected': lines.append('🔌 Bộ thu thập: ' + st['discovery'])
        if st['publisher'] != 'connected': lines.append('🔌 Trình đăng: ' + st['publisher'])
        if best: lines.append('🏆 Bài tốt nhất gần đây: %s (%s lượt xem)' % (best['title'][:50], format(best['views'], ',')))
        return '\n'.join(lines)

    def dashboard_data(self):
        st = self.status()
        cfg = self.settings()
        inside, nxt = self.window_state(cfg)
        with self.connect() as db:
            def rows(states, n=30):
                q = ','.join('?' * len(states))
                return [dict(r) for r in db.execute("SELECT id,platform,title,state,reason,route,meta,url,updated,first_seen,duration,output_file FROM jobs WHERE state IN (%s) ORDER BY updated DESC LIMIT ?" % q, (*states, n))]
            by_platform = {}
            for r in db.execute("SELECT platform,state,count(*) n FROM jobs GROUP BY platform,state"):
                by_platform.setdefault(r['platform'], {})[r['state']] = r['n']
            cols = 'id,platform,title,state,reason,route,meta,url,updated,first_seen,duration'
            # the queue is shown in the order it will be processed: the one being processed first, then oldest first (see claim())
            queue = [dict(r) for r in db.execute("SELECT %s FROM jobs WHERE state IN ('processing','queued') ORDER BY (state='processing') DESC, first_seen LIMIT 30" % cols)]
            candidates = [dict(r) for r in db.execute("SELECT %s FROM jobs WHERE state='candidate' ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 20" % cols)]
        return dict(st, review=rows(('needs_review',)), approval=rows(('awaiting_approval',)), queue=queue, candidates=candidates,
                    pipeline=rows(('candidate', 'queued', 'processing', 'ready', 'publishing')),
                    performance=self.performance(30), unresolved=self.unresolved(), events=self.recent_events(40),
                    by_platform=by_platform, weights=self.platform_weights(), in_window=inside, next_window=nxt,
                    settings={k: cfg[k] for k in ('daily_limit', 'min_publish_gap', 'post_windows', 'max_age_days', 'max_duration',
                                                  'max_candidates_per_scan', 'max_backlog', 'min_views', 'min_likes', 'audio_confidence', 'gemini_daily_limit',
                                                  'require_approval', 'voiceover_enabled', 'target', 'voice', 'timezone', 'model', 'tts_model', 'visibility')})

    def status(self):
        with self.connect() as db:
            counts={r['state']:r['n'] for r in db.execute('SELECT state,count(*) n FROM jobs GROUP BY state')}
            jobs=[dict(r) for r in db.execute('SELECT id,platform,title,state,reason,route,publish_url,updated FROM jobs ORDER BY updated DESC LIMIT 100')]
            streams=[dict(r) for r in db.execute('SELECT * FROM streams')]
        cfg=self.settings()
        discovery=self.component_state('discovery',cfg);publisher=self.component_state('publisher',cfg)
        return {'project':'TrendVN','target':cfg['target'],'counts':counts,'jobs':jobs,'streams':streams,
                'processing_enabled':cfg['processing_enabled'],'publisher_enabled':cfg['publisher_enabled'],
                'daily_limit':cfg['daily_limit'],'published_today':self.published_today(),
                'discovery':discovery,'publisher':publisher,'discovery_at':(cfg.get('hb_discovery') or {}).get('at'),'publisher_at':(cfg.get('hb_publisher') or {}).get('at'),
                'discovery_detail':(cfg.get('hb_discovery') or {}).get('detail'),
                'publisher_detail':(cfg.get('hb_publisher') or {}).get('detail'),
                'gemini_configured':(self.root/'gemini.key').exists(),
                'unresolved_publishes':len(self.unresolved()),
                'thresholds':{k:cfg[k] for k in ('min_views','min_likes','max_duration','max_candidates_per_scan','max_backlog','max_age_days')},
                'weights':self.platform_weights(),
                'require_approval':cfg['require_approval'],'voiceover_enabled':cfg['voiceover_enabled'],'publisher_challenge':bool(cfg.get('publisher_challenge')),
                'note':'Publishing stays off until the switch is turned on from the local dashboard.'}

BANNED_TAG_PARTS = ('tiktok', 'douyin', 'kuaishou', 'instagram', 'reels', 'fyp', 'foryou', 'viral', 'trending', 'xuhuong', 'capcut')


def _cut_at_word(text, limit):
    if len(text) <= limit: return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,;:-–—')
    return (cut if len(cut) >= limit * 0.5 else text[:limit]).strip()


def build_caption(analysis, title):
    """Vietnamese caption from the analysis; falls back to the source title. Never adds claims that were not in the video."""
    analysis = analysis if isinstance(analysis, dict) else {}
    caption = unicodedata.normalize('NFC', analysis.get('caption_vi').strip()) if isinstance(analysis.get('caption_vi'), str) else ''
    if not caption: caption = re.sub(r'\s+', ' ', re.sub(r'#\S+', ' ', title or '')).strip()
    caption = re.sub(r'[\x00-\x1f]', ' ', re.sub(r'#\S+', ' ', caption))        # hashtags are added below, never duplicated from the text
    caption = _cut_at_word(re.sub(r'\s+', ' ', caption).strip(), 110)
    tags = []
    raw_tags = analysis.get('hashtags') if isinstance(analysis.get('hashtags'), list) else []
    for h in raw_tags:
        if not isinstance(h, str): continue
        h = unicodedata.normalize('NFC', h).lstrip('#').strip().lower()
        if not re.fullmatch(r'[\w]{2,30}', h) or h in tags: continue
        if any(b in h for b in BANNED_TAG_PARTS): continue           # never advertise other platforms or filler, whatever the model says
        tags.append(h)
    tags = tags[:4]
    for d in (['xuhuong', 'nhac'] if analysis.get('kind') == 'music' else ['xuhuong', 'giaitri']):
        if d not in tags and len(tags) < 5: tags.append(d)
    return (caption + ' ' + ' '.join('#' + h for h in tags)).strip()


def lint_caption(caption):
    """Quality checks shown next to every caption. Returns {'ok': bool, 'tags': n, 'length': n, 'issues': [...]}."""
    issues = []
    text = re.sub(r'#\w+', '', caption).strip()
    tags = re.findall(r'#(\w+)', caption)
    if len(text) < 8: issues.append('Mô tả quá ngắn')
    if len(text) > 150: issues.append('Mô tả hơi dài (trên 150 ký tự dễ bị cắt khi xem)')
    if len(tags) < 3: issues.append('Nên có 3–5 hashtag')
    if len(tags) > 5: issues.append('Quá nhiều hashtag (nên tối đa 5)')
    if len({t.lower() for t in tags}) != len(tags): issues.append('Có hashtag bị lặp')
    if len(caption) > 2200: issues.append('Vượt giới hạn 2200 ký tự')
    return {'ok': not issues, 'tags': len(tags), 'length': len(text), 'issues': issues}
