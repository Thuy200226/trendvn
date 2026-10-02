"""Start-up: build the app, bind the handler to it and serve."""

import threading
from http.server import ThreadingHTTPServer

from ..version import VERSION
from .app import App
from .handler import Handler
from .log import log


class BoundedServer(ThreadingHTTPServer):
    """One thread per connection, but never more than MAX_THREADS at once: the surplus gets a quick 503 instead of exhausting
    memory (the dashboard, n8n and the browser agent together need a handful; a flood needs hundreds)."""

    MAX_THREADS = 48
    request_queue_size = 64  # listen backlog (the stdlib default is 5)

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(self.MAX_THREADS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 2\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            return self.shutdown_request(request)
        try:
            super().process_request(request, client_address)
        except BaseException:  # the thread never started, so nobody else would give the slot back
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def make_handler(app):
    """A Handler subclass bound to `app` (the stdlib instantiates handlers itself, so state travels via the class)."""
    return type("BoundHandler", (Handler,), {"app": app})


def main():
    app = App()
    log("worker %s listening on :%d, data in %s" % (VERSION, app.config.port, app.store.root))
    BoundedServer(("0.0.0.0", app.config.port), make_handler(app)).serve_forever()
