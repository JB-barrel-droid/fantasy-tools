"""Selected-package composition preview (JEG-1275) in a real browser: every case in
tests/fixtures/package_composition_preview/cases.json at 1280, 390 and 320 with no sideways scroll and nothing past the
right edge, the synthetic label on screen, keyboard disclosure (Tab to a toggle, Enter and Space open and close it, with
aria-expanded kept in step), the supplied errors in order with their exact text, the supplied lineup shown row for row,
final lineup unavailable without a lineup adapter, frozen inputs unchanged, no page errors and no storage writes.

The preview is mounted on its own harness page (tests/fixtures/package_composition_preview/preview.html with v2.css),
because the runtime hook waits on the reviewed JEG-1262 helper and a real lineup adapter. The roster check and the lineup
are mocks that replay recorded answers. Set PACKAGE_PREVIEW_SHOTS=<dir> to save screenshots for PR evidence.
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
APP = ROOT / "app" / "v2"
FIX = ROOT / "tests" / "fixtures" / "package_composition_preview"
DATA = json.loads((FIX / "cases.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)
STATE = {"valid_with_lineup": ("valid", "ready"), "valid_no_lineup": ("valid", "unavailable"),
         "duplicate_team": ("invalid", "unavailable"), "duplicate_player": ("invalid", "unavailable"),
         "unknown_ids": ("invalid", "unavailable"), "unavailable_none": ("unavailable", "unavailable"),
         "unavailable_throws": ("unavailable", "unavailable"), "unavailable_unreadable": ("unavailable", "unavailable"),
         "empty_selection": ("empty", "unavailable"), "incomplete_lineup": ("valid", "incomplete"),
         "long_names": ("valid", "unavailable")}

STORAGE_SPY = """(() => { window.__pcpWrites = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__pcpWrites.push([name, args[0]]); return real.apply(this, args); }; } })();"""


@contextlib.contextmanager
def harness():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("v2.css", "package-composition-preview.css", "package-composition-preview.js"):
            shutil.copy2(APP / name, Path(tmp) / name)
        shutil.copy2(FIX / "preview.html", Path(tmp) / "index.html")

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


class PackageCompositionPreviewRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(harness())
        shots = os.environ.get("PACKAGE_PREVIEW_SHOTS", "").strip()
        cls.shots = Path(shots) if shots else None
        if cls.shots:
            cls.shots.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, name, width, errors):
        context = self.chromium.new_context(viewport={"width": width, "height": 900})
        context.add_init_script(STORAGE_SPY)
        payload = {"fixture": DATA["fixture"], "league": DATA["league"], "case": DATA["cases"][name]}
        context.add_init_script(f"window.__PCP = {json.dumps(payload)};")
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base, wait_until="load")
        page.wait_for_selector("#pcpBox[data-state]")
        return page

    def assert_layout(self, page, label):
        fit = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,"
                            " wide: [...document.querySelectorAll('#pcpBox *')].filter(n => n.getClientRects().length && n.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5).map(n => n.className || n.tagName)})")
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: sideways scroll {fit}")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the right edge")
        heads = page.evaluate("() => [...document.querySelectorAll('h1, #pcpBox h2, #pcpBox h3, #pcpBox h4')].filter(h => h.getClientRects().length).map(h => [Number(h.tagName[1]), h.textContent.trim()])")
        for (prev, _), (level, text) in zip(heads, heads[1:]):
            self.assertLessEqual(level - prev, 1, f"{label}: heading level skipped before {text!r}")

    def open_all_toggles(self, page):
        for i in range(page.locator(".pcp-toggle").count()):
            page.locator(".pcp-toggle").nth(i).click()

    def test_every_case_at_every_width(self):
        for width in WIDTHS:
            for name, (state, lineup) in STATE.items():
                with self.subTest(width=width, case=name):
                    errors = []
                    page = self.open(name, width, errors)
                    self.assertEqual(page.get_attribute("#pcpBox", "data-state"), state)
                    self.assertEqual(page.get_attribute("#pcpBox", "data-lineup"), lineup)
                    self.assertIn("Synthetic example.", page.inner_text(".pcp-fixture"))
                    self.assert_layout(page, f"{name}@{width}")
                    self.open_all_toggles(page)  # everything disclosed must still fit
                    self.assert_layout(page, f"{name}@{width} open")
                    if self.shots and name in ("valid_with_lineup", "unknown_ids", "valid_no_lineup", "long_names", "incomplete_lineup"):
                        page.screenshot(path=str(self.shots / f"{name}-{width}.png"), full_page=True)
                    self.assertTrue(page.evaluate("window.__pcpCheckInputs()"), "frozen inputs unchanged")
                    self.assertEqual(page.evaluate("window.__pcpWrites"), [])
                    self.assertEqual(errors, [])
                    page.context.close()

    def test_supplied_errors_and_rows(self):
        for name in ("duplicate_team", "duplicate_player", "unknown_ids"):
            with self.subTest(case=name):
                case = DATA["cases"][name]
                page = self.open(name, 390, [])
                self.assertEqual(page.locator(".pcp-errors li").all_inner_texts(), [e["message"] for e in case["adapter"]["validation"]["errors"]])
                self.assertEqual(page.locator(".pcp-trade").count(), len(case["trades"]), "every trade row kept")
                flagged = sorted({e["tradeIndex"] for e in case["adapter"]["validation"]["errors"] if "tradeIndex" in e})
                self.assertEqual([int(x) for x in page.locator(".pcp-trade.is-invalid").evaluate_all("ns => ns.map(n => n.dataset.tradeIndex)")], flagged)
                self.assertEqual(page.locator(".pcp-lineup-table").count(), 0, "no lineup for an invalid package")
                page.context.close()

    def test_lineup_parity_and_unavailable(self):
        case = DATA["cases"]["valid_with_lineup"]
        page = self.open("valid_with_lineup", 1280, [])
        for side in ("before", "after"):
            rows = page.locator(f'.pcp-lineup-side[data-side="{side}"] table[data-rows="starters"] tbody tr').evaluate_all(
                "rs => rs.map(r => [r.querySelector('th').textContent, r.querySelector('td').textContent])")
            self.assertEqual(rows, [[r["slot"], r["name"]] for r in case["adapter"]["lineup"][side]["starters"]], f"{side} starters parity")
        self.assertEqual(page.evaluate("window.__pcpCalls.map(c => c[0])"), ["validatePackage", "applyPackage", "lineups"])
        page.context.close()
        page = self.open("valid_no_lineup", 1280, [])
        self.assertIn("Final lineup unavailable", page.inner_text(".pcp-lineup"))
        self.assertEqual(page.locator(".pcp-lineup table").count(), 0)
        self.assertEqual(page.evaluate("window.__pcpCalls.map(c => c[0])"), ["validatePackage"], "helper rosters never requested")
        page.context.close()

    def test_keyboard_disclosure(self):
        for width in WIDTHS:
            with self.subTest(width=width):
                page = self.open("valid_with_lineup", width, [])
                toggle = page.locator(".pcp-toggle").first
                region = toggle.get_attribute("aria-controls")
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                self.assertTrue(page.locator(f"#{region}").is_hidden())
                for _ in range(20):
                    page.keyboard.press("Tab")
                    if page.evaluate("document.activeElement.getAttribute('aria-controls')") == region:
                        break
                self.assertEqual(page.evaluate("document.activeElement.getAttribute('aria-controls')"), region, "the toggle is reachable by Tab")
                page.keyboard.press("Enter")
                self.assertEqual(toggle.get_attribute("aria-expanded"), "true")
                self.assertTrue(page.locator(f"#{region}").is_visible())
                self.assertIn("WR Atlas", page.inner_text(f"#{region}"))
                page.keyboard.press("Space")
                self.assertEqual(toggle.get_attribute("aria-expanded"), "false")
                self.assertTrue(page.locator(f"#{region}").is_hidden())
                page.context.close()

    def test_greedy_three_counterparty_package_and_final_lineup(self):
        """Real selector + roster helper + starter picker, then the unchanged preview."""
        for width in (390, 1280):
            with self.subTest(width=width):
                page = self.chromium.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.add_init_script(STORAGE_SPY)
                page.goto("about:blank")
                page.set_content('<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
                                 '<body><h1>Synthetic package search</h1><div id="pcpBox"></div></body></html>')
                for name in ("v2.css", "package-composition-preview.css"):
                    page.add_style_tag(path=str(APP / name))
                for name in ("trade.js", "finder.js", "opportunities.js", "trade-package-constraints.js",
                             "trade-package-search.js", "package-composition-preview.js"):
                    page.add_script_tag(path=str(APP / name))
                page.add_script_tag(path=str(ROOT / "tests" / "jeg1183_package_cases.js"))
                actual = page.evaluate("""() => {
                  const {league, candidates, ctx} = PackageSearchCases.makeCase();
                  const P = TradePackageConstraints, F = TradeValueFinder;
                  const before = JSON.stringify([league, candidates, [...ctx.rowsByKey]]);
                  const result = TradeValuePackageSearch.selectPackage(league, candidates, ctx);
                  const sequential = result.trades.reduce((l, t) => P.applyTrade(l, t).league, league);
                  const side = l => {
                    const rows = l.teams[0].entries.map(e => ctx.rowsByKey.get(e.key));
                    const p = F.pickStarters(rows, ctx.shape, F.OUR_KEY);
                    const row = (r, slot) => ({key: r.player_key, name: r.name, slot: slot || r.pos});
                    return {starters: Object.entries(p.slots).flatMap(([s, rs]) => rs.map(r => row(r, s))),
                      bench: p.bench.map(r => row(r))};
                  };
                  const vm = TradeValuePackagePreview.viewModel({league, trades: result.trades, package: P,
                    fixture: {kind: 'synthetic', label: 'Synthetic greedy package; not a live league.'},
                    lineup: {lineups: (l, applied) => ({before: side(l), after: side(applied)})}});
                  TradeValuePackagePreview.render(document.getElementById('pcpBox'), vm);
                  const moved = result.trades.flatMap(t => t.give.concat(t.receive).map(r => r.player_key));
                  return {status: result.status, ids: result.trades.map(t => t.opponentId),
                    uniquePlayers: new Set(moved).size === moved.length,
                    sequential: JSON.stringify(result.league) === JSON.stringify(sequential),
                    expected: side(sequential).starters.map(r => r.key),
                    unchanged: before === JSON.stringify([league, candidates, [...ctx.rowsByKey]])};
                }""")
                self.assertEqual(actual["status"], "ready")
                self.assertEqual(actual["ids"], ["d", "c", "b"])
                self.assertTrue(actual["uniquePlayers"])
                self.assertTrue(actual["sequential"])
                self.assertTrue(actual["unchanged"])
                self.assertEqual(actual["expected"], ["a-qb", "a-rb", "c-w", "d-t"])
                shown = page.locator('.pcp-lineup-side[data-side="after"] table[data-rows="starters"] tbody tr').evaluate_all(
                    "rs => rs.map(r => r.dataset.key)")
                self.assertEqual(shown, actual["expected"])
                self.assertEqual(page.locator(".pcp-trade").count(), 3)
                self.assertEqual(page.get_attribute("#pcpBox", "data-lineup"), "ready")
                self.open_all_toggles(page)
                self.assert_layout(page, f"greedy@{width}")
                self.assertEqual(errors, [])
                self.assertEqual(page.evaluate("window.__pcpWrites"), [])
                page.context.close()


    def test_package_panel_build_and_invalidation(self):
        for width in (390, 1280):
            with self.subTest(width=width):
                page = self.chromium.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.add_init_script(STORAGE_SPY)
                page.goto("about:blank")
                page.set_content('<h1>Synthetic package panel</h1><div id="pcpBox"></div>')
                for name in ("v2.css", "package-composition-preview.css", "trade-package-panel.css"):
                    page.add_style_tag(path=str(APP / name))
                for name in ("trade.js", "finder.js", "opportunities.js", "trade-package-constraints.js",
                             "trade-package-search.js", "package-composition-preview.js", "trade-package-panel.js"):
                    page.add_script_tag(path=str(APP / name))
                page.add_script_tag(path=str(ROOT / "tests" / "jeg1183_package_cases.js"))
                page.evaluate("""() => {
                  const c = PackageSearchCases.makeCase();
                  window.__panelInput = c;
                  window.__panelBefore = JSON.stringify([c.league, c.candidates, [...c.ctx.rowsByKey]]);
                  window.__panel = TradeValuePackagePanel.mount(document.getElementById('pcpBox'));
                  window.__snapshot = {status: 'ready', ...c};
                  __panel.update(__snapshot);
                }""")
                self.assertEqual(page.locator(".pcp-trade").count(), 0, "search waits for a user action")
                page.get_by_role("button", name="Build package", exact=True).focus()
                page.keyboard.press("Enter")
                self.assertEqual(page.get_attribute("#pcpBox", "data-package-size"), "3")
                self.assertEqual(page.locator(".pcp-trade").count(), 3)
                self.assertEqual(page.locator('.pcp-lineup-side[data-side="after"] [data-rows="starters"] tbody tr').evaluate_all(
                    "rs => rs.map(r => r.dataset.key)"), ["a-qb", "a-rb", "c-w", "d-t"])
                page.evaluate("__panel.update(__snapshot)")
                self.assertEqual(page.locator(".pcp-trade").count(), 3, "same result preserves the package")
                self.open_all_toggles(page)
                self.assert_layout(page, f"package panel@{width}")
                self.assertGreaterEqual(page.get_by_role("button", name="Build package", exact=True).bounding_box()["height"], 44)
                page.evaluate("__panel.update({status:'pending'})")
                self.assertTrue(page.get_by_role("button", name="Build package", exact=True).is_disabled())
                self.assertEqual(page.locator(".pcp-lineup-table").count(), 0, "no stale lineup during a new search")
                self.assertEqual(page.locator(".pcp-trade").count(), 0)
                page.evaluate("__panel.update({...__snapshot, candidates: []})")
                page.get_by_role("button", name="Build package", exact=True).click()
                self.assertIn("No viable package", page.inner_text(".package-panel-status"))
                page.evaluate("__panel.update({...__snapshot, ctx: null})")
                page.get_by_role("button", name="Build package", exact=True).click()
                self.assertEqual(page.get_attribute("#pcpBox", "data-state"), "unavailable")
                self.assertEqual(page.locator(".pcp-lineup-table").count(), 0)
                self.assertTrue(page.evaluate("__panelBefore === JSON.stringify([__panelInput.league, __panelInput.candidates, [...__panelInput.ctx.rowsByKey]])"))
                self.assertEqual(page.evaluate("window.__pcpWrites"), [])
                self.assertEqual(errors, [])
                page.context.close()


if __name__ == "__main__":
    unittest.main()
