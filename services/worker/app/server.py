"""TrendVN worker: dashboard + authenticated API. Local dashboard forms need Host, Origin and CSRF checks; the API needs the bearer token."""
import gzip
import hmac
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import traceback
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

import notify
import ui
from core import PLATFORMS, Store
from media import process_one, tts
from prompts import VOICE_SAMPLE
from tasks import Tasks, TaskBusy
from version import VERSION

store = Store(os.environ.get('TRENDVN_DATA', './data'))
store.notifier = notify.Notifier(store)
TOKEN = os.environ.get('TRENDVN_TOKEN', '')
if len(TOKEN) < 32:
    raise RuntimeError('TRENDVN_TOKEN is required')
CSRF = secrets.token_urlsafe(32)
lock = threading.Lock()
tasks = Tasks(store, TOKEN, process_one, lock)

# Hosts the dashboard answers to. Add your own (e.g. "my-server:5681") via TRENDVN_UI_HOSTS when you deliberately expose it.
PUBLIC_PORT = os.environ.get('TRENDVN_PUBLIC_PORT', '5681')
UI_HOSTS = {'localhost:' + PUBLIC_PORT, '127.0.0.1:' + PUBLIC_PORT, 'localhost:8080'} | {h.strip() for h in os.environ.get('TRENDVN_UI_HOSTS', '').split(',') if h.strip()}
UI_ORIGINS = {'http://' + h for h in UI_HOSTS} | {'https://' + h for h in UI_HOSTS}
LOOPBACK_HOSTS = {'localhost:' + PUBLIC_PORT, '127.0.0.1:' + PUBLIC_PORT, 'localhost:8080'}
UI_PASSWORD = os.environ.get('TRENDVN_UI_PASSWORD', '')
SESSION_COOKIE = 'tv_session'
SESSION_VALUE = hmac.new(TOKEN.encode(), b'dashboard-session', 'sha256').hexdigest()   # only someone who knew the password ever receives this
login_failures = {}                                                                   # ip -> (count, locked_until)

FLASH = {'started': 'Đã bắt đầu. Tiến độ hiện ngay trên trang, không cần tải lại.', 'caption_saved': 'Đã lưu mô tả và hashtag.', 'caption_reset': 'Đã trả về mô tả do hệ thống soạn.',
         'saved': 'Đã lưu cài đặt.', 'key': 'Đã lưu khóa Gemini.', 'decided': 'Đã ghi nhận quyết định của bạn.', 'resolved': 'Đã cập nhật trạng thái bài đăng.',
         'notify': 'Đã lưu kênh thông báo.', 'notify_cleared': 'Đã xóa kênh thông báo.', 'notify_sent': 'Đã gửi tin thử. Hãy kiểm tra điện thoại.',
         'ingested': 'Đã nhập dữ liệu quan sát.', 'voice': 'Đã tạo giọng đọc thử. Kéo xuống mục Cài đặt để nghe.'}


def parse_windows(text):
    text = text.strip()
    if not text:
        return []
    out = []
    for part in re.split(r'[,;]', text):
        m = re.fullmatch(r'\s*(\d{1,2})\s*-\s*(\d{1,2})\s*', part)
        if not m:
            raise ValueError('Giờ vàng nhập dạng 11-14, 19-23')
        out.append([int(m.group(1)), int(m.group(2))])
    return out


