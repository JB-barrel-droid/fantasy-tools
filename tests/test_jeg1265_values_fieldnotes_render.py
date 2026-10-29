"""Values page Fieldnotes view (JEG-1265) in a real browser: every state at 1280, 390 and 320 with no sideways scroll, one
"Value chart" h1, every shown number as the page's fmt() draws it, missing values as "—" with their reason, long names
readable, labelled controls, keyboard sort / search / disclosure / details with focus kept, and no storage writes.

The component is mounted on a private harness page (v2.css, values-fieldnotes.css, source-views.js, values-fieldnotes.js)
with the synthetic fixture injected and a small mocked controller standing in for the page (it filters by search and
position and keeps sort, shown and rank-by in memory). That controller is test scaffolding, not the live hookup: the real
page keeps its own filtering and state, and the hookup waits on JEG-1137. Set VALUES_FIELDNOTES_SHOTS=<dir> to save the
screenshots used as PR evidence.
"""
from __future__ import annotations

import contextlib
import copy
import decimal
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
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "values-fieldnotes" / "synthetic-values.json").read_text(encoding="utf-8"))
WIDTHS = (1280, 390, 320)
LONG_NAME = next(r["name"] for r in FIXTURE["rows"] if "Long-Named" in r["name"])

PAGE = """<!doctype html>
<html lang="en" data-canvas="paper" data-design="fieldnotes"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Values Fieldnotes view (test harness, synthetic data)</title>
<link rel="stylesheet" href="v2.css"><link rel="stylesheet" href="values-fieldnotes.css">
<script src="source-views.js"></script><script src="values-fieldnotes.js"></script>
</head><body class="v2"><div class="v2-app">
<main id="vfRoot" aria-labelledby="vfTitle"></main>
<div id="vfMockDrawer" role="dialog" aria-label="Player details (mock)" hidden><button type="button" id="vfMockDrawerClose">Close</button></div></div>
<script>
// Mocked preview controller (test scaffolding only). The live page filters view.visible itself and owns state.
(() => {
  const base = window.__VF_CTX;
  const ui = {search: base.filters ? base.filters.search : "", position: base.filters ? base.filters.position : "ALL",
    sort: base.sort || null, shown: base.shown, rankKey: base.rankKey};
  window.__vfOpened = [];
  const flex = new Set(["RB", "WR", "TE"]);
  const ctx = () => {
    if (!base.rows) return base;
    const q = ui.search.trim().toLowerCase();
    const rows = base.rows.filter(r => (!q || r.name.toLowerCase().includes(q))
      && (ui.position === "ALL" || (ui.position === "FLEX" ? flex.has(r.pos) : r.pos === ui.position)));
    return {...base, rows, sort: ui.sort, shown: ui.shown, rankKey: ui.rankKey, filters: {search: ui.search, position: ui.position}};
  };
  let handle = null;
  let drawerOpener = null;
  document.getElementById("vfMockDrawerClose").addEventListener("click", () => {
    document.getElementById("vfMockDrawer").hidden = true;
    if (drawerOpener && drawerOpener.focus) drawerOpener.focus();
    handle.update();
  });
  const on = {
    sort: next => { ui.sort = next; handle.update(); },
    filter: change => { Object.assign(ui, change); handle.update(); },
    rankBy: key => { ui.rankKey = key; ui.sort = null; handle.update(); },
    showMore: () => { ui.shown += 25; handle.update(); },
    // Mock drawer, as v2.js openDrawer/closeDrawer: remember the opener, focus the drawer, and on close send focus back
    // to the opener. The page then redraws (handle.update() runs wherever renderTable() does).
    // It sits inside .v2-app because v2.css hides every other child of body.v2.
    open: key => { window.__vfOpened.push(key); drawerOpener = document.activeElement;
      document.getElementById("vfMockDrawer").hidden = false; document.getElementById("vfMockDrawerClose").focus(); },
    clear: () => { ui.search = ""; ui.position = "ALL"; handle.update(true); }
  };
  handle = TradeValueValuesFieldnotes.mount(document.getElementById("vfRoot"), {getContext: ctx, on});
  window.__vfHandle = handle;
})();
</script>
</body></html>
"""

