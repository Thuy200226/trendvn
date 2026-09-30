"""Host-side TrendVN agent API (n8n calls it; it drives Chrome). Listens only on the project's private Docker bridge."""
import hmac
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ENV, TOKEN, log, worker  # noqa: E402

BIND = ENV.get('TRENDVN_AGENT_BIND', '172.20.0.1')
PORT = int(ENV.get('TRENDVN_AGENT_PORT', '5682'))
lock = threading.Lock()   # one Chrome job at a time: profiles cannot be shared and sites throttle parallel scans


class Handler(BaseHTTPRequestHandler):
    server_version = 'TrendVNAgent/1.0'

    def log_message(self, fmt, *args):
        pass

    def send(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization', '').encode('utf-8'), ('Bearer ' + TOKEN).encode('utf-8'))   # bytes: str with non-ASCII raises

    def do_GET(self):
        if self.path == '/health':
            return self.send(200, {'ok': True, 'service': 'trendvn-agent', 'busy': lock.locked()})
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.authorized():
            return self.send(401, {'error': 'Authentication required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length) or b'{}') if length else {}
        except Exception:
            return self.send(400, {'error': 'Invalid JSON'})
        routes = {'/api/collect': self.collect, '/api/publish': self.publish, '/api/session': self.session,
                  '/api/verify': self.verify, '/api/dry-run': self.dry_run, '/api/stats': self.stats}
        fn = routes.get(self.path)
        if not fn:
            return self.send(404, {'error': 'Not found'})
        if not lock.acquire(blocking=False):
            return self.send(409, {'error': 'Agent busy with another browser job'})
        try:
            self.send(200, fn(payload))
        except Exception as e:
            log('ERROR %s: %s' % (self.path, traceback.format_exc()[-600:]))
            self.send(500, {'error': str(e)[:300]})
        finally:
            lock.release()

    def collect(self, p):
        import collector
        platforms = p.get('platforms') if isinstance(p.get('platforms'), list) else None
        if platforms and any(x not in collector.SOURCES for x in platforms):
            raise ValueError('Unknown platform')
        return {'report': collector.collect(platforms, download_media=p.get('download', True))}

    def publish(self, p):
        import publisher
        return publisher.run_publish(p.get('job_id'))

    def dry_run(self, p):
        import publisher
        return publisher.dry_run_next(p.get('job_id'))

    def session(self, p):
        import publisher
        status = publisher.session_status()
        worker('/api/heartbeat', {'component': 'publisher', 'ok': status.get('logged_in', False),
                                  'detail': 'Đã đăng nhập TikTok, sẵn sàng' if status.get('logged_in') else status.get('reason')})
        return status

    def stats(self, p):
        import publisher
        return publisher.run_stats()

    def verify(self, p):
        import publisher
        return publisher.verify_unresolved()


if __name__ == '__main__':
    if len(TOKEN) < 32:
        raise SystemExit('TRENDVN_TOKEN missing; run ./trendvn install first')
    log('agent listening on %s:%s' % (BIND, PORT))
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
