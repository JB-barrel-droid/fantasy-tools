"""v2 Trade targets: every Our value x Compare against combination renders (JEG-868, JEG-869).

JEG-868 (live, 2026-10-22): with a trade chart as Our value and Compare against left on
"All trade charts", renderTargetTable read `p.cells[chart].value` for our own chart, which
the engine had (rightly) left out of the compared set, threw, and left the previous
selection's lists on the page. Jeremy's rule: any source as Our value against any other;
"All" with a chart as Our value means the other charts, and the page never keeps stale lists.
JEG-869: with one chart compared, the heading and sub-line say which chart, not "the charts".

Loads /v2/#trade-targets headless (1440 x 900 and 390 x 844) and, for every enabled
Our value option x every enabled Compare against option, checks:
  * no uncaught page error;
  * the engine state matches the selection (ours, the compared set excludes our own chart,
    a single pick compares that chart only, "all" compares every other enabled chart);
  * the rendered lists match that state, never the previous selection (Our value header,
    chart columns, row counts in the sub-line);
  * the copy matches the mode: "All other trade charts" when Our value is a chart; a
    single chart is named in the heading and "Against one chart: <name>" in the sub-line;
    no empty-state or sub-line copy claims 2 or more charts when one is compared;
  * no list shows the "could not be built" error state.

Discrimination (test_guard_fails_on_broken_builds): the JEG-868 bug reintroduced (our own
chart kept in `used`) must be caught; with the error guard also disabled the stale lists
must be caught as stale; the JEG-869 heading reverted and the "All other" label dropped
must each be caught.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import _render_env  # noqa: E402
from tests.test_v2_targets_render import V2_JS, _built_dist, _chromium_executable  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


VIEWPORTS = ((1440, 900), (390, 844))
CHART_NAMES = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS Sports"}

OPTIONS = """() => ({
  ours: [...document.querySelectorAll('#v2TOurs option')].filter(o => !o.disabled).map(o => o.value),
  charts: [...document.querySelectorAll('#v2TChart option')].filter(o => !o.disabled).map(o => o.value),
  chartKeys: window.TradeValueTargets.CHART_KEYS, short: window.TradeValueTargets.OUR_SHORT})"""

STATE = """() => {
  const t = window.TradeValueV2.targets();
  const q = s => document.querySelector(s);
  const side = (table, cards, meta, empty, title) => ({
    rows: document.querySelectorAll(`#${table} tbody tr[data-player-key]`).length,
    cards: document.querySelectorAll(`#${cards} li`).length,
    oursHead: q(`#${table} th.is-rank .th-sub`)?.textContent ?? null,
    cols: [...document.querySelectorAll(`#${table} th[data-chart]`)].map(th => th.dataset.chart),
    cellCols: [...new Set([...document.querySelectorAll(`#${table} tbody tr[data-player-key] td[data-chart], #${cards} li [data-chart]`)].map(n => n.dataset.chart))],
    meta: q('#' + meta).textContent.trim(), empty: q('#' + empty).hidden ? null : q('#' + empty).textContent.trim(),
    title: q('#' + title).textContent.trim()});
  return {ours: t.ours, used: t.used, single: t.singleChart, blocked: t.blocked, counts: {sell: t.sell.length, buy: t.buy.length},
    pick: q('#v2TChart').value, oursPick: q('#v2TOurs').value,
    allOpt: q('#v2TChart option[value=all]').textContent,
    sell: side('v2TTable', 'v2TCards', 'v2TSellMeta', 'v2TSellEmpty', 'v2TSellTitle'),
    buy: side('v2TBuyTable', 'v2TBuyCards', 'v2TBuyMeta', 'v2TBuyEmpty', 'v2TBuyTitle'),
    foot: q('#v2TFootnote').textContent};
}"""


def check_combo(state, ours, pick, opts, width, previous) -> list[str]:
    """Every rule one Our value x Compare against selection must satisfy; `previous` is the last render's state."""
    errors = []
    chart_keys = opts["chartKeys"]
    ours_is_chart = ours in chart_keys
    if state["ours"] != ours or state["oursPick"] != ours:
        errors.append(f"Our value is {state['ours']!r}/{state['oursPick']!r}, selected {ours!r}")
    if state["pick"] != pick:
        errors.append(f"Compare against is {state['pick']!r}, selected {pick!r}")
    enabled_charts = [k for k in opts["charts"] if k != "all"]
    expected_used = [k for k in chart_keys if k in enabled_charts and k != ours] if pick == "all" else [pick]
    if state["used"] != expected_used:
        errors.append(f"compared set {state['used']} for ours={ours} pick={pick}, expected {expected_used}")
    if ours in state["used"]:
        errors.append(f"our own chart {ours} is in the compared set {state['used']}")
    single = expected_used[0] if len(expected_used) == 1 else None
    if state["single"] != single:
        errors.append(f"singleChart {state['single']!r}, expected {single!r}")
    want_all = "All other trade charts" if ours_is_chart else "All trade charts"
    if state["allOpt"] != want_all:
        errors.append(f"'all' option reads {state['allOpt']!r} with ours={ours}, expected {want_all!r}")
    stale_marker = f"stale: previous selection {previous['ours']}/{previous['pick']} still rendered" if previous else "stale"
    for side in ("sell", "buy"):
        s = state[side]
        count = state["counts"][side]
        if "could not be built" in (s["empty"] or ""):
            errors.append(f"{side}: error state shown: {s['empty']!r}")
        shown = s["rows"] if width >= 768 else s["cards"]
        if shown != min(count, 5):
            errors.append(f"{side}: {shown} rendered, engine list has {count} ({stale_marker})")
        if count and width >= 768:
            if s["oursHead"] != opts["short"][ours]:
                errors.append(f"{side}: Our value header {s['oursHead']!r}, expected {opts['short'][ours]!r} ({stale_marker})")
            if s["cols"] != state["used"]:
                errors.append(f"{side}: chart columns {s['cols']} but compared set {state['used']} ({stale_marker})")
        if count and sorted(s["cellCols"]) != sorted(state["used"]):
            errors.append(f"{side}: rendered chart cells {s['cellCols']} but compared set {state['used']} ({stale_marker})")
        # JEG-977 (57f1c1b2) dropped the "N of M players" vanity count: the sub-line now leads with "N players · ".
        if not state["blocked"] and not s["meta"].startswith(f"{count} players · "):
            errors.append(f"{side}: sub-line {s['meta']!r} does not lead with {count} ({stale_marker})")
        if single:
            name = CHART_NAMES[single]
            want_title = f"Sell: {name} pays more than we would" if side == "sell" else f"Buy: {name} pays less than we would"
            if want_title not in s["title"]:
                errors.append(f"{side}: heading {s['title']!r}, expected {want_title!r} (JEG-869)")
            if not state["blocked"] and f"Against one chart: {name}." not in s["meta"]:
                errors.append(f"{side}: sub-line {s['meta']!r} lacks 'Against one chart: {name}.' (JEG-869)")
            for text in (s["meta"], s["empty"] or ""):
                if "2 or more" in text or "the charts" in text or "most charts" in text:
                    errors.append(f"{side}: single-chart copy still speaks of several charts: {text!r} (JEG-869)")
            if f"Against one chart: {name}." not in state["foot"]:
                errors.append(f"footnote lacks 'Against one chart: {name}.' (JEG-869)")
        else:
            word = "the other charts" if ours_is_chart else "the charts"
            want_title = f"Sell: {word} pay more than we would" if side == "sell" else f"Buy: {word} pay less than we would"
            if want_title not in s["title"]:
                errors.append(f"{side}: heading {s['title']!r}, expected {want_title!r}")
    return errors


