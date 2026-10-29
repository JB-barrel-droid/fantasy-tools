"""Simplified site section (JEG-1263) in a real browser: every state at 1280, 390 and 320 with no sideways scroll, one
"Simplified site" h1, the route contract (deep link, open a trade, Back), keyboard focus, the fixture label, the gain
text as the dashboard shows it, and no storage writes.

The section is mounted on a small harness page (v2.css, simplified-site.css, opportunities.js, simplified-site.js) with the
synthetic fixture injected, because the menu entry and route hunk in v2.js / shell.html wait on the shell owner's
agreement (JEG-1263). Set SIMPLIFIED_SITE_SHOTS=<dir> to save the screenshots used as PR evidence.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "simplified-site" / "synthetic-answer.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simplified site (test harness, synthetic data)</title>
<link rel="stylesheet" href="v2.css"><link rel="stylesheet" href="simplified-site.css">
<script src="opportunities.js"></script><script src="simplified-site.js"></script>
</head><body class="v2"><div class="v2-app">
<main id="v2Simplified" aria-labelledby="ssTitle"></main></div>
<script>window.__ssHandle = TradeValueSimplifiedSite.mount(document.getElementById("v2Simplified"), {getContext: () => window.__SS_CTX});</script>
</body></html>
"""

# Counts every storage write the page makes after load.
STORAGE_SPY = """(() => { window.__ssWrites = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__ssWrites.push([name, args[0]]); return real.apply(this, args); }; } })();"""


def state(name: str) -> dict:
    ctx = copy.deepcopy(FIXTURE)
    if name == "loading":
        return {"status": "loading", "fixture": ctx["fixture"]}
    if name == "error":
        return {"status": "error", "error": "synthetic failure for the test", "fixture": ctx["fixture"]}
    if name == "empty":
        ctx["league"] = None
    elif name == "incomplete":
        ctx["missing"] = [{"key": "context", "text": "Your saved league is not yet carried into this section reliably."}]
    elif name == "weekly":
        ctx["basis"]["horizon"] = "weekly"
    elif name == "none":
        ctx["ideas"]["recommendations"] = []
    return ctx


STATES = {"answer": "answer", "loading": "loading", "error": "error", "empty": "empty", "incomplete": "incomplete",
          "weekly": "incomplete", "none": "none"}


@contextlib.contextmanager
def harness():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("v2.css", "simplified-site.css", "opportunities.js", "simplified-site.js"):
            shutil.copy2(APP / name, Path(tmp) / name)
        (Path(tmp) / "index.html").write_text(PAGE, encoding="utf-8")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp)) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
            finally:
                server.shutdown()


@contextlib.contextmanager
def browser():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            yield chromium
        finally:
            chromium.close()


class SimplifiedSiteRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(harness())
        shots = os.environ.get("SIMPLIFIED_SITE_SHOTS", "").strip()
        cls.shots = Path(shots) if shots else None
        if cls.shots:
            cls.shots.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, ctx, width, hash_="#simplified-site", errors=None, wait=True):
        context = self.chromium.new_context(viewport={"width": width, "height": 900})
        context.add_init_script(STORAGE_SPY)
        context.add_init_script(f"window.__SS_CTX = {json.dumps(ctx)};")
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base + hash_, wait_until="load")
        if wait:
            page.wait_for_selector("#v2Simplified[data-state]")
        return page

    def shot(self, page, name):
        if self.shots:
            page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)

    def assert_layout(self, page, label):
        fit = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,"
                            " wide: [...document.querySelectorAll('#v2Simplified *')].filter(n => n.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5).map(n => n.className || n.tagName)})")
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: sideways scroll {fit}")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the right edge")
        heads = page.evaluate("() => [...document.querySelectorAll('#v2Simplified h1, #v2Simplified h2, #v2Simplified h3')].map(h => [Number(h.tagName[1]), h.textContent.trim()])")
        self.assertEqual([h for h in heads if h[0] == 1], [[1, "Simplified site"]], f"{label}: one h1, the exact name")
        for (prev, _), (level, text) in zip(heads, heads[1:]):
            self.assertLessEqual(level - prev, 1, f"{label}: heading level skipped before {text!r}")
        self.assertTrue(all(text for _, text in heads), f"{label}: empty heading")

    def test_every_state_at_every_width(self):
        for width in WIDTHS:
            for name, want in STATES.items():
                with self.subTest(width=width, state=name):
                    errors = []
                    page = self.open(state(name), width, errors=errors)
                    self.assertEqual(page.get_attribute("#v2Simplified", "data-state"), want)
                    self.assert_layout(page, f"{name}@{width}")
                    self.assertIn("Synthetic example.", page.inner_text(".ss-fixture"))
                    if name != "answer":
                        self.assertEqual(page.locator(".ss-offer, .ss-more").count(), 0, f"{name}: no answer shown")
                    if name in ("answer", "incomplete", "none", "empty"):
                        self.shot(page, f"{name}-{width}")
                    self.assertEqual(errors, [])
                    self.assertEqual(page.evaluate("window.__ssWrites"), [])
                    page.context.close()

    def test_answer_text_matches_dashboard_format(self):
        page = self.open(state("answer"), 1280)
        gains = page.locator(".ss-gain").all_inner_texts()
        # Answer, the two next tries, the stretch offer: opportunities.js fmt / the Trade opportunities capture cell.
        self.assertEqual(gains, ["You gain +4.2 in DDF Value.", "You gain +3.0 in DDF Value.", "You gain +0.1 in DDF Value.", "You gain +6.5 in DDF Value."])
        self.assertEqual(page.inner_text(".ss-offer"), "Offer RB Alpha to Synthetic Team B for WR India.")
        self.assertEqual(page.locator(".ss-band").all_inner_texts(), ["Likely", "Possible", "Possible", "Long shot"])
        self.assertEqual(page.locator(".ss-more .ss-rank").all_inner_texts(), ["2.", "3."])
        page.context.close()

    def test_deep_link_open_and_back_with_focus(self):
        first = FIXTURE["ideas"]["recommendations"][0]
        second = FIXTURE["ideas"]["recommendations"][1]
        for width in WIDTHS:
            with self.subTest(width=width):
                page = self.open(state("answer"), width)
                self.assertEqual(page.evaluate("document.activeElement.id"), "ssTitle", "entering the section focuses its title")
                # Keyboard: Tab to the answer's detail link, Enter opens the trade.
                for _ in range(10):
                    page.keyboard.press("Tab")
                    if page.evaluate("document.activeElement.dataset.detailFor || ''") == first["id"]:
                        break
                self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor"), first["id"])
                page.keyboard.press("Enter")
                page.wait_for_selector("#ssDetailTitle")
                self.assertEqual(page.evaluate("location.hash"), "#simplified-site/trade/" + quote(first["id"], safe=""))
                self.assertEqual(page.evaluate("document.activeElement.id"), "ssDetailTitle")
                self.assertEqual(page.get_attribute("#v2Simplified", "data-view"), "detail")
                detail = page.inner_text(".ss-detail")
                self.assertIn("Trade chart average (published)", detail)
                self.assertIn("not a prediction", detail)
                self.assert_layout(page, f"detail@{width}")
                self.shot(page, f"detail-{width}")
                page.go_back()
                page.wait_for_selector("#v2Simplified[data-view=section]")
                self.assertEqual(page.evaluate("location.hash"), "#simplified-site")
                self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor"), first["id"], "Back returns focus to the trade's link")
                page.context.close()
                # A fresh visit to a trade's address opens it directly; its Back link returns to the answer.
                page = self.open(state("answer"), width, hash_="#simplified-site/trade/" + quote(second["id"], safe=""))
                self.assertEqual(page.get_attribute("#v2Simplified", "data-view"), "detail")
                self.assertEqual(page.inner_text("#ssDetailTitle"), "Offer WR Bravo + TE Delta to Synthetic Team C for RB Golf.")
                self.assertEqual(page.evaluate("document.activeElement.id"), "ssDetailTitle")
                self.assertIn("fell back to the trade charts (nothing marked)", page.inner_text(".ss-detail"))
                page.click(".ss-back")
                page.wait_for_selector("#v2Simplified[data-view=section]")
                self.assertEqual(page.evaluate("document.activeElement.dataset.detailFor"), second["id"])
                self.assertEqual(page.evaluate("window.__ssWrites"), [])
                page.context.close()

    def test_unknown_or_withheld_deep_link(self):
        page = self.open(state("answer"), 390, hash_="#simplified-site/trade/" + quote("t9|nobody|nothing", safe=""))
        self.assertEqual(page.get_attribute("#v2Simplified", "data-view"), "section")
        self.assertIn("no longer in the list", page.inner_text(".ss-gone"))
        self.assertEqual(page.inner_text(".ss-offer"), "Offer RB Alpha to Synthetic Team B for WR India.")
        page.context.close()
        first = FIXTURE["ideas"]["recommendations"][0]
        page = self.open(state("incomplete"), 390, hash_="#simplified-site/trade/" + quote(first["id"], safe=""))
        self.assertEqual(page.get_attribute("#v2Simplified", "data-state"), "incomplete")
        self.assertEqual(page.locator(".ss-detail, .ss-offer").count(), 0, "a deep link cannot open a withheld answer")
        page.context.close()

    def test_activate_reads_live_context_once_mounted(self):
        """The dashboard's one call: activate() mounts once on the live adapter, withholds while a gate is closed, and
        re-reads on later calls without writing the workspace."""
        page = self.open(state("answer"), 390, hash_="#find-league", wait=False)
        result = page.evaluate("""([ideas]) => {
          const box = document.createElement('main'); document.body.append(box);
          const writes = [];
          const ws = {name: 'Synthetic League', myTeamId: 'a', teams: [{id: 'a', name: 'Synthetic Team A', entries: []}]};
          window.TradeValueWorkspace = {store: {get: () => ws, replace: () => writes.push('replace')}};
          window.TradeValueTradeIdeas = {compute: () => ideas};
          const S = window.TradeValueSimplifiedSite;
          location.hash = '#simplified-site';
          return new Promise(resolve => setTimeout(() => {
            const a = S.activate(box);
            const closed = box.dataset.state;
            window.TradeValueSimplifiedGates = {context: true, readout: true, lineup: true};
            const b = S.activate(box);
            resolve({same: a === b, closed, open: box.dataset.state, h1: box.querySelectorAll('h1').length, writes,
              fixture: box.querySelectorAll('.ss-fixture').length});
          }, 0));
        }""", [FIXTURE["ideas"]])
        self.assertTrue(result["same"], "mounted once")
        self.assertEqual(result["closed"], "incomplete", "gates closed: withheld")
        self.assertEqual(result["open"], "answer", "gates open: the answer")
        self.assertEqual(result["h1"], 1)
        self.assertEqual(result["fixture"], 0, "a live context is not labelled as a fixture")
        self.assertEqual(result["writes"], [])
        page.context.close()


if __name__ == "__main__":
    unittest.main()
