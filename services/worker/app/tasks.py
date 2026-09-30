"""Background tasks behind the dashboard buttons (update everything, collect, process, post one video, rehearse, read stats).

They run the same code paths as the n8n schedule and take the same locks (one browser job at a time in the agent, one processing run
at a time in the worker), so pressing a button can never collide with a scheduled run: if something is already running you are told
so and nothing starts. Progress is stored in the database, so the page can poll it and a restart never leaves a task "running" forever.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

BROWSER_KINDS = {'collect', 'publish', 'dryrun', 'stats'}
LABELS = {'update': 'Cập nhật tổng hợp', 'collect': 'Thu thập video mới', 'process': 'Xử lý video đang chờ',
          'publish': 'Đăng video', 'dryrun': 'Xem thử (không đăng)', 'stats': 'Đọc lượt xem'}
PLATFORM_NAMES = {'douyin': 'Douyin', 'kuaishou': 'Kuaishou', 'tiktok': 'TikTok', 'instagram': 'Instagram'}
PROCESS_LABELS = {'ready': 'sẵn sàng đăng', 'awaiting_approval': 'chờ bạn duyệt', 'needs_review': 'cần duyệt', 'rate_limited': 'chờ Gemini hết quá tải'}


class AgentError(Exception):
    """Something between the worker and the browser agent failed; the message is written for the owner, not for a log."""


class TaskBusy(ValueError):
    pass


def agent_url():
    base = os.environ.get('TRENDVN_AGENT_URL')
    return base or 'http://trendvn-agent:%s' % os.environ.get('TRENDVN_AGENT_PORT', '5682')


def call_agent(path, payload, token, timeout=1500):
    req = urllib.request.Request(agent_url() + path, data=json.dumps(payload).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            raise AgentError('Trình duyệt agent đang bận việc khác (có thể lịch tự động đang chạy). Thử lại sau vài phút.') from None
        detail = ''
        try:
            detail = json.loads(e.read().decode()).get('error', '')
        except Exception:
            pass
        raise AgentError('Agent báo lỗi %d%s' % (e.code, ': ' + detail[:200] if detail else '')) from None
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        raise AgentError('Không gọi được agent trình duyệt. Kiểm tra dịch vụ trendvn-agent đang chạy (./trendvn doctor).') from None


def summarize_collect(report):
    """One readable line per source from the agent's collect report."""
    lines = []
    for p, r in (report or {}).items():
        name = PLATFORM_NAMES.get(p, p)
        if r.get('status') == 'skipped':
            lines.append('%s: bỏ qua (%s)' % (name, r.get('reason', '').split('. ')[0].rstrip('.')[:90]))
        elif r.get('status') != 'ok':
            lines.append('%s: lỗi, %s' % (name, (r.get('reason') or '')[:80]))
        else:
            streams = [v for k, v in (r.get('summary') or {}).items() if isinstance(v, dict) and k != 'media']
            seen = sum(s.get('seen', 0) for s in streams)
            good = sum(s.get('qualified', 0) for s in streams)
            new = sum(s.get('new', 0) for s in streams if not s.get('baseline'))
            media = (r.get('summary') or {}).get('media') or {}
            base = any(s.get('baseline') for s in streams)
            lines.append('%s: đọc %d, đạt ngưỡng %d, %s, tải %d' % (name, seen, good, 'lần đầu: chỉ ghi mốc' if base else 'mới %d' % new, media.get('downloaded', 0)))
    return '\n'.join(lines) or 'Không có nguồn nào chạy.'


def summarize_process(results):
    if not results:
        return 'Không có video nào để xử lý.'
    first = results[0]
    if first.get('status') == 'disabled':
        return 'Xử lý video đang TẮT. Bật công tắc "Xử lý video" rồi bấm lại.'
    if first.get('status') == 'blocked':
        return first.get('reason', 'Chưa xử lý được.')
    if first.get('status') == 'idle':
        return 'Không có video nào đang chờ xử lý.'
    counts = {}
    for r in results:
        counts[r.get('status')] = counts.get(r.get('status'), 0) + 1
    return 'Đã xử lý: ' + ', '.join('%d %s' % (n, PROCESS_LABELS.get(k, k)) for k, n in counts.items() if k not in ('idle',)) + '.'


def summarize_publish(res):
    s = res.get('status')
    if s == 'published':
        return 'Đã đăng và xác nhận trên hồ sơ.' + ((' ' + res['url']) if res.get('url') else '')
    if s == 'dry_run':
        shot = str(res.get('screenshot') or '')
        link = ' Xem ảnh chụp: /media/shot/' + shot if re.fullmatch(r'shot_\d{9,12}\.png', shot) else ''
        return 'Chạy thử xong: đã tải video, điền mô tả và dừng trước nút Đăng.' + link
    if s == 'challenge':
        return 'TikTok đòi xác minh. Đăng tạm dừng; giải một lần bằng `./trendvn tiktok trust`.'
    if s == 'unknown':
        return 'Đã bấm Đăng nhưng chưa xác nhận được. Hệ thống dừng đăng; xem mục Cần xem.'
    return res.get('reason') or 'Chưa đăng được (%s).' % s


