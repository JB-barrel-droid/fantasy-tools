"""Serve the built dist/ (or a copy) for rendered tests, with optional
per-file body overrides, and find a Chromium to drive it.

JEG-453: the old chart dashboard (the engine page v2 runs hidden) is no longer
published; dist/classic/ is a redirect to the root. The engine page is built to
build/engine/index.html, and the render harnesses serve it at /classic/ on
their own servers (engine_path), so tests that drive the engine's own controls
keep running against the same page.

JEG-1539: the same for the retired v2 shell. dist/index.html is the redesigned front door and dist/v2/ a redirect
stub; the v2 shell is built to build/v2/index.html and served here at /v2-app.html (V2_URL), a root-level path, so
its relative assets and in-page #route links work as they did at the root."""
from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import threading
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ENGINE_PAGE = ROOT / "build" / "engine" / "index.html"
ENGINE_URL = "classic/"
V2_SHELL_PAGE = ROOT / "build" / "v2" / "index.html"
V2_URL = "v2-app.html"


def engine_path(url_path: str, prefix: str = "/") -> str | None:
    """The engine page's file for a request to <prefix>classic/, else None."""
    rel = url_path.split("?", 1)[0].split("#", 1)[0]
    if not rel.startswith(prefix):
        return None
    rel = rel[len(prefix):]
    if rel in (ENGINE_URL, ENGINE_URL + "index.html"):
        return str(ENGINE_PAGE)
    if rel == V2_URL:
        return str(V2_SHELL_PAGE)
    return None


def engine_built() -> bool:
    return ENGINE_PAGE.exists()


def chromium_executable(playwright):
    return _render_env.chromium_executable(playwright)


@contextlib.contextmanager
def serve(directory: Path = DIST, overrides: dict[str, bytes] | None = None):
    """Yield the base URL of `directory`. overrides maps a served path
    (e.g. "assets/curve-widget.js") to the body served in its place."""
    overrides = overrides or {}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def translate_path(self, path):
            return engine_path(path) or super().translate_path(path)

        def do_GET(self):
            rel = self.path.split("?")[0].lstrip("/")
            for key, body in overrides.items():
                if rel == key or rel.endswith("/" + key):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/javascript" if key.endswith(".js")
                                     else "text/html; charset=utf-8" if key.endswith(".html") else "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            super().do_GET()

    handler = functools.partial(Handler, directory=str(directory))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
