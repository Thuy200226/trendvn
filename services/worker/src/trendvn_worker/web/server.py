"""Start-up: build the app, bind the handler to it and serve."""

from http.server import ThreadingHTTPServer

from ..version import VERSION
from .app import App
from .handler import Handler
from .log import log


def make_handler(app):
    """A Handler subclass bound to `app` (the stdlib instantiates handlers itself, so state travels via the class)."""
    return type("BoundHandler", (Handler,), {"app": app})


def main():
    app = App()
    log("worker %s listening on :%d, data in %s" % (VERSION, app.config.port, app.store.root))
    ThreadingHTTPServer(("0.0.0.0", app.config.port), make_handler(app)).serve_forever()