def settings_patch(form):
    """Translate the dashboard form into validated settings (validation itself lives in core.validate_settings)."""
    g = lambda k: form.get(k, [''])[0].strip()
    patch = {}
    for k in ('processing_enabled', 'publisher_enabled', 'require_approval', 'voiceover_enabled'):
        if k in form:
            patch[k] = g(k) == 'true'
    for k in ('daily_limit', 'max_age_days', 'max_duration', 'max_candidates_per_scan', 'max_backlog', 'gemini_daily_limit'):
        if g(k):
            patch[k] = float(g(k)) if re.fullmatch(r'\d{1,9}(\.\d+)?', g(k)) else -1
    if g('gap_hours'):
        if not re.fullmatch(r'\d{1,3}(\.\d{1,2})?', g('gap_hours')):
            raise ValueError('Giãn cách nhập số giờ, ví dụ 3 hoặc 2.5')
        patch['min_publish_gap'] = round(float(g('gap_hours')) * 3600)
    if g('audio_confidence'):
        patch['audio_confidence'] = float(g('audio_confidence')) if re.fullmatch(r'\d(\.\d{1,3})?', g('audio_confidence')) else -1
    if 'post_windows' in form:
        patch['post_windows'] = parse_windows(g('post_windows'))
    for k in ('target', 'voice', 'model', 'tts_model', 'visibility'):
        if g(k):
            patch[k] = g(k)
    views = {p: int(g('views_' + p)) for p in PLATFORMS if re.fullmatch(r'\d+', g('views_' + p))}
    if views:
        patch['min_views'] = views
    if re.fullmatch(r'\d+', g('likes_douyin')):
        patch['min_likes'] = {'douyin': int(g('likes_douyin'))}
    return patch


def dashboard(flash=None, host=''):
    d = store.dashboard_data()
    d['ready'] = store.ready_list()
    d['tasks'] = store.tasks_recent(6)
    d['discovery_at'] = (store.settings().get('hb_discovery') or {}).get('at')
    # n8n lives on the same machine as this page: reuse the host the visitor used, swapping in n8n's port
    d['n8n_url'] = 'http://%s:%s' % ((host.rsplit(':', 1)[0] if host else 'localhost') or 'localhost', os.environ.get('TRENDVN_N8N_PORT', '5680'))
    d['notify_channels'] = notify.channels(notify.load_config(store.root))
    d['voice_sample'] = (store.root / 'exports' / 'voice_sample.wav').exists()
    for j in d['review']:
        j['has_source'] = True
    return ui.render(d, CSRF, flash)


def same(a, b):
    """Constant-time equality for strings that may contain non-ASCII characters (hmac.compare_digest raises TypeError on those)."""
    return hmac.compare_digest(str(a).encode('utf-8'), str(b).encode('utf-8'))


def log(msg):
    """One line per event on stdout: `./trendvn logs worker` (docker logs) shows it. Never includes tokens, cookies or request bodies."""
    print(time.strftime('%Y-%m-%d %H:%M:%S ') + msg, flush=True)


QUIET = ('/health', '/fragment/', '/media/', '/favicon')       # polled by the page or by Docker every few seconds: not worth a line


