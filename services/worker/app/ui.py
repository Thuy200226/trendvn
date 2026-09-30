"""Dashboard HTML for the TrendVN worker. Server-rendered, no external assets, every dynamic value escaped."""
import html
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

E = html.escape

STATE_LABELS = {
    'baseline': 'Mốc ban đầu', 'candidate': 'Ứng viên', 'queued': 'Chờ xử lý', 'processing': 'Đang xử lý',
    'awaiting_approval': 'Chờ bạn duyệt', 'ready': 'Sẵn sàng đăng', 'publishing': 'Đang đăng', 'published': 'Đã đăng',
    'needs_review': 'Cần duyệt', 'publish_unknown': 'Chưa xác nhận', 'duplicate': 'Trùng', 'failed': 'Lỗi', 'rejected': 'Đã bỏ',
}
STATE_TONE = {'published': 'good', 'ready': 'good', 'awaiting_approval': 'warn', 'needs_review': 'warn', 'publish_unknown': 'bad',
              'failed': 'bad', 'processing': 'info', 'publishing': 'info', 'queued': 'info', 'candidate': 'mute', 'baseline': 'mute',
              'duplicate': 'mute', 'rejected': 'mute'}
PLATFORM = {'douyin': ('Douyin', 'CN'), 'kuaishou': ('Kuaishou', 'CN'), 'tiktok': ('TikTok', 'US'), 'instagram': ('Instagram', 'US')}
COMPONENT = {'connected': ('Hoạt động', 'good'), 'not_connected': ('Chưa kết nối', 'mute'), 'stale': ('Lâu chưa báo cáo', 'warn'),
             'error': ('Cần chú ý', 'bad')}

EVENT_LABELS = {'processing': 'Bắt đầu xử lý', 'queued': 'Đã tải, chờ xử lý', 'ready': 'Đã dựng, sẵn sàng đăng', 'awaiting_approval': 'Chờ bạn duyệt',
                'needs_review': 'Cần bạn duyệt', 'publishing': 'Đang đăng', 'publish_published': 'Đã đăng thành công', 'publish_unknown': 'Đăng chưa xác nhận',
                'publish_failed': 'Đăng chưa thành công', 'publish_duplicate': 'Bỏ vì trùng bài đã có', 'candidate': 'Phát hiện video mới', 'failed': 'Lỗi',
                'duplicate': 'Trùng video đã có', 'released': 'Xếp lại hàng đợi', 'media_failed': 'Tải video lỗi', 'operator_approve': 'Bạn đã duyệt',
                'operator_reject': 'Bạn đã bỏ', 'resolved_published': 'Xác nhận đã đăng', 'resolved_failed': 'Xác nhận chưa đăng', 'settings': 'Đổi cài đặt'}

REASONS = (
    ('Audio needs review', 'Gemini chưa đủ chắc chắn về loại âm thanh'),
    ('Sensitive content', 'Nội dung nhạy cảm (chính trị, bạo lực, bi kịch, y tế...)'),
    ('Off-topic', 'Lệch chủ đề giải trí và âm nhạc'),
    ('Possible visual duplicate', 'Có thể trùng với một video đã xử lý'),
    ('Video duration outside', 'Thời lượng ngoài giới hạn cho phép'),
    ('Speech detected without transcript', 'Có lời nói nhưng không chép được lời'),
    ('Subtitle timestamps', 'Mốc thời gian phụ đề không hợp lệ'),
    ('Topic/sensitivity missing', 'Gemini không trả đủ thông tin chủ đề'),
    ('Gemini did not return valid', 'Gemini trả dữ liệu không đọc được'),
    ('Processing interrupted', 'Xử lý bị gián đoạn'),
    ('Local rolling 24-hour limit', 'Hết hạn mức Gemini trong 24 giờ; sẽ tự xử lý lại'),
    ('Initial observation only', 'Chỉ ghi mốc ban đầu'),
    ('Rejected by operator', 'Bạn đã bỏ video này'),
    ('Approved by operator', 'Bạn đã duyệt'),
)


def vi_reason(text):
    for key, vi in REASONS:
        if text and key in text:
            return vi
    return text or ''


