"""v2 Risers & fallers and Δ prior week, rendered: every number is the engine's.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless. For
every series the picker offers, the test asks the engine itself
(TradeValueCurveControls.getPriorWeek(series), getRows()) and checks:

  * a series the engine cannot price a prior week for is listed disabled;
  * every row of the Risers and Fallers cards (frames 05 / 06): "before →
    after" = the engine's prior-week and current values for that player, Δ =
    their difference with the right sign; risers have Δ > 0 largest first,
    fallers Δ < 0 most negative first; no player without a prior value is listed;
  * an earlier week pair (frame 19 #05, "Week N−1 → Week N"): both weeks are the
    engine's getWeekValues recompute at the current league;
  * Player values with Δ prior week on and an Indexed chart selected: every
    Δ cell equals current − prior for that exact series, or "Δ —" when the
    engine has no prior value (never a number);
  * desktop 1440 side-by-side cards and mobile 390 stacked cards; no page
    errors; no 390 overflow.
  * JEG-465: the tab opens on DDF Value (when the engine has its prior week),
    and DDF Value's movers are the engine's currentValues - values;
  * JEG-466: the shared series picker (Risers' series, Player values' Rank by)
    groups its options under the JEG-474 group names in vocabulary order, DDF
    Value first; a series the engine has no prior week for (one is forced
    unavailable through getPriorWeek) is disabled with its reason in the label.

Discrimination: test_guard_fails_on_broken_builds serves movers.js with the
sign flipped and with a missing prior read as 0, and v2.js with the picked
series ignored and with an earlier week pair keeping this week's values, and
requires the checks to fail on each; and v2.js with the picker's options
outside their groups and with Risers opening on another series.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
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


MOVERS_JS = ROOT / "app" / "v2" / "movers.js"
V2_JS = ROOT / "app" / "v2" / "v2.js"

READ = """async ([series, week]) => {
  const C = window.TradeValueCurveControls;
  const prior = await C.getPriorWeek(series);
  const served = prior.available && (week === null || week === prior.currentWeek);
  const before = served ? prior : await C.getWeekValues(series, week - 1);
  const after = served ? null : await C.getWeekValues(series, week);
  // DDF Value: the delta is currentValues - values over the same inputs (JEG-465), so "now" is currentValues.
  const now = served ? (prior.currentValues || Object.fromEntries(C.getRows().map(r => [String(r.player_key), r.values[series]])))
    : (after.values || {});
  const text = node => node ? node.textContent : null;
  const read = id => [...document.querySelectorAll(`#${id} li`)].map(li => ({key: li.dataset.playerKey,
    now: text(li.querySelector('[data-col="now"]')), before: text(li.querySelector('[data-col="before"]')),
    delta: text(li.querySelector('[data-col="delta"]'))}));
  const options = Object.fromEntries([...document.querySelectorAll('#v2RSeries option')].map(o => [o.value, !o.disabled]));
  return {series, week, picked: document.getElementById('v2RSeries').value,
    pickedWeek: document.getElementById('v2RWeeks').value,
    prior: {available: prior.available && before.available !== false, values: before.values,
      priorWeek: served ? prior.priorWeek : week - 1, currentWeek: served ? prior.currentWeek : week},
    now, rise: read('v2RRise'), fall: read('v2RFall'), options,
    weeks: [...document.querySelectorAll('#v2RWeeks option')].map(o => Number(o.value)),
    overflow: document.documentElement.scrollWidth - innerWidth};
}"""


def fmt(v):
    return f"{v:.1f}"


# JEG-474 group vocabulary, in order. Written out here, not read from v2.js.
GROUPS = ["DDF Value", "Projections", "Trade charts (adjusted)", "Trade charts (as published)",
          "Value above waivers (Advanced)"]
DDF = "ddf_value"
FORCED_OFF = "usatoday"   # getPriorWeek is patched to say this series has no prior week
FORCED_REASON = "test: no saved week before this one"


def expected_group(key):
    if key == DDF:
        return "DDF Value"
    if key.endswith("_vorp"):
        return "Value above waivers (Advanced)"
    if key.endswith("_adjusted"):
        return "Trade charts (adjusted)"
    if key in ("espn", "cbsros", "razzball"):
        return "Projections"
    return "Trade charts (as published)"


# The shared picker (JEG-466) as rendered, plus the engine's stale flags for the prior-week badge.
PICKER_READ = """sel => {
  const info = Object.fromEntries(window.TradeValueCurveControls.getSourceInfo({includeComposite: true}).map(i => [i.key, {stale: Boolean(i.stale), week: i.week}]));
  const select = document.querySelector(sel);
  return {value: select.value, height: select.getBoundingClientRect().height,
    options: [...select.querySelectorAll('option')].map(o => ({key: o.value, parent: o.parentElement.tagName,
      group: o.parentElement.tagName === 'OPTGROUP' ? o.parentElement.label : null, disabled: o.disabled, text: o.textContent,
      stale: (info[o.value] || {}).stale || false, week: (info[o.value] || {}).week ?? null}))};
}"""


def check_picker(snap, name, disabled=None) -> list[str]:
    """Groups and order follow the vocabulary, DDF Value first; disabled options carry a reason.

    disabled: {key: reason substring} the picker must show disabled (None: do not check which)."""
    errors = []
    opts = snap["options"]
    if not opts:
        return [f"{name}: no options"]
    for o in opts:
        if o["parent"] != "OPTGROUP" or o["group"] != expected_group(o["key"]):
            errors.append(f"{name}: {o['key']} sits in {o['parent']} {o['group']!r}, want group {expected_group(o['key'])!r}")
        if o["stale"] != ("· Wk" in o["text"] or "· Earlier week" in o["text"]):
            errors.append(f"{name}: {o['key']} prior-week badge {o['text']!r} but engine stale={o['stale']}")
        if o["disabled"] and "—" not in o["text"]:
            errors.append(f"{name}: {o['key']} disabled without a reason in its label: {o['text']!r}")
    order = [GROUPS.index(o["group"]) if o["group"] in GROUPS else -1 for o in opts]
    if order != sorted(order):
        errors.append(f"{name}: groups out of vocabulary order {[o['group'] for o in opts]}")
    keys = [o["key"] for o in opts]
    if DDF in keys and keys[0] != DDF:
        errors.append(f"{name}: DDF Value is not first: {keys}")
    if disabled is not None:
        got = {o["key"]: o["text"] for o in opts if o["disabled"]}
        if set(got) != set(disabled):
            errors.append(f"{name}: disabled {sorted(got)} != {sorted(disabled)}")
        for key, reason in disabled.items():
            if key in got and reason not in got[key]:
                errors.append(f"{name}: {key} label {got[key]!r} lacks the reason {reason!r}")
    if snap["height"] < 44:
        errors.append(f"{name}: picker is {snap['height']}px tall, under the 44 px target")
    return errors


def fmt_gap(v):
    t = f"{abs(v):.1f}"
    return "0.0" if t == "0.0" else ("+" if v > 0 else "−") + t


def finite(v):
    return isinstance(v, (int, float)) and v == v


def check_series(snap, side) -> list[str]:
    errors = []
    s = snap["series"]
    if snap["picked"] != s:
        return [f"{s}: picker shows {snap['picked']!r}"]
    prior = snap["prior"]
    if snap["week"] is None and snap["options"].get(s) != prior["available"]:
        errors.append(f"{s}: picker enabled={snap['options'].get(s)} but engine available={prior['available']}")
    if snap["week"] is not None and snap["pickedWeek"] != str(snap["week"]):
        return [f"{s}: week picker shows {snap['pickedWeek']!r}, wanted {snap['week']}"]
    items = snap[side]
    if not prior["available"]:
        if items:
            errors.append(f"{s}: engine has no prior week but {len(items)} rows are listed")
        return errors
    if not items:
        errors.append(f"{s} {side}: no rows rendered")
    deltas = []
    for item in items:
        cur, before = snap["now"].get(item["key"]), (prior["values"] or {}).get(item["key"])
        if not finite(cur) or not finite(before):
            errors.append(f"{s}/{item['key']}: listed without an exact pair (now {cur!r}, prior {before!r})")
            continue
        d = cur - before
        if not item["now"].endswith(fmt(cur)) or not item["before"].endswith(fmt(before)) or fmt_gap(d) not in item["delta"]:
            errors.append(f"{s}/{item['key']}: shows {item}, engine now {fmt(cur)} prior {fmt(before)} Δ {fmt_gap(d)}")
        if not item["before"] or not item["now"]:
            errors.append(f"{s}/{item['key']}: before → after not shown")
        if (side == "rise") != (d > 0) or ("▲" in item["delta"]) != (d > 0):
            errors.append(f"{s}/{item['key']}: Δ {d:+.2f} listed as {side} with {item['delta']!r}")
        deltas.append(d)
    if deltas != sorted(deltas, reverse=(side == "rise")):
        errors.append(f"{s} {side}: not ordered by Δ")
    return errors


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


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
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def run_checks(movers_js=None, v2_js=None, full=True) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 1000), (390, 844)) if full else ((1440, 1000),):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if movers_js is not None:
                    page.route("**/v2/movers.js*", functools.partial(_serve, movers_js))
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=40000)
                # One series with no prior week, so the disabled-with-reason path is exercised.
                page.evaluate("""([off, reason]) => { const C = window.TradeValueCurveControls; const real = C.getPriorWeek;
                  C.getPriorWeek = (key, week) => key === off ? Promise.resolve({source: key, available: false, reason}) : real(key, week); }""",
                              [FORCED_OFF, FORCED_REASON])
                page.evaluate("() => { location.hash = '#risers-fallers'; }")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.risers()", timeout=40000)
                page.wait_for_function("() => !/Recomputing|Reading/.test(document.getElementById('v2RMeta').textContent)", timeout=30000)
                options = page.evaluate("() => [...document.querySelectorAll('#v2RSeries option')].map(o => o.value)")
                if not options:
                    errors.append(f"{width}px: no series offered")
                # JEG-465: the tab opens on DDF Value whenever the engine has its prior week.
                ddf_ready = page.evaluate("async () => (await window.TradeValueCurveControls.getPriorWeek('ddf_value')).available")
                opened = page.evaluate("() => document.getElementById('v2RSeries').value")
                if not ddf_ready:
                    errors.append(f"[{width}px] the engine has no DDF Value prior week; the default went unchecked")
                elif opened != DDF:
                    errors.append(f"[{width}px] Risers & fallers opened on {opened!r}, not DDF Value")
                if DDF not in options:
                    errors.append(f"[{width}px] DDF Value is not offered")
                errors += [f"[{width}px] {e}" for e in check_picker(page.evaluate(PICKER_READ, "#v2RSeries"), "Risers series",
                                                                    disabled={FORCED_OFF: FORCED_REASON})]
                series_list = options if width == 1440 else [DDF]
                checked_pair = False
                for series in series_list:
                    enabled = page.evaluate(f"() => !document.querySelector('#v2RSeries option[value=\"{series}\"]').disabled")
                    available = page.evaluate("async s => (await window.TradeValueCurveControls.getPriorWeek(s)).available", series)
                    if enabled != available:
                        errors.append(f"[{width}px] {series}: picker enabled={enabled} but engine available={available}")
                    if not enabled:
                        continue
                    page.select_option("#v2RSeries", series)
                    page.wait_for_function("() => !/Recomputing|Reading/.test(document.getElementById('v2RMeta').textContent)", timeout=30000)
                    snap = page.evaluate(READ, [series, None])
                    for side in ("rise", "fall"):
                        errors += [f"[{width}px] {e}" for e in check_series(snap, side)]
                    if width <= 390 and snap["overflow"] > 0:
                        errors.append(f"[{width}px] horizontal overflow {snap['overflow']}px")
                    # Frame 19 #05: an earlier week pair, priced by the engine for both weeks.
                    earlier = [w for w in snap["weeks"] if w != snap["prior"]["currentWeek"]]
                    if width == 1440 and earlier and not checked_pair:
                        checked_pair = True
                        page.select_option("#v2RWeeks", str(earlier[0]))
                        page.wait_for_function("() => !/Recomputing|Reading/.test(document.getElementById('v2RMeta').textContent)", timeout=30000)
                        pair = page.evaluate(READ, [series, earlier[0]])
                        for side in ("rise", "fall"):
                            errors += [f"[{width}px] week {earlier[0]} {e}" for e in check_series(pair, side)]
                        page.select_option("#v2RWeeks", str(snap["prior"]["currentWeek"]))
                if width == 1440 and not checked_pair:
                    errors.append("no series offered an earlier week pair; the N−1 → N picker went unchecked")
                if width == 1440:
                    # Player values, Δ on, with an Indexed chart plotted.
                    page.evaluate("() => { location.hash = '#player-values'; }")
                    page.wait_for_function("() => !document.getElementById('v2Main').hidden")
                    errors += [f"[{width}px] {e}" for e in check_picker(page.evaluate(PICKER_READ, "#v2RankBy"), "Rank by")]
                    page.evaluate("""() => { const box = document.querySelector('#legacyEngine #sourceToggles input[data-source="fantasycalc"]');
                      if (box && !box.checked && !box.disabled) box.click(); }""")
                    page.click("#v2DeltaBtn")
                    page.wait_for_function("() => ![...document.querySelectorAll('#v2Table .delta')].some(d => d.textContent === 'Δ …')", timeout=30000)
                    cells = page.evaluate("""async () => { const C = window.TradeValueCurveControls; const rows = Object.fromEntries(C.getRows().map(r => [String(r.player_key), r.values]));
                      const priors = {}; const out = [];
                      for (const d of document.querySelectorAll('#v2Table .delta[data-source]')) {
                        const s = d.dataset.source; if (!(s in priors)) priors[s] = await C.getPriorWeek(s);
                        const idx = [...d.closest('tbody').children].indexOf(d.closest('tr'));
                        const key = String(window.TradeValueV2.view().rows[idx].player_key);
                        const p = priors[s]; out.push({s, key, text: d.textContent, now: rows[key][s], before: p.available ? (p.values[key] ?? null) : null});
                      } return out; }""")
                    fc = [c for c in cells if c["s"] == "fantasycalc"]
                    if not fc:
                        errors.append("Player values: no FantasyCalc · Index Δ cells")
                    for c in cells:
                        want = f"Δ {fmt_gap(c['now'] - c['before'])}" if finite(c["now"]) and finite(c["before"]) else "Δ —"
                        if c["text"] != want:
                            errors.append(f"Player values Δ {c['s']}/{c['key']}: {c['text']!r} != {want!r}")
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class RisersRenderTest(unittest.TestCase):
    def test_rendered_numbers_match_engine(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        movers = MOVERS_JS.read_text(encoding="utf-8")
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "sign flipped": {"movers_js": movers.replace("return {delta: current - before, before, current, reason: null};",
                                                         "return {delta: before - current, before, current, reason: null};", 1)},
            "missing prior read as zero": {"movers_js": movers.replace(
                "const before = prior.values ? prior.values[playerKey] : undefined;",
                "const before = (prior.values ? prior.values[playerKey] : undefined) ?? 0;", 1)},
            "picked series ignored": {"v2_js": v2.replace(
                "risersView = M.buildMovers(rows, R.series, prior);",
                "risersView = M.buildMovers(rows, R.series, priorCache.get('fantasycalc'));", 1)},
            "earlier pair keeps this week's values": {"v2_js": v2.replace(
                "source = source.map(row => ({...row, values: {...row.values, [R.series]: later[String(row.player_key)] ?? null}}));",
                "source = source.slice();", 1)},
            "picker ungrouped": {"v2_js": v2.replace(
                "      select.appendChild(optgroup);\n", "      select.append(...optgroup.children);\n", 1)},
            "Risers default not DDF": {"v2_js": v2.replace(
                "const RISERS_DEFAULT = DDF_KEY;", "const RISERS_DEFAULT = \"fantasycalc\";", 1)},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = next(iter(kwargs.values()))
                self.assertNotIn(body, (movers, v2), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(full=False, **kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
