"""v2 player detail (frames 13 / 14) and empty, loading and failure states (frame 18).

Builds dist/v2 into a temp copy of the built dist/ and loads it headless:

  * player detail: opened from the first Player values row at 1440 (side drawer
    on the right) and 390 (full screen, frame 14). Every value in the hero and
    the "Source values" matrix equals the engine's
    TradeValueCurveControls.getRows() value for that player and series; a
    missing one shows "—" with a reason, never 0; each series sits in its own
    method's column (Adjusted, Indexed, VORP vs waivers), so VORP vs waivers is
    never in a trade-value column;
  * empty: a search that matches no player hides the chart and table, says which
    filter emptied the list, offers "Clear search" for that filter (frame 18),
    and it brings the players back;
  * loading: the built page starts with every tab hidden behind the loading card;
  * failure: with the engine script served empty, the page shows the failure
    card with a retry button, no tab and no number;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with the detail
matrix columns out of method order, with the failure path leaving Player values
visible, and with the empty state never drawn, and v2.css with the old bottom
sheet instead of the full-screen detail, and requires the checks to fail on each.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"

READ_DRAWER = """() => {
  const drawer = document.getElementById('v2Drawer');
  const key = document.querySelector('#v2Table tbody tr').dataset.playerKey
    || window.TradeValueV2.view().rows[0].player_key;
  const row = window.TradeValueCurveControls.getRows().find(r => String(r.player_key) === String(key));
  const box = drawer.getBoundingClientRect();
  return {hidden: drawer.hidden, values: row ? row.values : null,
    groups: ['dda', 'indexed', 'vorp'].map((method, i) => ({method,
      cells: [...drawer.querySelectorAll('.v2-dmatrix tbody tr')].map(tr => tr.children[i + 1])
        .filter(td => td && td.dataset.source).map(td => ({key: td.dataset.source, text: td.textContent}))})),
    hero: [...drawer.querySelectorAll('.v2-dhero [data-source]')].map(n => ({key: n.dataset.source, text: n.textContent})),
    box: {left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height},
    vw: window.innerWidth, vh: window.innerHeight,
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""


def finite(value):
    return isinstance(value, (int, float)) and value == value and abs(value) != float("inf")


def check_drawer(snap, width) -> list[str]:
    errors = []
    if snap["hidden"] or not any(g["cells"] for g in snap["groups"]):
        return [f"{width}px: player detail did not open"]
    values = snap["values"] or {}
    snap["groups"].append({"method": None, "cells": snap["hero"]})
    for group in snap["groups"]:
        for cell in group["cells"]:
            key = cell["key"]
            is_vorp = key.endswith("_vorp")
            if group["method"] is not None and is_vorp != (group["method"] == "vorp"):
                errors.append(f"{width}px: {key} listed under {group['method']}")
            value = values.get(key)
            if finite(value):
                if cell["text"] != f"{value:.1f}":
                    errors.append(f"{width}px: {key} shows {cell['text']!r}, engine {value!r}")
            elif "—" not in cell["text"] or re.search(r"\d", cell["text"]):
                errors.append(f"{width}px: {key} has no engine value but shows {cell['text']!r}")
    box, vw, vh = snap["box"], snap["vw"], snap["vh"]
    if width <= 390:
        if abs(box["bottom"] - vh) > 1 or box["top"] > 1 or box["width"] < vw - 1:
            errors.append(f"{width}px: detail is not full screen: {box}")
    elif abs(box["right"] - vw) > 1 or box["top"] > 1 or box["width"] > 441:
        errors.append(f"{width}px: detail is not a right-hand drawer: {box}")
    if snap["overflow"] > 0 and width <= 390:
        errors.append(f"{width}px: horizontal overflow {snap['overflow']}px")
    return errors


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values", dist
            finally:
                server.shutdown()


def run_checks(v2_js=None, v2_css=None, with_failure=True) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as (url, dist), sync_playwright() as playwright:
        html = (dist / "v2" / "index.html").read_text(encoding="utf-8")
        if not re.search(r'<main class="v2-wrap v2-main" id="v2Main" hidden', html) \
                or 'data-state="loading"' not in html:
            errors.append("loading: the page must start with Player values hidden behind the loading card")
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc

        def open_page(width, height, engine_body=None):
            page = browser.new_page(viewport={"width": width, "height": height})
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
            if v2_css is not None:
                page.route("**/v2/v2.css*", functools.partial(_serve, v2_css, "text/css"))
            if engine_body is not None:
                page.route("**/assets/curve-widget.js*", functools.partial(_serve, engine_body, "text/javascript"))
            page.goto(url, wait_until="networkidle")
            return page, page_errors

        try:
            for width, height in ((1440, 1000), (390, 844)):
                page, page_errors = open_page(width, height)
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=30000)
                page.click("#v2Table tbody tr")
                page.wait_for_timeout(200)
                errors += check_drawer(page.evaluate(READ_DRAWER), width)
                page.keyboard.press("Escape")
                page.fill("#v2Search", "zzzz no such player")
                page.wait_for_timeout(400)
                empty = page.evaluate("""() => ({shown: !document.getElementById('v2Empty').hidden,
                  text: document.getElementById('v2EmptyText').textContent,
                  chart: !document.getElementById('v2Chart').hidden,
                  table: !document.querySelector('#v2Main .v2-table-card').hidden})""")
                if not empty["shown"] or "zzzz" not in empty["text"] or empty["chart"] or empty["table"]:
                    errors.append(f"{width}px: empty search state wrong: {empty}")
                if empty["shown"]:
                    page.click("#v2EmptyActions [data-clear=search]")
                else:
                    page.click("#v2ClearFilters")
                page.wait_for_timeout(400)
                if not page.evaluate("() => document.querySelectorAll('#v2Table tbody tr').length > 0 && document.getElementById('v2Empty').hidden"):
                    errors.append(f"{width}px: Clear filters did not bring the players back")
                if page_errors:
                    errors.append(f"{width}px: page errors {page_errors}")
                page.close()
            if with_failure:
                page, _ = open_page(1440, 1000, engine_body="")
                page.wait_for_function("() => document.querySelector('.v2-state').dataset.state === 'failed'"
                                       " || !document.getElementById('v2Main').hidden", timeout=45000)
                failed = page.evaluate("""() => ({state: document.querySelector('.v2-state').dataset.state,
                  retry: !document.getElementById('v2StateRetry').hidden,
                  tabs: ['v2Main', 'v2Targets', 'v2Risers', 'v2Compare', 'v2How'].filter(id => !document.getElementById(id).hidden),
                  digits: (document.querySelector('.v2-app').innerText.match(/\\d+(\\.\\d)?/g) || [])})""")
                if failed["state"] != "failed" or not failed["retry"] or failed["tabs"] or failed["digits"]:
                    errors.append(f"failure state wrong: {failed}")
                page.close()
        finally:
            browser.close()
    return errors


class StatesRenderTest(unittest.TestCase):
    def test_detail_and_states(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        broken = {
            "detail columns not split by method": {"v2_js": js.replace(
                'const METHOD_COLUMNS = [["dda", "Adjusted"], ["indexed", "Indexed"], ["vorp", "VORP vs waivers"]];',
                'const METHOD_COLUMNS = [["vorp", "Adjusted"], ["indexed", "Indexed"], ["dda", "VORP vs waivers"]];', 1),
                "with_failure": False},
            "failure leaves values visible": {"v2_js": js.replace(
                '["v2Main", "v2Targets", "v2Risers", "v2Compare", "v2How", "v2Methods"].forEach(id => { $(id).hidden = true; });',
                '$("v2Main").hidden = false;', 1)},
            "empty state never drawn": {"v2_js": js.replace("    renderEmpty();\n", "", 1), "with_failure": False},
            "bottom sheet instead of full screen": {"v2_css": css.replace(
                "  .v2-drawer { inset: 0; width: 100vw; height: 100vh; max-height: none;",
                "  .v2-drawer { top: auto; left: 0; right: 0; bottom: 0; width: 100vw; max-height: 85vh;", 1), "with_failure": False},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = kwargs.get("v2_js") or kwargs.get("v2_css")
                self.assertNotIn(body, (js, css), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(**kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
