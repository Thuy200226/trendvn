"""End-to-end check of the dashboard in a real Chrome: layout audit at many screen sizes plus every button flow.

Run:  .venv/bin/python tests/e2e/ui_e2e.py [--shots DIR]     (needs Playwright and Chrome; not part of `unittest discover`)
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))
from trendvn_worker.store import Store  # noqa: E402

SHOTS = None
if "--shots" in sys.argv:
    SHOTS = Path(sys.argv[sys.argv.index("--shots") + 1])
    SHOTS.mkdir(parents=True, exist_ok=True)
SAMPLE = (
    Path(os.environ["TRENDVN_SAMPLE"])
    if os.environ.get("TRENDVN_SAMPLE")
    else next(iter(sorted((ROOT / "data" / "worker" / "jobs").glob("*/final.mp4"))), None)
)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeAgent(BaseHTTPRequestHandler):
    calls = []
    mode = "ok"
    store = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(n) or b"{}")
        FakeAgent.calls.append((self.path, payload))
        if FakeAgent.mode == "busy":
            return self.reply(409, {"error": "busy"})
        if self.path in ("/api/search", "/api/search/open"):
            return self.reply(
                200,
                {
                    "items": [
                        {
                            "source_id": "1234567890",
                            "title": "Samsung Galaxy S24",
                            "platform": "tiktok",
                            "url": "https://www.tiktok.com/@creator/video/1234567890",
                            "media": {"kind": "direct", "url": "https://example.com/video.mp4"},
                        },
                        {
                            "source_id": "1234567891",
                            "title": "Samsung Galaxy S23",
                            "platform": "tiktok",
                            "url": "https://www.tiktok.com/@creator/video/1234567891",
                        },
                    ]
                },
            )
        if self.path == "/api/channel/login":
            time.sleep(1.2)  # the owner's window is open for a while: the card shows it
            FakeAgent.store.channel_report(payload["account"], payload["channel"], "ok", "")
            return self.reply(200, {"ok": True, "who": "", "channel": payload["channel"]})
        if self.path == "/api/channel/check":
            FakeAgent.store.channel_report(payload["account"], payload["channel"], "out", "")
            return self.reply(200, {"logged_in": False, "channel": payload["channel"]})
        if self.path == "/api/search/download":
            with FakeAgent.store.transaction() as db:
                db.execute("UPDATE jobs SET state='queued',reason='' WHERE id=?", (payload["job_id"],))
            return self.reply(200, {"state": "queued"})
        if self.path == "/api/collect":
            time.sleep(2.2)
            return self.reply(
                200,
                {
                    "report": {
                        "douyin": {
                            "status": "ok",
                            "summary": {"jingxuan": {"seen": 47, "qualified": 9, "baseline": False, "new": 3}, "media": {"downloaded": 2}},
                        },
                        "kuaishou": {
                            "status": "ok",
                            "summary": {
                                "brilliant": {"seen": 98, "qualified": 19, "baseline": False, "new": 5},
                                "media": {"downloaded": 1},
                            },
                        },
                        "tiktok": {"status": "skipped", "reason": "Cần IP US để lấy xu hướng đúng quốc gia; IP hiện tại: VN."},
                        "instagram": {"status": "skipped", "reason": "Cần IP US"},
                    }
                },
            )
        if self.path == "/api/publish":
            time.sleep(1.0)
            return self.reply(
                200, {"status": "published", "url": "https://www.tiktok.com/@u/video/7691188901918264597", "id": payload.get("job_id")}
            )
        if self.path == "/api/dry-run":
            time.sleep(0.6)
            return self.reply(200, {"status": "dry_run", "reason": "ok", "screenshot": "/tmp/x.png"})
        if self.path == "/api/stats":
            return self.reply(200, {"read": 3, "matched": 2})
        self.reply(404, {"error": "nf"})

    def reply(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def seed(root):
    s = Store(root)
    now = time.time()
    (Path(root) / "gemini.key").write_text("x" * 30)
    s.update_settings({"processing_enabled": True, "visibility": "self"})
    s.heartbeat(
        "discovery", True, {"douyin": {"jingxuan": {"seen": 47}}, "tiktok": "Cần IP US để lấy xu hướng đúng quốc gia; IP hiện tại: VN."}
    )
    s.heartbeat("publisher", True, "Đã đăng nhập TikTok, sẵn sàng")

    def add(state, platform, title, **kw):
        jid = kw.get("id") or uuid.uuid4().hex
        cols = dict(
            id=jid,
            platform=platform,
            source_id=jid[:10],
            url="https://x/" + jid,
            country="CN",
            title=title,
            first_seen=now - 7200,
            last_seen=now,
            state=state,
            updated=now - 300,
        )
        cols.update(kw)
        with s.transaction() as db:
            db.execute("INSERT INTO jobs(%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))), list(cols.values()))
            s.event(db, jid, state, kw.get("reason", ""))
        return jid

    ids = []
    titles = [
        "舅舅别睡了，给我闺蜜也泡一杯奶奶 #舅舅带娃 một tiêu đề rất rất dài để thử việc xuống dòng không làm vỡ thẻ trên màn hình điện thoại nhỏ",
        "Khoảnh khắc thú vị",
        "Bài hát hay nhất tuần",
    ]
    for n, title in enumerate(titles):
        jid = uuid.uuid4().hex
        folder = Path(root) / "jobs" / jid
        folder.mkdir(parents=True)
        if SAMPLE:
            shutil.copy(SAMPLE, folder / "final.mp4")
            poster = SAMPLE.with_name("poster.jpg")
            if poster.exists():
                shutil.copy(poster, folder / "poster.jpg")
        analysis = {
            "kind": "dialogue" if n < 2 else "music",
            "caption_vi": ["Lập luận đòi lương khiến ông bố cạn lời", "Khoảnh khắc thú vị", "Giai điệu nghe là nghiện"][n],
            "hashtags": ["haihuoc", "giadinh", "tinhhuonghai"] if n == 0 else (["vui"] if n == 1 else []),
        }
        info = {
            "w": 1080,
            "h": 1920,
            "duration": 38.2,
            "size": 4100000,
            "poster": bool(SAMPLE and (SAMPLE.with_name("poster.jpg")).exists()),
            "reframed": n == 1,
            "route": "vietsub",
        }
        ids.append(
            add(
                "ready" if n < 2 else "awaiting_approval",
                "douyin" if n != 1 else "kuaishou",
                title,
                id=jid,
                output_file=str(folder / "final.mp4"),
                output_hash="h",
                analysis=json.dumps(analysis),
                route="vietsub" if n < 2 else "original",
                meta=json.dumps({"score": 900000 - n * 1000, "likes": 386000, "age_h": 30}),
                output_info=json.dumps(info),
            )
        )
    for i in range(3):
        add("queued", "douyin", "Video chờ xử lý %d" % i, meta=json.dumps({"score": 1000 * (i + 1)}))
    src = Path(root) / "inbox" / "r.mp4"
    src.parent.mkdir(exist_ok=True)
    if SAMPLE:
        shutil.copy(SAMPLE, src)
    add(
        "needs_review",
        "kuaishou",
        "Video bị giữ lại xem xét",
        source_file=str(src),
        reason="Sensitive content (politics, violence, tragedy, adult or medical claims) needs review",
    )
    add(
        "published",
        "douyin",
        "Bài đã đăng thứ nhất",
        publish_url="https://www.tiktok.com/@u/video/7690000000000000001",
        published_at=now - 86400,
        route="vietsub",
    )
    s.record_stats([{"video_id": "7690000000000000001", "views": 15400, "likes": 1200}])
    for i in range(5):
        add("baseline", "douyin", "baseline %d" % i)
    seed_chat(s)
    return ids


def seed_chat(s):
    """A conversation that shows every kind of answer: long names, a different model, a failed search, a saved link and one still to confirm."""
    from trendvn_worker.domain.search_queries import explicit, query_plan

    username = s.account("main")["username"]
    identity = explicit("bàn phím mchose ace68")
    identity.update(
        queries=query_plan(identity), warnings=["Ảnh được nhận là KZZI K68; không khớp tên bạn nhập. Giữ nguyên tên bạn nhập."], links=[]
    )
    long_name = "Bàn phím cơ không dây MCHOSE ACE68 Air 8K polling rate hot-swap switch từ tính siêu dài để thử việc xuống dòng"
    s.chat_ask(
        "main",
        {
            "text": "bàn phím mchose ace68 " + "rất dài " * 12,
            "files": [{"name": "anh-ban-phim-ten-tep-rat-dai-de-thu-xuong-dong.png", "kind": "image"}],
            "link": False,
        },
        "product",
        {},
    )
    product = s.chat_thread()[-1]["id"]
    s.chat_set(product, "done", identity=identity)
    results = [
        {"source_id": "7300000000000000001", "platform": "tiktok", "title": long_name, "url": "https://www.tiktok.com/@a/video/7300000000000000001",
         "match": {"level": "candidate", "score": 100, "reason": "Khớp 100%; cần xem video và biến thể"}},
        {"source_id": "7300000000000000002", "platform": "tiktok", "title": "MCHOSE ACE68 Air", "url": "https://www.tiktok.com/@a/video/7300000000000000002",
         "match": {"level": "different", "score": 0, "reason": "Có biến thể khác với sản phẩm yêu cầu"}},
    ]  # fmt: skip
    body = {
        "identity": identity,
        "source": "tiktok",
        "account_username": username,
        "product": product,
        "results": results,
        "note": "Ứng viên từ TikTok",
    }
    s.chat_add("bot", "videos", body, account="main")
    failed = s.chat_add(
        "bot",
        "videos",
        body | {"results": [], "error": "TikTok yêu cầu xác minh; hãy tự xác minh rồi tìm lại"},
        state="error",
        account="main",
    )
    assert failed
    found = {
        "input": "https://vt.tiktok.com/ZSe2eSaved/",
        "product_id": "1729384756102938475",
        "title": long_name,
        "markers": {"share_creator_id": "7"},
        "tracked": True,
    }
    checks = [
        {"label": "Mã sản phẩm", "state": "ok", "detail": "Mã 1729384756102938475 trùng với sản phẩm đang tìm"},
        {"label": "Dấu hiệu nhà sáng tạo", "state": "ok", "detail": "Có tham số của người chia sẻ (share_creator_id)"},
        {
            "label": "Mã nhà sáng tạo",
            "state": "info",
            "detail": "Đây là link đầu tiên của tài khoản: xác nhận để lưu làm mốc cho các link sau",
        },
    ]
    verdict = {
        "verdict": "exact",
        "summary": "Đúng sản phẩm: cùng mã sản phẩm.",
        "kind": "affiliate",
        "needs_confirmation": True,
        "checks": checks,
    }
    s.chat_add("bot", "link", {"url": found["input"], "found": found, "verdict": verdict, "saved": True}, account="main")
    todo = dict(found, input="https://vt.tiktok.com/ZSe2eNew/", product_id="1729384756102938999")
    s.chat_add(
        "bot",
        "link",
        {"url": todo["input"], "found": todo, "verdict": verdict | {"verdict": "found", "summary": "Đã đọc được sản phẩm từ link."}},
        account="main",
    )
    s.channel_report("main", "douyin", "wall")
    s.channel_report("main", "tiktok", "ok", "chu_shop")
    s.commission_save("main", found | {"title": long_name})


AUDIT_JS = r"""
async () => {
  const issues = [];
  const frame = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
  document.documentElement.style.scrollBehavior = 'auto';
  scrollTo(0, 0);
  await frame();  // a hash change can scroll to its target a frame later; measure only once the page rests at the top
  scrollTo(0, 0);
  await frame();
  if (scrollY !== 0) issues.push('page did not rest at the top: scrollY ' + scrollY);
  // a chat thread scrolls inside itself: only the part of a message that shows inside it counts
  const box = e => { const r = e.getBoundingClientRect(), t = e.closest('.thread'); if (!t || t === e) return r; const c = t.getBoundingClientRect(); return { left: Math.max(r.left, c.left), right: Math.min(r.right, c.right), top: Math.max(r.top, c.top), bottom: Math.min(r.bottom, c.bottom), width: Math.min(r.right, c.right) - Math.max(r.left, c.left), height: Math.min(r.bottom, c.bottom) - Math.max(r.top, c.top) }; };
  const vis = e => { const r = box(e), s = getComputedStyle(e); if (e.closest('details:not([open])') && !e.matches('summary') && !e.closest('summary')) return false; return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const desc = e => (e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/)[0] : '') + ' "' + (e.innerText || e.value || '').trim().slice(0, 28).replace(/\n/g, ' ') + '"');
  if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('horizontal overflow: scrollWidth ' + document.documentElement.scrollWidth + ' > ' + innerWidth);
  const nav = document.querySelector('.bottomnav');
  const navVisible = nav && vis(nav);
  const sel = '.card,.kpi,.pill,.qs,.step,.banner,.taskpanel,.strip>div,tr:not(.hd),.tag,.chip,video,textarea,input:not([type=hidden]),select,button,.topnav>a,h1,h2,h3,.lint,.note,.ttl,.facts,.tags,.btns>*,.btngrid>*,label';
  const els = [...document.querySelectorAll(sel)].filter(vis).filter(e => !e.closest('.bottomnav') && !e.closest('header') || e.closest('header') && innerWidth > 720);
  for (let i = 0; i < els.length; i++) for (let j = i + 1; j < els.length; j++) {
    const a = els[i], b = els[j];
    if (a.contains(b) || b.contains(a)) continue;
    const ra = box(a), rb = box(b);
    const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (w > 2 && h > 2) issues.push('overlap ' + Math.round(w) + 'x' + Math.round(h) + ': ' + desc(a) + '  <->  ' + desc(b));
  }
  const cards = [...document.querySelectorAll('section.on > .card, section.on .stack > .card, section.on > form.card')].filter(vis);
  for (let i = 1; i < cards.length; i++) {
    const p = cards[i - 1].getBoundingClientRect(), c = cards[i].getBoundingClientRect();
    if (c.top >= p.bottom - 1 && c.top - p.bottom < 6 && Math.abs(c.left - p.left) < 4) issues.push('cards touch (gap ' + Math.round(c.top - p.bottom) + 'px): ' + desc(cards[i - 1]) + ' / ' + desc(cards[i]));
  }
  [...document.querySelectorAll('button,select,input:not([type=hidden]),.bottomnav a,.topnav a')].filter(vis).forEach(e => {
    const r = e.getBoundingClientRect();  // the whole control, even where a scrolling thread cuts it off
    if (r.height < 43.5 && !e.closest('.fs > summary')) issues.push('small tap target ' + Math.round(r.width) + 'x' + Math.round(r.height) + ': ' + desc(e));
  });
  [...document.querySelectorAll('body *')].filter(vis).forEach(e => {
    const s = getComputedStyle(e);
    if (e.scrollWidth > e.clientWidth + 2 && ['hidden', 'clip'].includes(s.overflowX) && !['VIDEO', 'SELECT', 'TEXTAREA', 'INPUT', 'BUTTON'].includes(e.tagName) && e.clientWidth > 0) issues.push('clipped text: ' + desc(e));
    if (parseFloat(s.fontSize) < (innerWidth <= 370 && e.closest('.bottomnav') ? 10 : 11) && (e.innerText || '').trim() && e.children.length === 0 && !e.closest('svg')) issues.push('tiny font ' + s.fontSize + ': ' + desc(e));
    const r = box(e);
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
    const last = [...document.querySelectorAll('main *')].filter(vis).map(e => box(e).bottom).reduce((m, v) => Math.max(m, v), 0);
    if (last > navTop - 2) issues.push('bottom nav covers the end of the page: content ends at ' + Math.round(last) + ', nav starts at ' + Math.round(navTop));
    scrollTo(0, 0);
  }
  return issues;
}
"""


def main():
    from playwright.sync_api import sync_playwright

    tmp = tempfile.mkdtemp(prefix="trendvn-e2e-")
    results = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(("PASS " if ok else "FAIL ") + name + (("  -> " + detail) if detail and not ok else ""), flush=True)

    ids = seed(tmp)
    FakeAgent.store = Store(tmp)
    agent_port, port = free_port(), free_port()
    agent = ThreadingHTTPServer(("127.0.0.1", agent_port), FakeAgent)
    threading.Thread(target=agent.serve_forever, daemon=True).start()
    env = dict(
        os.environ,
        TRENDVN_DATA=tmp,
        TRENDVN_TOKEN="t" * 40,
        TRENDVN_PORT=str(port),
        TRENDVN_PUBLIC_PORT=str(port),
        TRENDVN_AGENT_URL="http://127.0.0.1:%d" % agent_port,
    )
    server = subprocess.Popen(
        [sys.executable, "-m", "trendvn_worker"],
        cwd=str(ROOT / "services" / "worker" / "src"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = "http://localhost:%d" % port
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            errors = []

            def go(pg, url):
                """A fresh page at `url`, surviving a form redirect still in flight (it would otherwise abort the new navigation). When only
                the #hash differs from where the page is, goto changes the hash without loading anything: the page is reloaded then."""
                for _ in range(3):
                    try:
                        pg.wait_for_load_state("load")
                        same_page = pg.url.split("#")[0] == url.split("#")[0]
                        response = pg.goto(url, wait_until="load")
                        return pg.reload(wait_until="load") if same_page else response
                    except Exception as e:
                        if not any(
                            text in str(e) for text in ("interrupted by another navigation", "ERR_ABORTED")
                        ):  # the page may reload itself when a task ends
                            raise
                        pg.wait_for_timeout(500)
                return pg.goto(url, wait_until="load")

            def new_ctx(w, h, mobile):
                ctx = browser.new_context(
                    viewport={"width": w, "height": h},
                    is_mobile=mobile,
                    has_touch=mobile,
                    device_scale_factor=2 if mobile else 1,
                    accept_downloads=False,
                )
                pg = ctx.new_page()
                pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                pg.on("pageerror", lambda e: errors.append(str(e)))
                return ctx, pg

            # ---------------- pass A: layout audit on every tab and size
            sizes = [
                (320, 640, True),
                (360, 740, True),
                (375, 812, True),
                (414, 896, True),
                (768, 1024, True),
                (1280, 900, False),
                (1440, 900, False),
            ]
            for w, h, mobile in sizes:
                ctx, pg = new_ctx(w, h, mobile)
                go(pg, base + "/")
                for tab in ("home", "search", "queue", "publish", "attention", "posted", "more"):
                    pg.evaluate("t => { location.hash = '#' + t; }", tab)
                    pg.wait_for_timeout(250)
                    if tab == "more":
                        pg.evaluate("() => document.querySelectorAll('#more details').forEach(d => d.open = true)")
                        pg.wait_for_timeout(150)
                    issues = pg.evaluate(AUDIT_JS)
                    check(
                        "layout %dx%d %-9s" % (w, h, tab),
                        not issues,
                        "; ".join(issues[:4]) + (" (+%d more)" % (len(issues) - 4) if len(issues) > 4 else ""),
                    )
                    if SHOTS and w in (375, 1280):
                        pg.screenshot(path=str(SHOTS / ("%dx%d_%s.png" % (w, h, tab))), full_page=(w == 375))
                ctx.close()
            check("no console or page errors during layout audit", not errors, "; ".join(errors[:3]))

            # ---------------- pass B: flows (phone size)
            errors.clear()
            ctx, pg = new_ctx(375, 812, True)
            pg.on("dialog", lambda d: d.accept())
            go(pg, base + "/#home")
            FakeAgent.calls.clear()
            pg.click('#control button[value="update"]')
            pg.wait_for_selector('#control .taskpanel[data-running="1"]', timeout=6000)
            check("Start: progress panel appears while running", True)
            check(
                "Start: buttons disabled while a task runs",
                pg.evaluate("() => [...document.querySelectorAll('#control button')].every(b => b.disabled)") is True,
            )
            pg.wait_for_selector('#control .taskpanel[data-running="0"]', timeout=30000)
            pg.wait_for_timeout(600)
            panel = pg.inner_text("#control .taskpanel")
            check("Start: result lists each source in Vietnamese", "Douyin" in panel and "Kuaishou" in panel, panel[:120])
            check(
                "Start: agent was called exactly once for collect",
                [c for c in FakeAgent.calls if c[0] == "/api/collect"] and len([c for c in FakeAgent.calls if c[0] == "/api/collect"]) == 1,
            )
            check("Start: process step ran (no Gemini in the test, so it reports the state)", "Xử lý" in panel)

            # double click protection
            FakeAgent.calls.clear()
            go(pg, base + "/#home")
            pg.evaluate("() => { const b = document.querySelector('#control button[value=\"collect\"]'); b.click(); b.click(); }")
            pg.wait_for_timeout(3500)
            check(
                "Double click starts a single task",
                len([c for c in FakeAgent.calls if c[0] == "/api/collect"]) == 1,
                str(len(FakeAgent.calls)),
            )

            # agent busy
            FakeAgent.mode = "busy"
            go(pg, base + "/#home")
            pg.click('#control button[value="collect"]')
            pg.wait_for_selector('#queue .taskpanel[data-running="0"]', timeout=15000)
            pg.wait_for_timeout(800)
            check("Collect button lands on the Hàng đợi tab and shows its result there", pg.evaluate("() => location.hash") == "#queue")
            check(
                "Agent busy: clear message, no crash", "bận" in pg.inner_text("#queue .taskpanel"), pg.inner_text("#queue .taskpanel")[:120]
            )
            FakeAgent.mode = "ok"
            # agent down
            agent.shutdown()
            agent.server_close()
            go(pg, base + "/#home")
            pg.click('#control button[value="collect"]')
            pg.wait_for_timeout(2500)
            go(pg, base + "/#home")
            check(
                "Agent down: owner-readable error",
                "agent" in pg.inner_text("#control .taskpanel").lower(),
                pg.inner_text("#control .taskpanel")[:150],
            )
            agent = ThreadingHTTPServer(("127.0.0.1", agent_port), FakeAgent)
            threading.Thread(target=agent.serve_forever, daemon=True).start()

            # publish flows
            go(pg, base + "/#publish")
            cards = pg.query_selector_all("#publish form.ready")
            check("Publish tab lists every processed video", len(cards) == 3, str(len(cards)))
            check("Each card has Đăng ngay, Xem thử, Lưu, Bỏ", all(len(c.query_selector_all("button")) >= 4 for c in cards))
            first_id = cards[0].get_attribute("data-id")
            ta = cards[0].query_selector("textarea")
            check(
                "Caption box shows caption with hashtags",
                "#haihuoc" in ta.input_value() and "#xuhuong" in ta.input_value(),
                ta.input_value(),
            )
            FakeAgent.calls.clear()
            ta.fill("Mô tả sửa tay để kiểm tra #kiemtra #haihuoc #vui")
            cards[0].query_selector('button[value="publish"]').click()
            pg.wait_for_selector("#publish .taskpanel", timeout=8000)
            check(
                "Post now: progress is shown on the Publish tab itself",
                "Đăng video" in pg.inner_text("#publish .taskpanel"),
                pg.inner_text("#publish .taskpanel")[:100],
            )
            pg.wait_for_selector('#publish .taskpanel[data-running="0"]', timeout=20000)
            pg.wait_for_timeout(800)
            check(
                "Post now: success message with link is visible there",
                "Đã đăng" in pg.inner_text("#publish .taskpanel"),
                pg.inner_text("#publish .taskpanel")[:160],
            )
            pub = [c for c in FakeAgent.calls if c[0] == "/api/publish"]
            check("Post now: agent receives that exact video", len(pub) == 1 and pub[0][1].get("job_id") == first_id, str(pub))
            st = Store(tmp)
            edited = [j for j in st.ready_list() if j["id"] == first_id][0]
            check(
                "Post now: edited caption saved before posting",
                edited["caption"].startswith("Mô tả sửa tay") and edited["caption_edited"],
                edited["caption"],
            )
            go(pg, base + "/#publish")
            check('Edited caption persists and shows "đã sửa tay"', "đã sửa tay" in pg.inner_text('form.ready[data-id="%s"]' % first_id))
            FakeAgent.calls.clear()
            pg.query_selector('form.ready[data-id="%s"] button[value="dryrun"]' % first_id).click()
            pg.wait_for_timeout(2500)
            check(
                "Rehearsal: agent dry-run called for that video",
                any(c[0] == "/api/dry-run" and c[1].get("job_id") == first_id for c in FakeAgent.calls),
                str(FakeAgent.calls),
            )
            go(pg, base + "/#publish")
            pg.query_selector('form.ready[data-id="%s"] button[value="reset"]' % first_id).click()
            pg.wait_for_timeout(800)
            check(
                "Reset returns to the system caption", not [j for j in Store(tmp).ready_list() if j["id"] == first_id][0]["caption_edited"]
            )
            go(pg, base + "/#publish")
            pg.query_selector('form.ready[data-id="%s"] button[formaction="/decide"]' % ids[1]).click()
            pg.wait_for_timeout(800)
            check("Discard removes the video from the list", ids[1] not in [j["id"] for j in Store(tmp).ready_list()])
            # ---------------- Hàng đợi tab (the Start flow above has processed the seeded queue, so put three videos back in it)
            store = Store(tmp)
            for i in range(3):
                jid = uuid.uuid4().hex
                with store.transaction() as db:
                    db.execute(
                        "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,updated,meta) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            jid,
                            "douyin",
                            jid[:10],
                            "https://x/" + jid,
                            "CN",
                            "Video chờ xử lý %d" % i,
                            time.time() - 600 + i,
                            time.time(),
                            "queued",
                            time.time(),
                            json.dumps({"score": 1000 * (i + 1)}),
                        ),
                    )
            go(pg, base + "/#queue")
            rows = pg.evaluate(
                "() => [...document.querySelectorAll('#queue .tablewrap')][0] ? [...document.querySelectorAll('#queue .tablewrap')][0].innerText : ''"
            )
            check("Hàng đợi tab lists the waiting videos", all("Video chờ xử lý %d" % i in rows for i in range(3)), rows[:120])
            check(
                "Bottom nav has seven entries and Hàng đợi carries the waiting count",
                pg.evaluate("() => document.querySelectorAll('.bottomnav a').length") == 7
                and pg.inner_text('.bottomnav a[data-go="queue"] i') == "3",
            )
            check(
                "Nav badge for waiting videos is not red (it is not an alarm)",
                pg.evaluate("() => document.querySelector('.bottomnav a[data-go=queue] i').className") == "n",
            )
            pg.click('#queue a.step[href="#publish"]')
            pg.wait_for_timeout(300)
            check("Funnel step opens the matching tab", pg.evaluate("() => location.hash") == "#publish" and pg.is_visible("#publish"))
            go(pg, base + "/#home")
            check(
                "Status is a card of rows, not a scrolling strip",
                pg.evaluate(
                    "() => { const p = document.querySelector('.pills'); return p.scrollWidth <= p.clientWidth + 1 && getComputedStyle(p).overflowX === 'visible'; }"
                ),
            )
            pill_rows = pg.evaluate("() => [...document.querySelectorAll('.pill')].map(e => e.innerText.replace(/\\s+/g, ' '))")
            check(
                "Every status row is fully readable", all(len(x) > 8 for x in pill_rows) and len(pill_rows) == 4, str(pill_rows)
            )  # collector, publisher, golden hour, disk

            # processing switched off: the tab says so and one tap turns it on
            go(pg, base + "/#home")
            pg.click('form.qs:has(input[name="processing_enabled"]) button')  # the Home quick switch is the way to turn it off
            pg.wait_for_timeout(900)
            go(pg, base + "/#queue")
            check(
                "Processing OFF: Hàng đợi explains it and offers the switch",
                "đang TẮT" in pg.inner_text("#queue") and pg.is_visible('#queue button:has-text("Bật xử lý video")'),
                pg.inner_text("#queue")[:900].replace(chr(10), " / "),
            )
            pg.click('#queue button:has-text("Bật xử lý video")')
            pg.wait_for_timeout(900)
            check(
                "The switch turns processing on and returns to Hàng đợi",
                Store(tmp).settings()["processing_enabled"] is True and pg.evaluate("() => location.hash") == "#queue",
            )
            check(
                "Then the process button is live and counts the waiting videos",
                pg.is_enabled('#queue button:has-text("Xử lý 3 video chờ")'),
            )

            # publish tab with nothing processed: it must say why, not just be empty
            for j in store.ready_list():
                store.decide(j["id"], "reject")
            go(pg, base + "/#publish")
            guide = pg.inner_text("#publish")
            if SHOTS:
                pg.screenshot(path=str(SHOTS / "375x812_publish_empty.png"), full_page=True)
            check(
                "Empty Đăng bài explains what is going on and how to continue",
                "Chưa có video nào xử lý xong" in guide
                and "3 video đang chờ xử lý" in guide
                and pg.is_visible('#publish button:has-text("Xử lý ngay (3)")'),
                guide[:200],
            )

            go(pg, base + "/#home")
            FakeAgent.calls.clear()
            pg.click('#control button[value="process"]')
            pg.wait_for_selector('#queue .taskpanel[data-running="0"]', timeout=15000)
            pg.wait_for_timeout(600)
            check(
                "Process button reports why nothing ran or what ran",
                len(pg.inner_text("#queue .taskpanel")) > 20,
                pg.inner_text("#queue .taskpanel")[:100],
            )
            check("Process does not call the browser agent", not FakeAgent.calls, str(FakeAgent.calls))

            # accounts: add one, choose its topics by tapping, save, see where a video would go, delete it
            go(pg, base + "/#accounts")
            check("Accounts section opens from its link", pg.is_visible("#accounts .acct"))
            pg.fill('#accounts form[action="/account-add"] input[name="username"]', "kenh_meo")
            for topic in ("pets", "food"):
                pg.click('#accounts form[action="/account-add"] label.tg:has(input[value="%s"])' % topic)
            pg.click('#accounts form[action="/account-add"] button')
            pg.wait_for_selector('#accounts .acct:has-text("@kenh_meo")', timeout=6000)
            added = Store(tmp).account("kenh_meo")
            check(
                "Adding an account by tapping topics saves exactly those topics", added and added["topics"] == ["pets", "food"], str(added)
            )
            card = '#accounts .acct:has-text("@kenh_meo")'
            pg.click(card + " label.tg:has(input[value='pets'])")  # untick pets
            pg.click(card + " label.tg:has(input[value='gaming'])")  # tick gaming
            pg.click(card + " summary")
            pg.fill(card + ' input[name="daily_limit"]', "4")
            pg.click(card + " button.go")
            pg.wait_for_timeout(900)
            saved = Store(tmp).account("kenh_meo")
            check(
                "Saving changes the topics and the account's own daily limit",
                saved["topics"] == ["food", "gaming"] and saved["daily_limit"] == 4,
                str(saved),
            )
            check(
                "The topics the accounts take are listed for the collector",
                {"food", "gaming"} <= set(Store(tmp).wanted_topics()),
            )
            pg.click(card + ' button:has-text("Xóa")')
            pg.wait_for_timeout(900)
            check("Deleting removes the account", Store(tmp).account("kenh_meo") is None)
            pg.fill('#accounts form[action="/account-add"] input[name="username"]', "no_topics")
            pg.click('#accounts form[action="/account-add"] button')
            pg.wait_for_timeout(900)
            check(
                "Adding without a topic is refused with a message", Store(tmp).account("no_topics") is None and pg.is_visible(".flash.bad")
            )

            # The product chat, through the real HTTP worker and the isolated fake agent.
            go(pg, base + "/#search")
            check("Chat: the file picker stays hidden behind the attach button", not pg.is_visible('[data-chat-form] input[type="file"]'))
            if SHOTS:
                pg.locator("[data-chat]").screenshot(path=str(SHOTS / "chat_375.png"))
            find = pg.locator('button[data-chat-act="find"][data-source="douyin"]')
            asked = find.count()
            pg.fill('[data-chat-form] textarea[name="text"]', "Samsung Galaxy S24")
            pg.click("[data-chat-form] button.send")
            pg.wait_for_function(
                "n => document.querySelectorAll('button[data-chat-act=find][data-source=douyin]').length > n", arg=asked, timeout=10000
            )
            check(
                "Chat: the message and the recognised product appear without a reload",
                "Samsung Galaxy S24" in pg.inner_text("#chat-thread"),
            )
            check("Chat: the composer is cleared after sending", pg.input_value('[data-chat-form] textarea[name="text"]') == "")
            FakeAgent.calls.clear()
            find.last.click()
            pg.wait_for_selector('#chat-thread > .msg.bot:last-child[data-state="done"] article', timeout=10000)
            cards = pg.locator("#chat-thread > .msg.bot:last-child article")
            check("Chat: a candidate of another model cannot be picked", cards.nth(1).locator('button[data-chat-act="pick"]').count() == 0)
            check("Chat: the search is pinned to the chosen account", FakeAgent.calls[0][1]["account"] == "main")
            check("Chat: the chosen source reaches the browser agent", FakeAgent.calls[0][1]["source"] == "douyin")
            check(
                "Chat: the search words are shown before any pick",
                "Douyin:" in pg.locator('#chat-thread .msg.bot:has(button[data-chat-act="find"])').last.inner_text(),
            )
            cards.first.locator('button[data-chat-act="pick"]').click()
            check("Chat: a pick without the owner's tick is refused in words", "tích ô xác nhận" in pg.inner_text("[data-chat-message]"))
            with FakeAgent.store.connect() as db:
                check(
                    "Chat: nothing was queued by the refused pick",
                    db.execute("SELECT count(*) FROM jobs WHERE source_id='1234567890'").fetchone()[0] == 0,
                )
            cards.first.locator("[data-chat-confirm]").check()
            cards.first.locator('button[data-chat-act="pick"]').click()
            pg.wait_for_function(
                "() => !document.querySelector('#chat-thread > .msg.bot:last-child article button[data-chat-act=pick]')", timeout=10000
            )
            for _ in range(50):  # the download is a background task: the page shows the pick at once, the queue a moment later
                with FakeAgent.store.connect() as db:
                    selected = db.execute("SELECT state,search_account FROM jobs WHERE source_id='1234567890'").fetchone()
                if selected and selected[0] == "queued":
                    break
                pg.wait_for_timeout(200)
            check("Chat: the picked video enters the processing queue for that account", selected and tuple(selected) == ("queued", "main"))
            # the seeded failed search offers the owner's own verification window; it asks again with the Chinese words kept
            FakeAgent.calls.clear()
            pg.locator('button[data-human="true"]').first.click()
            pg.wait_for_timeout(1500)
            check(
                "Chat: the verification window searches with the Chinese words and the product model kept",
                any(
                    path == "/api/search/open" and payload["queries"]["douyin"] == "迈从 ACE68 磁轴键盘"
                    for path, payload in FakeAgent.calls
                ),
            )
            # a pasted link that is still to be confirmed: the owner confirms, then can copy it
            copies = pg.locator("[data-copy]").count()
            pg.locator('button[data-chat-act="confirm"]').first.click()
            pg.wait_for_function("n => document.querySelectorAll('[data-copy]').length > n", arg=copies, timeout=10000)
            check("Chat: a confirmed link is kept for the account", Store(tmp).commission_get("main", "1729384756102938999") is not None)
            pg.locator("[data-copy]").last.click()
            pg.wait_for_timeout(400)  # the browser may refuse the clipboard first and the script then copies another way
            check("Chat: the copy button says it copied", pg.locator("[data-copy]").last.inner_text() == "Đã chép")
            # signing in to a search channel: a window opens on the machine, the card says so, and the column beside the chat learns the result
            go(pg, base + "/#search")
            side = pg.locator("#chat-side")
            check("Side: every state the system knows is shown", "Đòi xác minh" in side.inner_text() and "Sẵn sàng" in side.inner_text())
            pg.locator('#chat-side button[data-chat-act="login"][data-channel="douyin"]').click()
            pg.wait_for_selector("#chat-thread >> text=Đã mở cửa sổ Chrome trên máy chạy TrendVN", timeout=8000)
            check(
                "Sign-in: while the window is open the card says whose window it is and that nothing is typed for the owner",
                "không nhập mật khẩu thay bạn" in pg.inner_text("#chat-thread"),
            )
            pg.wait_for_selector("#chat-thread >> text=Đã đăng nhập: tìm kiếm trên Douyin dùng được", timeout=15000)
            pg.wait_for_function("() => /Douyin[\\s\\S]*Sẵn sàng/.test(document.getElementById('chat-side').innerText)", timeout=8000)
            check(
                "Sign-in: the column beside the chat shows Douyin ready without a reload", "Đòi xác minh" not in pg.inner_text("#chat-side")
            )
            pg.locator('#chat-side button[data-chat-act="check"][data-channel="tiktok"]').click()
            pg.wait_for_selector("#chat-thread >> text=Chưa đăng nhập.", timeout=10000)
            check(
                "Check: a profile that is signed out is said so and offers the window",
                pg.locator('#chat-thread button[data-chat-act="login"][data-channel="tiktok"]').count() >= 1,
            )
            # saved links: forget; history: clear keeps what is not history
            saved_before, in_db = pg.locator("#chat-side .saved").count(), len(Store(tmp).commission_list("main"))
            pg.locator('#chat-side button[data-chat-act="forget"]').first.click()
            pg.wait_for_function("n => document.querySelectorAll('#chat-side .saved').length < n", arg=saved_before, timeout=8000)
            check(
                "Saved links: forgetting one removes it from the column and the database",
                len(Store(tmp).commission_list("main")) == in_db - 1 >= 0,
            )
            pg.locator('#chat-side button[data-chat-act="clear"]').click()
            pg.wait_for_function("() => document.getElementById('chat-thread').innerText.includes('Gửi cho mình')", timeout=8000)
            with FakeAgent.store.connect() as db:
                kept = db.execute("SELECT state FROM jobs WHERE source_id='1234567890'").fetchone()
            check(
                "History: clearing empties the thread but keeps the picked video and the sign-in states",
                kept and kept[0] == "queued" and "Sẵn sàng" in pg.inner_text("#chat-side"),
            )

            # files stay in memory, are sent as content, and can be removed
            captured = []

            def intercept(route):
                captured.append(route.request.post_data_json)
                route.fulfill(status=200, content_type="application/json", body='{"id":1}')

            pg.route("**/chat/send", intercept)
            pg.set_input_files(
                '[data-chat-form] input[type="file"]', {"name": "reference.txt", "mimeType": "text/plain", "buffer": b"Samsung Galaxy S24"}
            )
            check("Chat: the attached file's name is shown", pg.locator("[data-chat-files]").inner_text().startswith("📎 reference.txt"))
            pg.fill('[data-chat-form] textarea[name="text"]', "ghi chú")
            pg.press('[data-chat-form] textarea[name="text"]', "Control+Enter")
            pg.wait_for_timeout(600)
            check(
                "Chat: Ctrl+Enter sends the real content, not the file name",
                captured and captured[-1]["files"][0]["data"] == "U2Ftc3VuZyBHYWxheHkgUzI0" and captured[-1]["text"] == "ghi chú",
            )
            check("Chat: sending clears the attachments", not pg.locator("[data-chat-files]").inner_text())
            pg.set_input_files('[data-chat-form] input[type="file"]', {"name": "gone.txt", "mimeType": "text/plain", "buffer": b"x"})
            pg.click("[data-chat-files] button")
            check("Chat: an attachment can be removed before sending", not pg.locator("[data-chat-files]").inner_text())
            pg.locator("[data-chat]").evaluate(
                "e => { const d=new DataTransfer(); d.setData('text/plain','https://vt.tiktok.com/ZSdropped/'); e.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:d})); }"
            )
            check("Chat: a dragged link lands in the message", "ZSdropped" in pg.input_value('[data-chat-form] textarea[name="text"]'))
            pg.locator('[data-chat-form] textarea[name="text"]').evaluate(
                "e => { const d=new DataTransfer(); d.items.add(new File(['%PDF-1.7\\n'], 'pasted.pdf',{type:'application/pdf'})); e.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:d})); }"
            )
            check("Chat: a pasted file joins the attachments", "pasted.pdf" in pg.locator("[data-chat-files]").inner_text())
            pg.evaluate("() => { document.querySelector('[data-chat-form] input[type=file]').dispatchEvent(new Event('change')); }")
            for number in range(4):
                pg.set_input_files(
                    '[data-chat-form] input[type="file"]', {"name": "f%d.txt" % number, "mimeType": "text/plain", "buffer": b"x"}
                )
            check("Chat: more than three files are refused in words", "Tối đa 3 tệp" in pg.inner_text("[data-chat-message]"))
            pg.unroute("**/chat/send", intercept)

            check("No console or page errors during flows", not errors, "; ".join(errors[:3]))
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
    print("\n%d checks, %d failed" % (len(results), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