def ago(ts, now=None):
    if not ts:
        return '—'
    s = int((now or time.time()) - ts)
    if s < 60:
        return 'vừa xong'
    for div, unit in ((86400, 'ngày'), (3600, 'giờ'), (60, 'phút')):
        if s >= div:
            return '%d %s trước' % (s // div, unit)
    return '—'


def num(n):
    return format(int(n), ',').replace(',', '.') if isinstance(n, (int, float)) else '—'


def meta_of(job):
    try:
        return json.loads(job.get('meta') or '{}')
    except Exception:
        return {}


def chip(text, tone='mute'):
    return '<span class="chip %s">%s</span>' % (tone, E(text))


def state_chip(state):
    return chip(STATE_LABELS.get(state, state), STATE_TONE.get(state, 'mute'))


def platform_badge(p):
    name, country = PLATFORM.get(p, (p, ''))
    return '<span class="plat">%s <b>%s</b></span>' % (E(name), E(country))


def select(name, current, options):
    return '<select name="%s">%s</select>' % (name, ''.join(
        '<option value="%s"%s>%s</option>' % (v, ' selected' if v == current else '', E(label)) for v, label in options))


def switch_select(name, on, on_label, off_label):
    return select(name, 'true' if on else 'false', (('true', on_label), ('false', off_label)))


def windows_text(wins):
    return ', '.join('%d-%d' % (a, b) for a, b in wins)


def checklist(d):
    items = [
        (d['gemini_configured'], 'Khóa Gemini API', 'Nhập khóa ở mục Cài đặt bên dưới.'),
        (d['processing_enabled'], 'Bật xử lý video', 'Video sẽ được gửi tới Google Gemini để phân tích khi bạn bật.'),
        (d['discovery'] == 'connected', 'Bộ thu thập chạy được', 'Cần agent trên máy và workflow n8n 01 đã bật.'),
        (d['publisher'] == 'connected', 'Đã đăng nhập TikTok', 'Chạy: ./trendvn tiktok login'),
        (d['publisher_enabled'], 'Bật tự đăng', 'Nên chạy thử dry-run và xem ảnh chụp trước khi bật.'),
        (bool(d['notify_channels']), 'Nhận thông báo điện thoại', 'Tùy chọn: Telegram, ntfy hoặc webhook (mục Thông báo).'),
    ]
    done = sum(1 for ok, _, _ in items if ok)
    rows = ''.join('<li class="%s"><span class="tick">%s</span><div><b>%s</b><small>%s</small></div></li>' % (
        'ok' if ok else 'todo', '✓' if ok else '○', E(t), '' if ok else E(h)) for ok, t, h in items)
    return done, len(items), rows


def source_cards(d, now):
    detail = d.get('discovery_detail') if isinstance(d.get('discovery_detail'), dict) else {}
    last = {}
    for s in d['streams']:
        p = s['name'].split(':')[0]
        last[p] = max(last.get(p, 0), s['last_scan'] or 0)
    cards = []
    for p, (name, country) in PLATFORM.items():
        st = d['by_platform'].get(p, {})
        info = detail.get(p)
        text = json.dumps(info, ensure_ascii=False) if isinstance(info, dict) else (info or '')
        skipped = isinstance(info, str) and 'IP' in info
        tone = 'warn' if skipped else ('good' if last.get(p) else 'mute')
        w = d['weights'].get(p, 1.0)
        cards.append('<div class="card src"><div class="row"><h3>%s</h3>%s</div><p class="muted">Quét gần nhất: <b>%s</b></p>'
                     '<div class="mini">%s</div><small class="muted">%s</small><small>Trọng số ưu tiên: <b>%.2f</b></small></div>' % (
                         E(name), chip('Cần IP %s' % country if skipped else ('Đang thu thập' if last.get(p) else 'Chưa quét'), tone),
                         ago(last.get(p), now),
                         ' '.join('<span>%s <b>%d</b></span>' % (E(STATE_LABELS.get(k, k)), n) for k, n in sorted(st.items())) or 'Chưa có dữ liệu',
                         E(text[:260]), w))
    return ''.join(cards)


from version import VERSION

ICONS = {
    'home': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
    'send': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>',
    'bell': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9a6 6 0 1 1 12 0c0 6 2 7 2 7H4s2-1 2-7zM10 20a2 2 0 0 0 4 0"/></svg>',
    'chart': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    'list': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>',
    'menu': '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
}
STALE_TASK = 900
TASK_ICON = {'running': '<span class="spin" aria-label="Đang chạy"></span>', 'done': '✓', 'error': '✗'}
ROUTE_LABEL = {'vietsub': 'Vietsub', 'voiceover': 'Lồng tiếng + Vietsub', 'original': 'Giữ nguyên'}
TAB_FOR = {'publish': 'publish', 'dryrun': 'publish', 'stats': 'posted'}


def table(headers, rows, empty):
    """Desktop table that turns into a stack of cards on phones (every cell carries data-label)."""
    body = ''.join(rows) if rows else '<tr class="none"><td colspan="%d" class="empty">%s</td></tr>' % (len(headers), E(empty))
    return '<div class="tablewrap"><table><tr class="hd">%s</tr>%s</table></div>' % (''.join('<th>%s</th>' % E(h) for h in headers), body)


def cell(label, value, cls=''):
    return '<td data-label="%s"%s>%s</td>' % (E(label), (' class="%s"' % cls) if cls else '', value)


def fieldset(title, body, opened=True):
    return '<details class="fs"%s><summary>%s</summary><div class="fsbody">%s</div></details>' % (' open' if opened else '', E(title), body)


def quick_switch(csrf, key, label, on, on_text, off_text, next_tab='home', danger=False, confirm=''):
    """One-tap switch on the home screen: POSTs a single setting and returns to the same screen."""
    return ('<form method="post" action="/settings" class="qs"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="%s">'
            '<input type="hidden" name="%s" value="%s"><button class="%s" aria-pressed="%s"%s><span>%s</span><b>%s</b></button></form>') % (
        csrf, next_tab, key, 'false' if on else 'true', ('on' if on else 'off') + (' danger' if danger and on else ''),
        'true' if on else 'false', (' data-confirm="%s"' % E(confirm)) if (confirm and not on) else '', E(label), E(on_text if on else off_text))


def task_panel(tasks, now=None, kinds=None):
    """Progress of the latest button-started task. data-running=1 makes the page poll it until it finishes.
    kinds: show it only when the latest task is one of these (so each tab shows only what is relevant to it); None = always."""
    now = now or time.time()
    if kinds is not None and (not tasks or tasks[0]['kind'] not in kinds):
        return ''
    if kinds is not None and tasks[0]['state'] != 'running' and now - (tasks[0].get('finished') or tasks[0]['started']) > STALE_TASK:
        return ''                                # an hours-old result on a tab you only just opened is noise, not news
    if not tasks:
        return '<div class="taskpanel idle" data-running="0"><p class="muted">Chưa chạy việc nào từ nút bấm. Bấm "Bắt đầu" để cập nhật.</p></div>'
    t = tasks[0]
    running = t['state'] == 'running'
    from tasks import LABELS
    link = lambda text: re.sub(r'/media/shot/(shot_\d{9,12}\.png)', r'<a href="/media/shot/\1" target="_blank" rel="noopener">mở ảnh chụp</a>', E(text))   # only our own file names are turned into links
    steps = ''.join('<li class="%s"><span class="ti">%s</span><div><b>%s</b>%s</div></li>' % (
        s['state'], TASK_ICON.get(s['state'], ''), E(s['name']), ('<small>%s</small>' % link(s['detail'])) if s.get('detail') else '') for s in t['steps'])
    if not steps and t.get('error'):
        steps = '<li class="error"><span class="ti">✗</span><div><b>%s</b></div></li>' % E(t['error'])
    state_chip_ = chip('Đang chạy…', 'info') if running else (chip('Xong', 'good') if t['state'] == 'done' else chip('Có lỗi', 'bad'))
    return ('<div class="taskpanel %s" data-running="%d"><div class="row"><b>%s</b>%s</div><ul class="steps">%s</ul>'
            '<small class="muted">Bắt đầu %s%s</small></div>') % (
        t['state'], 1 if running else 0, E(LABELS.get(t['kind'], t['kind'])), state_chip_, steps, ago(t['started'], now),
        ' · chạy nền, bạn có thể rời trang' if running else '')


def ready_card(j, d, csrf, now, blocked, busy):
    """One rendered video: preview, editable caption and hashtags, quality facts, and the buttons to post it."""
    m = meta_of(j)
    info = j.get('info') or {}
    lint = j['lint']
    facts = []
    if info.get('w'):
        ratio_ok = info['h'] > info['w'] and abs(info['w'] / info['h'] - 9 / 16) < 0.03
        facts.append(chip('%d×%d%s' % (info['w'], info['h'], ' · 9:16' if ratio_ok else ''), 'good' if ratio_ok else 'warn'))
    if info.get('duration'):
        facts.append(chip('%s giây' % info['duration'], 'mute'))
    if info.get('size'):
        facts.append(chip('%.1f MB' % (info['size'] / 1e6), 'mute'))
    facts.append(chip(ROUTE_LABEL.get(j['route'], j['route'] or ''), 'info'))
    if info.get('reframed'):
        facts.append(chip('đã đưa vào khung dọc', 'mute'))
    if info.get('warning'):
        facts.append(chip(info['warning'], 'warn'))
    score = []
    if m.get('score'):
        score.append('điểm %s' % num(m['score']))
    if m.get('likes'):
        score.append('%s tim' % num(m['likes']))
    if m.get('views'):
        score.append('%s xem' % num(m['views']))
    if m.get('age_h') is not None:
        score.append('%.0f giờ tuổi' % m['age_h'])
    cfg = d['settings']
    vis = {'public': 'CÔNG KHAI', 'friends': 'BẠN BÈ', 'self': 'CHỈ MÌNH TÔI'}.get(cfg['visibility'], cfg['visibility'])
    warn = []
    if d['published_today'] >= d['daily_limit']:
        warn.append('Hôm nay đã đăng đủ %d/%d bài, bạn vẫn muốn đăng thêm?' % (d['published_today'], d['daily_limit']))
    if not d['in_window']:
        warn.append('Đang ngoài giờ vàng.')
    confirm = 'Đăng video này lên @%s ngay bây giờ? Chế độ hiển thị: %s. %s' % (cfg['target'], vis, ' '.join(warn))
    poster = ' poster="/media/%s/poster"' % E(j['id']) if info.get('poster') else ''
    media = '<video controls preload="none" playsinline%s src="/media/%s/final"></video>' % (poster, E(j['id']))
    tags = re.findall(r'#\w+', j['caption'])
    lint_html = ('<div class="lint ok">✓ Mô tả tốt: %d ký tự, %d hashtag</div>' % (lint['length'], lint['tags'])) if lint['ok'] else \
        '<div class="lint warn">⚠ %s</div>' % E(' · '.join(lint['issues']))
    dis = ' disabled' if (blocked or busy) else ''
    reason = ''
    if blocked:
        reason = '<div class="note warn">%s</div>' % E(blocked)
    elif busy:
        reason = '<div class="note">Đang có việc khác chạy. Nút sẽ dùng được khi nó xong.</div>'
    chips_html = ''.join('<span class="tag">%s</span>' % E(t) for t in tags)
    return ('<form method="post" action="/task" class="card ready" data-id="%(id)s"><input type="hidden" name="csrf" value="%(csrf)s"><input type="hidden" name="id" value="%(id)s">'
            '<div class="media">%(media)s</div>'
            '<div class="body stack">'
            '<div class="row">%(plat)s%(state)s</div>'
            '<div class="ttl">%(title)s</div>'
            '<div class="muted small">%(score)s</div>'
            '<div class="facts">%(facts)s</div>'
            '<label class="cap">Mô tả và hashtag sẽ đăng'
            '<textarea name="caption" rows="4" maxlength="2200" data-caption spellcheck="false">%(caption)s</textarea></label>'
            '<div class="row small"><span class="muted"><span data-len>%(length)d</span> ký tự · <span data-tags>%(ntags)d</span> hashtag%(edited)s</span></div>'
            '<div class="tags">%(chips)s</div>%(lint)s%(reason)s'
            '<div class="btns">'
            '%(approve)s<button class="go big" formaction="/task" name="kind" value="publish" data-confirm="%(confirm)s"%(dis)s>🚀 Đăng ngay</button>'
            '<button class="ghost" formaction="/task" name="kind" value="dryrun"%(dis)s>👁 Xem thử, không đăng</button>'
            '<button class="ghost" formaction="/caption" name="action" value="save">💾 Lưu mô tả</button>%(reset)s'
            '<button class="ghost danger" formaction="/decide" name="action" value="reject" data-confirm="Bỏ video này khỏi danh sách đăng?">🗑 Bỏ video</button>'
            '</div></div></form>') % {
        'id': E(j['id']), 'csrf': csrf, 'media': media, 'plat': platform_badge(j['platform']), 'state': state_chip(j['state']),
        'title': E((j['title'] or '(không có tiêu đề)')[:120]), 'score': E(' · '.join(score)), 'facts': ''.join(facts),
        'caption': E(j['caption']), 'length': lint['length'], 'ntags': lint['tags'], 'edited': ' · đã sửa tay' if j['caption_edited'] else '',
        'chips': chips_html, 'lint': lint_html, 'reason': reason, 'confirm': E(confirm), 'dis': dis,
        'approve': '<button class="ghost" formaction="/decide" name="action" value="approve">✔ Duyệt cho lịch tự đăng</button>' if j['state'] == 'awaiting_approval' else '',
        'reset': '<button class="ghost" formaction="/caption" name="action" value="reset">↺ Dùng mô tả của hệ thống</button>' if j['caption_edited'] else ''}


def review_card(job, csrf, now):
    m = meta_of(job)
    bits = []
    if m.get('score'):
        bits.append('điểm %s' % num(m['score']))
    if m.get('likes'):
        bits.append('%s tim' % num(m['likes']))
    if m.get('age_h') is not None:
        bits.append('%.0f giờ tuổi' % m['age_h'])
    return ('<form method="post" action="/decide" class="card ready"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
            '<div class="media"><video controls preload="none" playsinline src="/media/%s/source"></video></div>'
            '<div class="body stack"><div class="row">%s%s</div><div class="ttl">%s</div><div class="muted small">%s</div>'
            '<div class="note warn">Lý do giữ lại: <b>%s</b></div>'
            '<div class="btns">%s<button class="go" name="action" value="approve" title="Chạy lại và bỏ qua kiểm tra chủ đề/độ chắc chắn">Duyệt lại, bỏ qua kiểm tra</button>'
            '<button class="ghost danger" name="action" value="reject">Bỏ</button></div></div></form>') % (
        csrf, E(job['id']), E(job['id']), platform_badge(job['platform']), state_chip(job['state']), E((job['title'] or '(không có tiêu đề)')[:120]),
        E(' · '.join(bits)), E(vi_reason(job['reason'])),
        '<button class="ghost" name="action" value="retry" title="Video đã dựng xong; đưa về danh sách sẵn sàng đăng">↩ Đưa về sẵn sàng đăng</button>' if job.get('output_file') else '')


def render(d, csrf, flash=None, now=None):
    now = now or time.time()
    tz = ZoneInfo(d['settings']['timezone'])
    clock = datetime.fromtimestamp(now, tz).strftime('%H:%M %d/%m')
    cfg = d['settings']
    done, total, todo_rows = checklist(d)
    c = d['counts']
    ready = d.get('ready', [])
    tasks_ = d.get('tasks', [])
    running = [t for t in tasks_ if t['state'] == 'running']
    busy_browser = any(t['kind'] in ('collect', 'publish', 'dryrun', 'stats', 'update') for t in running)
    busy_process = any(t['kind'] in ('process', 'update') for t in running)
    challenge_on = bool(d.get('publisher_challenge'))
    attention = len(d['review']) + len(d['unresolved']) + (1 if challenge_on else 0)
    total_views = sum(p['views'] or 0 for p in d['performance'])
    auto_on = d['processing_enabled'] and d['publisher_enabled']
    n8n_url = d.get('n8n_url') or 'http://localhost:5680'
    waiting = c.get('queued', 0) + c.get('processing', 0)
    banner = ('<div class="banner good"><b>Đang tự động hoàn toàn.</b> Thu thập, xử lý và đăng chạy theo lịch.</div>' if auto_on and not attention else
              '<div class="banner warn"><b>Chưa tự động hoàn toàn.</b> %s</div>' % (
                  'Có %d việc cần bạn xem ở tab Cần xem.' % attention if attention else 'Hoàn tất danh sách thiết lập để bật tự động.'))
    pill = lambda label, state: '<div class="pill"><span>%s</span>%s</div>' % (E(label), chip(*COMPONENT.get(state, (state, 'mute'))))
    pills = (pill('Thu thập video', d['discovery']) + pill('Đăng TikTok', d['publisher']) +
             '<div class="pill"><span>Giờ vàng</span>%s</div>' % chip('Đang mở' if d['in_window'] else 'Mở lúc ' + (d['next_window'] or '—'), 'good' if d['in_window'] else 'mute'))
    quick = '<div class="quick">%s%s</div>' % (
        quick_switch(csrf, 'processing_enabled', 'Xử lý video', d['processing_enabled'], 'ĐANG BẬT', 'ĐANG TẮT',
                     confirm='Bật xử lý video? Video sẽ được gửi tới Google Gemini để phân tích.'),
        quick_switch(csrf, 'publisher_enabled', 'Tự đăng TikTok', d['publisher_enabled'], 'ĐANG BẬT · chạm để dừng', 'ĐANG TẮT', danger=True,
                     confirm='Bật tự đăng? Hệ thống sẽ tự đăng lên @%s theo lịch (tối đa %d bài/ngày, chế độ %s).' % (
                         cfg['target'], cfg['daily_limit'], {'public': 'công khai', 'friends': 'bạn bè', 'self': 'chỉ mình tôi'}.get(cfg['visibility'], cfg['visibility']))))
    kpis = ''.join('<div class="kpi"><small>%s</small><b>%s</b></div>' % (E(a), E(str(b))) for a, b in (
        ('Đăng hôm nay', '%d / %d' % (d['published_today'], d['daily_limit'])),
        ('Chờ xử lý', waiting), ('Sẵn sàng đăng', len(ready)),
        ('Cần xem', attention), ('Tổng đã đăng', c.get('published', 0)), ('Lượt xem bài đã đăng', num(total_views))))
    flash_html = ''
    if flash:
        flash_html = '<div class="flash %s" role="status">%s</div>' % ('bad' if flash[0] == 'err' else 'good', E(flash[1]))

    # ---------------- control panel (buttons that run things now; the n8n schedule keeps running on its own)
    def action(kind, label, cls, disabled, next_tab='home'):
        return ('<form method="post" action="/task"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="%s">'
                '<button class="%s" name="kind" value="%s"%s>%s</button></form>') % (csrf, next_tab, cls, kind, ' disabled' if disabled else '', label)

    def enable_processing(next_tab):
        if not d['gemini_configured']:
            return '<p class="note warn">Chưa có khóa Gemini nên chưa bật được. <a href="#settings">Dán khóa ở Thêm → Cài đặt</a>, rồi quay lại bật xử lý video.</p>'
        return ('<form method="post" action="/settings"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="%s">'
                '<input type="hidden" name="processing_enabled" value="true"><button class="go big" data-confirm="Bật xử lý video? Video sẽ được gửi tới Google Gemini để phân tích.">'
                '✔ Bật xử lý video</button></form>') % (csrf, next_tab)
    hint = ('Thu thập video mới → xử lý (Vietsub/lồng tiếng) → sẵn sàng đăng. ' if d['processing_enabled'] else
            'Xử lý video đang TẮT nên nút này chỉ thu thập; bật công tắc "Xử lý video" để đi trọn vòng. ')
    control = ('<div class="card stack" id="control"><h2>Điều khiển</h2>%s<p class="hint">%sLịch tự động vẫn chạy song song như cũ.</p>'
               '<div class="btngrid">%s%s</div>%s</div>') % (
        action('update', '▶ Bắt đầu: cập nhật &amp; chuẩn bị đăng', 'go xl', busy_browser or busy_process, 'home'), E(hint),
        action('collect', '🔎 Thu thập video mới', 'ghost', busy_browser, 'queue'),
        action('process', '⚙️ Xử lý video chờ (%d)' % waiting, 'ghost', busy_process, 'queue'), task_panel(tasks_, now))
    last_scan = d.get('discovery_at')
    schedule = ('<div class="card stack"><h2>Lịch tự động</h2><ul class="plain"><li><b>Thu thập và xử lý:</b> mỗi 3 giờ (n8n)%s</li>'
                '<li><b>Đăng:</b> kiểm tra mỗi 30 phút, chỉ đăng trong giờ vàng %s, tối đa %d bài/ngày, cách nhau ≥ %s giờ</li>'
                '<li><b>Chốt ngày:</b> 23:30, đọc lượt xem và gửi tóm tắt</li></ul>'
                '<p class="muted small">Các nút ở trên chỉ là bổ sung; không thay thế và không làm gián đoạn lịch.</p></div>') % (
        (' · lần gần nhất %s' % ago(last_scan, now)) if last_scan else '', E(windows_text(cfg['post_windows']) or 'mọi lúc'),
        cfg['daily_limit'], E('%g' % round(cfg['min_publish_gap'] / 3600, 2)))

    # ---------------- publish tab
    blocked = ''
    if challenge_on:
        blocked = 'TikTok đang đòi xác minh: giải một lần bằng ./trendvn tiktok trust (xem mục Cần xem).'
    elif d['unresolved_publishes']:
        blocked = 'Có bài đăng chưa xác nhận: xử lý ở mục Cần xem trước.'
    vis = {'public': 'Công khai', 'friends': 'Bạn bè', 'self': 'Chỉ mình tôi'}.get(cfg['visibility'], cfg['visibility'])
    strip = ('<div class="card strip"><div><small>Hôm nay</small><b>%d / %d</b></div><div><small>Hiển thị</small><b>%s</b></div>'
             '<div><small>Giờ vàng</small><b>%s</b></div></div>') % (d['published_today'], d['daily_limit'], E(vis), 'đang mở' if d['in_window'] else E('mở lúc ' + (d['next_window'] or '—')))
    if ready:
        ready_html = ''.join(ready_card(j, d, csrf, now, blocked, busy_browser) for j in ready)
    else:
        cands = c.get('candidate', 0)
        if waiting and not d['processing_enabled']:
            why = ('<p><b>%d video đang chờ xử lý</b> nhưng công tắc "Xử lý video" đang <b>TẮT</b>, nên chưa video nào được dựng.</p>'
                   '<p class="hint">Bật lên để Gemini làm Vietsub hoặc lồng tiếng. Video xong sẽ hiện ở đây để bạn đăng.</p>%s') % (waiting, enable_processing('publish'))
        elif waiting:
            why = ('<p><b>%d video đang chờ xử lý</b> (mỗi video khoảng 1–3 phút). Xử lý xong sẽ hiện ở đây.</p>%s') % (
                waiting, action('process', '⚙️ Xử lý ngay (%d)' % waiting, 'go big', busy_process, 'publish'))
        else:
            why = ('<p>Chưa có video nào để xử lý%s.</p><p class="hint">Bấm cập nhật để thu thập video mới và xử lý; video xong sẽ hiện ở đây.</p>%s') % (
                (' (có %d ứng viên chưa tải về)' % cands) if cands else '', action('update', '▶ Cập nhật &amp; chuẩn bị đăng', 'go big', busy_browser or busy_process, 'publish'))
        more_hint = []
        if attention:
            more_hint.append('%d video đang ở tab <a href="#attention">Cần xem</a> (hệ thống giữ lại để bạn duyệt).' % attention)
        more_hint.append('<a href="#queue">Xem hàng đợi →</a>')
        ready_html = '<div class="card stack empty-guide"><h3>Chưa có video nào xử lý xong</h3>%s<p class="small muted">%s</p></div>' % (why, ' '.join(more_hint))
    publish_html = ('<h2>Đăng bài</h2><p class="hint">Đây là các video đã xử lý xong. Xem thử, sửa mô tả và hashtag nếu muốn, rồi bấm <b>Đăng ngay</b> để đăng đúng video đó. '
                    'Lịch tự động vẫn tự chọn bài điểm cao nhất để đăng trong giờ vàng.</p>%s%s<div class="stack">%s</div>') % (task_panel(tasks_, now, ('publish', 'dryrun', 'update')), strip, ready_html)

    # ---------------- attention tab
    challenge = ('<div class="card alert stack"><h3>🧩 TikTok đang yêu cầu xác minh</h3><p>Đăng bài đang <b>tạm dừng</b> để không kích hoạt thêm. Hãy giải hình xác minh một lần trong cửa sổ Chrome thật:</p>'
                 '<p><code>./trendvn tiktok trust</code></p><p class="muted small">Mac: nhấp đúp <code>macos/Xac-minh-TikTok.command</code>. Xong hệ thống tự đăng tiếp.</p></div>') if challenge_on else ''
    unresolved = ''.join(
        '<form method="post" action="/resolve" class="card alert stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
        '<h3>🚨 Chưa xác nhận đã đăng: %s</h3><p>Hệ thống đã dừng đăng để không đăng trùng. Mở TikTok kiểm tra rồi chọn:</p><div class="btns">'
        '<button name="outcome" value="published" class="go">Bài đã lên TikTok</button><button name="outcome" value="failed" class="ghost">Chưa có, cho phép đăng lại</button></div></form>' % (
            csrf, E(u['id']), E((u['title'] or '')[:100])) for u in d['unresolved'])
    reviews = ''.join(review_card(dict(j), csrf, now) for j in d['review'])
    attention_html = (challenge + unresolved + reviews) or ('<div class="card empty stack"><p>Không có việc nào cần bạn xem. 🎉</p><p class="small">Video đang chờ xử lý nằm ở tab <a href="#queue">Hàng đợi</a>; '
                                                  'video đã xử lý xong nằm ở tab <a href="#publish">Đăng bài</a>.</p></div>')

    def acc(id_, title, body):
        return '<details class="acc card" id="%s"><summary>%s</summary><div class="accbody stack">%s</div></details>' % (id_, E(title), body)

    funnel = '<div class="funnel">%s</div>' % ''.join('<a class="step" href="#%s"><b>%d</b><small>%s</small></a>' % (to, n, l) for l, n, to in (
        ('Ứng viên', c.get('candidate', 0), 'queue'), ('Chờ xử lý', waiting, 'queue'), ('Sẵn sàng', len(ready), 'publish'), ('Đã đăng', c.get('published', 0), 'posted')))

    def queue_table(items, empty):
        return table(('Nguồn', 'Video', 'Trạng thái', 'Điểm', 'Tìm thấy'), [
            '<tr>%s%s%s%s%s</tr>' % (
                cell('Nguồn', platform_badge(j['platform'])), cell('Video', E((j['title'] or '')[:90]), 't'), cell('Trạng thái', state_chip(j['state'])),
                cell('Điểm', E(num(meta_of(j).get('score'))) if meta_of(j).get('score') else '—'), cell('Tìm thấy', ago(j['first_seen'], now)))
            for j in items], empty)
    if not d['processing_enabled']:
        proc_card = ('<div class="card stack alert-soft"><h3>Xử lý video đang TẮT</h3><p>Video vẫn được thu thập nhưng chưa được dựng, nên %s'
                     'Bật lên để Gemini làm Vietsub hoặc lồng tiếng.</p>%s</div>') % (
            ('<b>%d video</b> đang nằm chờ. ' % waiting) if waiting else 'sẽ nằm chờ ở đây. ', enable_processing('queue'))
    else:
        proc_card = ('<div class="card stack"><h3>Xử lý</h3><p class="hint">%s</p><div class="btngrid">%s%s</div></div>') % (
            ('Đang có <b>%d video</b> chờ Gemini làm Vietsub/lồng tiếng. Video xong sẽ chuyển sang tab Đăng bài.' % waiting) if waiting else
            'Không có video nào chờ xử lý. Bấm <b>Thu thập</b> để tìm video mới.',
            action('process', '⚙️ Xử lý %d video chờ' % waiting if waiting else '⚙️ Không có video chờ', 'go big', busy_process or not waiting, 'queue'),
            action('collect', '🔎 Thu thập video mới', 'ghost big', busy_browser, 'queue'))
    queue_html = ('<h2>Hàng đợi</h2><p class="hint">Đường đi của một video: <b>Ứng viên</b> (đã tìm thấy, chưa tải) → <b>Chờ xử lý</b> (đã tải, chờ Gemini) → '
                  '<b>Sẵn sàng</b> (sang tab Đăng bài) → <b>Đã đăng</b>.</p>%s%s%s<h3 class="sub">Đang chờ xử lý (%d)</h3>%s%s') % (
        funnel, proc_card, task_panel(tasks_, now, ('process', 'update', 'collect')), waiting,
        queue_table(d.get('queue', []), 'Không có video nào chờ xử lý.'),
        acc('candidates', 'Ứng viên chưa tải về (%d)' % c.get('candidate', 0),
            '<p class="muted small">Đã tìm thấy và đạt ngưỡng thịnh hành; sẽ được tải về ở lần thu thập kế tiếp.</p>' + queue_table(d.get('candidates', []), 'Không có ứng viên nào.')))
    perf = table(('Nguồn', 'Bài đăng', 'Kiểu', 'Lượt xem', 'Tim', 'Đăng'), [
        '<tr>%s%s%s%s%s%s</tr>' % (
            cell('Nguồn', platform_badge(p['platform'])),
            cell('Bài đăng', ('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (E(p['publish_url']), E((p['title'] or '')[:80]))) if p['publish_url'] else E((p['title'] or '')[:80]), 't'),
            cell('Kiểu', E(ROUTE_LABEL.get(p['route'], p['route'] or ''))),
            cell('Lượt xem', num(p['views'])), cell('Tim', num(p['likes'])), cell('Đăng', ago(p['published_at'], now)))
        for p in d['performance']], 'Chưa có bài nào được đăng.')
    posted_html = ('<h2>Đã đăng và hiệu quả</h2><div class="card stack"><p class="hint">Đọc lượt xem và tim từ hồ sơ TikTok để cập nhật bảng và để hệ thống học nguồn nào hiệu quả hơn.</p>%s%s</div>%s') % (
        action('stats', '📊 Đọc lượt xem ngay', 'ghost', busy_browser, 'posted'), task_panel(tasks_, now, ('stats',)), perf)
    events = table(('Lúc', 'Sự kiện', 'Video', 'Chi tiết'), [
        '<tr>%s%s%s%s</tr>' % (cell('Lúc', ago(e['at'], now)), cell('Sự kiện', E(EVENT_LABELS.get(e['event'], e['event']))),
                                cell('Video', E((e['title'] or '')[:70]), 't'), cell('Chi tiết', E(vi_reason(e['detail'] or '')[:120])))
        for e in d['events']], 'Chưa có sự kiện.')

    mv, ml = cfg['min_views'], cfg['min_likes']
    field = lambda label, inner, hint='': '<label>%s%s%s</label>' % (E(label), inner, ('<small>%s</small>' % E(hint)) if hint else '')
    inp = lambda name, val, extra='': '<input name="%s" value="%s" %s>' % (name, E(str(val)), extra)
    num_in = lambda name, val, lo, hi, step='1': inp(name, val, 'type="number" inputmode="%s" min="%s" max="%s" step="%s"' % ('decimal' if step != '1' else 'numeric', lo, hi, step))
    plain = 'autocapitalize="none" autocorrect="off" spellcheck="false"'
    settings_form = ('<form method="post" action="/settings" class="settings stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="settings">%s%s%s%s%s'
                     '<div class="btns"><button class="go">Lưu cài đặt</button></div></form>') % (
        csrf,
        fieldset('Tự động', ''.join((
            field('Xử lý video bằng Gemini', switch_select('processing_enabled', d['processing_enabled'], 'Bật', 'Tắt')),
            field('Tự đăng lên TikTok', switch_select('publisher_enabled', d['publisher_enabled'], 'Bật', 'Tắt'), 'Luôn kiểm tra hash, trùng lặp và giới hạn ngày.'),
            field('Duyệt tay trước khi đăng', switch_select('require_approval', cfg['require_approval'], 'Bật — chờ tôi duyệt', 'Tắt — hoàn toàn tự động')),
            field('Lồng tiếng Việt cho video thuyết minh', switch_select('voiceover_enabled', cfg['voiceover_enabled'], 'Bật', 'Tắt — chỉ Vietsub'), 'Hãy nghe thử giọng đọc trước khi bật.')))),
        fieldset('Lịch đăng', ''.join((
            field('Số bài tối đa mỗi ngày', num_in('daily_limit', cfg['daily_limit'], 1, 10)),
            field('Giãn cách tối thiểu (giờ)', num_in('gap_hours', round(cfg['min_publish_gap'] / 3600, 2), 0, 24, '0.25')),
            field('Giờ vàng (giờ Việt Nam)', inp('post_windows', windows_text(cfg['post_windows']), 'placeholder="11-14, 19-23" inputmode="text"'), 'Để trống nếu muốn đăng bất kỳ lúc nào.'),
            field('Tài khoản TikTok đích', inp('target', cfg['target'], plain)),
            field('Chế độ hiển thị bài đăng', select('visibility', cfg['visibility'], (('public', 'Mọi người (công khai)'), ('friends', 'Bạn bè'), ('self', 'Chỉ mình tôi (dùng để chạy thử an toàn)'))), 'Áp dụng cho mọi bài sắp đăng.'))), False),
        fieldset('Chọn video', ''.join((
            field('Video mới trong (ngày)', num_in('max_age_days', cfg['max_age_days'], 1, 60), 'Chỉ lấy video được đăng gần đây.'),
            field('Độ dài tối đa (giây)', num_in('max_duration', cfg['max_duration'], 10, 600)),
            field('Tải tối đa mỗi lần quét', num_in('max_candidates_per_scan', cfg['max_candidates_per_scan'], 1, 10)),
            field('Hàng chờ tối đa', num_in('max_backlog', cfg['max_backlog'], 1, 20), 'Đủ số này thì tạm ngừng tải thêm.'),
            field('Độ chắc chắn tối thiểu của Gemini', num_in('audio_confidence', cfg['audio_confidence'], 0.5, 0.99, '0.01')))), False),
        fieldset('Ngưỡng thịnh hành', ''.join((
            field('Douyin: tim tối thiểu', num_in('likes_douyin', ml.get('douyin', 0), 0, 10**9)),
            field('Kuaishou: lượt xem tối thiểu', num_in('views_kuaishou', mv.get('kuaishou', 0), 0, 10**10)),
            field('TikTok: lượt xem tối thiểu', num_in('views_tiktok', mv.get('tiktok', 0), 0, 10**10)),
            field('Instagram: lượt xem tối thiểu', num_in('views_instagram', mv.get('instagram', 0), 0, 10**10)),
            field('Douyin: lượt xem tối thiểu', num_in('views_douyin', mv.get('douyin', 0), 0, 10**10)))), False),
        fieldset('Gemini', ''.join((
            field('Giọng đọc', inp('voice', cfg['voice'], plain), 'Tên giọng Gemini, ví dụ Kore, Puck, Charon.'),
            field('Hạn mức gọi Gemini / 24 giờ', num_in('gemini_daily_limit', cfg['gemini_daily_limit'], 1, 500), 'Tăng nếu tài khoản Gemini của bạn cho phép.'),
            field('Model phân tích', inp('model', cfg['model'], plain), 'Google có thể ngừng model cũ; hệ thống tự chuyển sang model mới hơn khi gặp lỗi 404.'),
            field('Model giọng đọc', inp('tts_model', cfg['tts_model'], plain)))), False))

    notify_form = ('<p class="muted">Kênh đang dùng: <b>%s</b>. Thông báo gửi khi có video cần duyệt, đăng xong, lỗi hoặc bài chưa xác nhận.</p>'
                   '<form method="post" action="/notify-save" class="stack"><input type="hidden" name="csrf" value="%s">%s%s%s'
                   '<div class="btns"><button class="go">Lưu kênh thông báo</button></div></form>'
                   '<div class="btns two"><form method="post" action="/notify-test"><input type="hidden" name="csrf" value="%s"><button class="ghost">Gửi tin thử</button></form>'
                   '<form method="post" action="/notify-clear"><input type="hidden" name="csrf" value="%s"><button class="ghost">Xóa các kênh</button></form></div>') % (
        E(', '.join(d['notify_channels']) or 'chưa cấu hình'), csrf,
        fieldset('Telegram', field('Bot token', '<input type="password" name="telegram_token" autocomplete="off" placeholder="để trống để giữ nguyên">') +
                 field('Chat id', '<input name="telegram_chat" autocomplete="off" inputmode="text" placeholder="-100123456 hoặc @kenh">')),
        fieldset('Discord / Slack (webhook https)', field('Địa chỉ webhook', '<input type="password" name="webhook" autocomplete="off" placeholder="https://...">'), False),
        fieldset('ntfy (https)', field('Địa chỉ chủ đề', '<input type="password" name="ntfy" autocomplete="off" placeholder="https://ntfy.sh/ten-rieng">'), False), csrf, csrf)

    key_form = ('<form method="post" action="/setup" class="stack"><input type="hidden" name="csrf" value="%s">'
                '<p class="muted">Khóa được lưu trong <code>data/worker/gemini.key</code>, không gửi vào n8n hay nhật ký. %s</p>'
                '%s<div class="btns"><button class="go">Lưu khóa</button></div></form>'
                '<form method="post" action="/voice-test"><input type="hidden" name="csrf" value="%s"><div class="btns"><button class="ghost" title="Dùng 1 lượt gọi Gemini">🔊 Nghe thử giọng đọc</button></div></form>%s') % (
        csrf, 'Đã có khóa.' if d['gemini_configured'] else 'Chưa có khóa.',
        field('Gemini API key (để trống để giữ khóa hiện tại)', '<input type="password" name="key" autocomplete="off">'), csrf,
        '<audio controls preload="none" src="/media/voice-sample"></audio>' if d.get('voice_sample') else '')

    manual = ('<form method="post" action="/ingest-form" class="stack"><input type="hidden" name="csrf" value="%s">'
              '<textarea name="batch" rows="5" placeholder=\'{"platform":"douyin","stream":"hot_music","observed_at":0,"items":[]}\'></textarea>'
              '<div class="btns"><button class="ghost">Kiểm tra và nhập</button></div></form>') % csrf


    nav = [('home', 'Tổng quan', 'home', 0), ('queue', 'Hàng đợi', 'list', waiting), ('publish', 'Đăng bài', 'send', len(ready)),
           ('attention', 'Cần xem', 'bell', attention), ('posted', 'Đã đăng', 'chart', 0), ('more', 'Thêm', 'menu', 0)]
    badge = lambda k, n: '<i class="%s">%d</i>' % ('' if k == 'attention' else 'n', n)      # red only for what needs you; blue for plain counts
    bottom = ''.join('<a href="#%s" data-go="%s"><span class="ic">%s%s</span><small>%s</small></a>' % (
        k, k, ICONS[ic], badge(k, n) if n else '', E(label)) for k, label, ic, n in nav)
    top = ''.join('<a href="#%s" data-go="%s">%s%s</a>' % (k, k, E(label), (' ' + badge(k, n)) if n else '') for k, label, _, n in nav)

    return '''<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1522" media="(prefers-color-scheme: dark)"><meta name="theme-color" content="#f4f6fb" media="(prefers-color-scheme: light)">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="TrendVN">
<link rel="icon" href="data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%%3E%%3Crect width='64' height='64' rx='14' fill='%%230b7a66'/%%3E%%3Cpath d='M16 42l12-14 8 8 14-18' stroke='white' stroke-width='6' fill='none' stroke-linecap='round' stroke-linejoin='round'/%%3E%%3C/svg%%3E">
<title>TrendVN · Bảng điều khiển</title><style>%s</style></head><body>
<header><div class="wrap head"><div class="brand"><h1>TrendVN</h1><p class="muted">TikTok <b>@%s</b> · %s</p></div>
<nav class="topnav">%s<a href="%s" target="_blank" rel="noopener">n8n ↗</a></nav><button class="refresh ghost" onclick="location.reload()" aria-label="Làm mới">↻</button></div></header>
<main class="wrap">%s
<section data-tab="home" id="home" class="stack">%s%s%s<div class="card pills"><h3>Tình trạng</h3>%s</div><div class="kpis">%s</div>%s
<div class="card"><h2>Thiết lập <small>%d/%d hoàn tất</small></h2><ul class="check">%s</ul></div>
<div class="card stack"><h2>Luồng xử lý</h2>%s<p class="muted small">Chạm vào từng bước để xem chi tiết. Mốc ban đầu (%d) chỉ để nhận diện video mới, không bao giờ đăng.</p></div></section>
<section data-tab="queue" id="queue" class="stack">%s</section>
<section data-tab="publish" id="publish" class="stack">%s</section>
<section data-tab="attention" id="attention" class="stack"><h2>Cần xem</h2>%s</section>
<section data-tab="posted" id="posted" class="stack">%s</section>
<section data-tab="more" id="more" class="stack"><h2 class="desk">Nguồn, cài đặt, thông báo, nhật ký</h2>
%s%s%s%s%s</section>
<footer class="muted">TrendVN %s</footer></main>
<nav class="bottomnav" aria-label="Điều hướng">%s</nav>
<script>%s</script></body></html>''' % (
        CSS, E(d['target']), E(clock), top, E(n8n_url), flash_html, banner, control, quick, pills, kpis, schedule,
        done, total, todo_rows, funnel, c.get('baseline', 0),
        queue_html, publish_html, attention_html, posted_html,
        acc('sources', 'Nguồn thu thập', '<div class="grid4">%s</div>' % source_cards(d, now)),
        acc('settings', 'Cài đặt', settings_form + '<h3 class="sub">Khóa Gemini và giọng đọc</h3>' + key_form),
        acc('notify', 'Thông báo điện thoại', notify_form),
        acc('log', 'Nhật ký', events),
        acc('advanced', 'Nâng cao: nhập quan sát bằng tay', manual),
        E(VERSION), bottom, JS)


CSS = r"""
:root{--bg:#f4f6fb;--card:#fff;--ink:#16202e;--mute:#5d6b80;--line:#dde3ee;--accent:#0b7a66;--accent2:#e8f6f2;--good:#0b7a66;--warn:#a55b00;--bad:#b3261e;--info:#1b5fbf;--onaccent:#fff;--shadow:0 1px 2px rgba(20,30,50,.06);--s1:6px;--s2:10px;--s3:14px;--s4:20px;--r:16px}
@media (prefers-color-scheme:dark){:root{--bg:#0e1522;--card:#162033;--ink:#e6ecf7;--mute:#a4b1c7;--line:#2a3850;--accent:#5fd6bd;--accent2:#12312f;--good:#5fd6bd;--warn:#ffc46b;--bad:#ff8a80;--info:#8ab8ff;--onaccent:#08231d;--shadow:none}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;min-width:0}html{scroll-behavior:smooth;scroll-padding-top:84px}section{scroll-margin-top:84px}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%;overflow-wrap:anywhere}
.wrap{max-width:1200px;margin:0 auto;padding-left:20px;padding-right:20px}
.stack>*+*{margin-top:var(--s3)}
header{background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20;padding-top:env(safe-area-inset-top)}
.head{display:flex;justify-content:space-between;align-items:center;gap:14px;padding-top:12px;padding-bottom:12px}
h1{margin:0;font-size:26px;letter-spacing:-.5px;line-height:1.1}h2{font-size:20px;margin:0}h2 small{color:var(--mute);font-weight:400;font-size:13px}h3{margin:0;font-size:16px}h3.sub{margin-top:var(--s4)}
.muted{color:var(--mute)}.small{font-size:13px}p{margin:0}.hint{color:var(--mute);font-size:14px}.brand p{margin-top:2px;font-size:13px}
.topnav{display:flex;gap:4px;flex-wrap:wrap;margin-left:auto}.topnav a{color:var(--ink);text-decoration:none;padding:11px 12px;border-radius:9px;font-size:14px;line-height:22px}.topnav a:hover,.topnav a.on{background:var(--accent2)}
i.n{background:var(--info);color:var(--card)}i{background:var(--bad);color:#fff;border-radius:9px;padding:0 6px;font-style:normal;font-size:12px;font-weight:700}
.refresh{display:none;padding:6px 12px;font-size:18px;min-height:44px;min-width:44px}
main{padding-top:var(--s4);padding-bottom:48px}section{margin:0 0 var(--s4)}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:var(--s3);box-shadow:var(--shadow)}
.banner{padding:13px 16px;border-radius:14px}.banner.good{background:var(--accent2);color:var(--good)}.banner.warn{background:#fff3e0;color:#7a4300}@media (prefers-color-scheme:dark){.banner.warn{background:#3a2a10;color:var(--warn)}}
.flash{padding:12px 16px;border-radius:12px;margin:0 0 var(--s3);font-weight:600}.flash.good{background:var(--accent2);color:var(--good)}.flash.bad{background:#fde7e5;color:var(--bad)}
.pills h3{margin-bottom:2px}.pill{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--line);font-size:15px}.pill:last-child{border:0;padding-bottom:0}.pill .chip{text-align:right}
@media (min-width:721px){.pills{display:grid;grid-template-columns:repeat(3,1fr);column-gap:28px}.pills h3{grid-column:1/-1}.pill{border:0;padding:6px 0}}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid currentColor}.chip.good{color:var(--good)}.chip.warn{color:var(--warn)}.chip.bad{color:var(--bad)}.chip.info{color:var(--info)}.chip.mute{color:var(--mute)}
.quick{display:grid;grid-template-columns:1fr 1fr;gap:var(--s2)}.qs{margin:0}.qs button{width:100%;text-align:left;display:flex;flex-direction:column;gap:2px;padding:14px 16px;min-height:72px;border-radius:16px;border:1.5px solid var(--line);background:var(--card);color:var(--ink);font-weight:500}
.qs button span{font-size:13px;color:var(--mute)}.qs button b{font-size:15px}.qs button.on{border-color:var(--good);background:var(--accent2)}.qs button.on b{color:var(--good)}.qs button.danger{border-color:var(--bad)}.qs button.danger b{color:var(--bad)}.qs button.off b{color:var(--mute)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--s2)}.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 14px}.kpi small{color:var(--mute);display:block;font-size:12px}.kpi b{font-size:24px;letter-spacing:-.5px}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:var(--s3)}
.check{list-style:none;margin:var(--s2) 0 0;padding:0}.check li{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}.check li:last-child{border:0}.tick{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;font-size:13px;flex:none;border:1.5px solid var(--mute);color:var(--mute)}
.check .ok .tick{background:var(--good);border-color:var(--good);color:var(--card)}.check small{display:block;color:var(--mute)}
.plain{margin:0;padding-left:18px}.plain li+li{margin-top:6px}
.funnel{display:flex;gap:8px}.step{flex:1;display:block;text-align:center;text-decoration:none;color:var(--ink);background:var(--accent2);border-radius:12px;padding:12px 4px;min-height:64px}.step b{font-size:26px;display:block}.step small{color:var(--mute);font-size:12px}a.step:active{transform:scale(.97)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:space-between}.plat{font-size:12px;color:var(--mute);border:1px solid var(--line);border-radius:6px;padding:1px 8px;white-space:nowrap}.plat b{color:var(--ink)}
.tablewrap{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:var(--r)}table{width:100%;border-collapse:collapse}th,td{padding:10px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.04em}tr:last-child td{border:0}td.t{max-width:420px}
.empty{padding:22px;text-align:center;color:var(--mute)}a{color:var(--info)}.mini span{display:inline-block;margin:2px 10px 2px 0;font-size:13px}.src small{display:block;margin-top:6px}
.acc{padding:0}.acc>summary{cursor:pointer;font-weight:700;font-size:16px;padding:16px;list-style:none;display:flex;justify-content:space-between;align-items:center;min-height:56px}.acc>summary::after{content:"＋";font-size:20px;color:var(--mute)}.acc[open]>summary::after{content:"－"}.acc>summary::-webkit-details-marker{display:none}.accbody{padding:0 16px 16px}
.fs{border:1px solid var(--line);border-radius:12px;background:var(--bg)}.fs>summary{cursor:pointer;padding:12px 14px;font-weight:600;list-style:none;min-height:48px;display:flex;align-items:center;justify-content:space-between}.fs>summary::after{content:"›";font-size:20px;color:var(--mute);transform:rotate(90deg)}.fs[open]>summary::after{transform:rotate(-90deg)}.fs>summary::-webkit-details-marker{display:none}.fsbody{padding:0 14px 12px}
label{display:block;margin-top:12px;font-size:13px;color:var(--mute)}label small{display:block;font-size:12px;margin-top:2px}
input,select,textarea{display:block;width:100%;padding:11px 12px;margin-top:4px;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:10px;font:inherit;font-size:16px;min-height:44px}textarea{resize:vertical;line-height:1.45}input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
button{font:inherit;font-weight:600;border-radius:12px;padding:10px 18px;min-height:46px;border:1px solid var(--accent);cursor:pointer;background:var(--accent);color:var(--onaccent);width:100%}button.ghost{background:transparent;color:var(--accent)}button.danger{color:var(--bad);border-color:var(--bad)}button:active{transform:scale(.98)}button:disabled{opacity:.45;cursor:not-allowed;transform:none}
button.xl{min-height:60px;font-size:17px}button.big{min-height:52px;font-size:16px}
.btns,.btngrid{display:grid;grid-template-columns:1fr;gap:var(--s2)}.btns.two,.btngrid{grid-template-columns:1fr 1fr}.btngrid form,.btns form{margin:0}
#control>form{margin:0}audio{display:block;margin-top:12px;width:100%}code{background:var(--bg);padding:1px 6px;border-radius:5px}
.taskpanel{border:1px dashed var(--line);border-radius:12px;padding:var(--s3)}.taskpanel.running{border-color:var(--info);background:var(--bg)}.taskpanel.error{border-color:var(--bad)}.taskpanel.done{border-color:var(--good)}
.steps{list-style:none;margin:var(--s2) 0;padding:0}.steps li{display:flex;gap:10px;padding:6px 0}.steps small{display:block;white-space:pre-wrap;color:var(--mute);margin-top:2px}.ti{flex:none;width:22px;text-align:center}.steps .done .ti{color:var(--good)}.steps .error .ti{color:var(--bad)}
.spin{display:inline-block;width:16px;height:16px;border:2px solid var(--line);border-top-color:var(--info);border-radius:50%;animation:rot .8s linear infinite;vertical-align:-3px}@keyframes rot{to{transform:rotate(360deg)}}
.ready{display:grid;grid-template-columns:260px 1fr;gap:var(--s3);align-items:start}.ready .media{background:#000;border-radius:12px;overflow:hidden;aspect-ratio:9/16;max-height:480px}.ready video{display:block;width:100%;height:100%;object-fit:contain;background:#000}
.ttl{font-weight:600;line-height:1.35}.facts{display:flex;flex-wrap:wrap;gap:6px}.tags{display:flex;flex-wrap:wrap;gap:6px}.tag{background:var(--accent2);color:var(--good);border-radius:8px;padding:2px 8px;font-size:13px}
.cap textarea{margin-top:6px}.lint{font-size:13px;border-radius:10px;padding:8px 12px}.lint.ok{background:var(--accent2);color:var(--good)}.lint.warn{background:#fff3e0;color:#7a4300}@media (prefers-color-scheme:dark){.lint.warn{background:#3a2a10;color:var(--warn)}}
.note{font-size:13px;border-radius:10px;padding:8px 12px;background:var(--bg);color:var(--mute)}.note.warn{background:#fff3e0;color:#7a4300}@media (prefers-color-scheme:dark){.note.warn{background:#3a2a10;color:var(--warn)}}
.strip{display:grid;grid-template-columns:repeat(3,1fr);gap:var(--s2);text-align:center;margin-bottom:var(--s3)}.strip small{display:block;color:var(--mute);font-size:12px}.strip b{font-size:15px}
.alert{border-color:var(--bad)}.alert-soft{border-color:var(--warn)}.empty-guide{text-align:left}.empty-guide h3{font-size:17px}
footer{margin-top:32px;text-align:center;font-size:13px}.bottomnav{display:none}.desk{display:block}
@media (max-width:860px){.ready{grid-template-columns:1fr}.ready .media{max-height:52vh;width:min(100%,300px);margin:0 auto}}
@media (max-width:720px){
  body{font-size:16px;padding-bottom:calc(84px + env(safe-area-inset-bottom))}
  .wrap{padding-left:14px;padding-right:14px}h1{font-size:22px}h2{font-size:19px}
  .topnav{display:none}.refresh{display:inline-block;margin-left:auto;width:auto}.desk{display:none}
  header{position:static}
  main{padding-top:var(--s3)}section{margin:0}
  body.tabs section[data-tab]{display:none}body.tabs section[data-tab].on{display:block}
  .kpis{grid-template-columns:1fr 1fr}.kpi b{font-size:26px}
  .funnel{gap:6px}.step b{font-size:22px}
  .quick{grid-template-columns:1fr}.qs button{min-height:64px}
  .btngrid,.btns.two{grid-template-columns:1fr}
  .tablewrap{background:none;border:0;overflow:visible}table,tbody,tr,td{display:block;width:100%}tr.hd{display:none}
  tr{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px 14px;margin-bottom:var(--s2)}tr.none{background:none;border:0;margin:0}
  td{display:flex;justify-content:space-between;align-items:baseline;gap:14px;border:0;padding:5px 0;text-align:right}td::before{content:attr(data-label);color:var(--mute);font-size:12px;flex:none;text-transform:uppercase;letter-spacing:.03em}
  td.t{display:block;text-align:left;max-width:none;font-weight:600;padding-bottom:8px;margin-bottom:4px;border-bottom:1px dashed var(--line)}td.t::before{display:none}td[colspan]{display:block;text-align:center}td[colspan]::before{display:none}
  .bottomnav{display:flex;gap:2px;position:fixed;left:0;right:0;bottom:0;z-index:40;background:var(--card);border-top:1px solid var(--line);padding:6px 4px calc(6px + env(safe-area-inset-bottom));box-shadow:0 -4px 18px rgba(0,0,0,.08)}
  .bottomnav a{flex:1 1 auto;display:flex;flex-direction:column;align-items:center;gap:2px;text-decoration:none;color:var(--mute);padding:6px 2px;border-radius:12px;min-height:54px}
  .bottomnav a small{font-size:11px;font-weight:600;white-space:nowrap;letter-spacing:-.2px}.bottomnav a.on{color:var(--accent);background:var(--accent2)}
  .ic{position:relative;display:block;width:24px;height:24px}.ic svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.ic i{position:absolute;top:-6px;right:-14px;min-width:18px;text-align:center;padding:0 5px}
  footer{margin-top:24px}
}
@media (max-width:340px){.bottomnav{padding-left:0;padding-right:0;gap:0}.bottomnav a{padding-left:0;padding-right:0}.bottomnav a small{font-size:10px;letter-spacing:-.3px}}
"""

JS = r"""
(function(){
  var phone=window.matchMedia('(max-width:720px)'),tabs=['home','queue','publish','attention','posted','more'];
  function tabOf(hash){
    var h=(hash||'').replace('#','');
    if(tabs.indexOf(h)>=0)return {tab:h};
    var el=h&&document.getElementById(h);
    if(el){var s=el.closest('section[data-tab]');if(s)return {tab:s.dataset.tab,open:el};}
    return {tab:'home'};
  }
  function apply(){
    document.body.classList.toggle('tabs',phone.matches);
    var r=tabOf(location.hash),cur=r.tab;
    document.querySelectorAll('section[data-tab]').forEach(function(s){s.classList.toggle('on',s.dataset.tab===cur);});
    document.querySelectorAll('[data-go]').forEach(function(a){a.classList.toggle('on',a.dataset.go===cur);});
    if(r.open&&r.open.tagName==='DETAILS'){r.open.open=true;if(phone.matches)setTimeout(function(){r.open.scrollIntoView();},30);}
  }
  window.addEventListener('hashchange',function(){apply();if(phone.matches)window.scrollTo(0,0);});
  (phone.addEventListener||phone.addListener).call(phone,'change',apply);
  function folds(){document.querySelectorAll('.settings .fs,#notify .fs').forEach(function(d,i){if(phone.matches&&i>0&&!d.dataset.touched)d.open=false;});}
  document.addEventListener('toggle',function(e){if(e.target.classList&&e.target.classList.contains('fs'))e.target.dataset.touched='1';},true);
  apply();folds();

  // confirm dangerous buttons (post now, discard), count caption characters and hashtags while typing
  document.addEventListener('click',function(e){var b=e.target.closest('button[data-confirm]');if(b&&!window.confirm(b.dataset.confirm))e.preventDefault();});
  document.addEventListener('input',function(e){
    var t=e.target;if(!t.matches||!t.matches('textarea[data-caption]'))return;
    var card=t.closest('.ready'),txt=t.value;
    card.querySelector('[data-len]').textContent=txt.replace(/#[\p{L}\p{N}_]+/gu,'').trim().length;
    card.querySelector('[data-tags]').textContent=(txt.match(/#[\p{L}\p{N}_]+/gu)||[]).length;
  });
  // one click, one action: a second click while the first is being sent does nothing
  document.addEventListener('submit',function(e){
    var f=e.target;if(f.dataset.sent){e.preventDefault();return;}
    f.dataset.sent='1';setTimeout(function(){f.querySelectorAll('button').forEach(function(b){b.disabled=true;});},0);
  });
  var dirty=false;
  document.addEventListener('input',function(e){if(e.target.closest&&e.target.closest('form'))dirty=true;});

  // live progress of a running task: poll a small fragment; when it finishes, reload once to refresh every list
  function poll(){
    var panels=document.querySelectorAll('.taskpanel[data-running="1"]');
    if(!panels.length)return;
    fetch('/fragment/tasks',{cache:'no-store'}).then(function(r){return r.ok?r.text():null;}).then(function(html){
      if(!html)return;
      var tmp=document.createElement('div');tmp.innerHTML=html;var fresh=tmp.firstElementChild;
      if(fresh.dataset.running==='0'){location.reload();return;}
      panels.forEach(function(p){p.replaceWith(fresh.cloneNode(true));});
    }).catch(function(){});
  }
  setInterval(poll,2500);

  // idle refresh (no task, no typing, no playing media, tab visible) so numbers never go stale
  setInterval(function(){
    var a=document.activeElement,playing=false,panel=document.querySelector('.taskpanel[data-running="1"]');
    document.querySelectorAll('video,audio').forEach(function(v){if(!v.paused)playing=true;});
    if(!dirty&&!playing&&!document.hidden&&!panel&&!(a&&/^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)))location.reload();
  },90000);
})();
"""
