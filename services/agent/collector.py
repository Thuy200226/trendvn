"""Discovery + media fetch for Douyin, Kuaishou (CN) and TikTok, Instagram Reels (US).

Reads the same public JSON the sites' own web pages load, inside a real Chrome. It never solves CAPTCHAs or logs in;
a login wall or verification page is reported as a stream failure, not bypassed. US streams are only collected when the
browser's exit country is verified as US, so Vietnamese feeds are never mislabelled as US trends.
"""
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from common import ENV, RUNTIME, chrome, log, proxy_for, worker

MAX_DURATION = 180
MAX_BYTES = 250 * 1024 * 1024
CDN_SUFFIXES = ('zjcdn.com', 'douyinvod.com', 'douyincdn.com', 'douyin.com', 'bytecdn.cn', 'bytedance.com', 'ibytedtos.com',
                'tiktok.com', 'tiktokcdn.com', 'tiktokcdn-us.com', 'tiktokv.com', 'tiktokv.us',
                'kwaicdn.com', 'yximgs.com', 'kuaishou.com', 'gifshow.com', 'ksapisrv.com')


# ---------------------------------------------------------------- normalisers (pure, unit-tested)

def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def parse_douyin(payload):
    items = []
    for a in (payload.get('aweme_list') or []):
        if not isinstance(a, dict) or a.get('aweme_type') != 0 or a.get('is_ads') or not a.get('video'):
            continue
        stats = a.get('statistics') or {}
        vid = str(a.get('aweme_id') or '')
        urls = ((a['video'].get('play_addr') or {}).get('url_list')) or []
        urls = [u for u in urls if isinstance(u, str) and u.startswith('http')]
        if not vid or not urls or not stats:
            continue
        urls = [u.replace('http://', 'https://', 1) for u in urls]
        duration = (a.get('duration') or a['video'].get('duration') or 0) / 1000
        items.append({'source_id': vid, 'url': 'https://www.douyin.com/video/' + vid, 'title': str(a.get('desc') or '')[:500],
                      'likes': _num(stats.get('digg_count')), 'views': None, 'duration': duration, 'created': _num(a.get('create_time')),
                      'media': {'kind': 'direct', 'url': urls[0], 'referer': 'https://www.douyin.com/'}})
    return items