def collect(v2_js=None, viewports=VIEWPORTS) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    combos = 0
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                tag = f"[{width}x{height}] "
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=v2_js))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=40000)
                opts = page.evaluate(OPTIONS)
                if len([k for k in opts["charts"] if k != "all"]) < 2 or not any(k in opts["ours"] for k in opts["chartKeys"]):
                    errors.append(tag + f"fixture has too few enabled charts to cover the combinations: {opts}")
                previous = None
                for ours in opts["ours"]:
                    seen = len(page_errors)
                    page.select_option("#v2TOurs", ours)
                    page.wait_for_timeout(150)
                    combos += 1
                    # The render right after the Our value change is itself a combination: the page keeps the
                    # previous Compare pick, or falls back to "all" when that pick was this very chart.
                    state = page.evaluate(STATE)
                    label = tag + f"ours={ours} (just picked, compare={state['pick']}): "
                    if len(page_errors) > seen:
                        errors.append(label + f"page error: {page_errors[seen:]}")
                    if state["pick"] == ours:
                        errors.append(label + "Compare against stayed on our own chart")
                    errors += [label + e for e in check_combo(state, ours, state["pick"], page.evaluate(OPTIONS), width, previous)]
                    # The options change with Our value (our own chart is disabled in Compare against).
                    picks = page.evaluate("() => [...document.querySelectorAll('#v2TChart option')].filter(o => !o.disabled).map(o => o.value)")
                    if ours in picks:
                        errors.append(tag + f"ours={ours}: Compare against still offers our own chart")
                    for pick in picks:
                        seen = len(page_errors)
                        page.select_option("#v2TChart", pick)
                        page.wait_for_timeout(150)
                        combos += 1
                        label = tag + f"ours={ours} compare={pick}: "
                        if len(page_errors) > seen:
                            errors.append(label + f"page error: {page_errors[seen:]}")
                        state = page.evaluate(STATE)
                        errors += [label + e for e in check_combo(state, ours, pick, opts, width, previous)]
                        previous = {"ours": ours, "pick": pick}
                page.close()
        finally:
            browser.close()
    if combos < 8:
        errors.append(f"only {combos} combinations were exercised")
    return errors


