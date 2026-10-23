"""The three DDF Value versions in the v2 front end (JEG-542, front end of JEG-497, contract GL-09), rendered.

Run against the built dist/ in headless Chromium. Checks:

  * defaults: Customize lists "DDF Value", "DDF Value: charts only" and
    "DDF Value: projections only" (JEG-850 names); only the blended one is ticked and shown;
  * the DDF blend tab lists the inputs once (JEG-850: the per-version copies are gone): the
    projections under "Projections" and, since JEG-804, no trade charts;
  * ticking the other two and pressing Done shows them, and every table cell
    equals the engine row's values[<version key>] to one decimal;
  * the grouped picker (Rank by, Risers & fallers, Compare's Player values
    shown) offers all three, and Rank by a version makes the engine rank by it;
  * the selection (shown versions and the ranking) survives a reload
    (ddf.v2.selection);
  * a one-source version shows "◐ 1 source" on its own column only.

A deliberately broken build (the versions on by default; Rank by without the
versions) must fail these checks.
"""
from __future__ import annotations

import functools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_ddf_render import _built_dist, _serve, ready  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
KEYS = ["ddf_value", "ddf_value_charts", "ddf_value_projections"]
NAMES = {"ddf_value": "DDF Value", "ddf_value_charts": "DDF Value: charts only",
         "ddf_value_projections": "DDF Value: projections only"}
FAMILY = {"ddf_value_charts": {"fantasycalc", "usatoday", "fantasypros", "cbs"},
          "ddf_value_projections": {"espn", "cbsros", "razzball"}}

SNAP = """() => {
  const C = window.TradeValueCurveControls, V2 = window.TradeValueV2;
  return {shown: V2.shown(), rank: C.getRankSource(), rankBy: document.getElementById('v2RankBy').value,
    rankOptions: [...document.querySelectorAll('#v2RankBy option')].map(o => o.value),
    engine: Object.fromEntries(C.getRows().map(r => [String(r.player_key), {
      ddf_value: r.values.ddf_value, ddf_value_charts: r.values.ddf_value_charts,
      ddf_value_projections: r.values.ddf_value_projections}])),
    cells: [...document.querySelectorAll('#v2Table tbody tr')].map(tr => ({key: tr.dataset.playerKey,
      text: Object.fromEntries(['ddf_value', 'ddf_value_charts', 'ddf_value_projections'].map(k => {
        const td = tr.querySelector(`td[data-source="${k}"]`);
        return [k, td ? (td.firstChild ? td.firstChild.textContent : '').trim() : null];
      }))}))};
}"""


def fmt(value):
    return "—" if value is None else f"{value:.1f}"