def parse_kuaishou(payload):
    items = []
    feeds = (((payload.get('data') or {}).get('brilliantTypeData') or {}).get('feeds')) or []
    for f in feeds:
        p = f.get('photo') if isinstance(f, dict) else None
        if not p or not p.get('id') or not p.get('photoUrl'):
            continue
        vid = str(p['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', vid):
            continue
        items.append({'source_id': vid, 'url': 'https://www.kuaishou.com/short-video/' + vid,
                      'title': str(p.get('caption') or '')[:500], 'likes': _num(p.get('realLikeCount')),
                      'views': _num(p.get('viewCount')), 'duration': (p.get('duration') or 0) / 1000,
                      'created': (_num(p.get('timestamp')) or 0) // 1000 or None,
                      'media': {'kind': 'direct', 'url': p['photoUrl'], 'referer': 'https://www.kuaishou.com/'}})
    return items


def parse_tiktok(payload):
    items = []
    for it in (payload.get('itemList') or []):
        if not isinstance(it, dict) or it.get('isAd') or not it.get('video') or not it.get('id'):
            continue
        vid = str(it['id'])
        user = (it.get('author') or {}).get('uniqueId') or ''
        if not re.fullmatch(r'\d{6,25}', vid) or not re.fullmatch(r'[A-Za-z0-9._-]{1,50}', user):
            continue
        v = it['video']
        media = v.get('downloadAddr') or v.get('playAddr')
        if not media:
            continue
        stats = it.get('stats') or {}
        items.append({'source_id': vid, 'url': f'https://www.tiktok.com/@{user}/video/{vid}', 'title': str(it.get('desc') or '')[:500],
                      'likes': _num(stats.get('diggCount')), 'views': _num(stats.get('playCount')),
                      'duration': v.get('duration') or 0, 'created': _num(it.get('createTime')),
                      'media': {'kind': 'direct', 'url': media, 'referer': 'https://www.tiktok.com/'},
                      'origin_country': it.get('locationCreated')})
    return items


def parse_instagram_codes(text):
    """Reel shortcodes visible on the public Reels page (order preserved, de-duplicated)."""
    seen, codes = set(), []
    for m in re.finditer(r'/reels?/([A-Za-z0-9_-]{6,20})/', text):
        c = m.group(1)
        if c not in seen and c != 'audio':
            seen.add(c)
            codes.append(c)
    for m in re.finditer(r'"code":"([A-Za-z0-9_-]{8,14})"', text):
        c = m.group(1)
        if c not in seen:
            seen.add(c)
            codes.append(c)
    return codes


def age_hours(item, now=None):
    created = item.get('created')
    return max(0.0, ((now or time.time()) - created) / 3600) if created else None


def qualifies(platform, item, thresholds, now=None):
    """Engagement, length, freshness and structure gates applied before anything reaches the queue."""
    age = age_hours(item, now)
    if age is not None and age > 24 * thresholds.get('max_age_days', 7):
        return False
    duration = item.get('duration')
    if duration is None and platform == 'instagram':
        pass  # yt-dlp omits it for some reels; the worker probes the real file and enforces the limit
    elif not 1 <= (duration or 0) <= min(MAX_DURATION, thresholds.get('max_duration', MAX_DURATION)):
        return False
    min_views = (thresholds.get('min_views') or {}).get(platform, 0)
    min_likes = (thresholds.get('min_likes') or {}).get(platform, 0)
    if item.get('views') is not None and item['views'] < min_views:
        return False
    if min_likes and item.get('likes') is not None and item['likes'] < min_likes:
        return False
    if min_views and item.get('views') is None and platform != 'instagram':
        return False
    return True


def score(platform, item, weights=None, now=None):
    """Newly-trending score: engagement per (softened) hour of age, nudged by how well this source performed for us.
    Views are used when the site shows them; otherwise likes stand in (about 4% of viewers like a video)."""
    base = item.get('views') or (item.get('likes') or 0) * 25
    age = age_hours(item, now)
    per_hour = base / (max(age, 6.0) ** 0.6) if age is not None else base / 24 ** 0.6
    return round(per_hour * (weights or {}).get(platform, 1.0))


# ---------------------------------------------------------------- browser capture

class Blocked(Exception):
    pass


def _looks_blocked(page):
    try:
        text = page.inner_text('body', timeout=3000)[:2000].lower()
    except Exception:
        return False
    return any(w in text for w in ('captcha', 'verify to continue', '验证码', '请完成验证', 'security verification', 'log in to continue'))


def exit_country(ctx):
    """Country of the browser's public exit IP, so region-bound streams are never guessed."""
    for url in ('https://ipinfo.io/country', 'https://api.country.is/'):
        try:
            r = ctx.request.get(url, timeout=15000)
            if r.ok:
                text = r.text().strip()
                m = re.search(r'\b([A-Z]{2})\b', text.replace('"country":"', ' ').replace('"', ' '))
                if m:
                    return m.group(1)
        except Exception:
            continue
    return None


def capture(ctx, url, match, parse, attempts=3, **kw):
    """Sites reset connections now and then; retry with a fresh page before calling a stream empty."""
    last = None
    for n in range(1, attempts + 1):
        try:
            items = _capture_once(ctx, url, match, parse, **kw)
            if items:
                return items
            last = Blocked('no videos returned') if n == attempts else None
        except Blocked:
            raise
        except Exception as e:
            last = e
        log('capture retry %d/%d for %s' % (n, attempts, url))
        time.sleep(6 * n)
    if last:
        raise last
    return []


def _capture_once(ctx, url, match, parse, scrolls=4, wait_ms=12000, before_scroll=None):
    page = ctx.new_page()
    found = {}
    order = []

    def on_response(r):
        try:
            if r.status == 200 and match(r.url) and 'json' in r.headers.get('content-type', ''):
                for it in parse(json.loads(r.body())):
                    if it['source_id'] not in found:
                        found[it['source_id']] = it
                        order.append(it['source_id'])
        except Exception:
            pass

    page.on('response', on_response)
    try:
        try:
            page.goto(url, wait_until='commit', timeout=60000)
        except Exception as e:
            log('goto warning %s: %s' % (url, str(e)[:100]))
        page.wait_for_timeout(wait_ms)
        if before_scroll:
            before_scroll(page)
            page.wait_for_timeout(4000)
        for _ in range(scrolls):
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(2500)
        if not found and _looks_blocked(page):
            raise Blocked('verification or login wall shown')
        for n, sid in enumerate(order, 1):
            found[sid]['rank'] = n
        return [found[s] for s in order]
    finally:
        page.close()


def scan_douyin(ctx):
    return {'jingxuan': capture(ctx, 'https://www.douyin.com/jingxuan', lambda u: '/aweme/v2/web/module/feed' in u or '/aweme/v1/web/tab/feed' in u, parse_douyin)}


def scan_kuaishou(ctx):
    return {'brilliant': capture(ctx, 'https://www.kuaishou.com/brilliant', lambda u: u.endswith('/graphql'), parse_kuaishou, wait_ms=14000)}


def _click_chip(text):
    def go(page):
        page.locator('[data-e2e="explore-category-chip"]', has_text=re.compile('^' + re.escape(text) + '$')).first.click(timeout=8000)
    return go


TIKTOK_CHIPS = [('singing_dancing', 'Singing & Dancing'), ('comedy', 'Comedy'), ('lipsync', 'Lipsync'), ('shows', 'Shows')]


def scan_tiktok(ctx):
    out = {}
    for stream, chip in TIKTOK_CHIPS:
        try:
            out[stream] = capture(ctx, 'https://www.tiktok.com/explore', lambda u: '/api/explore/item_list/' in u, parse_tiktok,
                                  scrolls=2, wait_ms=9000, before_scroll=_click_chip(chip))
        except Blocked:
            raise
        except Exception as e:
            log('tiktok chip %s failed: %s' % (chip, str(e)[:120]))
            out[stream] = []
    return out


def scan_instagram(ctx):
    page = ctx.new_page()
    try:
        try:
            page.goto('https://www.instagram.com/reels/', wait_until='commit', timeout=60000)
        except Exception as e:
            log('instagram goto warning: ' + str(e)[:100])
        page.wait_for_timeout(9000)
        codes = []
        for _ in range(4):
            codes = parse_instagram_codes(page.content())
            page.keyboard.press('ArrowDown')
            page.wait_for_timeout(2500)
        codes = parse_instagram_codes(page.url + ' ' + page.content()) or codes
        if not codes and _looks_blocked(page):
            raise Blocked('login wall shown')
    finally:
        page.close()
    items = []
    for n, code in enumerate(codes[:14], 1):
        meta = ytdlp_meta('https://www.instagram.com/reel/%s/' % code)
        if not meta:
            continue
        items.append({'source_id': code, 'url': 'https://www.instagram.com/reel/%s/' % code, 'title': str(meta.get('description') or meta.get('title') or '')[:500],
                      'likes': _num(meta.get('like_count')), 'views': _num(meta.get('view_count')), 'duration': meta.get('duration'),
                      'created': _num(meta.get('timestamp')),
                      'rank': n, 'media': {'kind': 'ytdlp', 'url': 'https://www.instagram.com/reel/%s/' % code}})
    return {'reels': items}


def ytdlp_proxy():
    """Instagram goes through yt-dlp, so it must use the same US exit as the browser (validated by proxy_for)."""
    if proxy_for('us') is None:
        return []
    return ['--proxy', ENV['TRENDVN_US_PROXY'].strip()]


def ytdlp_meta(url):
    try:
        p = subprocess.run([sys.executable, '-m', 'yt_dlp', '-j', '--no-warnings', '--no-playlist', '--socket-timeout', '20', *ytdlp_proxy(), url],
                           capture_output=True, timeout=90)
        return json.loads(p.stdout) if p.returncode == 0 and p.stdout else None
    except Exception:
        return None


# ---------------------------------------------------------------- media download

def download(ctx, item, platform):
    """Fetch one video into the shared inbox and return its file name. Raises on any doubt."""
    m = item['media']
    name = '%s_%s.mp4' % (platform, item['source_id'])
    dest = RUNTIME / 'inbox' / name
    tmp = dest.with_suffix('.part')
    if m['kind'] == 'ytdlp':
        p = subprocess.run([sys.executable, '-m', 'yt_dlp', '--no-warnings', '--no-playlist', *ytdlp_proxy(), '-f', 'mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
                            '--merge-output-format', 'mp4', '--max-filesize', str(MAX_BYTES), '-o', str(tmp) + '.%(ext)s', m['url']],
                           capture_output=True, timeout=240)
        produced = list(RUNTIME.glob('inbox/' + tmp.name + '.*'))
        if p.returncode or not produced:
            raise ValueError('yt-dlp could not download this reel')
        produced[0].rename(tmp)
    else:
        host = (urlsplit(m['url']).hostname or '').lower()
        if not m['url'].startswith('https://') or not any(host == d or host.endswith('.' + d) for d in CDN_SUFFIXES):
            raise ValueError('Media host is not a known platform CDN: ' + host)
        r = ctx.request.get(m['url'], headers={'Referer': m['referer']}, timeout=120000)
        if not r.ok:
            raise ValueError('Media HTTP %s' % r.status)
        body = r.body()
        if not 50_000 <= len(body) <= MAX_BYTES:
            raise ValueError('Media size out of range')
        tmp.write_bytes(body)
    head = tmp.read_bytes()[:12]
    if b'ftyp' not in head:
        tmp.unlink(missing_ok=True)
        raise ValueError('Downloaded file is not an MP4 container')
    tmp.replace(dest)
    return name


# ---------------------------------------------------------------- orchestration

SOURCES = {
    # geo_locked: the feed depends on the viewer's IP, so the exit country must match. Douyin and Kuaishou only serve
    # mainland-China content, so any IP sees the same source.
    'douyin': {'country': 'CN', 'locale': 'zh-CN', 'scan': scan_douyin, 'geo_locked': False},
    'kuaishou': {'country': 'CN', 'locale': 'zh-CN', 'scan': scan_kuaishou, 'geo_locked': False},
    'tiktok': {'country': 'US', 'locale': 'en-US', 'scan': scan_tiktok, 'geo_locked': True},
    'instagram': {'country': 'US', 'locale': 'en-US', 'scan': scan_instagram, 'geo_locked': True},
}


def collect(platforms=None, download_media=True, ingest=True, thresholds=None, limit=None):
    from common import worker_get
    st = worker_get('/api/status')
    thresholds = dict(thresholds or st.get('thresholds') or {}, weights=st.get('weights') or {})
    limit = limit or thresholds.get('max_candidates_per_scan', 6)
    report = {}
    selected = list(platforms or SOURCES)
    by_country = {}
    for p in selected:
        by_country.setdefault(SOURCES[p]['country'], []).append(p)
    for country, plats in by_country.items():
        try:
            with chrome('collector-' + country.lower(), locale=SOURCES[plats[0]]['locale'], region=country) as ctx:
                exit_c = exit_country(ctx)
                log('%s sources use exit country %s' % (country, exit_c))
                for platform in plats:
                    if SOURCES[platform]['geo_locked'] and exit_c != country:
                        report[platform] = {'status': 'skipped', 'reason': 'Cần IP %s để lấy xu hướng đúng quốc gia; IP hiện tại: %s. Đặt TRENDVN_%s_PROXY.' % (country, exit_c or 'không xác định', country)}
                        continue
                    report[platform] = run_platform(ctx, platform, thresholds, download_media, ingest, limit)
        except Exception as e:
            for platform in plats:
                report.setdefault(platform, {'status': 'error', 'reason': str(e)[:200]})
    ok = [p for p, r in report.items() if r.get('status') == 'ok']
    detail = {p: (r.get('summary') or r.get('reason')) for p, r in report.items()}
    if ingest:
        worker('/api/heartbeat', {'component': 'discovery', 'ok': bool(ok), 'detail': detail})
    return report


def run_platform(ctx, platform, thresholds, download_media, ingest, limit):
    cfg = SOURCES[platform]
    try:
        streams = cfg['scan'](ctx)
    except Blocked as e:
        return {'status': 'error', 'reason': 'Trang yêu cầu xác minh/đăng nhập (%s); không vượt qua CAPTCHA.' % e}
    except Exception as e:
        return {'status': 'error', 'reason': 'Lỗi thu thập: ' + str(e)[:160]}
    summary = {}
    downloads = []
    weights = thresholds.get('weights') or {}
    for stream, raw in streams.items():
        good = [i for i in raw if qualifies(platform, i, thresholds)]
        for i in good:
            age = age_hours(i)
            i['score'] = score(platform, i, weights)
            i['meta'] = {k: v for k, v in (('score', i['score']), ('likes', i.get('likes')), ('views', i.get('views')),
                                            ('age_h', round(age, 1) if age is not None else None), ('created', i.get('created'))) if v is not None}
        summary[stream] = {'seen': len(raw), 'qualified': len(good)}
        if not ingest or not good:
            continue
        batch = {'platform': platform, 'stream': stream, 'observed_at': time.time(), 'items': [
            {'source_id': i['source_id'], 'url': i['url'], 'country': cfg['country'], 'title': i['title'],
             'rank': i['rank'], 'views': i['views'], 'evidence_url': i['url'], 'meta': i['meta']} for i in good[:100]]}
        try:
            res = worker('/api/ingest', batch)
            summary[stream].update(baseline=res['baseline'], new=res['new'])
        except Exception as e:
            summary[stream]['error'] = str(e)[:160]
        downloads.extend(good)
    if download_media and ingest:
        summary['media'] = fetch_pending(ctx, platform, {i['source_id']: i for i in downloads}, limit)
    return {'status': 'ok' if any(s.get('seen') for s in summary.values() if isinstance(s, dict)) else 'error',
            'summary': summary, 'reason': None if any(s.get('seen') for s in summary.values() if isinstance(s, dict)) else 'Không đọc được video nào'}


def fetch_pending(ctx, platform, seen_now, limit):
    from common import worker_get
    counts = worker_get('/api/status')['counts']
    backlog = sum(counts.get(k, 0) for k in ('queued', 'processing', 'ready'))
    room = max(0, (worker_get('/api/status')['thresholds'].get('max_backlog', 4)) - backlog)
    limit = min(limit, room)
    if limit == 0:
        return {'downloaded': 0, 'failed': 0, 'waiting': 0, 'note': 'Hàng chờ đã đủ; chưa tải thêm'}
    pending = [p for p in worker('/api/media/pending', {'limit': 100})['items'] if p['platform'] == platform and p['source_id'] in seen_now]
    pending.sort(key=lambda p: seen_now[p['source_id']].get('score', 0), reverse=True)
    done = failed = 0
    for job in pending[:limit]:
        item = seen_now[job['source_id']]
        try:
            name = download(ctx, item, platform)
            res = worker('/api/attach', {'id': job['id'], 'filename': name})
            log('%s %s -> %s' % (platform, job['source_id'], res['state']))
            done += 1
        except Exception as e:
            failed += 1
            log('download failed %s %s: %s' % (platform, job['source_id'], str(e)[:160]))
            try:
                worker('/api/media/failed', {'id': job['id'], 'reason': str(e)[:300]})
            except Exception:
                pass
    return {'downloaded': done, 'failed': failed, 'waiting': max(0, len(pending) - limit)}


if __name__ == '__main__':
    import sys
    plats = [a for a in sys.argv[1:] if a in SOURCES]
    print(json.dumps(collect(plats or None), ensure_ascii=False, indent=2))
