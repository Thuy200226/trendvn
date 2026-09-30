"""TikTok Studio publisher driven through a dedicated, isolated Chrome profile (no TikTok API, no cookies copied).

You sign in once yourself in the visible window opened by `./trendvn tiktok login`; the session then lives only in
data/agent/profiles/publisher. The publisher never types a password. Outcomes are conservative: once the Post button has
been clicked, anything short of a verified post is reported as "unknown" and publishing stops until it is resolved, so a
video can never be posted twice by an automatic retry.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from common import DATA, ENV, RUNTIME, chrome, log, worker

UPLOAD_URL = 'https://www.tiktok.com/tiktokstudio/upload?from=upload'
def _want_window():
    """A real, visible Chrome window is the honest default wherever a screen exists: TikTok challenges hidden automated browsers far
    more often, and the owner can solve a check on the spot. TRENDVN_PUBLISH_HEADED=0/1 overrides."""
    forced = ENV.get('TRENDVN_PUBLISH_HEADED')
    if forced in ('0', '1'):
        return forced == '1'
    return sys.platform in ('darwin', 'win32') or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


HEADED = _want_window()
LOGIN_URL = 'https://www.tiktok.com/login'
POST_LABELS = re.compile(r'^\s*(Post|Đăng|Publish)\s*$', re.I)
NOT_NOW = re.compile(r'^\s*(Not now|Cancel|Later|Để sau|Hủy|Huỷ|Bỏ qua)\s*$', re.I)
UPLOADED_HINTS = ('Uploaded', 'Đã tải lên', 'Upload complete', 'Tải lên hoàn tất')
VISIBILITY_LABELS = {'public': ('Mọi người', 'Everyone'), 'friends': ('Bạn bè', 'Friends'), 'self': ('Chỉ mình bạn', 'Only me')}
POPUP_BUTTONS = ('Hủy', 'Đã hiểu', 'Cancel', 'Got it')          # 'Hủy' here answers 'turn on automatic content checks?' with no: that is an account setting, yours to change
CHALLENGE_GRACE = 45                                            # TikTok sometimes clears a check by itself; only a persistent one pauses publishing
CHALLENGE_TEXT = ('Chọn 2 đối tượng', 'Select 2 objects', 'Kéo thanh trượt', 'Drag the slider', 'Xoay hình', 'Rotate the image',
                  'Verify to continue', 'Xác minh để tiếp tục', 'Hoàn thành xác minh')


class Challenge(Exception):
    """TikTok asked for human verification. We never solve it: stop, report, let the owner pass it once with `trust`."""


def has_challenge(page):
    try:
        if page.locator('#captcha_container, .captcha_verify_container, [class*="captcha" i]').count():
            return True
        text = page.inner_text('body', timeout=3000)
    except Exception:
        return False
    return any(w in text for w in CHALLENGE_TEXT)


def wait_for_upload_ui(page, seconds=150):
    """TikTok Studio needs 20-30s to build its upload page. Returns (frame, file_input); raises Challenge if a CAPTCHA persists."""
    deadline = time.time() + seconds
    challenge_since = None
    while time.time() < deadline:
        for frame in [page] + list(page.frames):
            try:
                loc = frame.locator('input[type="file"]')
                if loc.count():
                    return frame, loc.first
            except Exception:
                continue          # TikTok creates and destroys child frames while the page builds itself
        if has_challenge(page):
            challenge_since = challenge_since or time.time()
            if time.time() - challenge_since > CHALLENGE_GRACE:
                raise Challenge('TikTok yêu cầu xác minh (CAPTCHA)')
        else:
            challenge_since = None
        page.wait_for_timeout(1500)
    return page, None


def dismiss_popups(page):
    """Close TikTok's tips and the 'automatic content checks' offer that cover the editor. Returns how many were closed."""
    closed = 0
    for _ in range(6):
        hit = False
        for name in POPUP_BUTTONS:
            try:
                b = page.get_by_role('button', name=re.compile('^' + name + '$'))
                if b.count() and b.first.is_visible():
                    b.first.click(timeout=5000)
                    page.wait_for_timeout(900)
                    hit = True
                    closed += 1
            except Exception:
                continue
        if not hit:
            break
    return closed


