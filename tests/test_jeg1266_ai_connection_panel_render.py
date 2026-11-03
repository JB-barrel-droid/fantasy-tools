"""Homepage AI connection panel (JEG-1266) in a real browser: every fixture state at 1280, 390 and 320 with no sideways scroll,
connect explained before sharing, the one guide link, keyboard order and focus, copy success and copy failure, the fixture label,
no connection claim, and no storage writes.

The panel is mounted on a small harness page (v2.css, ai-connection-panel.css, ai-connection-panel.js) with synthetic contexts
injected, because the homepage hunk in shell.html / v2.js / build_v2_page.py waits on the JEG-1137 owner. Set
AI_PANEL_SHOTS=<dir> to save the screenshots used as PR evidence.
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

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "ai-connection-panel" / "synthetic-states.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)
GUIDE = "connect/"

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI connection panel (test harness, synthetic data)</title>
<link rel="stylesheet" href="v2.css"><link rel="stylesheet" href="ai-connection-panel.css">
<script src="ai-connection-panel.js"></script>
</head><body class="v2"><div class="v2-app"><main class="v2-wrap"><h1>Home (harness)</h1>
<section id="v2AiPanel"></section></main></div>
<script>window.__aipHandle = TradeValueAiConnectionPanel.mount(document.getElementById("v2AiPanel"), {
  getContext: () => window.__AIP_CTX, getLink: () => window.__AIP_LINK, writeClipboard: t => navigator.clipboard.writeText(t)});</script>
</body></html>
"""

# Counts storage writes; replaces the clipboard with a stub that succeeds or rejects, recording what it was given.
SPY = """(() => { window.__aipWrites = []; window.__aipClip = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__aipWrites.push([name, args[0]]); return real.apply(this, args); }; }
  window.__aipHold = [];   // with __AIP_CLIP_HOLD set, each write waits until the test settles it (JEG-1300)
  const writeText = t => { window.__aipClip.push(t);
    if (window.__AIP_CLIP_HOLD) return new Promise((resolve, reject) => window.__aipHold.push({resolve, reject}));
    return window.__AIP_CLIP_FAILS ? Promise.reject(new DOMException("denied", "NotAllowedError")) : Promise.resolve(); };
  Object.defineProperty(navigator, "clipboard", {value: {writeText}, configurable: true}); })();"""

STATES = {name: (name, *want) for name, *want in [
    ("ready", "available", "ready"), ("default-league", "available", "ready"), ("setup-unavailable", "unavailable", "ready"),
    ("setup-unknown", "unknown", "ready"), ("link-unavailable", "available", "unavailable"), ("link-unknown", "available", "unknown"),
    ("clipboard-off", "available", "ready"), ("missing-league", "available", "missing"), ("claims-connected", "available", "ready")]}
SHOTS = {"ready", "setup-unavailable", "link-unknown", "missing-league"}


def ctx_for(name: str) -> dict:
    ctx = copy.deepcopy(FIXTURE["states"][name])
    ctx["fixture"] = FIXTURE["fixture"]
    return ctx


@contextlib.contextmanager
def harness():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("v2.css", "ai-connection-panel.css", "ai-connection-panel.js"):
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


class AiConnectionPanelRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(harness())
        shots = os.environ.get("AI_PANEL_SHOTS", "").strip()
        cls.shots = Path(shots) if shots else None
        if cls.shots:
            cls.shots.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, ctx, width, clip_fails=False, errors=None):
        context = self.chromium.new_context(viewport={"width": width, "height": 900})
        context.add_init_script(SPY)
        context.add_init_script(f"window.__AIP_CTX = {json.dumps(ctx)}; window.__AIP_LINK = {json.dumps(FIXTURE['link'])};"
                                f" window.__AIP_CLIP_FAILS = {json.dumps(clip_fails)};")
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base, wait_until="load")
        page.wait_for_selector("#v2AiPanel[data-share]")
        return page

    def shot(self, page, name):
        if self.shots:
            page.locator("#v2AiPanel").screenshot(path=str(self.shots / f"{name}.png"))

    def assert_layout(self, page, label):
        fit = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,"
                            " wide: [...document.querySelectorAll('#v2AiPanel *')].filter(n => n.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5).map(n => n.className || n.tagName)})")
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: sideways scroll {fit}")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the right edge")
        heads = page.evaluate("() => [...document.querySelectorAll('#v2AiPanel h2, #v2AiPanel h3')].map(h => [Number(h.tagName[1]), h.textContent.trim()])")
        self.assertEqual(heads[0], [2, "Find your best trade in Claude or ChatGPT"], f"{label}: the panel title")
        self.assertEqual([h for h in heads if h[0] == 2], heads[:1], f"{label}: one h2")
        self.assertEqual(page.evaluate("document.getElementById(document.getElementById('v2AiPanel').getAttribute('aria-labelledby')).textContent"),
                         "Find your best trade in Claude or ChatGPT")
        small = page.evaluate("() => [...document.querySelectorAll('#v2AiPanel a, #v2AiPanel button')].filter(n => n.getBoundingClientRect().height < 44)"
                              ".map(n => n.textContent)")
        self.assertEqual(small, [], f"{label}: controls under 44 px tall")

    def test_every_state_at_every_width(self):
        for width in WIDTHS:
            for name, (_, setup, share) in STATES.items():
                with self.subTest(width=width, state=name):
                    errors = []
                    page = self.open(ctx_for(name), width, errors=errors)
                    panel = "#v2AiPanel"
                    self.assertEqual(page.get_attribute(panel, "data-setup"), setup)
                    self.assertEqual(page.get_attribute(panel, "data-share"), share)
                    self.assert_layout(page, f"{name}@{width}")
                    self.assertIn("Synthetic example.", page.inner_text(".aip-fixture"))
                    text = page.inner_text(panel)
                    self.assertNotRegex(text, r"(?i)\b(you're|you are|is|now) connected\b|✓", f"{name}: claims a connection")
                    # Connect is explained before sharing, and the share step says pasting does not connect.
                    order = page.evaluate("() => [...document.querySelectorAll('#v2AiPanel .aip-setup, #v2AiPanel .aip-next, #v2AiPanel .aip-share')].map(n => n.className.split(' ')[0])")
                    self.assertEqual(order, ["aip-setup", "aip-next", "aip-share"])
                    self.assertIn("Pasting a link does not connect the tool.", text)
                    links = page.locator(f"{panel} a").evaluate_all("ns => ns.map(n => [n.textContent, n.getAttribute('href')])")
                    self.assertEqual(links, [["Connect the tool", GUIDE]] if setup == "available" else [], f"{name}: links")
                    self.assertEqual(page.locator("#aipCopy").count(), 1 if share == "ready" else 0)
                    if name in SHOTS:
                        self.shot(page, f"{name}-{width}")
                    self.assertEqual(errors, [])
                    self.assertEqual(page.evaluate("window.__aipWrites"), [])
                    page.context.close()

    def test_keyboard_order_and_copy_success(self):
        for width in WIDTHS:
            with self.subTest(width=width):
                errors = []
                page = self.open(ctx_for("ready"), width, errors=errors)
                seen = []
                for _ in range(2):
                    page.keyboard.press("Tab")
                    seen.append(page.evaluate("[document.activeElement.id, getComputedStyle(document.activeElement).outlineStyle]"))
                self.assertEqual(seen, [["aipConnect", "solid"], ["aipCopy", "solid"]], "Tab reaches Connect, then Copy link, each with a ring")
                page.keyboard.press("Enter")
                page.wait_for_selector("#v2AiPanel[data-copy=copied]")
                self.assertEqual(page.evaluate("window.__aipClip"), [FIXTURE["link"]])
                self.assertEqual(page.inner_text("#aipResult"), "Copied the link.")
                self.assertEqual(page.inner_text(".aip-live"), "Copied the link.")
                self.assertEqual(page.evaluate("document.activeElement.id"), "aipCopy", "focus stays on Copy link")
                self.assertEqual(page.locator("#aipLinkText").count(), 0)
                self.shot(page, f"copied-{width}")
                self.assertEqual(errors, [])
                self.assertEqual(page.evaluate("window.__aipWrites"), [])
                page.context.close()

    def test_copy_failure_shows_the_link_to_copy(self):
        for width in WIDTHS:
            for name, fails in (("ready", True), ("clipboard-off", False)):
                with self.subTest(width=width, state=name):
                    errors = []
                    page = self.open(ctx_for(name), width, clip_fails=fails, errors=errors)
                    if name == "clipboard-off":
                        self.assertEqual(page.inner_text("#aipCopy"), "Show the link to copy")
                    page.click("#aipCopy")
                    page.wait_for_selector("#v2AiPanel[data-copy=failed]")
                    self.assertEqual(page.inner_text("#aipResult"), "Couldn't copy. Copy this link:")
                    self.assertEqual(page.input_value("#aipLinkText"), FIXTURE["link"])
                    self.assertEqual(page.evaluate("document.activeElement.id"), "aipLinkText", "focus moves to the link text")
                    sel = page.evaluate("(() => { const a = document.activeElement; return [a.selectionStart, a.selectionEnd, a.value.length]; })()")
                    self.assertEqual(sel, [0, len(FIXTURE["link"]), len(FIXTURE["link"])], "the link is selected")
                    self.assertEqual(len(page.evaluate("window.__aipClip")), 1 if fails else 0, "clipboard off never tries the clipboard")
                    self.assert_layout(page, f"failed-{name}@{width}")
                    if name == "ready":
                        self.shot(page, f"copy-failed-{width}")
                    self.assertEqual(errors, [])
                    page.context.close()

    def test_new_view_clears_the_result(self):
        page = self.open(ctx_for("ready"), 390)
        page.click("#aipCopy")
        page.wait_for_selector("#v2AiPanel[data-copy=copied]")
        self.assertEqual(page.inner_text(".aip-live"), "Copied the link.")
        page.evaluate("location.hash = '#trade-targets'")
        page.wait_for_selector("#v2AiPanel[data-copy=idle]")
        self.assertEqual(page.inner_text(".aip-live"), "")
        page.context.close()

    def test_late_copy_after_the_view_moved_is_dropped(self):
        # JEG-1300: a slow copy started on view A settles after the reader opened view B (hashchange) or changed the league or
        # roster on the same route. Neither "Copied" nor A's link as the fallback may show on the newer view.
        other = "https://example.invalid/fantasy-tools/#trade-targets?v=1&scoring=half_ppr&teams=12&target=9"
        for settle in ("resolve", "reject"):
            for move in ("hashchange", "same-route"):
                with self.subTest(settle=settle, move=move):
                    errors = []
                    page = self.open(ctx_for("ready"), 390, errors=errors)
                    page.evaluate("window.__AIP_CLIP_HOLD = true")
                    page.click("#aipCopy")
                    page.wait_for_function("window.__aipHold.length === 1")
                    page.evaluate(f"window.__AIP_CTX = {json.dumps(ctx_for('default-league'))}; window.__AIP_LINK = {json.dumps(other)};")
                    if move == "hashchange":
                        page.evaluate("location.hash = '#trade-targets'")
                    else:
                        page.evaluate("window.__aipHandle.update()")
                    page.evaluate(f"window.__aipHold[0].{settle}(new DOMException('slow', 'NotAllowedError'))" if settle == "reject"
                                  else "window.__aipHold[0].resolve()")
                    page.wait_for_timeout(100)
                    self.assertEqual(page.get_attribute("#v2AiPanel", "data-copy"), "idle")
                    self.assertEqual(page.locator("#aipResult").count(), 0)
                    self.assertEqual(page.locator("#aipLinkText").count(), 0, "view A's link shown as view B's fallback")
                    self.assertEqual(page.inner_text(".aip-live"), "")
                    self.assertIn("the default league settings", page.inner_text(".aip-carries"))
                    self.assertEqual(errors, [])
                    page.context.close()


if __name__ == "__main__":
    unittest.main()
