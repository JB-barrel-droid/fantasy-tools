"""Trade target answer card (JEG-1274) in a real browser: every state at 1280, 390 and 320 with no sideways scroll,
closed and open; supplied values shown exactly (a real zero as 0); keyboard and touch disclosures; focus kept on
repeated open/close and on re-render; the mocked detail slot mounted and cleaned up; and no storage writes or network.

The card is mounted by the fixture preview (tests/fixtures/target_answer_card/preview.html) with the synthetic cases
injected, because the targets route hookup waits on JEG-1137 / JEG-1138 / JEG-1130 (JEG-1274). Set
TARGET_ANSWER_CARD_SHOTS=<dir> to save the screenshots used as PR evidence.

Run: python3 -m unittest tests.test_target_answer_card_render
"""
from __future__ import annotations

import contextlib
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
FIXTURES = ROOT / "tests" / "fixtures" / "target_answer_card"
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)
FILES = ["app/v2/v2.css", "app/v2/target-answer-card.css", "app/v2/target-answer-card.js",
         "tests/fixtures/target_answer_card/preview.html", "tests/fixtures/target_answer_card/cases.json"]
PREVIEW = "tests/fixtures/target_answer_card/preview.html"
STATE_OF = {"buy": "buy", "sell": "sell", "fair": "fair", "empty": "empty", "missing": "missing",
            "unavailable": "unavailable", "zero": "sell", "long_name": "buy"}

# Counts every storage write the page makes after load.
STORAGE_SPY = """(() => { window.__tacWrites = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__tacWrites.push([name, args[0]]); return real.apply(this, args); }; } })();"""

LAYOUT_JS = """() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,
  wide: [...document.querySelectorAll('.tac, .tac *')].filter(n => { const r = n.getBoundingClientRect();
    return r.width > 0 && (r.right > document.documentElement.clientWidth + 0.5 || r.left < -0.5); })
    .map(n => n.className || n.tagName)})"""


@contextlib.contextmanager
def server():
    with tempfile.TemporaryDirectory() as tmp:
        for rel in FILES:
            (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, Path(tmp) / rel)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=tmp)) as srv:
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{srv.server_address[1]}/{PREVIEW}"
            finally:
                srv.shutdown()


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


class TargetAnswerCardRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(server())
        shots = os.environ.get("TARGET_ANSWER_CARD_SHOTS", "").strip()
        cls.shots = Path(shots) if shots else None
        if cls.shots:
            cls.shots.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, width, case=None, touch=False):
        context = self.chromium.new_context(viewport={"width": width, "height": 900}, has_touch=touch, is_mobile=touch)
        self.addCleanup(context.close)
        context.add_init_script(STORAGE_SPY)
        context.add_init_script(f"window.__TAC_CASES = {json.dumps(CASES)};")
        page = context.new_page()
        errors, requests = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: requests.append(r.url))
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base + (f"?case={case}" if case else ""), wait_until="load")
        page.wait_for_selector("body[data-ready=true]")
        self.addCleanup(lambda: self.assertEqual(errors, [], "page errors"))
        page.tac_requests = requests
        return page

    def shot(self, page, name):
        if self.shots:
            page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)

    def assert_fits(self, page, label):
        fit = page.evaluate(LAYOUT_JS)
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: page scrolls sideways")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the viewport")

    def open_all(self, page):
        page.evaluate("() => Object.values(window.__tacHandles).forEach(h => { h.open('sources'); h.open('detail'); })")

    def test_every_state_fits_at_each_width(self):
        for width in WIDTHS:
            for name, state in STATE_OF.items():
                with self.subTest(width=width, case=name):
                    page = self.open(width, name)
                    host = page.locator(f"#card-{name}")
                    self.assertEqual(host.get_attribute("data-state"), state)
                    self.assertEqual(page.locator(f"#card-{name} .tac-fixture").inner_text(), CASES["fixture"]["label"])
                    self.assert_fits(page, f"{name} closed at {width}")
                    self.shot(page, f"{name}-{width}-closed")
                    self.open_all(page)
                    self.assert_fits(page, f"{name} open at {width}")
                    self.shot(page, f"{name}-{width}-open")
                    page.context.close()

    def test_all_cases_together_fit(self):
        for width in WIDTHS:
            with self.subTest(width=width):
                page = self.open(width)
                self.open_all(page)
                self.assert_fits(page, f"all cases at {width}")
                self.shot(page, f"all-{width}")
                page.context.close()

    def test_values_shown_exactly(self):
        page = self.open(390)
        for name, case in CASES["cases"].items():
            for item in case.get("values", []):
                text = page.locator(f'#card-{name} .tac-value[data-key="{item["key"]}"] dd').first.inner_text()
                if item.get("display"):
                    want = item["display"]
                elif item["value"] is None:
                    want = "No value"
                else:
                    want = "0" if item["value"] == 0 else json.dumps(item["value"])
                self.assertEqual(text, want, f"{name}/{item['key']}")
        page.evaluate("() => window.__tacHandles.zero.open('sources')")
        self.assertEqual(page.locator('#card-zero .tac-source[data-key="syn_chart_a"] .tac-source-value').inner_text(), "0")

    def test_keyboard_disclosure_and_escape(self):
        page = self.open(390, "buy")
        toggle = page.locator('#card-buy [data-tac-toggle="sources"]')
        panel = page.locator("#card-buy .tac-disclosure[data-key=sources] .tac-panel")
        page.keyboard.press("Tab")
        self.assertEqual(page.evaluate("() => document.activeElement.getAttribute('data-tac-toggle')"), "sources")
        self.assertFalse(panel.is_visible())
        page.keyboard.press("Enter")
        self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
        self.assertTrue(panel.is_visible())
        page.keyboard.press("Space")
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        self.assertFalse(panel.is_visible())
        # Escape from inside an open detail panel closes it and returns focus to its toggle.
        page.keyboard.press("Tab")
        self.assertEqual(page.evaluate("() => document.activeElement.getAttribute('data-tac-toggle')"), "detail")
        page.keyboard.press("Enter")
        page.locator("#card-buy .mock-detail-action").focus()
        page.keyboard.press("Escape")
        self.assertEqual(page.locator('#card-buy [data-tac-toggle="detail"]').get_attribute("aria-expanded"), "false")
        self.assertEqual(page.evaluate("() => document.activeElement.getAttribute('data-tac-toggle')"), "detail")

    def test_touch_disclosure(self):
        page = self.open(320, "sell", touch=True)
        toggle = page.locator('#card-sell [data-tac-toggle="detail"]')
        box = toggle.bounding_box()
        self.assertGreaterEqual(box["height"], 44, "touch target height")
        toggle.tap()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
        self.assertIn("Runner Bravo", page.locator("#card-sell .mock-detail").inner_text())
        toggle.tap()
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        self.assertEqual(page.locator("#card-sell .mock-detail").count(), 0, "closing removes the mocked detail")

    def test_focus_kept_on_repeated_toggle_and_rerender(self):
        page = self.open(1280, "buy")
        toggle = page.locator('#card-buy [data-tac-toggle="detail"]')
        toggle.focus()
        for i in range(4):
            page.keyboard.press("Enter")
            self.assertEqual(page.evaluate("() => document.activeElement.getAttribute('data-tac-focus')"), "detail", f"press {i + 1}")
        self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
        page.keyboard.press("Enter")
        for i in range(3):
            page.evaluate("() => window.__tacHandles.buy.update(Object.assign({fixture: window.__tacCases.fixture}, window.__tacCases.cases.buy))")
            self.assertEqual(page.evaluate("() => document.activeElement.getAttribute('data-tac-focus')"), "detail", f"re-render {i + 1}")
            self.assertEqual(page.locator('#card-buy [data-tac-toggle="detail"]').get_attribute("aria-expanded"), "true", "open kept")
            self.assertEqual(page.locator("#card-buy .mock-detail").count(), 1, "one detail mounted")
        log = page.evaluate("() => window.__tacSlotLog")
        mounts = sum(1 for e in log if e[0] == "mount")
        cleanups = sum(1 for e in log if e[0] == "cleanup")
        self.assertEqual(mounts - cleanups, 1, f"every earlier mount was cleaned up: {log}")
        # A different player resets the disclosures.
        page.evaluate("() => window.__tacHandles.buy.update(Object.assign({fixture: window.__tacCases.fixture}, window.__tacCases.cases.sell))")
        self.assertEqual(page.locator('#card-buy [data-tac-toggle="detail"]').get_attribute("aria-expanded"), "false")
        self.assertEqual(page.locator("#card-buy .tac").get_attribute("data-player-id"), CASES["cases"]["sell"]["player"]["id"])

    def test_failing_detail_slot_keeps_the_card(self):
        page = self.open(390, "buy")
        page.evaluate("""() => { const host = document.createElement('div'); host.id = 'card-throws'; document.body.appendChild(host);
          const h = TradeValueTargetAnswerCard.mount(host, {renderDetail: () => { throw new Error('synthetic slot failure'); }});
          h.update(Object.assign({fixture: window.__tacCases.fixture}, window.__tacCases.cases.buy)); h.open('detail'); }""")
        self.assertEqual(page.locator("#card-throws .tac-detail-slot").inner_text(), "Details could not be shown.")
        self.assertEqual(page.locator("#card-throws").get_attribute("data-state"), "buy")

    def test_no_renderer_means_no_detail_disclosure(self):
        page = self.open(390, "buy")
        count = page.evaluate("""() => { const host = document.createElement('div'); document.body.appendChild(host);
          const h = TradeValueTargetAnswerCard.mount(host, {});
          h.update(Object.assign({fixture: window.__tacCases.fixture}, window.__tacCases.cases.buy));
          return [host.querySelectorAll('[data-tac-toggle=detail]').length, host.querySelectorAll('[data-tac-toggle=sources]').length]; }""")
        self.assertEqual(count, [0, 1])

    def test_escape_in_a_nested_card_closes_only_that_card(self):
        page = self.open(390, "buy")
        result = page.evaluate("""() => { const host = document.createElement('div'); document.body.appendChild(host);
          let inner = null; const C = window.__tacCases;
          const outer = TradeValueTargetAnswerCard.mount(host, {renderDetail: slot => { const box = document.createElement('div'); slot.appendChild(box);
            inner = TradeValueTargetAnswerCard.mount(box, {}); inner.update(Object.assign({fixture: C.fixture}, C.cases.sell)); inner.open('sources');
            return () => inner.destroy(); }});
          outer.update(Object.assign({fixture: C.fixture}, C.cases.buy)); outer.open('detail');
          let bubbled = 0; document.addEventListener('keydown', e => { if (e.key === 'Escape') bubbled += 1; });
          const innerToggle = host.querySelector('.tac-detail-slot [data-tac-toggle=sources]');
          host.querySelector('.tac-detail-slot .tac-panel .tac-source').setAttribute('tabindex', '-1');
          host.querySelector('.tac-detail-slot .tac-panel .tac-source').focus();
          document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
          return {inner: inner.isOpen('sources'), outer: outer.isOpen('detail'), focus: document.activeElement === innerToggle, bubbled}; }""")
        self.assertEqual(result, {"inner": False, "outer": True, "focus": True, "bubbled": 0})

    def test_no_storage_or_network(self):
        page = self.open(390)
        self.open_all(page)
        page.evaluate("() => Object.values(window.__tacHandles).forEach(h => { h.close('sources'); h.close('detail'); })")
        self.assertEqual(page.evaluate("() => window.__tacWrites"), [])
        local = [u for u in page.tac_requests if not u.endswith("/favicon.ico") and not any(u.endswith(f) for f in FILES)]
        self.assertEqual(local, [], "only the page and its own files were requested")

    def test_input_still_frozen_and_unchanged(self):
        page = self.open(390)
        changed = page.evaluate("""() => { const deepFreeze = x => { if (x && typeof x === 'object') { Object.values(x).forEach(deepFreeze); Object.freeze(x); } return x; };
          const out = []; Object.entries(window.__tacCases.cases).forEach(([name, c]) => {
            const input = deepFreeze(JSON.parse(JSON.stringify(Object.assign({fixture: window.__tacCases.fixture}, c))));
            const before = JSON.stringify(input); const host = document.createElement('div'); document.body.appendChild(host);
            const h = TradeValueTargetAnswerCard.mount(host, {renderDetail: (slot, d) => { slot.textContent = 'x'; }});
            h.update(input); h.open('sources'); h.open('detail'); h.update(input); h.close('detail');
            if (JSON.stringify(input) !== before) out.push(name); h.destroy(); host.remove(); }); return out; }""")
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