# Counts every storage write the page makes after load.
STORAGE_SPY = """(() => { window.__vfWrites = [];
  for (const name of ["setItem", "removeItem", "clear"]) { const real = Storage.prototype[name];
    Storage.prototype[name] = function (...args) { window.__vfWrites.push([name, args[0]]); return real.apply(this, args); }; } })();"""


def state(name: str) -> dict:
    ctx = copy.deepcopy(FIXTURE)
    if name == "loading":
        ctx["status"] = "loading"
    elif name == "unavailable":
        ctx["status"] = "unavailable"
        ctx["reason"] = "Synthetic: no values could be read for this test."
    elif name == "empty":
        ctx["filters"]["search"] = "no such player"
    elif name == "missing":
        # A published chart with no value for most players, beside the unavailable CBS rest-of-season column.
        for row in ctx["rows"][::2]:
            row["values"]["fantasypros"] = None
            row["reasons"]["fantasypros"] = "FantasyPros has no value for this player"
    elif name == "mixed":
        next(c for c in ctx["columns"] if c["id"] == "espn")["horizon"] = "weekly"
    return ctx


STATES = {"ready": "ready", "missing": "ready", "empty": "empty", "unavailable": "unavailable", "loading": "loading", "mixed": "mixed"}


def fmt(v):
    """v2.js fmt(), for the expected text (the harness proves the component's copy equals v2.js itself)."""
    if not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        return "—"
    # Number.prototype.toFixed rounds the exact binary value half away from zero (70.25 -> "70.3"); Python's format
    # rounds half to even, so the expected text is rounded with Decimal instead.
    text = str(decimal.Decimal(v).quantize(decimal.Decimal("0.1"), rounding=decimal.ROUND_HALF_UP))
    return "0.0" if text == "-0.0" else text.replace("-", "−")


@contextlib.contextmanager
def harness():
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("v2.css", "values-fieldnotes.css", "source-views.js", "values-fieldnotes.js"):
            shutil.copy2(APP / name, Path(tmp) / name)
        shutil.copytree(APP / "fonts", Path(tmp) / "fonts")   # Fraunces, which the Fieldnotes opt-in names
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


class ValuesFieldnotesRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._stack = contextlib.ExitStack()
        cls.chromium = cls._stack.enter_context(browser())
        cls.base = cls._stack.enter_context(harness())
        shots = os.environ.get("VALUES_FIELDNOTES_SHOTS", "").strip()
        cls.shots = Path(shots) if shots else None
        if cls.shots:
            cls.shots.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls._stack.close()

    def open(self, ctx, width, errors=None, dark=False):
        context = self.chromium.new_context(viewport={"width": width, "height": 900}, color_scheme="dark" if dark else "light")
        context.add_init_script(STORAGE_SPY)
        context.add_init_script(f"window.__VF_CTX = {json.dumps(ctx)};")
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)) if errors is not None else None)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base, wait_until="load")
        page.wait_for_selector("#vfRoot[data-state]")
        return page

    def shot(self, page, name):
        if self.shots:
            page.screenshot(path=str(self.shots / f"{name}.png"), full_page=True)

    def assert_layout(self, page, label):
        fit = page.evaluate("() => ({scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth,"
                            " wide: [...document.querySelectorAll('#vfRoot *')].filter(n => n.offsetParent !== null"
                            " && !n.closest('.vf-tablewrap') && n.getBoundingClientRect().right > document.documentElement.clientWidth + 0.5)"
                            ".map(n => n.className || n.tagName)})")
        self.assertLessEqual(fit["scroll"], fit["width"], f"{label}: sideways page scroll {fit}")
        self.assertEqual(fit["wide"], [], f"{label}: elements past the right edge")
        heads = page.evaluate("() => [...document.querySelectorAll('#vfRoot h1, #vfRoot h2, #vfRoot h3')].filter(h => h.offsetParent !== null)"
                              ".map(h => [Number(h.tagName[1]), h.textContent.trim()])")
        self.assertEqual([h for h in heads if h[0] == 1], [[1, "Value chart"]], f"{label}: one h1")
        for (prev, _), (level, text) in zip(heads, heads[1:]):
            self.assertLessEqual(level - prev, 1, f"{label}: heading level skipped before {text!r}")
        # Every visible control has an accessible name.
        unnamed = page.evaluate("""() => [...document.querySelectorAll('#vfRoot button, #vfRoot input, #vfRoot select, #vfRoot summary')]
          .filter(n => n.offsetParent !== null).filter(n => {
            const label = n.labels && n.labels.length ? n.labels[0].textContent.trim() : '';
            return !(n.getAttribute('aria-label') || label || n.textContent.trim()); }).map(n => n.outerHTML.slice(0, 80))""")
        self.assertEqual(unnamed, [], f"{label}: controls without a name")

    def shown_numbers(self, page, width):
        """The value cells the reader sees: [player key, column, text, title]."""
        sel = ".vf-table tbody tr" if width >= 720 else ".vf-cards > li"
        return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].flatMap(row => {
          const key = row.dataset.playerKey;
          const cells = row.matches('tr') ? [...row.querySelectorAll('td[data-col]')].map(td => [td.dataset.col, td])
            : [...row.querySelectorAll('.vf-disclosure dd')].map((dd, i) => [i, dd]);
          return cells.map(([col, node]) => { const n = node.querySelector('.vf-num, .vf-missing');
            return [key, col, n.firstChild.textContent, n.getAttribute('title')]; }); })""", sel)

    def test_every_state_at_every_width(self):
        for width in WIDTHS:
            for name, want in STATES.items():
                with self.subTest(width=width, state=name):
                    errors = []
                    page = self.open(state(name), width, errors=errors)
                    self.assertEqual(page.get_attribute("#vfRoot", "data-state"), want)
                    self.assert_layout(page, f"{name}@{width}")
                    self.assertIn("Synthetic example.", page.inner_text(".vf-fixture"))
                    if want != "ready":
                        self.assertEqual(page.locator(".vf-num:visible").count(), 0, f"{name}: no numbers shown")
                    table = page.locator(".vf-table").count() and page.locator(".vf-table").is_visible()
                    cards = page.locator(".vf-cards").count() and page.locator(".vf-cards").is_visible()
                    if want == "ready":
                        self.assertEqual((bool(table), bool(cards)), (width >= 720, width < 720), f"{name}@{width}: table on desktop, cards on phones")
                    self.shot(page, f"{name}-{width}")
                    self.assertEqual(errors, [])
                    self.assertEqual(page.evaluate("window.__vfWrites"), [])
                    page.context.close()

    def test_numbers_match_the_page_format(self):
        ctx = state("missing")
        byKey = {r["player_key"]: r for r in ctx["rows"]}
        cols = {c["id"]: c for c in ctx["columns"]}
        value_cols = [c for c in ctx["columns"] if c["kind"] in ("value", "spread")]
        for width in (1280, 390):
            with self.subTest(width=width):
                page = self.open(ctx, width)
                if width < 720:
                    page.evaluate("document.querySelectorAll('.vf-disclosure').forEach(d => d.open = true)")
                shown = self.shown_numbers(page, width)
                self.assertGreater(len(shown), 200)
                for key, col, text, title in shown:
                    c = cols[col] if width >= 720 else value_cols[col]
                    row = byKey[key]
                    v = row["spread"] if c["kind"] == "spread" else row["values"].get(c["source"])
                    self.assertEqual(text, fmt(v), f"{key} {c['id']}@{width}")
                    if v is None:
                        self.assertEqual(title, row["reasons"].get(c["id"]) or c.get("unavailable"), f"{key} {c['id']} reason")
                    else:
                        self.assertIsNone(title, f"{key} {c['id']}: a value has no missing reason")
                zero = page.locator('[data-player-key="syn-09"] td[data-col="espn"] .vf-num') if width >= 720 else None
                if zero is not None:
                    self.assertEqual(zero.inner_text(), "0.0", "a finite 0 is shown as 0.0, not as missing")
                page.context.close()

    def test_long_names_readable(self):
        for width in WIDTHS:
            with self.subTest(width=width):
                page = self.open(state("ready"), width)
                node = page.locator(f".{'vf-table' if width >= 720 else 'vf-cards'} .vf-name", has_text="Long-Named").first
                self.assertEqual(node.inner_text(), LONG_NAME)
                box = node.evaluate("n => ({sw: n.scrollWidth, cw: n.clientWidth, right: n.getBoundingClientRect().right,"
                                    " vw: document.documentElement.clientWidth})")
                self.assertLessEqual(box["sw"], box["cw"] + 1, f"name clipped at {width}: {box}")
                if width < 720:
                    self.assertLessEqual(box["right"], box["vw"], f"name past the edge at {width}")
                page.context.close()

    def test_keyboard_sort_keeps_focus(self):
        page = self.open(state("ready"), 1280)
        self.assertEqual(page.get_attribute('th[data-col="ddf_value"]', "aria-sort"), "descending")
        page.focus('button[data-focus="sort:espn"]')
        page.keyboard.press("Enter")
        self.assertEqual(page.get_attribute('th[data-col="espn"]', "aria-sort"), "descending")
        self.assertIsNone(page.get_attribute('th[data-col="ddf_value"]', "aria-sort"))
        self.assertEqual(page.evaluate("document.activeElement.dataset.focus"), "sort:espn", "focus stays on the header")
        page.keyboard.press("Enter")
        self.assertEqual(page.get_attribute('th[data-col="espn"]', "aria-sort"), "ascending")
        # Missing values sort last either way.
        page.focus('button[data-focus="sort:usatoday"]')
        page.keyboard.press("Enter")
        page.keyboard.press("Enter")
        self.assertEqual(page.get_attribute('th[data-col="usatoday"]', "aria-sort"), "ascending")
        page.locator('button[data-focus="more"]').click()
        last = page.evaluate("[...document.querySelectorAll('.vf-table tbody tr')].pop().dataset.playerKey")
        self.assertEqual(last, "syn-04", "missing USA Today value sorts last")
        page.context.close()

    def test_keyboard_search_position_and_clear(self):
        for width in (1280, 320):
            with self.subTest(width=width):
                page = self.open(state("ready"), width)
                page.focus("#vfSearch")
                page.keyboard.type("golf")
                self.assertEqual(page.evaluate("document.activeElement.id"), "vfSearch", "focus stays in the search box")
                self.assertEqual(page.input_value("#vfSearch"), "golf")
                self.assertEqual(page.inner_text("#vfMeta"), "1 player · ranks 1–30")
                page.keyboard.type("zzz")
                self.assertEqual(page.get_attribute("#vfRoot", "data-state"), "empty")
                page.focus('button[data-focus="clear"]')
                page.keyboard.press("Enter")
                self.assertEqual(page.get_attribute("#vfRoot", "data-state"), "ready")
                self.assertEqual(page.evaluate("document.activeElement.id"), "vfTitle", "after clearing, focus returns to the title")
                page.focus("#vfPosition")
                page.select_option("#vfPosition", "TE")
                self.assertTrue(page.inner_text("#vfMeta").startswith("7 players"))
                self.assertEqual(page.evaluate("document.activeElement.id"), "vfPosition")
                page.context.close()

    def test_phone_disclosure_and_details(self):
        for width in (390, 320):
            with self.subTest(width=width):
                page = self.open(state("ready"), width)
                summary = page.locator(".vf-cards > li").first.locator("summary")
                self.assertIn("All values", summary.inner_text())
                summary.focus()
                page.keyboard.press("Enter")
                self.assertTrue(page.locator(".vf-cards > li").first.locator("details").evaluate("d => d.open"))
                self.assert_layout(page, f"open disclosure@{width}")
                self.shot(page, f"disclosure-{width}")
                page.keyboard.press("Space")
                self.assertFalse(page.locator(".vf-cards > li").first.locator("details").evaluate("d => d.open"))
                details = page.locator('.vf-cards button[data-focus="open:card:syn-01"]')
                self.assertEqual(details.get_attribute("aria-label"), f"Details for {FIXTURE['rows'][0]['name']}")
                details.focus()
                page.keyboard.press("Enter")
                self.assertEqual(page.evaluate("window.__vfOpened"), ["syn-01"])
                ev = page.locator(".vf-evidence")
                ev.locator("summary").focus()
                page.keyboard.press("Enter")
                self.assertIn("Observed-trade estimates", ev.inner_text())
                page.context.close()

    # JEG-1299: the table row and the phone card both have a Details button. After a redraw, focus must go back to the one
    # the reader was on, which on a phone is the card's (the table is display: none at 719px and below).
    FOCUSED = """() => { const a = document.activeElement; const li = a && a.closest('.vf-cards > li, .vf-table tbody tr');
      return {tag: a ? a.tagName : null, label: a ? a.getAttribute('aria-label') : null, visible: !!(a && a.offsetParent !== null),
        where: li ? (li.matches('tr') ? 'table' : 'card') : null, key: li ? li.dataset.playerKey : null}; }"""

    def details_button(self, page, width, key):
        where = ".vf-table tbody tr" if width >= 720 else ".vf-cards > li"
        return page.locator(f'{where}[data-player-key="{key}"] button[aria-label^="Details for"]')

    def test_details_focus_survives_redraw(self):
        name = next(r["name"] for r in FIXTURE["rows"] if r["player_key"] == "syn-03")
        for width in (390, 320, 1280):
            with self.subTest(width=width):
                page = self.open(state("ready"), width)
                button = self.details_button(page, width, "syn-03")
                self.assertTrue(button.is_visible(), "the Details button for this width is the visible one")
                button.focus()
                page.evaluate("window.__vfHandle.update()")
                want = {"tag": "BUTTON", "label": f"Details for {name}", "visible": True,
                        "where": "table" if width >= 720 else "card", "key": "syn-03"}
                self.assertEqual(page.evaluate(self.FOCUSED), want, "after a redraw focus is back on the visible Details button")
                page.context.close()

    def test_details_drawer_return_after_redraw(self):
        name = next(r["name"] for r in FIXTURE["rows"] if r["player_key"] == "syn-02")
        for width in (390, 320, 1280):
            with self.subTest(width=width):
                page = self.open(state("ready"), width)
                self.details_button(page, width, "syn-02").focus()
                page.keyboard.press("Enter")
                self.assertEqual(page.evaluate("window.__vfOpened"), ["syn-02"])
                self.assertEqual(page.evaluate("document.activeElement.id"), "vfMockDrawerClose", "the drawer has focus")
                page.keyboard.press("Enter")
                want = {"tag": "BUTTON", "label": f"Details for {name}", "visible": True,
                        "where": "table" if width >= 720 else "card", "key": "syn-02"}
                self.assertEqual(page.evaluate(self.FOCUSED), want, "closing the drawer returns focus to the Details button")
                page.context.close()

    def test_details_focus_falls_back_to_title(self):
        # The focused player is filtered out by the redraw: nothing visible matches, so focus goes to the title.
        for width in (390, 1280):
            with self.subTest(width=width):
                page = self.open(state("ready"), width)
                self.details_button(page, width, "syn-03").focus()
                page.evaluate("() => { window.__VF_CTX.rows = window.__VF_CTX.rows.filter(r => r.player_key !== 'syn-03'); }")
                page.evaluate("window.__vfHandle.update()")
                self.assertEqual(page.locator('[data-player-key="syn-03"]').count(), 0)
                self.assertEqual(page.evaluate("document.activeElement.id"), "vfTitle", "nothing visible matches, so focus goes to the title")
                page.context.close()

    def test_dark_theme(self):
        for width in (1280, 390):
            with self.subTest(width=width):
                page = self.open(state("ready"), width, dark=True)
                self.assert_layout(page, f"dark@{width}")
                colors = page.evaluate("() => { const s = getComputedStyle(document.querySelector('.values-fieldnotes')); return [s.color, s.backgroundColor]; }")
                self.assertNotEqual(colors[0], colors[1])
                self.shot(page, f"dark-{width}")
                page.context.close()


if __name__ == "__main__":
    unittest.main()
