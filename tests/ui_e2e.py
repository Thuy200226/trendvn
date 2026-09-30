"""End-to-end check of the dashboard in a real Chrome: layout audit at many screen sizes plus every button flow.

Run:  .venv/bin/python tests/ui_e2e.py [--shots DIR]     (needs Playwright and Chrome; not part of `unittest discover`)
It starts a throw-away worker (temp data dir, random port) and a fake browser agent, never touching your real data, TikTok or Gemini.
Exit code 1 if any check fails.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'worker' / 'app'))
import core  # noqa: E402

SHOTS = None
if '--shots' in sys.argv:
    SHOTS = Path(sys.argv[sys.argv.index('--shots') + 1])
    SHOTS.mkdir(parents=True, exist_ok=True)
SAMPLE = Path(os.environ['TRENDVN_SAMPLE']) if os.environ.get('TRENDVN_SAMPLE') else next(iter(sorted((ROOT / 'data' / 'worker' / 'jobs').glob('*/final.mp4'))), None)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class FakeAgent(BaseHTTPRequestHandler):
    calls = []
    mode = 'ok'

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(n) or b'{}')
        FakeAgent.calls.append((self.path, payload))
        if FakeAgent.mode == 'busy':
            return self.reply(409, {'error': 'busy'})
        if self.path == '/api/collect':
            time.sleep(2.2)
            return self.reply(200, {'report': {
                'douyin': {'status': 'ok', 'summary': {'jingxuan': {'seen': 47, 'qualified': 9, 'baseline': False, 'new': 3}, 'media': {'downloaded': 2}}},
                'kuaishou': {'status': 'ok', 'summary': {'brilliant': {'seen': 98, 'qualified': 19, 'baseline': False, 'new': 5}, 'media': {'downloaded': 1}}},
                'tiktok': {'status': 'skipped', 'reason': 'Cần IP US để lấy xu hướng đúng quốc gia; IP hiện tại: VN.'},
                'instagram': {'status': 'skipped', 'reason': 'Cần IP US'}}})
        if self.path == '/api/publish':
            time.sleep(1.0)
            return self.reply(200, {'status': 'published', 'url': 'https://www.tiktok.com/@u/video/7691188901918264597', 'id': payload.get('job_id')})
        if self.path == '/api/dry-run':
            time.sleep(0.6)
            return self.reply(200, {'status': 'dry_run', 'reason': 'ok', 'screenshot': '/tmp/x.png'})
        if self.path == '/api/stats':
            return self.reply(200, {'read': 3, 'matched': 2})
        self.reply(404, {'error': 'nf'})

    def reply(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def seed(root):
    s = core.Store(root)
    now = time.time()
    (Path(root) / 'gemini.key').write_text('x' * 30)
    s.update_settings({'processing_enabled': True, 'visibility': 'self'})
    s.heartbeat('discovery', True, {'douyin': {'jingxuan': {'seen': 47}}, 'tiktok': 'Cần IP US để lấy xu hướng đúng quốc gia; IP hiện tại: VN.'})
    s.heartbeat('publisher', True, 'Đã đăng nhập TikTok, sẵn sàng')

    def add(state, platform, title, **kw):
        jid = kw.get('id') or uuid.uuid4().hex
        cols = dict(id=jid, platform=platform, source_id=jid[:10], url='https://x/' + jid, country='CN', title=title, first_seen=now - 7200, last_seen=now,
                    state=state, updated=now - 300)
        cols.update(kw)
        with s.transaction() as db:
            db.execute('INSERT INTO jobs(%s) VALUES (%s)' % (','.join(cols), ','.join('?' * len(cols))), list(cols.values()))
            s.event(db, jid, state, kw.get('reason', ''))
        return jid

    ids = []
    titles = ['舅舅别睡了，给我闺蜜也泡一杯奶奶 #舅舅带娃 một tiêu đề rất rất dài để thử việc xuống dòng không làm vỡ thẻ trên màn hình điện thoại nhỏ',
              'Khoảnh khắc thú vị', 'Bài hát hay nhất tuần']
    for n, title in enumerate(titles):
        jid = uuid.uuid4().hex
        folder = Path(root) / 'jobs' / jid
        folder.mkdir(parents=True)
        if SAMPLE:
            shutil.copy(SAMPLE, folder / 'final.mp4')
            poster = SAMPLE.with_name('poster.jpg')
            if poster.exists():
                shutil.copy(poster, folder / 'poster.jpg')
        analysis = {'kind': 'dialogue' if n < 2 else 'music', 'caption_vi': ['Lập luận đòi lương khiến ông bố cạn lời', 'Khoảnh khắc thú vị', 'Giai điệu nghe là nghiện'][n],
                    'hashtags': ['haihuoc', 'giadinh', 'tinhhuonghai'] if n == 0 else (['vui'] if n == 1 else [])}
        info = {'w': 1080, 'h': 1920, 'duration': 38.2, 'size': 4100000, 'poster': bool(SAMPLE and (SAMPLE.with_name('poster.jpg')).exists()), 'reframed': n == 1, 'route': 'vietsub'}
        ids.append(add('ready' if n < 2 else 'awaiting_approval', 'douyin' if n != 1 else 'kuaishou', title, id=jid, output_file=str(folder / 'final.mp4'), output_hash='h',
                       analysis=json.dumps(analysis), route='vietsub' if n < 2 else 'original', meta=json.dumps({'score': 900000 - n * 1000, 'likes': 386000, 'age_h': 30}),
                       output_info=json.dumps(info)))
    for i in range(3):
        add('queued', 'douyin', 'Video chờ xử lý %d' % i, meta=json.dumps({'score': 1000 * (i + 1)}))
    src = Path(root) / 'inbox' / 'r.mp4'
    src.parent.mkdir(exist_ok=True)
    if SAMPLE:
        shutil.copy(SAMPLE, src)
    add('needs_review', 'kuaishou', 'Video bị giữ lại xem xét', source_file=str(src), reason='Sensitive content (politics, violence, tragedy, adult or medical claims) needs review')
    p1 = add('published', 'douyin', 'Bài đã đăng thứ nhất', publish_url='https://www.tiktok.com/@u/video/7690000000000000001', published_at=now - 86400, route='vietsub')
    s.record_stats([{'video_id': '7690000000000000001', 'views': 15400, 'likes': 1200}])
    for i in range(5):
        add('baseline', 'douyin', 'baseline %d' % i)
    return ids


AUDIT_JS = r"""
() => {
  const issues = [];
  document.documentElement.style.scrollBehavior = 'auto';
  scrollTo(0, 0);
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); if (e.closest('details:not([open])') && !e.matches('summary') && !e.closest('summary')) return false; return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const desc = e => (e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/)[0] : '') + ' "' + (e.innerText || e.value || '').trim().slice(0, 28).replace(/\n/g, ' ') + '"');
  if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('horizontal overflow: scrollWidth ' + document.documentElement.scrollWidth + ' > ' + innerWidth);
  const nav = document.querySelector('.bottomnav');
  const navVisible = nav && vis(nav);
  const sel = '.card,.kpi,.pill,.qs,.step,.banner,.taskpanel,.strip>div,tr:not(.hd),.tag,.chip,video,textarea,input:not([type=hidden]),select,button,.topnav>a,h1,h2,h3,.lint,.note,.ttl,.facts,.tags,.btns>*,.btngrid>*,label';
  const els = [...document.querySelectorAll(sel)].filter(vis).filter(e => !e.closest('.bottomnav') && !e.closest('header') || e.closest('header') && innerWidth > 720);
  for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
    const a = els[i], b = els[j];
    if (a.contains(b) || b.contains(a)) continue;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (w > 2 && h > 2) issues.push('overlap ' + Math.round(w) + 'x' + Math.round(h) + ': ' + desc(a) + '  <->  ' + desc(b));
  }
  const cards = [...document.querySelectorAll('section.on > .card, section.on .stack > .card, section.on > form.card')].filter(vis);
  for (let i = 1; i < cards.length; i++) {
    const p = cards[i - 1].getBoundingClientRect(), c = cards[i].getBoundingClientRect();
    if (c.top >= p.bottom - 1 && c.top - p.bottom < 6 && Math.abs(c.left - p.left) < 4) issues.push('cards touch (gap ' + Math.round(c.top - p.bottom) + 'px): ' + desc(cards[i - 1]) + ' / ' + desc(cards[i]));
  }
  [...document.querySelectorAll('button,select,input:not([type=hidden]),.bottomnav a,.topnav a')].filter(vis).forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.height < 43.5 && !e.closest('.fs > summary')) issues.push('small tap target ' + Math.round(r.width) + 'x' + Math.round(r.height) + ': ' + desc(e));
  });
  [...document.querySelectorAll('body *')].filter(vis).forEach(e => {
    const s = getComputedStyle(e);
    if (e.scrollWidth > e.clientWidth + 2 && ['hidden', 'clip'].includes(s.overflowX) && !['VIDEO', 'SELECT', 'TEXTAREA', 'INPUT', 'BUTTON'].includes(e.tagName) && e.clientWidth > 0) issues.push('clipped text: ' + desc(e));
    if (parseFloat(s.fontSize) < (innerWidth <= 340 && e.closest('.bottomnav') ? 10 : 11) && (e.innerText || '').trim() && e.children.length === 0 && !e.closest('svg')) issues.push('tiny font ' + s.fontSize + ': ' + desc(e));
    const r = e.getBoundingClientRect();
    if (r.right > innerWidth + 1 && s.position !== 'fixed' && !e.closest('.tablewrap')) issues.push('sticks out right by ' + Math.round(r.right - innerWidth) + 'px: ' + desc(e));
  });
  if (navVisible) {
    const items = [...nav.querySelectorAll('a')], boxes = items.map(a => a.getBoundingClientRect());
    items.forEach((a, i) => {
      const sm = a.querySelector('small'), rg = document.createRange();
      rg.selectNodeContents(sm);
      const t = rg.getBoundingClientRect();
      if (t.height > 18) issues.push('bottom nav label wraps to two lines: ' + sm.innerText);
      if (t.width > boxes[i].width - 2) issues.push('bottom nav label touches its neighbours: ' + sm.innerText + ' (' + Math.round(t.width) + 'px in ' + Math.round(boxes[i].width) + 'px)');
      if (i && boxes[i].left < boxes[i - 1].right - 0.5) issues.push('bottom nav buttons overlap: ' + sm.innerText);
    });
    scrollTo(0, document.documentElement.scrollHeight);
    const navTop = nav.getBoundingClientRect().top;
    const last = [...document.querySelectorAll('main *')].filter(vis).map(e => e.getBoundingClientRect().bottom).reduce((m, v) => Math.max(m, v), 0);
    if (last > navTop - 2) issues.push('bottom nav covers the end of the page: content ends at ' + Math.round(last) + ', nav starts at ' + Math.round(navTop));
    scrollTo(0, 0);
  }
  return issues;
}
"""


def main():
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix='trendvn-e2e-')
    results = []

    def check(name, ok, detail=''):
        results.append((name, ok, detail))
        print(('PASS ' if ok else 'FAIL ') + name + (('  -> ' + detail) if detail and not ok else ''), flush=True)

    ids = seed(tmp)
    agent_port, port = free_port(), free_port()
    agent = ThreadingHTTPServer(('127.0.0.1', agent_port), FakeAgent)
    threading.Thread(target=agent.serve_forever, daemon=True).start()
    env = dict(os.environ, TRENDVN_DATA=tmp, TRENDVN_TOKEN='t' * 40, TRENDVN_PORT=str(port), TRENDVN_PUBLIC_PORT=str(port),
               TRENDVN_AGENT_URL='http://127.0.0.1:%d' % agent_port)
    server = subprocess.Popen([sys.executable, str(ROOT / 'services' / 'worker' / 'app' / 'server.py')], cwd=str(ROOT / 'services' / 'worker' / 'app'), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = 'http://localhost:%d' % port
    try:
        for _ in range(50):
            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            errors = []

            def go(pg, url):
                """goto that survives a form redirect still in flight (it would otherwise abort the new navigation)."""
                for _ in range(3):
                    try:
                        pg.wait_for_load_state('load')
                        return pg.goto(url, wait_until='load')
                    except Exception as e:
                        if 'interrupted by another navigation' not in str(e):
                            raise
                        pg.wait_for_timeout(500)
                return pg.goto(url, wait_until='load')

            def new_ctx(w, h, mobile):
                ctx = browser.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1, accept_downloads=False)
                pg = ctx.new_page()
                pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
                pg.on('pageerror', lambda e: errors.append(str(e)))
                return ctx, pg

            # ---------------- pass A: layout audit on every tab and size
            sizes = [(320, 640, True), (360, 740, True), (375, 812, True), (414, 896, True), (768, 1024, True), (1280, 900, False), (1440, 900, False)]
            for w, h, mobile in sizes:
                ctx, pg = new_ctx(w, h, mobile)
                go(pg, base + '/')
                for tab in ('home', 'queue', 'publish', 'attention', 'posted', 'more'):
                    pg.evaluate("t => { location.hash = '#' + t; }", tab)
                    pg.wait_for_timeout(250)
                    if tab == 'more':
                        pg.evaluate("() => document.querySelectorAll('#more details').forEach(d => d.open = true)")
                        pg.wait_for_timeout(150)
                    issues = pg.evaluate(AUDIT_JS)
                    check('layout %dx%d %-9s' % (w, h, tab), not issues, '; '.join(issues[:4]) + (' (+%d more)' % (len(issues) - 4) if len(issues) > 4 else ''))
                    if SHOTS and w in (375, 1280):
                        pg.screenshot(path=str(SHOTS / ('%dx%d_%s.png' % (w, h, tab))), full_page=(w == 375))
                ctx.close()
            check('no console or page errors during layout audit', not errors, '; '.join(errors[:3]))

            # ---------------- pass B: flows (phone size)
            errors.clear()
            ctx, pg = new_ctx(375, 812, True)
            pg.on('dialog', lambda d: d.accept())
            go(pg, base + '/#home')
            FakeAgent.calls.clear()
            pg.click('#control button[value="update"]')
            pg.wait_for_selector('#control .taskpanel[data-running="1"]', timeout=6000)
            check('Start: progress panel appears while running', True)
            check('Start: buttons disabled while a task runs', pg.evaluate("() => [...document.querySelectorAll('#control button')].every(b => b.disabled)") is True)
            pg.wait_for_selector('#control .taskpanel[data-running="0"]', timeout=30000)
            pg.wait_for_timeout(600)
            panel = pg.inner_text('#control .taskpanel')
            check('Start: result lists each source in Vietnamese', 'Douyin' in panel and 'Kuaishou' in panel, panel[:120])
            check('Start: agent was called exactly once for collect', [c for c in FakeAgent.calls if c[0] == '/api/collect'] and len([c for c in FakeAgent.calls if c[0] == '/api/collect']) == 1)
            check('Start: process step ran (no Gemini in the test, so it reports the state)', 'Xử lý' in panel)

            # double click protection
            FakeAgent.calls.clear()
            go(pg, base + '/#home')
            pg.evaluate("() => { const b = document.querySelector('#control button[value=\"collect\"]'); b.click(); b.click(); }")
            pg.wait_for_timeout(3500)
            check('Double click starts a single task', len([c for c in FakeAgent.calls if c[0] == '/api/collect']) == 1, str(len(FakeAgent.calls)))

            # agent busy
            FakeAgent.mode = 'busy'
            go(pg, base + '/#home')
            pg.click('#control button[value="collect"]')
            pg.wait_for_selector('#queue .taskpanel[data-running="0"]', timeout=15000)
            pg.wait_for_timeout(800)
            check('Collect button lands on the Hàng đợi tab and shows its result there', pg.evaluate("() => location.hash") == '#queue')
            check('Agent busy: clear message, no crash', 'bận' in pg.inner_text('#queue .taskpanel'), pg.inner_text('#queue .taskpanel')[:120])
            FakeAgent.mode = 'ok'
            # agent down
            agent.shutdown()
            agent.server_close()
            go(pg, base + '/#home')
            pg.click('#control button[value="collect"]')
            pg.wait_for_timeout(2500)
            go(pg, base + '/#home')
            check('Agent down: owner-readable error', 'agent' in pg.inner_text('#control .taskpanel').lower(), pg.inner_text('#control .taskpanel')[:150])
            agent = ThreadingHTTPServer(('127.0.0.1', agent_port), FakeAgent)
            threading.Thread(target=agent.serve_forever, daemon=True).start()

            # publish flows
            go(pg, base + '/#publish')
            cards = pg.query_selector_all('#publish form.ready')
            check('Publish tab lists every processed video', len(cards) == 3, str(len(cards)))
            check('Each card has Đăng ngay, Xem thử, Lưu, Bỏ', all(len(c.query_selector_all('button')) >= 4 for c in cards))
            first_id = cards[0].get_attribute('data-id')
            ta = cards[0].query_selector('textarea')
            check('Caption box shows caption with hashtags', '#haihuoc' in ta.input_value() and '#xuhuong' in ta.input_value(), ta.input_value())
            FakeAgent.calls.clear()
            ta.fill('Mô tả sửa tay để kiểm tra #kiemtra #haihuoc #vui')
            cards[0].query_selector('button[value="publish"]').click()
            pg.wait_for_selector('#publish .taskpanel', timeout=8000)
            check('Post now: progress is shown on the Publish tab itself', 'Đăng video' in pg.inner_text('#publish .taskpanel'), pg.inner_text('#publish .taskpanel')[:100])
            pg.wait_for_selector('#publish .taskpanel[data-running="0"]', timeout=20000)
            pg.wait_for_timeout(800)
            check('Post now: success message with link is visible there', 'Đã đăng' in pg.inner_text('#publish .taskpanel'), pg.inner_text('#publish .taskpanel')[:160])
            pub = [c for c in FakeAgent.calls if c[0] == '/api/publish']
            check('Post now: agent receives that exact video', len(pub) == 1 and pub[0][1].get('job_id') == first_id, str(pub))
            st = core.Store(tmp)
            edited = [j for j in st.ready_list() if j['id'] == first_id][0]
            check('Post now: edited caption saved before posting', edited['caption'].startswith('Mô tả sửa tay') and edited['caption_edited'], edited['caption'])
            go(pg, base + '/#publish')
            check('Edited caption persists and shows "đã sửa tay"', 'đã sửa tay' in pg.inner_text('form.ready[data-id="%s"]' % first_id))
            FakeAgent.calls.clear()
            pg.query_selector('form.ready[data-id="%s"] button[value="dryrun"]' % first_id).click()
            pg.wait_for_timeout(2500)
            check('Rehearsal: agent dry-run called for that video', any(c[0] == '/api/dry-run' and c[1].get('job_id') == first_id for c in FakeAgent.calls), str(FakeAgent.calls))
            go(pg, base + '/#publish')
            pg.query_selector('form.ready[data-id="%s"] button[value="reset"]' % first_id).click()
            pg.wait_for_timeout(800)
            check('Reset returns to the system caption', not [j for j in core.Store(tmp).ready_list() if j['id'] == first_id][0]['caption_edited'])
            go(pg, base + '/#publish')
            pg.query_selector('form.ready[data-id="%s"] button[formaction="/decide"]' % ids[1]).click()
            pg.wait_for_timeout(800)
            check('Discard removes the video from the list', ids[1] not in [j['id'] for j in core.Store(tmp).ready_list()])
            # ---------------- Hàng đợi tab (the Start flow above has processed the seeded queue, so put three videos back in it)
            store = core.Store(tmp)
            for i in range(3):
                jid = uuid.uuid4().hex
                with store.transaction() as db:
                    db.execute("INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,updated,meta) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               (jid, 'douyin', jid[:10], 'https://x/' + jid, 'CN', 'Video chờ xử lý %d' % i, time.time() - 600 + i, time.time(), 'queued', time.time(), json.dumps({'score': 1000 * (i + 1)})))
            go(pg, base + '/#queue')
            rows = pg.evaluate("() => [...document.querySelectorAll('#queue .tablewrap')][0] ? [...document.querySelectorAll('#queue .tablewrap')][0].innerText : ''")
            check('Hàng đợi tab lists the waiting videos', all('Video chờ xử lý %d' % i in rows for i in range(3)), rows[:120])
            check('Bottom nav has six entries and Hàng đợi carries the waiting count',
                  pg.evaluate("() => document.querySelectorAll('.bottomnav a').length") == 6 and pg.inner_text('.bottomnav a[data-go="queue"] i') == '3')
            check('Nav badge for waiting videos is not red (it is not an alarm)', pg.evaluate("() => document.querySelector('.bottomnav a[data-go=queue] i').className") == 'n')
            pg.click('#queue a.step[href="#publish"]')
            pg.wait_for_timeout(300)
            check('Funnel step opens the matching tab', pg.evaluate("() => location.hash") == '#publish' and pg.is_visible('#publish'))
            go(pg, base + '/#home')
            check('Status is a card of rows, not a scrolling strip', pg.evaluate("() => { const p = document.querySelector('.pills'); return p.scrollWidth <= p.clientWidth + 1 && getComputedStyle(p).overflowX === 'visible'; }"))
            pill_rows = pg.evaluate("() => [...document.querySelectorAll('.pill')].map(e => e.innerText.replace(/\\s+/g, ' '))")
            check('Every status row is fully readable', all(len(x) > 8 for x in pill_rows) and len(pill_rows) == 3, str(pill_rows))

            # processing switched off: the tab says so and one tap turns it on
            go(pg, base + '/#home')
            pg.click('form.qs:has(input[name="processing_enabled"]) button')          # the Home quick switch is the way to turn it off
            pg.wait_for_timeout(900)
            go(pg, base + '/#queue')
            check('Processing OFF: Hàng đợi explains it and offers the switch', 'đang TẮT' in pg.inner_text('#queue') and pg.is_visible('#queue button:has-text("Bật xử lý video")'), pg.inner_text('#queue')[:900].replace(chr(10), ' / '))
            pg.click('#queue button:has-text("Bật xử lý video")')
            pg.wait_for_timeout(900)
            check('The switch turns processing on and returns to Hàng đợi', core.Store(tmp).settings()['processing_enabled'] is True and pg.evaluate("() => location.hash") == '#queue')
            check('Then the process button is live and counts the waiting videos', pg.is_enabled('#queue button:has-text("Xử lý 3 video chờ")'))

            # publish tab with nothing processed: it must say why, not just be empty
            for j in store.ready_list():
                store.decide(j['id'], 'reject')
            go(pg, base + '/#publish')
            guide = pg.inner_text('#publish')
            if SHOTS:
                pg.screenshot(path=str(SHOTS / '375x812_publish_empty.png'), full_page=True)
            check('Empty Đăng bài explains what is going on and how to continue', 'Chưa có video nào xử lý xong' in guide and '3 video đang chờ xử lý' in guide and pg.is_visible('#publish button:has-text("Xử lý ngay (3)")'), guide[:200])

            go(pg, base + '/#home')
            FakeAgent.calls.clear()
            pg.click('#control button[value="process"]')
            pg.wait_for_selector('#queue .taskpanel[data-running="0"]', timeout=15000)
            pg.wait_for_timeout(600)
            check('Process button reports why nothing ran or what ran', len(pg.inner_text('#queue .taskpanel')) > 20, pg.inner_text('#queue .taskpanel')[:100])
            check('Process does not call the browser agent', not FakeAgent.calls, str(FakeAgent.calls))

            check('No console or page errors during flows', not errors, '; '.join(errors[:3]))
            ctx.close()
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(5)
        except Exception:
            server.kill()
        agent.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    print('\n%d checks, %d failed' % (len(results), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
