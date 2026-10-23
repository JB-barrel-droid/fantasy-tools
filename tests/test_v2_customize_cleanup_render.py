"""Customize values cleanup (JEG-850), rendered. One check per audit defect, each with a simulated broken build.

Audit: ~/code/fantasy-tools-selfhost-notes/customize-toggle-audit.md (8 defects). Decisions: Jeremy, JEG-850 comment 2026-10-22.

  D1  Done applies exactly what the dialog shows. A draft with no engine series (Trade charts "Select none", DDF Value
      alone) is refused with "Pick at least one source" and nothing changes.
  D2  The last usable DDF input is locked on; a held input never counts, so every usable input cannot be unticked.
  D3  "DDF Value: charts only" ignores the DDF blend selection (JEG-930, Jeremy 2026-10-23): a blend edit never blanks it
      and its dialog row never warns "No sources on in the DDF blend". (The old D3, "a version with no source on says so",
      could only be reached through that bug: the engine refuses an empty selection and locks the last usable input.)
  D4  The "On the chart" line says when the DDF blend is customized and when the chart legend hid a line; the dialog
      counter names a legend hide; Reset to default clears it.
  D5  No raw pipeline text ("held: fidelity: scrape_validity") anywhere in the dialog; a held input says "Paused this week".
  Structure: two tabs ("Chart lines", "DDF blend") keep one draft; the blend tab says it applies on every page and
  counts "Using N of M sources"; every row, tab and footer action is 44 px at 375; the phone footer stacks Done, Cancel,
  Reset; the VORP group is collapsed until one is selected.

Discrimination: every check also runs against a build with exactly one fault (the fault each check names) and must fail.
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

from tests import _render_env  # noqa: E402
from tests._holds import pin_holds_in_dist  # noqa: E402

V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
WIDGET_JS = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
MODEL_JS = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"
ACTIVE = "() => window.TradeValueV2.shown()"
RAW_TEXT = re.compile(r"scrape_validity|fidelity:|held:|validation|divergence:|_vorp|_adj_values", re.I)


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        # Held-proof fixture (tests/_holds.py): one held DDF input, so "a held input does not count" is exercised.
        # JEG-804 (#814): DDF Value is projections-only, so the pinned CBS (a trade chart) hold is not a DDF input;
        # Razzball is held here as the held DDF input.
        pin_holds_in_dist(dist, extra_held=("razzball",))
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        class Server(socketserver.ThreadingTCPServer):
            request_queue_size = 128

        with Server(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def _serve_body(body, route):
    route.fulfill(status=200, content_type="text/javascript", body=body)


def _open(browser, base, width, height=900, js=None, css=None, assets=None):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    for name, body in (assets or {}).items():   # engine files served with one fault, e.g. {"value-model.js": ...}
        page.route(f"**/assets/{name}*", functools.partial(_serve_body, body))
    if js is not None:
        page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=js))
    if css is not None:
        page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
    page.goto(base, wait_until="networkidle")
    page.wait_for_selector("#v2Table tbody tr")
    page.wait_for_timeout(600)
    return page


def _customize(page):
    page.click("#v2EditSources")
    page.wait_for_selector("#v2Popover .v2-panel-body")


def _tab(page, name):
    page.click(f"#v2Popover [data-tab='{name}']")


def _done(page):
    page.click("#v2Popover [data-apply='sources']")
    page.wait_for_timeout(300)


def _open_now(page):
    return page.evaluate("() => !document.getElementById('v2Popover').hidden")


def _untick_all_but_last(page):
    for _ in range(12):
        boxes = page.query_selector_all("#v2Popover [data-ddf-input]:checked:not(:disabled)")
        if not boxes:
            return
        boxes[0].click()


# ---------- the checks ----------

def check_d1_done_matches(page):
    errors = []
    before = page.evaluate(ACTIVE)
    _customize(page)
    page.click("#v2Popover [data-group='pub'] .v2-call")   # Trade charts: Select none -> DDF Value alone
    summary = page.text_content("#v2Popover [data-panel='lines'] .v2-psummary")
    _done(page)
    err = page.evaluate("() => { const e = document.querySelector('#v2Popover .v2-perror'); return e && !e.hidden ? e.textContent : ''; }")
    if not _open_now(page) or "Pick at least one source" not in err:
        errors.append(f"D1: Done on a draft with no engine series did not block with the message (open={_open_now(page)}, message={err!r}, dialog said {summary!r})")
    if page.evaluate(ACTIVE) != before:
        errors.append(f"D1: the page changed ({before} -> {page.evaluate(ACTIVE)}) although Done was blocked or said something else")
    return errors


def check_d2_last_input(page):
    errors = []
    _customize(page)
    _tab(page, "blend")
    held = page.evaluate("() => [...document.querySelectorAll('#v2Popover [data-ddf-input]')].filter(b => b.disabled).map(b => b.dataset.ddfInput)")
    if not held:
        return ["D2: the pinned fixture has no held DDF input, so the held-does-not-count rule is not exercised"]
    _untick_all_but_last(page)
    left = page.evaluate("""() => [...document.querySelectorAll('#v2Popover [data-ddf-input]')]
      .filter(b => b.checked).map(b => ({key: b.dataset.ddfInput, disabled: b.disabled}))""")
    if len(left) != 1 or not left[0]["disabled"]:
        errors.append(f"D2: after unticking every free input the usable ones left are {left}; the last one must be ticked and locked")
    counter = page.text_content("#v2Popover [data-panel='blend'] .v2-psummary")
    if not re.fullmatch(r"Using 1 of \d+ sources", counter.strip()):
        errors.append(f"D2: the blend counter reads {counter!r}, wanted 'Using 1 of N sources'")
    _done(page)
    series = page.evaluate("() => window.TradeValueCurveControls.getCompositeInputs().series")
    if len(series) != 1:
        errors.append(f"D2: the blend reads {series} after Done, wanted exactly one usable input")
    if page.evaluate("() => window.TradeValueCurveControls.getRankSource()") != "ddf_value":
        errors.append("D2: the ranking series moved off DDF Value")
    return errors


CHARTS_COUNT = """() => window.TradeValueCurveControls.getRows()
  .filter(r => (r.ddf_value_charts != null) || (r.values && r.values.ddf_value_charts != null)).length"""


def check_d3_charts_only_survives_blend_edit(page):
    """JEG-930 (Jeremy, 2026-10-23): 'DDF Value: charts only' ignores the DDF blend selection, so editing the blend
    never blanks it and its dialog row never says 'No sources on in the DDF blend'."""
    errors = []
    before = page.evaluate(CHARTS_COUNT)
    if not before:
        return ["D3: the pinned fixture gives 'DDF Value: charts only' no values before any edit, so the check proves nothing"]
    _customize(page)
    _tab(page, "blend")
    page.click("#v2Popover [data-ddf-input='espn']")   # a real edit: the selection is no longer the default
    _tab(page, "lines")
    page.click("#v2Popover [data-series='ddf_value_charts']")
    note = page.text_content("#v2Popover [data-series='ddf_value_charts'] >> xpath=ancestor::label")
    if "No sources on in the DDF blend" in note:
        errors.append(f"D3: the dialog row of 'DDF Value: charts only' warns about the DDF blend after a blend edit: {note!r}")
    _done(page)
    after = page.evaluate(CHARTS_COUNT)
    if after != before:
        errors.append(f"D3: 'DDF Value: charts only' has {after} values after a blend edit, wanted the {before} it had before")
    series = page.evaluate("() => window.TradeValueCurveControls.getCompositeInputs('ddf_value_charts').series")
    if not series:
        errors.append("D3: the engine lists no sources for 'DDF Value: charts only' after a blend edit")
    titles = page.evaluate("() => [...new Set([...document.querySelectorAll('#v2Table .missing')].map(m => m.title))]")
    if any("No sources are turned on" in t for t in titles):
        errors.append(f"D3: a blank cell says no source is turned on after a blend edit: {titles}")
    return errors


def check_d4_strip_and_reset(page):
    errors = []
    strip = lambda: page.text_content("#v2ShowingText")  # noqa: E731
    _customize(page)
    _tab(page, "blend")
    page.click("#v2Popover [data-ddf-input='espn']")   # JEG-804: the blend tab lists projections only (was FantasyCalc)
    _done(page)
    if "custom blend" not in strip():
        errors.append(f"D4: the 'On the chart' line does not say the DDF blend is customized: {strip()!r}")
    _customize(page)
    page.click("#v2Popover .v2-preset")
    _done(page)
    if "custom blend" in strip():
        errors.append(f"D4: Reset to default left 'custom blend' in the line: {strip()!r}")
    # A line hidden with the chart legend.
    page.click("#v2Legend .v2-legend-item[data-series='usatoday']")
    page.wait_for_timeout(200)
    has_col = lambda: page.evaluate("() => [...document.querySelectorAll('#v2Table thead th')].some(t => /USA Today/.test(t.textContent))")  # noqa: E731
    if has_col():
        errors.append("D4: the legend hide did not remove the USA Today column (test premise)")
    if "hidden with the chart legend" not in strip():
        errors.append(f"D4: the 'On the chart' line ignores a line the legend hid: {strip()!r}")
    _customize(page)
    summary = page.text_content("#v2Popover [data-panel='lines'] .v2-psummary")
    row = page.text_content("#v2Popover [data-series='usatoday'] >> xpath=ancestor::label")
    if "hidden with the chart legend" not in summary or "Hidden with the chart legend" not in row:
        errors.append(f"D4: the dialog does not name the hidden line (counter {summary!r}, row {row!r})")
    page.click("#v2Popover .v2-preset")
    _done(page)
    if not has_col() or "hidden" in strip():
        errors.append(f"D4: Reset to default + Done left the legend hide in place (column back: {has_col()}, line: {strip()!r})")
    return errors


def check_d5_plain_text(page, width):
    errors = []
    _customize(page)
    text = page.evaluate("() => document.getElementById('v2Popover').textContent")
    raw = RAW_TEXT.findall(text)
    if raw:
        errors.append(f"D5 ({width}): raw pipeline text in the dialog: {sorted(set(raw))}")
    _tab(page, "blend")
    rows = page.evaluate("""() => [...document.querySelectorAll('#v2Popover [data-ddf-input]')].filter(b => b.disabled)
      .map(b => b.closest('label').textContent)""")
    if not rows or not all("Paused this week" in r for r in rows):
        errors.append(f"D5 ({width}): a held input does not say 'Paused this week': {rows}")
    return errors


def check_structure(page, phone):
    errors = []
    _customize(page)
    tabs = page.evaluate("() => [...document.querySelectorAll('#v2Popover [role=tab]')].map(t => ({text: t.textContent, h: t.getBoundingClientRect().height}))")
    if [t["text"] for t in tabs] != ["Chart lines", "DDF blend"]:
        return [f"structure: tabs are {tabs}, wanted 'Chart lines' and 'DDF blend'"]
    if any(t["h"] < 44 for t in tabs):
        errors.append(f"structure: a tab is under 44 px: {tabs}")
    # The draft survives a tab switch.
    page.click("#v2Popover [data-series='usatoday']")
    _tab(page, "blend")
    body = page.text_content("#v2Popover [data-panel='blend']")
    if "applies on every page" not in body or not re.search(r"Using \d+ of \d+ sources", body):
        errors.append(f"structure: the blend tab lacks 'applies on every page' or 'Using N of M sources': {body[:160]!r}")
    rows = page.evaluate("() => [...document.querySelectorAll('#v2Popover [data-panel=blend] .v2-crow')].map(r => r.getBoundingClientRect().height)")
    if not rows or min(rows) < 43.5:
        errors.append(f"structure: a blend row is under 44 px: {rows}")
    _tab(page, "lines")
    if page.is_checked("#v2Popover [data-series='usatoday']"):
        errors.append("structure: a tab switch dropped the draft (USA Today is ticked again)")
    vorp = page.evaluate("() => document.querySelector('#v2Popover details[data-group=vorp]').open")
    if vorp:
        errors.append("structure: the value-above-waivers group is open although none is selected")
    if phone:
        foot = page.evaluate("""() => {
          const box = document.getElementById('v2Popover').getBoundingClientRect();
          const f = n => { const b = [...document.querySelectorAll('#v2Popover .v2-panel-foot button')].find(x => x.textContent.trim() === n).getBoundingClientRect();
            return {top: b.top, h: b.height, w: b.width}; };
          return {box: box.width, done: f('Done'), cancel: f('Cancel'), reset: f('Reset to default'), overflow: document.documentElement.scrollWidth > window.innerWidth};
        }""")
        for name in ("done", "cancel", "reset"):
            if foot[name]["h"] < 44 or foot[name]["w"] < foot["box"] * 0.85:
                errors.append(f"structure: phone footer {name} is {foot[name]['w']:.0f}x{foot[name]['h']:.0f}, wanted full width and 44 px")
        if not foot["done"]["top"] < foot["cancel"]["top"] < foot["reset"]["top"]:
            errors.append(f"structure: phone footer is not stacked Done, Cancel, Reset: {foot}")
        if foot["overflow"]:
            errors.append("structure: the phone page scrolls sideways")
    # Cancel discards on both tabs.
    before = page.evaluate(ACTIVE)
    page.click("#v2Popover .v2-panel-foot button:has-text('Cancel')")
    if page.evaluate(ACTIVE) != before or _open_now(page):
        errors.append("structure: Cancel did not close and keep the page as it was")
    # The VORP group opens when a VORP series is selected.
    _customize(page)
    vorp_key = page.evaluate("() => (document.querySelector('#v2Popover [data-group=vorp] [data-series]:not(:disabled)') || {dataset: {}}).dataset.series || ''")
    if vorp_key:
        page.click("#v2Popover details[data-group=vorp] summary")
        page.click(f"#v2Popover [data-series='{vorp_key}']")
        _done(page)
        _customize(page)
        if not page.evaluate("() => document.querySelector('#v2Popover details[data-group=vorp]').open"):
            errors.append("structure: the value-above-waivers group is collapsed although one is selected")
    if page.errors:
        errors.append(f"page errors: {page.errors[:2]}")
    return errors


class CustomizeCleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise _render_env.unavailable("playwright is not installed")
        exe = _render_env.chromium_executable()
        if exe is None and not _render_env.required():
            raise _render_env.unavailable("no browser")
        cls._stack = contextlib.ExitStack()
        cls.base = cls._stack.enter_context(_served())
        cls.pw = cls._stack.enter_context(sync_playwright())
        cls.browser = cls.pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        cls.js = V2_JS.read_text(encoding="utf-8")
        cls.css = V2_CSS.read_text(encoding="utf-8")
        cls.widget = WIDGET_JS.read_text(encoding="utf-8")
        cls.model = MODEL_JS.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._stack.close()

    def run_check(self, check, width=1440, js=None, css=None, *args, assets=None):
        page = _open(self.browser, self.base, width, 812 if width < 500 else 900, js, css, assets)
        try:
            return check(page, *args)
        except Exception as error:   # a control the check needs is missing: that is a failure, not a pass
            return [f"{check.__name__} raised {type(error).__name__}: {str(error).splitlines()[0][:160]}"]
        finally:
            page.close()

    def mutate(self, old, new, text=None):
        source = text if text is not None else self.js
        self.assertEqual(source.count(old), 1, f"stale mutation anchor: {old[:60]!r}")
        return source.replace(old, new)

    def assertCaught(self, check, label, *, js=None, css=None, width=1440, args=(), assets=None):
        self.assertTrue(self.run_check(check, width, js, css, *args, assets=assets), f"the guard did not catch: {label}")

    # ---- D1 ----
    def test_d1_done_matches_the_dialog(self):
        self.assertEqual(self.run_check(check_d1_done_matches), [])

    def test_d1_guard_catches_a_stray_series(self):
        js = self.mutate("if (![...draft].some(key => !isDdfKey(key) && view.infoByKey[key] && view.infoByKey[key].available)) {",
                         "if (false) {")
        self.assertCaught(check_d1_done_matches, "Done applies a draft with no engine series", js=js)

    # ---- D2 ----
    def test_d2_last_usable_input_is_locked(self):
        self.assertEqual(self.run_check(check_d2_last_input), [])

    def test_d2_guard_catches_the_old_lock(self):
        js = self.mutate("input.disabled = Boolean(out) || last;",
                         "input.disabled = Boolean(out) || (inputsDraft.size === 1 && inputsDraft.has(key));")
        self.assertCaught(check_d2_last_input, "the lock counts held inputs", js=js)

    # ---- D3 ----
    def test_d3_charts_only_survives_a_blend_edit(self):
        self.assertEqual(self.run_check(check_d3_charts_only_survives_blend_edit), [])

    def test_d3_guard_catches_the_blank_charts_variant(self):
        # The engine's per-version pool (curve-widget.js) honouring the blend again.
        widget = self.mutate("(ignoresBlend || !compositeInputs || compositeInputs.includes(key))",
                             "(!compositeInputs || compositeInputs.includes(key))", self.widget)
        self.assertCaught(check_d3_charts_only_survives_blend_edit, "engine inputs emptied by the blend", assets={"curve-widget.js": widget})
        # The value pipeline (value-model.js) filtering the charts by the selection again.
        model = self.mutate('version === "charts" || !selection || selection.indexOf(k) !== -1',
                            "!selection || selection.indexOf(k) !== -1", self.model)
        self.assertCaught(check_d3_charts_only_survives_blend_edit, "values blanked by the blend", assets={"value-model.js": model})
        # The dialog row counting the blend draft for the charts variant again.
        js = self.mutate('versionKey === "ddf_value_charts" ? chartsUsable() : ', "")
        self.assertCaught(check_d3_charts_only_survives_blend_edit, "row warns 'No sources on in the DDF blend'", js=js)

    # ---- D4 ----
    def test_d4_strip_counter_and_reset(self):
        self.assertEqual(self.run_check(check_d4_strip_and_reset), [])

    def test_d4_guard_catches_each_gap(self):
        js = self.mutate('(c.g.id === "ddf" && customBlend ? " (custom blend)" : "")', '""')
        self.assertCaught(check_d4_strip_and_reset, "the line ignores a customized blend", js=js)
        js = self.mutate('      + (legendHidden ? ` · ${legendHidden} hidden with the chart legend` : "")', "")
        self.assertCaught(check_d4_strip_and_reset, "the line ignores a legend hide", js=js)
        js = self.mutate("state.hiddenSeries.clear();   // JEG-907: the draft is the whole state; a legend hide never survives Done", "")
        self.assertCaught(check_d4_strip_and_reset, "Reset keeps a legend hide", js=js)

    # ---- D5 ----
    def test_d5_no_raw_text_desktop_and_phone(self):
        for width in (1440, 375):
            self.assertEqual(self.run_check(check_d5_plain_text, width, None, None, width), [], width)

    def test_d5_guard_catches_raw_text(self):
        js = self.mutate("function plainOutReason(reason) {\n    const text = String(reason || \"\");",
                         "function plainOutReason(reason) {\n    return String(reason || \"held: fidelity: scrape_validity\");\n    const text = String(reason || \"\");")
        self.assertCaught(check_d5_plain_text, "raw held text", js=js, args=(1440,))

    # ---- structure ----
    def test_structure_desktop_and_phone(self):
        self.assertEqual(self.run_check(check_structure, 1440, None, None, False), [])
        self.assertEqual(self.run_check(check_structure, 375, None, None, True), [])

    def test_structure_guard_catches_each_fault(self):
        js = self.mutate("if (hasBlend) body.appendChild(tabBar);", "")
        self.assertCaught(check_structure, "no tabs", js=js, args=(False,))
        js = self.mutate("if (advanced && items.some(item => draft.has(item.key))) section.open = true;", "if (advanced) section.open = true;")
        self.assertCaught(check_structure, "value-above-waivers always open", js=js, args=(False,))
        css = self.mutate(".v2-popover .v2-cust-foot { flex-direction: column; align-items: stretch; }", "", self.css)
        self.assertCaught(check_structure, "phone footer not stacked", css=css, width=375, args=(True,))
        css = self.mutate(".v2-crow { display: flex; align-items: center; gap: 10px; min-height: 44px;",
                          ".v2-crow { display: flex; align-items: center; gap: 10px; min-height: 40px;", self.css)
        self.assertCaught(check_structure, "rows under 44 px", css=css, args=(False,))


if __name__ == "__main__":
    unittest.main()