def wait_uploaded(page, seconds=240):
    """The upload status block reads 'Đã tải lên (size)' when TikTok has received the whole file."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            box = page.locator('[data-e2e="upload_status_container"]')
            if box.count() and any(h.lower() in box.first.inner_text().lower() for h in UPLOADED_HINTS):
                return True
        except Exception:
            pass
        page.wait_for_timeout(2000)
    return False


def set_caption(page, editor, caption):
    """Replace the pre-filled file name with our caption and confirm it really is there."""
    editor.click(timeout=15000)
    page.keyboard.press('Control+A')
    page.keyboard.press('Meta+A')
    page.keyboard.press('Delete')
    page.keyboard.type(caption, delay=25)
    page.wait_for_timeout(1200)
    shown = re.sub(r'\s+', ' ', editor.inner_text()).strip()
    return norm(shown).startswith(norm(caption)[:25]) and 'final' != shown


def set_visibility(page, wanted):
    """Pick who can see the post. 'public' is TikTok's default and is left untouched."""
    if wanted == 'public' or wanted not in VISIBILITY_LABELS:
        return True
    labels = VISIBILITY_LABELS[wanted]
    box = page.locator('[data-e2e="video_visibility_container"]')
    box.locator('button, [role="combobox"], [role="button"]').first.click(timeout=10000)
    page.wait_for_timeout(800)
    for label in labels:
        opt = page.get_by_text(label, exact=True)
        if opt.count():
            opt.last.click(timeout=8000)
            page.wait_for_timeout(800)
            break
    return any(l in box.inner_text() for l in labels)


def studio_shows(ctx, caption, seconds=60):
    """Second opinion for posts the public profile cannot show (private or friends-only): TikTok Studio's own content list."""
    page = ctx.new_page()
    try:
        page.goto('https://www.tiktok.com/tiktokstudio/content', wait_until='domcontentloaded', timeout=60000)
        needle = re.sub(r'\s+', ' ', caption).strip()[:25]
        deadline = time.time() + seconds
        while time.time() < deadline:
            if needle and needle in re.sub(r'\s+', ' ', page.inner_text('body')):
                return True
            page.wait_for_timeout(2500)
    except Exception:
        pass
    finally:
        page.close()
    return False


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def norm(text):
    return re.sub(r'[^\w]+', '', (text or '').lower())[:60]


def logged_in(ctx):
    return any(c['name'] == 'sessionid' and 'tiktok.com' in c['domain'] for c in ctx.cookies())


def login(minutes=10):
    """Open a visible window and wait (default 10 minutes) for you to finish signing in yourself."""
    with chrome('publisher', headless=False, locale='vi-VN', viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URL, wait_until='domcontentloaded')
        log('Đăng nhập TikTok trong cửa sổ vừa mở. Hệ thống không nhập mật khẩu thay bạn.')
        deadline = time.time() + 60 * minutes
        while time.time() < deadline:
            if logged_in(ctx):
                page.wait_for_timeout(4000)
                log('Đã có phiên đăng nhập; phiên chỉ lưu trong hồ sơ trình duyệt riêng.')
                return True
            page.wait_for_timeout(2000)
    return False


