"""Serve the built dist/ (or a copy) for rendered tests, with optional
per-file body overrides, and find a Chromium to drive it."""
from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def chromium_executable(playwright):
    for candidate in (Path(playwright.chromium.executable_path), CHROME):
        if candidate.exists():
            return str(candidate)
    return None


@contextlib.contextmanager
def serve(directory: Path = DIST, overrides: dict[str, bytes] | None = None):
    """Yield the base URL of `directory`. overrides maps a served path
    (e.g. "assets/curve-widget.js") to the body served in its place."""
    overrides = overrides or {}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            rel = self.path.split("?")[0].lstrip("/")
            for key, body in overrides.items():
                if rel == key or rel.endswith("/" + key):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/javascript" if key.endswith(".js") else "application/json")
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