def check_defaults(page, tag) -> list[str]:
    errors = []
    snap = page.evaluate(SNAP)
    on = [k for k in KEYS if k in snap["shown"]]
    if on != ["ddf_value"]:
        errors.append(tag + f"DDF Value versions shown by default {on}, want only the blended one")
    if snap["rank"] != "ddf_value":
        errors.append(tag + f"default ranking {snap['rank']}, want ddf_value")
    page.click("#v2EditSources")
    rows = page.evaluate("""() => KEYS.map(k => {
      const b = document.querySelector(`#v2Popover [data-series="${k}"]`);
      return {key: k, on: b ? b.checked : null, name: b ? b.closest('label').querySelector('.v2-crow-name').textContent.trim() : null};
    })""".replace("KEYS", str(KEYS)))
    for row in rows:
        if row["on"] is None:
            errors.append(tag + f"Customize has no row for {row['key']}")
            continue
        if row["on"] != (row["key"] == "ddf_value"):
            errors.append(tag + f"Customize ticks {row['key']}={row['on']} by default")
        if not row["name"].endswith(NAMES[row["key"]]):
            errors.append(tag + f"Customize names {row['key']} {row['name']!r}, want {NAMES[row['key']]!r}")
    # The blend tab lists every input once. JEG-804 (#814, Jeremy 2026-10-22 "Out of DDF Value"): the blend is projections
    # only, so the tab has the "Projections" group and no "Trade charts" group (charts stay in "Chart lines").
    page.click('#v2Popover [data-tab="blend"]')
    sets = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#v2Popover [data-blend-group]')].map(g =>
      [g.dataset.blendGroup, [...g.querySelectorAll('input[data-ddf-input]')].map(i => i.dataset.ddfInput)]))""")
    if set(sets.get("proj", [])) != FAMILY["ddf_value_projections"]:
        errors.append(tag + f"the blend tab lists {sets.get('proj')} under Projections, want {sorted(FAMILY['ddf_value_projections'])}: {sets}")
    if sets.get("pub"):
        errors.append(tag + f"trade charts are back in the DDF blend tab: {sets.get('pub')}")
    if page.evaluate("() => document.querySelectorAll('#v2Popover [data-ddf-version-input], #v2Popover fieldset[data-ddf-version]').length"):
        errors.append(tag + "the per-version copies of the inputs are back")
    page.click('#v2Popover [data-apply="sources"]')
    page.wait_for_timeout(250)
    return errors


def check_pickers(page, tag) -> list[str]:
    errors = []
    snap = page.evaluate(SNAP)
    if [k for k in KEYS if k not in snap["rankOptions"]] :
        errors.append(tag + f"Rank by offers {snap['rankOptions']}, want all three DDF Value versions")
    page.goto(page.url.split("#")[0] + "#risers-fallers", wait_until="load")
    page.wait_for_timeout(1500)
    risers = page.evaluate("() => [...document.querySelectorAll('#v2RSeries option')].map(o => o.value)")
    if [k for k in KEYS if k not in risers]:
        errors.append(tag + f"Risers & fallers offers {risers}, want all three DDF Value versions")
    page.goto(page.url.split("#")[0] + "#compare-trade", wait_until="load")
    page.wait_for_timeout(1500)
    compare = page.evaluate("() => [...document.querySelectorAll('#v2CShown option')].map(o => o.value)")
    if [k for k in KEYS if k not in compare]:
        errors.append(tag + f"Compare's Player values shown offers {compare}, want all three DDF Value versions")
    page.goto(page.url.split("#")[0] + "#targets", wait_until="load")
    page.wait_for_timeout(1500)
    ours = page.evaluate("() => [...document.querySelectorAll('#v2TOurs option')].map(o => o.value)")
    if [k for k in KEYS if k not in ours]:
        errors.append(tag + f"Targets' our value offers {ours}, want all three DDF Value versions")
    page.goto(page.url.split("#")[0] + "#player-values", wait_until="load")
    ready(page)
    return errors


def check_versions_shown(page, tag) -> list[str]:
    errors = []
    page.click("#v2EditSources")
    for key in KEYS[1:]:
        page.check(f'#v2Popover [data-series="{key}"]')
    page.click('#v2Popover [data-apply="sources"]')
    page.wait_for_timeout(400)
    snap = page.evaluate(SNAP)
    if not all(k in snap["shown"] for k in KEYS):
        errors.append(tag + f"after ticking the versions the shown series are {snap['shown']}")
    checked = 0
    for cell in snap["cells"]:
        for key in KEYS:
            text = cell["text"][key]
            want = fmt(snap["engine"][cell["key"]][key])
            if text is None:
                errors.append(tag + f"row {cell['key']} has no {key} cell")
            elif text != want:
                errors.append(tag + f"row {cell['key']} {key} shows {text!r}, engine {want!r}")
            checked += 1
    if not checked:
        errors.append(tag + "no table rows")
    if len({tuple(snap["engine"][c["key"]][k] for k in KEYS) for c in snap["cells"]}) < 2 or not any(
            snap["engine"][c["key"]]["ddf_value_charts"] != snap["engine"][c["key"]]["ddf_value_projections"]
            for c in snap["cells"]):
        errors.append(tag + "the versions' values are all alike: the value check is not discriminating")
    return errors


def check_rank_and_reload(page, tag, base) -> list[str]:
    errors = []
    if "ddf_value_charts" not in page.evaluate(SNAP)["rankOptions"]:
        return [tag + "Rank by has no trade-charts version to pick"]
    page.select_option("#v2RankBy", "ddf_value_charts")
    page.wait_for_timeout(400)
    snap = page.evaluate(SNAP)
    if snap["rank"] != "ddf_value_charts" or snap["rankBy"] != "ddf_value_charts":
        errors.append(tag + f"Rank by the charts version gives engine rank {snap['rank']} / picker {snap['rankBy']}")
    values = [snap["engine"][c["key"]]["ddf_value_charts"] for c in snap["cells"]]
    finite = [v for v in values if v is not None]
    if finite != sorted(finite, reverse=True):
        errors.append(tag + "the table is not in the trade-charts version's order")
    page.click("#v2EditSources")
    page.click('#v2Popover [data-apply="sources"]')
    page.wait_for_timeout(250)
    page.goto(base + "#player-values", wait_until="networkidle")
    page.reload(wait_until="networkidle")
    ready(page)
    again = page.evaluate(SNAP)
    if not all(k in again["shown"] for k in KEYS) or again["rank"] != "ddf_value_charts":
        errors.append(tag + f"after reload shown {again['shown']} rank {again['rank']}, want all three and the charts version")
    return errors


def check_low_confidence(page, tag) -> list[str]:
    errors = []
    probe = page.evaluate("""() => {
      const C = window.TradeValueCurveControls, V2 = window.TradeValueV2;
      const trs = [...document.querySelectorAll('#v2Table tbody tr')];
      const m = (tr, k) => Boolean(tr.querySelector(`td[data-source="${k}"] [data-low-confidence]`));
      const plain = trs.find(tr => !m(tr, 'ddf_value_charts'));
      if (!plain) return null;
      const low = plain.dataset.playerKey;
      const before = {blended: m(plain, 'ddf_value'), projections: m(plain, 'ddf_value_projections')};
      const real = C.getRows;
      window.__realGetRows = real;
      C.getRows = () => real().map(r => String(r.player_key) !== low ? r : {...r, ddfByVersion: {...r.ddfByVersion,
        charts: {...r.ddfByVersion.charts, count: 1, lowConfidence: true, confidenceNote: 'Only one source prices this player'}}});
      V2.setShown(V2.shown());
      return {low, before};
    }""")
    if not probe:
        return [tag + "no rows to simulate a one-source version on"]
    page.wait_for_timeout(300)
    got = page.evaluate("""({low}) => {
      const m = k => document.querySelector(`#v2Table tbody tr[data-player-key="${low}"] td[data-source="${k}"] [data-low-confidence]`);
      return {charts: m('ddf_value_charts') ? m('ddf_value_charts').textContent : null, blended: Boolean(m('ddf_value')),
        projections: Boolean(m('ddf_value_projections'))};
    }""", probe)
    if got["charts"] != "◐ 1 source" or got["blended"] != probe["before"]["blended"] or got["projections"] != probe["before"]["projections"]:
        errors.append(tag + f"one-source trade-charts version marker {got}, want '◐ 1 source' on that column only")
    page.evaluate("() => { window.TradeValueCurveControls.getRows = window.__realGetRows; }")
    return errors


def run_checks(overrides=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    tag = "[1440px] "
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            for name, (body, ctype) in (overrides or {}).items():
                page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
            page.goto(base + "#player-values", wait_until="networkidle")
            ready(page)
            errors += check_defaults(page, tag)
            errors += check_pickers(page, tag)
            errors += check_versions_shown(page, tag)
            errors += check_low_confidence(page, tag)
            errors += check_rank_and_reload(page, tag, base)
            if page_errors:
                errors.append(tag + f"page errors {page_errors}")
            context.close()
        finally:
            browser.close()
    return errors


class DdfVersionsRenderTest(unittest.TestCase):
    def test_versions_follow_the_engine(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "versions on by default": v2.replace("    return [DDF_KEY].concat(info.filter(", "    return DDF_KEYS.concat(info.filter(", 1),
            "Rank by without the versions": v2.replace(
                "const rankKeys = DDF_KEYS.filter(key => view.infoByKey[key])",
                "const rankKeys = [DDF_KEY].filter(key => view.infoByKey[key])", 1),
            "one-source version tag read from the blend": v2.replace(
                "const flagged = key === DDF_KEY ? Boolean(row && row.ddfLowConfidence) : Boolean(entry && entry.lowConfidence);",
                "const flagged = Boolean(row && row.ddfLowConfidence);", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, v2, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks({"v2.js": (body, "text/javascript")}), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