def trust(minutes=15):
    """Open the upload page in a visible window so YOU can pass TikTok's human check once. Nothing is uploaded or posted."""
    with chrome('publisher', headless=False, locale='vi-VN', viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(UPLOAD_URL, wait_until='domcontentloaded')
        log('Nếu TikTok hiện hình xác minh, hãy tự giải trong cửa sổ vừa mở. Hệ thống không giải thay bạn.')
        deadline = time.time() + 60 * minutes
        while time.time() < deadline:
            if page.locator('input[type="file"]').count() and not has_challenge(page):
                page.wait_for_timeout(3000)
                log('Trang tải lên đã sẵn sàng, không còn yêu cầu xác minh.')
                try:
                    worker('/api/publisher/challenge', {'active': False})   # publishing resumes on its own
                except Exception:
                    pass
                return True
            page.wait_for_timeout(2000)
    return False


def session_status(deep=False):
    """Shallow (default, used by the schedule): is there a login cookie? No window opens. Deep (CLI `status`): load Studio and confirm."""
    with chrome('publisher', locale='vi-VN', headless=not (deep and HEADED)) as ctx:
        if not logged_in(ctx):
            return {'logged_in': False, 'reason': 'Chưa đăng nhập. Chạy: ./trendvn tiktok login'}
        if not deep:
            return {'logged_in': True}
        page = ctx.new_page()
        try:
            page.goto(UPLOAD_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(6000)
            if '/login' in page.url:
                return {'logged_in': False, 'reason': 'Phiên đã hết hạn. Đăng nhập lại.'}
            return {'logged_in': True}
        finally:
            page.close()


def own_descriptions(ctx, target):
    """Captions already on the account (public profile), used to avoid re-posting the same idea."""
    page = ctx.new_page()
    seen = []

    def on_resp(r):
        try:
            if '/api/post/item_list' in r.url and r.status == 200:
                for it in json.loads(r.body()).get('itemList') or []:
                    st = it.get('stats') or {}
                    seen.append({'id': str(it.get('id')), 'desc': it.get('desc') or '', 'views': st.get('playCount'), 'likes': st.get('diggCount'),
                                 'comments': st.get('commentCount'), 'shares': st.get('shareCount')})
        except Exception:
            pass
    page.on('response', on_resp)
    try:
        page.goto('https://www.tiktok.com/@' + target, wait_until='domcontentloaded', timeout=60000)
        deadline = time.time() + 40            # the profile builds itself as slowly as Studio does; wait for the first video list
        while not seen and time.time() < deadline:
            page.wait_for_timeout(1500)
        for _ in range(3):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(2000)
    except Exception as e:
        log('profile read warning: ' + str(e)[:120])
    finally:
        page.close()
    return seen


def _shot(page, name):
    try:
        path = DATA / 'shots' / ('%s_%d.png' % (name, int(time.time())))
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None


def export_shot(page, name):
    """Screenshot the owner can open from the dashboard (the worker serves data/worker/exports/shot_*.png). Returns the file name."""
    try:
        folder = RUNTIME / 'exports'
        folder.mkdir(exist_ok=True)
        fname = 'shot_%d.png' % int(time.time())
        page.screenshot(path=str(folder / fname), full_page=False)
        for old in sorted(folder.glob('shot_*.png'))[:-20]:          # keep the latest twenty
            old.unlink(missing_ok=True)
        return fname
    except Exception:
        return ''


def publish_one(job, dry_run=True):
    """Never raises. Returns (outcome, url, reason) with outcome in published|failed|deferred|challenge|unknown|duplicate|dry_run.
    Any error before the Post button is clicked is 'failed' (nothing was posted); after the click it is always 'unknown'."""
    state = {'clicked': False}
    try:
        return _publish_one(job, dry_run, state)
    except Exception as e:
        log('publish error: %s' % str(e)[:200])
        if state['clicked']:
            return 'unknown', '', 'Đã bấm Đăng nhưng gặp lỗi khi xác nhận: ' + str(e)[:140]
        return 'failed', '', 'Không chạy được trình duyệt hoặc lỗi trước khi đăng: ' + str(e)[:160]


def _publish_one(job, dry_run, state):
    video = RUNTIME / 'jobs' / job['id'] / 'final.mp4'
    if not video.is_file():
        return 'failed', '', 'Không thấy file video đã dựng'
    if sha256(video) != job['output_hash']:
        return 'failed', '', 'Hash video thay đổi sau khi dựng; không đăng'
    clicked_post = False
    with chrome('publisher', locale='vi-VN', headless=not HEADED, viewport=(1280, 1000)) as ctx:
        if not logged_in(ctx):
            return 'failed', '', 'Chưa đăng nhập TikTok trong hồ sơ riêng'
        existing = own_descriptions(ctx, job['target'])
        key = norm(job['caption'])
        if key and any(norm(e['desc']) == key for e in existing):
            if job.get('manual'):       # the owner chose this video: let them edit the caption instead of discarding it
                return 'deferred', '', 'Tài khoản đã có bài có mô tả giống hệt. Hãy sửa mô tả rồi đăng lại.'
            return 'duplicate', '', 'Tài khoản đã có bài cùng nội dung mô tả'
        before_ids = {e['id'] for e in existing}
        page = ctx.new_page()
        try:
            page.goto(UPLOAD_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(3000)
            if '/login' in page.url:
                return 'failed', '', 'Phiên đăng nhập đã hết hạn'
            target, file_input = wait_for_upload_ui(page)
            if file_input is None:
                return 'failed', _shot(page, 'no_file_input') or '', 'Không tìm thấy ô chọn file; giao diện TikTok Studio có thể đã đổi'
            file_input.set_input_files(str(video))
            editor = target.locator('[contenteditable="true"]').first
            editor.wait_for(timeout=180000)
            if not wait_uploaded(page):
                return 'failed', _shot(page, 'upload_slow') or '', 'TikTok chưa nhận xong video sau 4 phút'
            dismiss_popups(page)
            if not set_caption(page, editor, job['caption']):
                dismiss_popups(page)
                if not set_caption(page, editor, job['caption']):
                    return 'failed', _shot(page, 'caption') or '', 'Không điền được mô tả vào ô nhập của TikTok'
            if not set_visibility(page, job.get('visibility', 'public')):
                return 'failed', _shot(page, 'visibility') or '', 'Không chọn được chế độ hiển thị; dừng để không đăng sai đối tượng'
            dismiss_popups(page)
            deadline = time.time() + 300
            post_btn = None
            while time.time() < deadline:
                for cand in (target.locator('[data-e2e="post_video_button"]'), target.get_by_role('button', name=POST_LABELS)):
                    if cand.count() and cand.first.is_enabled():
                        post_btn = cand.first
                        break
                if post_btn:
                    break
                page.wait_for_timeout(2000)
            if post_btn is None:
                return 'failed', _shot(page, 'post_disabled') or '', 'Nút Đăng chưa sẵn sàng (video chưa tải xong hoặc bị chặn)'
            if dry_run:
                return 'dry_run', export_shot(page, 'dry_run'), 'Chạy thử: đã tải video, điền mô tả, dừng trước nút Đăng'
            clicked_post = state['clicked'] = True
            post_btn.click()
            page.wait_for_timeout(3000)
            for label in ('Post now', 'Đăng ngay'):
                confirm = page.get_by_role('button', name=re.compile('^' + label + '$', re.I))
                if confirm.count():
                    confirm.first.click()
                    break
            for _ in range(30):                      # TikTok leaves the upload page once it accepted the post
                if 'tiktokstudio/upload' not in page.url:
                    break
                page.wait_for_timeout(2000)
            page.wait_for_timeout(5000)
        except Challenge as e:
            shot = _shot(page, 'challenge')
            if clicked_post:
                return 'unknown', shot or '', 'Đã bấm Đăng nhưng TikTok đòi xác minh: chưa biết bài có lên không'
            return 'challenge', shot or '', '%s. Đăng tạm dừng tới khi bạn giải: ./trendvn tiktok trust' % e
        except Exception as e:
            shot = _shot(page, 'error')
            if clicked_post:
                return 'unknown', shot or '', 'Đã bấm Đăng nhưng chưa xác nhận: ' + str(e)[:120]
            return 'failed', shot or '', 'Lỗi trước khi bấm Đăng: ' + str(e)[:160]
        finally:
            page.close()
        # verification: the new caption must appear on the public profile with an id we have not seen before
        for _ in range(4):
            after = own_descriptions(ctx, job['target'])
            fresh = [e for e in after if e['id'] not in before_ids and norm(e['desc']) == key]
            if fresh:
                return 'published', 'https://www.tiktok.com/@%s/video/%s' % (job['target'], fresh[0]['id']), 'Đã xác nhận trên hồ sơ'
            if job.get('visibility', 'public') != 'public' and studio_shows(ctx, job['caption']):
                return 'published', '', 'Đã xác nhận trong trang nội dung của TikTok Studio (bài không công khai nên chưa có trên hồ sơ)'
            time.sleep(45)
    return 'unknown', '', 'Đã bấm Đăng nhưng chưa thấy bài trên hồ sơ công khai (có thể đang chờ duyệt)'


def run_publish(job_id=None):
    """Claim one video from the worker and post it. Scheduled: the worker enforces switch, window, daily limit and spacing.
    With job_id (the dashboard's Post button) the owner's click is the consent and only the account-protecting rails apply."""
    claim = worker('/api/publish/claim', {'job_id': job_id} if job_id else {})
    if claim['status'] != 'claimed':
        return claim
    outcome, url, reason = publish_one(claim, dry_run=False)
    # 'deferred' = nothing was posted and it is not this video's fault (verification, duplicate caption): not counted as a failure
    finish = {'published': 'published', 'duplicate': 'duplicate', 'unknown': 'unknown', 'deferred': 'deferred', 'challenge': 'deferred'}.get(outcome, 'failed')
    if outcome == 'challenge':
        worker('/api/publisher/challenge', {'active': True})
    worker('/api/publish/finish', {'id': claim['id'], 'lease': claim['lease'], 'outcome': finish,
                                   'url': url if url.startswith('https://') else '', 'reason': reason})
    return {'status': outcome, 'id': claim['id'], 'reason': reason, 'url': url if url.startswith('https://') else ''}


def dry_run_next(job_id=None):
    """Rehearse a ready video (the next one, or the chosen one) without touching the switch: upload, caption, screenshot, stop."""
    st = worker('/api/publish/peek', {'job_id': job_id} if job_id else {})
    if st.get('status') != 'ready':
        return st
    outcome, shot, reason = publish_one(st, dry_run=True)
    return {'status': outcome, 'reason': reason, 'screenshot': shot}


def run_stats():
    """Read views/likes of our posts from the public profile and hand them to the worker (feeds the source weights)."""
    from common import worker_get
    target = worker_get('/api/status')['target']
    with chrome('publisher', locale='vi-VN', headless=not HEADED) as ctx:
        posts = own_descriptions(ctx, target)
    items = [{'video_id': p['id'], 'views': p['views'] or 0, 'likes': p['likes'] or 0, 'comments': p['comments'] or 0,
              'shares': p['shares'] or 0} for p in posts if p['id'].isdigit()]
    matched = 0
    for i in range(0, len(items), 200):            # the worker accepts 200 posts per call; a busy channel has more
        matched += worker('/api/stats', {'items': items[i:i + 200]}).get('matched', 0)
    return {'read': len(items), 'matched': matched}


def verify_unresolved():
    """Resolve uncertain publishes by reading the public profile; never re-posts."""
    items = worker('/api/publish/unresolved', {})['items']
    if not items:
        return {'resolved': 0}
    from common import worker_get
    target = worker_get('/api/status')['target']
    resolved = 0
    with chrome('publisher', locale='vi-VN', headless=not HEADED) as ctx:
        posts = own_descriptions(ctx, target)
        for job in items:
            key = norm(job.get('caption'))
            match = [p for p in posts if key and norm(p['desc']) == key]
            if match:
                worker('/api/publish/resolve', {'id': job['id'], 'outcome': 'published',
                                                'url': 'https://www.tiktok.com/@%s/video/%s' % (target, match[0]['id'])})
                resolved += 1
    return {'resolved': resolved, 'still_unknown': len(items) - resolved}


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'login':
        print('OK' if login(int(sys.argv[2]) if len(sys.argv) > 2 else 10) else 'TIMEOUT')
    elif cmd == 'trust':
        print('OK' if trust(int(sys.argv[2]) if len(sys.argv) > 2 else 15) else 'TIMEOUT')
    elif cmd == 'status':
        print(json.dumps(session_status(deep=True), ensure_ascii=False))
    elif cmd == 'dry-run':
        print(json.dumps(dry_run_next(), ensure_ascii=False))
    elif cmd == 'stats':
        print(json.dumps(run_stats(), ensure_ascii=False))
    elif cmd == 'verify':
        print(json.dumps(verify_unresolved(), ensure_ascii=False))
    else:
        print('usage: publisher.py login|trust|status|dry-run|verify|stats')