class Tasks:
    def __init__(self, store, token, process_fn, process_lock):
        self.store, self.token, self.process_fn, self.process_lock = store, token, process_fn, process_lock
        self.guard = threading.Lock()
        store.tasks_reap()

    def start(self, kind, job_id=None):
        if kind not in LABELS:
            raise ValueError('Việc không hợp lệ')
        if kind in ('publish', 'dryrun') and not job_id:
            raise ValueError('Cần chọn một video')
        with self.guard:                         # check-and-create is atomic, so a double click starts one task, not two
            running = {t['kind'] for t in self.store.tasks_running()}
            wants_browser = kind in BROWSER_KINDS or kind == 'update'
            wants_gemini = kind in ('process', 'update')
            if wants_browser and running & (BROWSER_KINDS | {'update'}):
                raise TaskBusy('Đang có một việc dùng trình duyệt chạy (%s). Đợi nó xong rồi bấm lại.' % ', '.join(LABELS[k] for k in running & (BROWSER_KINDS | {'update'})))
            if wants_gemini and running & {'process', 'update'}:
                raise TaskBusy('Đang xử lý video rồi. Đợi nó xong rồi bấm lại.')
            tid = self.store.task_create(kind, job_id)
        threading.Thread(target=self._run, args=(tid, kind, job_id), daemon=True, name='task-' + kind).start()
        return tid

    # ------------------------------------------------------------------ runners
    def _run(self, tid, kind, job_id):
        steps = []

        def step(name):
            steps.append({'name': name, 'state': 'running', 'detail': ''})
            self.store.task_update(tid, steps=steps)
            return len(steps) - 1

        def finish_step(i, state, detail=''):
            steps[i].update(state=state, detail=detail)
            self.store.task_update(tid, steps=steps)

        try:
            results = []
            if kind in ('update', 'collect'):
                i = step('Thu thập video mới từ các nguồn')
                try:
                    report = call_agent('/api/collect', {}, self.token).get('report', {})
                    finish_step(i, 'done', summarize_collect(report))
                    results.append(True)
                except AgentError as e:
                    finish_step(i, 'error', str(e))
                    results.append(False)
            if kind in ('update', 'process'):
                i = step('Xử lý video đang chờ')
                try:
                    text = self._process()
                    finish_step(i, 'done', text)
                    results.append(True)
                except TaskBusy as e:
                    finish_step(i, 'error', str(e))
                    results.append(False)
            if kind in ('publish', 'dryrun'):
                i = step('Đăng video lên TikTok' if kind == 'publish' else 'Chạy thử: tải lên, điền mô tả, dừng trước nút Đăng')
                try:
                    res = call_agent('/api/publish' if kind == 'publish' else '/api/dry-run', {'job_id': job_id}, self.token)
                    text = summarize_publish(res)
                    ok = res.get('status') in ('published', 'dry_run')
                    finish_step(i, 'done' if ok else 'error', text)
                    results.append(ok)
                except AgentError as e:
                    finish_step(i, 'error', str(e))
                    results.append(False)
            if kind == 'stats':
                i = step('Đọc lượt xem từ hồ sơ TikTok')
                try:
                    res = call_agent('/api/stats', {}, self.token)
                    finish_step(i, 'done', 'Đọc %d bài, khớp %d bài đã đăng.' % (res.get('read', 0), res.get('matched', 0)))
                    results.append(True)
                except AgentError as e:
                    finish_step(i, 'error', str(e))
                    results.append(False)
            ok = any(results)
            print(time.strftime('%Y-%m-%d %H:%M:%S ') + 'task %s %s%s' % (kind, 'done' if ok else 'error',
                  '' if ok else ': ' + (steps[-1]['detail'] if steps else '')[:200].replace('\n', ' ')), flush=True)
            self.store.task_update(tid, steps=steps, state='done' if ok else 'error',
                                   result='\n'.join('%s %s' % ('✓' if s['state'] == 'done' else '✗', s['detail'] or s['name']) for s in steps),
                                   error='' if ok else (steps[-1]['detail'] if steps else 'Thất bại'))
        except Exception as e:                   # never leave a task "running" after an unexpected error
            self.store.task_update(tid, steps=steps, state='error', error='Lỗi bất ngờ: %s' % str(e)[:300])

    def _process(self):
        """Process up to 4 queued videos, sharing the worker lock with the scheduled /api/process so they never overlap."""
        if not self.process_lock.acquire(blocking=False):
            raise TaskBusy('Worker đang xử lý video cho lịch tự động. Đợi nó xong rồi bấm lại.')
        try:
            self.store.housekeeping()               # frees jobs a crash left 'processing' (the schedule does this too)
            results = []
            for _ in range(4):
                r = self.process_fn(self.store)
                results.append(r)
                if r.get('status') in ('disabled', 'blocked', 'idle', 'rate_limited'):
                    break
            return summarize_process(results)
        finally:
            self.process_lock.release()