class TradeTargetsCombinationsRenderTest(unittest.TestCase):
    def test_every_combination_renders(self):
        self.maxDiff = None
        self.assertEqual(collect(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8").replace("\r\n", "\n")
        desk = ((1440, 900),)
        bug = ("    const used = compared.used.filter(key => key !== ownChart);\n", "    const used = compared.used;\n")
        no_guard = ("      } catch (error) {\n        $(ids.table).replaceChildren();", "      } catch (error) {\n        throw error;")
        broken = {
            # The JEG-868 bug: our own chart kept in the compared set, so the render reads a cell the engine never made.
            "own chart kept in compared set (JEG-868 bug returns)": ((bug,), "page error"),
            # Same bug with the error guard disabled: the lists stay on the previous selection and must read as stale.
            "stale lists kept after an error": ((bug, no_guard), "stale"),
            # JEG-869: the single-chart heading reverted to the plural copy.
            "single-chart heading not named (JEG-869)": (((
                "        ? (side === \"sell\" ? ` Sell: ${scName} pays more than we would` : ` Buy: ${scName} pays less than we would`)\n",
                "        ? (side === \"sell\" ? ` Sell: the charts pay more than we would` : ` Buy: the charts pay less than we would`)\n"),), "JEG-869"),
            "'Against one chart' dropped from the sub-line (JEG-869)": (((
                "        ? (side === \"sell\" ? `Against one chart: ${scName}. ${scName} pays more than our value.` : `Against one chart: ${scName}. ${scName} ranks them lower than we do.`)\n",
                "        ? (side === \"sell\" ? `${scName} pays more than our value.` : `${scName} ranks them lower than we do.`)\n"),), "JEG-869"),
            "'All other trade charts' label dropped (JEG-868)": (((
                '    all.textContent = TT.CHART_KEYS.includes(targetsView.ours) ? "All other trade charts" : "All trade charts";\n',
                '    all.textContent = "All trade charts";\n'),), "'all' option reads"),
            "self-compare pick not resolved before the lists are built (JEG-868)": (((
                '    if (T.chart !== "all" && T.chart === ourKey) T.chart = "all";\n', ""),), "compared set"),
        }
        for name, (pairs, must_mention) in broken.items():
            with self.subTest(mutation=name):
                source = v2
                for old, new in pairs:
                    self.assertEqual(source.count(old), 1, f"mutation anchor for {name!r} is stale: {old!r}")
                    source = source.replace(old, new, 1)
                found = collect(v2_js=source, viewports=desk)
                self.assertNotEqual(found, [], f"render checks did not catch: {name}")
                self.assertTrue(any(must_mention in e for e in found), f"{name}: caught, but not as {must_mention!r}: {found[:3]}")


if __name__ == "__main__":
    unittest.main()
