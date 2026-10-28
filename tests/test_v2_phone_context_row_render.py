"""Phone context row height (JEG-1134).

Measurement step (Jeremy, 2026-10-27, option C): print the height of #v2Context at 390x844 and 375x667 on the
current layout, with a screenshot of each, so the coordinator can pick A (one line, about 48 px or less) or B
(taller: rebuild the one-line phone summary). The screenshots go to the CI log as base64 JPEG between
JEG1134-SHOT markers, since no workflow that runs this test uploads an artifact.

TEMPORARY (JEG-1156, removed before the final commit): test_live_site_probe reads the live site and prints the week
it shows and how many Values rows show a DDF Value. It needs the network and never fails.
"""
from __future__ import annotations

import base64
import contextlib
import functools
import http.server
import json
import socketserver
import sys
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PHONES = ((390, 844), (375, 667))


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(DIST))) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
        finally:
            server.shutdown()


MEASURE = """() => {
  const ctx = document.getElementById('v2Context');
  const r = ctx.getBoundingClientRect();
  const kids = [...ctx.querySelectorAll('.v2-context-inner > *')].filter(e => e.offsetParent || e.getClientRects().length)
    .map(e => { const b = e.getBoundingClientRect(); return {el: e.id || e.className, top: Math.round(b.top - r.top), h: Math.round(b.height)}; });
  const lines = new Set(kids.filter(k => k.h > 0).map(k => k.top)).size;
  const main = document.getElementById('v2Main');
  return {height: Math.round(r.height * 10) / 10, top: Math.round(r.top), lines, kids,
          contentTop: main && !main.hidden ? Math.round(main.getBoundingClientRect().top) : null,
          text: ctx.innerText.replace(/\\s+/g, ' ').trim().slice(0, 200)};
}"""


def _browser(p):
    exe = _render_env.chromium_executable(p)
    return p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    return sync_playwright


def _print_shot(label, jpeg: bytes):
    data = base64.b64encode(jpeg).decode("ascii")
    print(f"JEG1134-SHOT-BEGIN {label} {len(jpeg)} bytes", file=sys.stderr)
    for i in range(0, len(data), 1000):
        print(data[i:i + 1000], file=sys.stderr)
    print(f"JEG1134-SHOT-END {label}", file=sys.stderr)


class PhoneContextRowMeasureTest(unittest.TestCase):
    def test_measure_context_row(self):
        sync_playwright = _playwright()
        results = {}
        with _served() as base, sync_playwright() as p:
            browser = _browser(p)
            for width, height in PHONES:
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.add_init_script(_render_env.pin_data_week_script())
                page.goto(base + "#player-values", wait_until="networkidle")
                with contextlib.suppress(Exception):
                    page.wait_for_selector("#v2Main:not([hidden])", timeout=60000)
                page.wait_for_timeout(1500)
                m = page.evaluate(MEASURE)
                results[f"{width}x{height}"] = m
                print(f"JEG1134-MEASURE {width}x{height}: #v2Context height {m['height']} px, top {m['top']} px, "
                      f"{m['lines']} line(s), first content top {m['contentTop']} px", file=sys.stderr)
                print(f"JEG1134-MEASURE {width}x{height} detail: {json.dumps(m)}", file=sys.stderr)
                _print_shot(f"{width}x{height}", page.screenshot(type="jpeg", quality=60))
                page.close()
            browser.close()
        for key, m in results.items():
            self.assertGreater(m["height"], 0, key)


LIVE = "https://jb-barrel-droid.github.io/fantasy-tools/#player-values"

LIVE_READ = """() => {
  const txt = id => { const e = document.getElementById(id); return e ? e.textContent.trim() : null; };
  const fresh = document.getElementById('v2Freshness');
  const table = document.getElementById('v2Table');
  const out = {freshShort: txt('v2FreshnessShort'), freshLabel: txt('v2FreshnessLabel'),
               freshAria: fresh ? fresh.getAttribute('aria-label') : null, valueLine: txt('v2ValueLine'),
               tableMeta: txt('v2TableMeta'), showing: txt('v2ShowingText')};
  if (!table) return {...out, error: 'no #v2Table'};
  const heads = [...table.querySelectorAll('thead th')].map(th => th.innerText.replace(/\\s+/g, ' ').trim());
  const col = heads.findIndex(h => /DDF Value/i.test(h));
  const rows = [...table.querySelectorAll('tbody tr')].filter(tr => tr.cells.length > 1 && !tr.classList.contains('v2-more'));
  const blank = v => !v || /^[—–\\-]?$/.test(v) || v === 'n/a';
  const cell = (tr, i) => (tr.cells[i] ? tr.cells[i].innerText.replace(/\\s+/g, ' ').trim() : '');
  const withVal = col < 0 ? null : rows.filter(tr => !blank(cell(tr, col))).length;
  const first = rows.slice(0, 5).map(tr => ({cells: [0, 1, 2].map(i => cell(tr, i)), ddf: col < 0 ? null : cell(tr, col)}));
  return {...out, heads, ddfCol: col, rows: rows.length, withDdf: withVal, first};
}"""


class LiveSiteProbe(unittest.TestCase):
    """TEMPORARY (JEG-1156). Reads the live site; prints, never fails."""

    def test_live_site_probe(self):
        sync_playwright = _playwright()
        with sync_playwright() as p:
            exe = _render_env.chromium_executable(p)
            browser = p.chromium.launch(executable_path=exe)
            for width, height in ((1366, 768), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                try:
                    page.goto(LIVE, wait_until="networkidle", timeout=90000)
                    with contextlib.suppress(Exception):
                        page.wait_for_selector("#v2Table tbody tr", timeout=60000)
                    page.wait_for_timeout(3000)
                    r = page.evaluate(LIVE_READ)
                    print(f"JEG1156-LIVE {width}x{height}: {json.dumps(r)}", file=sys.stderr)
                except Exception as exc:  # the probe only reports
                    print(f"JEG1156-LIVE {width}x{height}: probe failed: {exc!r}", file=sys.stderr)
                page.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