class Handler(BaseHTTPRequestHandler):
    server_version = 'TrendVN/' + VERSION

    def log_request(self, code='-', size='-'):
        # path only (the query string can carry flash text, never logged). `path`/`command` are not set yet for malformed requests.
        path = urlsplit(getattr(self, 'path', '') or '').path
        command = getattr(self, 'command', None) or '-'
        code = str(code)
        if command == 'GET' and code.startswith('2') and (path == '/' or path.startswith(QUIET)):
            return
        if path.startswith(QUIET) and not code.startswith(('4', '5')):
            return
        log('%s %s -> %s' % (command, path, code))

    def log_message(self, fmt, *args):             # malformed requests and other server-level complaints
        log('http: ' + (fmt % args))

    def send(self, code, data, kind='application/json; charset=utf-8', extra=None):
        body = (json.dumps(data, ensure_ascii=False) if not isinstance(data, (str, bytes)) else data)
        body = body.encode() if isinstance(body, str) else body
        zipped = len(body) > 1500 and 'gzip' in self.headers.get('Accept-Encoding', '') and (kind.startswith('text/') or 'json' in kind)
        if zipped:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')   # 'no-referrer' makes Chrome send Origin: null on form posts, which broke every button
        if zipped:
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Vary', 'Accept-Encoding')
        if kind.startswith('text/html'):
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; media-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return same(self.headers.get('Authorization', ''), 'Bearer ' + TOKEN)

    def host_ok(self):
        return self.headers.get('Host', '') in UI_HOSTS

    def session_ok(self):
        for part in self.headers.get('Cookie', '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == SESSION_COOKIE and same(v, SESSION_VALUE):
                return True
        return False

    def local_ui(self):
        """The dashboard is open without a password only on this machine. Any other host you allow (TRENDVN_UI_HOSTS) needs the
        password from TRENDVN_UI_PASSWORD; without one, such hosts are refused outright."""
        host = self.headers.get('Host', '')
        return host in LOOPBACK_HOSTS or (host in UI_HOSTS and bool(UI_PASSWORD) and self.session_ok())

    def login_page(self, message=''):
        body = ('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TrendVN · Đăng nhập</title>'
                '<style>body{font:16px system-ui;background:#0e1522;color:#e6ecf7;display:grid;place-items:center;min-height:100vh;margin:0}form{width:min(92vw,360px);background:#162033;padding:24px;border-radius:16px}'
                'input,button{width:100%%;padding:12px;margin-top:12px;border-radius:10px;border:1px solid #2a3850;font:inherit;box-sizing:border-box}button{background:#5fd6bd;color:#08231d;font-weight:700;border:0}p{color:#ff8a80}</style>'
                '<form method="post" action="/login"><h2>TrendVN</h2><p>%s</p><input type="password" name="password" placeholder="Mật khẩu bảng điều khiển" autofocus autocomplete="current-password"><button>Đăng nhập</button></form></html>') % html_escape(message)
        return self.send(200, body, 'text/html; charset=utf-8')

    def redirect(self, key=None, err=None, anchor=''):
        loc = '/' + ('?ok=' + key if key else '?err=' + quote(err[:200], safe='') if err else '') + anchor
        self.send_response(303)
        self.send_header('Location', loc)
        self.end_headers()

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        try:
            return self._get()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            log('ERROR GET %s\n%s' % (urlsplit(self.path).path, traceback.format_exc().rstrip()))
            try:
                return self.send(500, {'error': 'Internal failure; inspect local service'})
            except Exception:
                return

    def _get(self):
        u = urlsplit(self.path)
        path = u.path
        if path == '/health':
            return self.send(200, {'ok': True, 'project': 'trendvn', 'version': VERSION})
        if path == '/login' and self.host_ok() and not self.local_ui():
            if not UI_PASSWORD:
                return self.send(403, {'error': 'Đặt TRENDVN_UI_PASSWORD trong .env để mở bảng điều khiển từ máy khác'})
            return self.login_page()
        if path == '/' and self.host_ok() and not self.local_ui():
            self.send_response(303)
            self.send_header('Location', '/login')
            self.end_headers()
            return
        if path.startswith('/media/shot/') and self.local_ui():
            return self.media(path)
        if path == '/' and self.local_ui():
            q = parse_qs(u.query)
            flash = ('ok', FLASH[q['ok'][0]]) if q.get('ok', [''])[0] in FLASH else (('err', q['err'][0]) if q.get('err') else None)
            return self.send(200, dashboard(flash, self.headers.get('Host', '')), 'text/html; charset=utf-8')
        if path == '/api/status' and (self.authorized() or self.local_ui()):
            return self.send(200, store.status())
        if path == '/api/dashboard' and (self.authorized() or self.local_ui()):
            return self.send(200, store.dashboard_data())
        if path == '/fragment/tasks' and self.local_ui():
            return self.send(200, ui.task_panel(store.tasks_recent(6)), 'text/html; charset=utf-8')
        if path == '/api/tasks' and (self.authorized() or self.local_ui()):
            return self.send(200, {'running': store.tasks_running(), 'tasks': store.tasks_recent(6)})
        if path.startswith('/media/') and self.local_ui():
            return self.media(path)
        return self.send(404, {'error': 'Not found'})

    def media(self, path):
        parts = unquote(path).split('/')[2:]
        if parts == ['voice-sample']:
            f = store.root / 'exports' / 'voice_sample.wav'
        elif len(parts) == 2 and parts[0] == 'shot' and re.fullmatch(r'shot_\d{9,12}\.png', parts[1]):
            f = store.root / 'exports' / parts[1]
        elif len(parts) == 2 and re.fullmatch(r'[0-9a-f]{32}', parts[0]) and parts[1] in ('final', 'source', 'poster'):
            with store.connect() as db:
                row = db.execute('SELECT output_file,source_file FROM jobs WHERE id=?', (parts[0],)).fetchone()
            if row and parts[1] == 'poster':
                f = Path(row['output_file'] or '').with_name('poster.jpg') if row['output_file'] else None
            else:
                f = Path((row['output_file'] if parts[1] == 'final' else row['source_file']) or '') if row else None
        else:
            f = None
        try:
            f = f.resolve() if f else None
            if not f or not f.is_file() or store.root not in f.parents:
                return self.send(404, {'error': 'Not found'})
        except OSError:
            return self.send(404, {'error': 'Not found'})
        size = f.stat().st_size
        start, end = 0, size - 1
        m = re.fullmatch(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                return self.send(416, {'error': 'Bad range'}, extra={'Content-Range': 'bytes */%d' % size})
            end = min(end, size - 1)
        kind = mimetypes.guess_type(str(f))[0] or 'application/octet-stream'
        self.send_response(206 if m else 200)
        self.send_header('Content-Type', kind)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1))
        if m:
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'private, max-age=60')
        self.end_headers()
        with open(f, 'rb') as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        path = urlsplit(self.path).path
        if path == '/login':
            return self.login_post()
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2 * 1024 * 1024:
                return self.send(413, {'error': 'Request too large or empty'})
            if path in self.FORMS:
                origin = self.headers.get('Origin')
                same_site = self.headers.get('Sec-Fetch-Site') == 'same-origin'
                if not self.local_ui() or not (origin in UI_ORIGINS or (origin in (None, 'null') and same_site)):
                    return self.send(403, {'error': 'Local form only'})
                form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
                if not same(form.get('csrf', [''])[0], CSRF):
                    return self.send(403, {'error': 'Refresh the page and retry'})
                try:
                    return getattr(self, self.FORMS[path])(form)
                except (ValueError, KeyError, TypeError, OSError, OverflowError) as e:
                    return self.redirect(err=str(e) or 'Không thực hiện được')
            if not self.authorized():
                return self.send(401, {'error': 'Authentication required'})
            payload = json.loads(self.rfile.read(length))
            return self.api(path, payload)
        except (ValueError, KeyError, TypeError, OverflowError) as e:
            return self.send(400, {'error': str(e)[:700]})
        except Exception:
            log('ERROR POST %s\n%s' % (path, traceback.format_exc().rstrip()))
            return self.send(500, {'error': 'Internal failure; inspect local service'})

    def login_post(self):
        if not self.host_ok() or not UI_PASSWORD:
            return self.send(403, {'error': 'Not available'})
        ip = self.client_address[0]
        count, locked = login_failures.get(ip, (0, 0))
        if time.time() < locked:
            return self.login_page('Thử sai quá nhiều lần. Đợi một phút rồi thử lại.')
        try:
            form = parse_qs(self.rfile.read(min(int(self.headers.get('Content-Length', '0')), 4096)).decode(), keep_blank_values=True)
        except Exception:
            form = {}
        if same(form.get('password', [''])[0], UI_PASSWORD):
            login_failures.pop(ip, None)
            self.send_response(303)
            self.send_header('Set-Cookie', '%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000' % (SESSION_COOKIE, SESSION_VALUE))
            self.send_header('Location', '/')
            self.end_headers()
            return
        count += 1
        login_failures[ip] = (count, time.time() + 60 if count >= 5 else 0)
        time.sleep(1)                       # slow down guessing
        return self.login_page('Mật khẩu chưa đúng.')

    FORMS = {'/setup': 'f_setup', '/settings': 'f_settings', '/decide': 'f_decide', '/resolve': 'f_resolve', '/ingest-form': 'f_ingest',
             '/notify-save': 'f_notify_save', '/notify-clear': 'f_notify_clear', '/notify-test': 'f_notify_test', '/voice-test': 'f_voice',
             '/task': 'f_task', '/caption': 'f_caption'}

    def f_setup(self, form):
        key = form.get('key', [''])[0].strip()
        if not key:
            return self.redirect(err='Chưa nhập khóa', anchor='#settings')
        if len(key) < 20 or len(key) > 300 or any(c.isspace() for c in key):
            raise ValueError('Khóa không đúng định dạng')
        p = store.root / 'gemini.key'
        p.write_text(key)
        p.chmod(0o600)
        self.redirect('key', anchor='#settings')

    def f_settings(self, form):
        store.update_settings(settings_patch(form))
        back = form.get('next', ['settings'])[0]
        self.redirect('saved', anchor='#' + (back if back in ('home', 'publish', 'attention', 'queue', 'posted', 'more', 'settings') else 'settings'))

    def f_task(self, form):
        kind = form.get('kind', [''])[0]
        job = form.get('id', [''])[0] or None
        if job and not re.fullmatch(r'[0-9a-f]{32}', job):
            raise ValueError('Mã video không hợp lệ')
        cap = form.get('caption', [None])[0]
        if kind in ('publish', 'dryrun') and job and cap is not None:
            store.set_caption(job, cap)        # what you see in the box is what gets posted, even if you did not press Save first
        back = form.get('next', [''])[0]           # the tab that has the button, so the progress shows where you pressed it
        if back not in ('home', 'queue', 'publish', 'posted'):
            back = 'publish' if kind in ('publish', 'dryrun') else 'posted' if kind == 'stats' else 'queue' if kind == 'process' else 'home'
        try:
            tasks.start(kind, job)
        except TaskBusy as e:
            return self.redirect(err=str(e), anchor='#' + back)
        self.redirect('started', anchor='#' + back)

    def f_caption(self, form):
        jid = form['id'][0]
        if form.get('action', ['save'])[0] == 'reset':
            store.reset_caption(jid)
            return self.redirect('caption_reset', anchor='#publish')
        store.set_caption(jid, form.get('caption', [''])[0])
        self.redirect('caption_saved', anchor='#publish')

    def f_decide(self, form):
        store.decide(form['id'][0], form['action'][0])
        self.redirect('decided', anchor='#attention')

    def f_resolve(self, form):
        store.resolve_unknown(form['id'][0], form['outcome'][0])
        self.redirect('resolved', anchor='#attention')

    def f_ingest(self, form):
        store.ingest(json.loads(form.get('batch', ['{}'])[0]))
        self.redirect('ingested', anchor='#queue')

    def f_notify_save(self, form):
        f = store.root / 'notify.json'
        cfg = json.loads(f.read_text()) if f.exists() else {}
        for k in ('telegram_token', 'telegram_chat', 'webhook', 'ntfy'):
            v = form.get(k, [''])[0].strip()
            if v:
                cfg[k] = v
        notify.save_config(store.root, cfg)
        self.redirect('notify', anchor='#notify')

    def f_notify_clear(self, form):
        notify.clear_config(store.root)
        self.redirect('notify_cleared', anchor='#notify')

    def f_notify_test(self, form):
        cfg = notify.load_config(store.root)
        if not notify.channels(cfg):
            raise ValueError('Chưa có kênh thông báo nào')
        results = notify.send(cfg, '✅ TrendVN: tin thử. Thông báo hoạt động.')
        if not any(results.values()):
            raise ValueError('Gửi không thành công; kiểm tra lại token, chat id hoặc địa chỉ')
        self.redirect('notify_sent', anchor='#notify')

    def f_voice(self, form):
        if not lock.acquire(blocking=False):
            raise ValueError('Worker đang bận, thử lại sau')
        try:
            (store.root / 'exports').mkdir(exist_ok=True)
            tts(store, store.settings(), VOICE_SAMPLE, store.root / 'exports' / 'voice_sample.wav')
        finally:
            lock.release()
        self.redirect('voice', anchor='#settings')

    def api(self, path, payload):
        if path == '/api/ingest':
            return self.send(200, store.ingest(payload))
        if path == '/api/attach':
            return self.send(200, store.attach(payload['id'], payload['filename']))
        if path == '/api/housekeeping':
            return self.send(200, store.housekeeping())
        if path == '/api/heartbeat':
            store.heartbeat(payload['component'], payload['ok'], payload.get('detail'))
            return self.send(200, {'ok': True})
        if path == '/api/media/pending':
            return self.send(200, {'items': store.candidates_without_media(int(payload.get('limit', 20)))})
        if path == '/api/media/failed':
            store.mark_media_failed(payload['id'], str(payload.get('reason', '')))
            return self.send(200, {'ok': True})
        if path == '/api/publisher/challenge':
            store.set_challenge(bool(payload.get('active')))
            return self.send(200, {'ok': True})
        if path == '/api/stats':
            return self.send(200, store.record_stats(payload['items']))
        if path == '/api/settings':
            return self.send(200, {'changed': sorted(store.update_settings(payload))})
        if path == '/api/notify':
            kind = payload.get('kind', 'summary')
            text = store.summary_text() if kind == 'summary' else str(payload.get('text', ''))[:1500]
            cfg = notify.load_config(store.root)
            return self.send(200, {'channels': notify.channels(cfg), 'sent': notify.send(cfg, text) if notify.channels(cfg) else {}})
        if path == '/api/publish/peek':
            return self.send(200, store.publish_peek(payload.get('job_id')))
        if path == '/api/publish/claim':
            jid = payload.get('job_id')
            if jid is not None and not re.fullmatch(r'[0-9a-f]{32}', str(jid)):
                raise ValueError('Mã video không hợp lệ')
            return self.send(200, store.publish_claim(job_id=jid))
        if path == '/api/tasks/start':
            return self.send(200, {'id': tasks.start(payload.get('kind', ''), payload.get('job_id'))})
        if path == '/api/publish/finish':
            store.publish_finish(payload['id'], payload['lease'], payload['outcome'], payload.get('url', ''), str(payload.get('reason', '')))
            return self.send(200, {'ok': True})
        if path == '/api/publish/unresolved':
            return self.send(200, {'items': store.unresolved()})
        if path == '/api/publish/resolve':
            store.resolve_unknown(payload['id'], payload['outcome'], payload.get('url', ''))
            return self.send(200, {'ok': True})
        if path == '/api/process':
            if not lock.acquire(blocking=False):
                return self.send(409, {'error': 'Worker busy; do not run concurrently'})
            try:
                n = max(1, min(int(payload.get('max', 1)), 8))
                results = []
                for _ in range(n):
                    r = process_one(store)
                    results.append(r)
                    if r.get('status') in ('disabled', 'blocked', 'idle', 'rate_limited'):
                        break
            finally:
                lock.release()
            log('process: ' + ', '.join('%s' % r.get('status') for r in results))
            return self.send(200, results[0] if n == 1 else {'results': results, 'processed': sum(1 for r in results if r.get('status') in ('ready', 'awaiting_approval', 'needs_review'))})
        return self.send(404, {'error': 'Not found'})


if __name__ == '__main__':
    port = int(os.environ.get('TRENDVN_PORT', '8080'))
    log('worker %s listening on :%d, data in %s' % (VERSION, port, store.root))
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
