"""Shared plumbing for the TrendVN host agent: config, worker client, isolated Chrome profiles."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data' / 'agent'         # browser profiles + logs, never mounted into containers
RUNTIME = ROOT / 'data' / 'worker'      # shared with the worker container as /data


def load_env():
    sys.path.insert(0, str(ROOT / 'scripts'))       # the same .env reader every tool uses (comments, quotes)
    from envfile import parse
    env = parse(ROOT / '.env')
    env.update({k: v for k, v in os.environ.items() if k.startswith('TRENDVN_')})
    return env


ENV = load_env()
WORKER_URL = ENV.get('TRENDVN_WORKER_URL', 'http://127.0.0.1:%s' % ENV.get('TRENDVN_WORKER_PORT', '5681'))
TOKEN = ENV.get('TRENDVN_TOKEN', '')


def ensure_dirs():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    (DATA / 'shots').mkdir(exist_ok=True, mode=0o700)


def log(msg):
    """Print and append to data/agent/agent.log. Logging must never break the job it describes (disk full, wrong owner, read-only mount)."""
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + str(msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        ensure_dirs()
        with open(DATA / 'agent.log', 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def worker(path, payload=None, timeout=900):
    """Call the isolated worker API with the shared bearer token."""
    if len(TOKEN) < 32:
        raise RuntimeError('TRENDVN_TOKEN missing; run ./trendvn install')
    data = json.dumps(payload if payload is not None else {}).encode()
    req = urllib.request.Request(WORKER_URL + path, data=data if payload is not None or path.startswith('/api/') else None,
                                 headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'},
                                 method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors='replace')[:400]
        raise RuntimeError(f'worker {path} -> {e.code}: {detail}') from None


def worker_get(path, timeout=30):
    req = urllib.request.Request(WORKER_URL + path, headers={'Authorization': 'Bearer ' + TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def proxy_for(region):
    """Optional per-region exit, e.g. TRENDVN_US_PROXY=http://user:pass@host:port for real US trends."""
    value = ENV.get('TRENDVN_%s_PROXY' % region.upper(), '').strip()
    if not value:
        return None
    m = re.fullmatch(r'(https?|socks5)://(?:([^:@/]+):([^@/]*)@)?([^:/@]+):(\d{1,5})', value)
    if not m:
        raise ValueError('TRENDVN_%s_PROXY has an invalid format' % region.upper())
    scheme, user, password, host, port = m.groups()
    cfg = {'server': f'{scheme}://{host}:{port}'}
    if user:
        cfg.update(username=user, password=password)
    return cfg


@contextmanager
def chrome(profile, locale='en-US', headless=True, region=None, viewport=(1366, 900)):
    """Persistent, isolated Chrome profile driven by Playwright (real Chrome channel, not bundled Chromium)."""
    from playwright.sync_api import sync_playwright
    ensure_dirs()
    pdir = DATA / 'profiles' / profile
    pdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with sync_playwright() as p:
        # Honest automation: no flags or User-Agent edits that hide the fact that a program is driving the browser.
        kwargs = dict(channel='chrome', headless=headless, locale=locale, viewport={'width': viewport[0], 'height': viewport[1]},
                      args=['--no-first-run', '--no-default-browser-check'])
        proxy = proxy_for(region) if region else None
        if proxy:
            kwargs['proxy'] = proxy
        ctx = p.chromium.launch_persistent_context(str(pdir), **kwargs)
        try:
            yield ctx
        finally:
            ctx.close()
