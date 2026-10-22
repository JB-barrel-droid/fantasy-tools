"""Values auditing > single-source build-up view, rendered (JEG-849).

Loads the built page headless, mounts app/v2/audit-source.js into the shell's
#audit-source-root (through the DDFAudit.register contract) and checks, for
all seven sources at the committed fixture's league setting:

  * tie to the engine: the view's Published, Indexed and Adjusted series, and
    the table cells, equal the numbers Player values reads from the engine
    (getAllRows values, getPublishedMath, the *_adjusted series), no second
    calculation;
  * a projection has no Indexed stage: no series, no column, a stated reason;
  * estimated players are shown (same count as the engine marks) and marked
    in the table and on the chart;
  * a missing value is never drawn or shown as zero;
  * the page follows league settings (teams change -> values change, still tied);
  * toggling sources leaves the engine's selection (getActiveSources) alone;
  * desktop and 375 px: no page-level overflow from the view, chart inside it.

Discrimination: test_guard_fails_on_broken_builds serves audit-source.js with
one named bug at a time and requires the checks to fail on each.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_panels_render import ROOT, _built_dist, _serve, _serve_css  # noqa: E402

AUDIT_JS = ROOT / "app" / "v2" / "audit-source.js"
AUDIT_CSS = ROOT / "app" / "v2" / "audit-source.css"
SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball"]
PROJECTIONS = {"espn", "cbsros", "razzball"}

STUB = "window.DDFAudit = {register: (name, fn) => { window.__audit = window.__audit || {}; window.__audit[name] = fn; }};"

# Mount into the app container (the shell's own page does this once it lands).
MOUNT = """() => {
  const app = document.querySelector('.v2-app');
  app.querySelectorAll(':scope > main').forEach(m => { m.hidden = true; });
  const root = document.createElement('main');
  root.id = 'audit-source-root';
  app.append(root);
  window.__audit['single-source'](root, {});
  return true;
}"""

# Independent oracle: what Player values reads for this source, per player.
ORACLE = """(src) => {
  const C = window.TradeValueCurveControls;
  const chart = ['fantasycalc', 'usatoday', 'fantasypros', 'cbs'].includes(src);
  const insp = C.getInspection();
  const out = {};
  C.getAllRows().forEach(r => {
    const key = String(r.player_key);
    if (!(key in insp.players[src])) return;
    const fin = v => (typeof v === 'number' && Number.isFinite(v) ? v : null);
    out[key] = {
      // A listed player's published number is the chart's own; an estimated one has none, only the engine's fill-in.
      published: chart ? ((r.estimated || {})[src] ? fin(insp.players[src][key].native) : fin((C.getPublishedMath(r.player_key, src) || {}).native)) : fin(insp.natives[src][key]),
      indexed: chart ? fin(r.values[src]) : null,
      adjusted: chart ? fin(r.values[src + '_adjusted']) : fin(r.values[src]),
      estimated: Boolean((r.estimated || {})[src])
    };
  });
  return {oracle: out, listed: Object.keys(insp.players[src]).length};
}"""

READ = """() => {
  const m = window.DDFAuditSource.current();
  return {
    source: m.source, stages: m.stages, shown: m.shown, estimatedCount: m.estimatedCount,
    rows: m.rows.map(r => ({key: r.key, published: r.published, indexed: r.indexed, adjusted: r.adjusted, estimated: r.estimated})),
    series: Object.fromEntries(Object.entries(m.series).map(([k, v]) => [k, v.map(p => [p.key, p.value])])),
    paths: Object.fromEntries([...document.querySelectorAll('#audit-source-root path[data-series]')].map(p => [p.dataset.series, Number(p.dataset.count)])),
    thead: [...document.querySelectorAll('#audit-source-root th')].map(t => t.textContent),
    cells: [...document.querySelectorAll('#audit-source-root tbody tr')].map(tr => ({
      key: tr.dataset.playerKey, estimated: tr.hasAttribute('data-estimated'),
      badge: Boolean(tr.querySelector('[data-estimated-badge]')),
      v: Object.fromEntries([...tr.querySelectorAll('td[data-stage]')].map(td => [td.dataset.stage, {value: td.dataset.value, text: td.textContent}]))})),
    stageNotes: Object.fromEntries([...document.querySelectorAll('#audit-source-root .as-stage')].map(li => [li.dataset.stage, {exists: li.dataset.exists, text: li.textContent}])),
    marks: document.querySelectorAll('#audit-source-root circle[data-estimated]').length
  };
}"""

SELECT = """(src) => { document.querySelector(`#audit-source-root .as-seg[data-source="${src}"]`).click(); return true; }"""
SHOW_ALL = """() => { let n = 0; while (document.querySelector('#audit-source-root .as-more') && n++ < 30) document.querySelector('#audit-source-root .as-more').click(); return n; }"""


def close(a, b):
    return a is None and b is None or (a is not None and b is not None and abs(a - b) <= 1e-9 * max(1.0, abs(b)))


def check_source(page, src) -> list[str]:
    errors = []
    page.evaluate(SELECT, src)
    page.evaluate(SHOW_ALL)
    got = page.evaluate(READ)
    ref = page.evaluate(ORACLE, src)
    oracle = ref["oracle"]
    if got["source"] != src:
        return [f"{src}: toggle did not switch the view to it ({got['source']})"]
    if got["shown"] != ref["listed"] or {r["key"] for r in got["rows"]} != set(oracle):
        errors.append(f"{src}: shows {got['shown']} players, engine lists {ref['listed']} (oracle {len(oracle)})")
    for r in got["rows"]:
        o = oracle.get(r["key"])
        if not o:
            continue
        for stage in ("published", "indexed", "adjusted"):
            if not close(r[stage], o[stage]):
                errors.append(f"{src}/{r['key']}/{stage}: view {r[stage]} != engine {o[stage]}")
                break
        if r["estimated"] != o["estimated"]:
            errors.append(f"{src}/{r['key']}: estimated {r['estimated']} but the engine says {o['estimated']}")
    # The drawn series carry the same numbers, and never a zero for a missing value.
    for stage in ("published", "indexed", "adjusted"):
        want = [[r["key"], oracle[r["key"]][stage]] for r in got["rows"] if r["key"] in oracle and oracle[r["key"]][stage] is not None]
        have = got["series"][stage]
        if len(have) != len(want) or any(h[0] != w[0] or not close(h[1], w[1]) for h, w in zip(have, want)):
            errors.append(f"{src}: {stage} series ({len(have)} points) does not match the engine ({len(want)})")
        if want and got["paths"].get(stage) != len(want):
            errors.append(f"{src}: the drawn {stage} line has {got['paths'].get(stage)} points, engine {len(want)}")
        if not want and stage in got["paths"]:
            errors.append(f"{src}: a {stage} line is drawn but the engine has no {stage} values")
    # Table cells carry the same numbers as the model.
    cells = {c["key"]: c for c in got["cells"]}
    if len(cells) != len(got["rows"]):
        errors.append(f"{src}: table has {len(cells)} rows for {len(got['rows'])} players")
    for r in got["rows"]:
        c = cells.get(r["key"])
        if not c:
            continue
        for stage, cell in c["v"].items():
            value = None if cell["value"] == "" else float(cell["value"])
            if not close(value, r[stage]):
                errors.append(f"{src}/{r['key']}/{stage}: table cell {cell['value']!r} != model {r[stage]}")
            if value is None and cell["text"].strip() not in ("—",):
                errors.append(f"{src}/{r['key']}/{stage}: missing value shown as {cell['text']!r}")
    # Indexed stage exists only for the charts, and the page says so where it does not.
    if src in PROJECTIONS:
        if got["stages"]["indexed"]["exists"] or got["series"]["indexed"] or "indexed" in got["paths"]:
            errors.append(f"{src}: a projection must have no Indexed stage")
        if "Indexed" in got["thead"]:
            errors.append(f"{src}: Indexed column shown for a projection")
        note = got["stageNotes"].get("indexed", {})
        if note.get("exists") != "false" or "not available" not in note.get("text", ""):
            errors.append(f"{src}: the page does not say the Indexed stage is missing: {note}")
    else:
        if not got["series"]["indexed"] or "Indexed" not in got["thead"]:
            errors.append(f"{src}: chart has no Indexed series/column")
    # Estimated players: shown, marked in the table and on the chart.
    want_est = sum(1 for o in oracle.values() if o["estimated"])
    if got["estimatedCount"] != want_est:
        errors.append(f"{src}: {got['estimatedCount']} estimated players shown, engine marks {want_est}")
    for c in got["cells"]:
        if c["estimated"] != c["badge"]:
            errors.append(f"{src}/{c['key']}: estimated row {c['estimated']} but badge {c['badge']}")
    if sum(1 for c in got["cells"] if c["estimated"]) != want_est:
        errors.append(f"{src}: table marks {sum(1 for c in got['cells'] if c['estimated'])} estimated rows, engine {want_est}")
    if want_est and got["marks"] < want_est:
        errors.append(f"{src}: chart has {got['marks']} estimated markers for {want_est} estimated players")
    return errors


# A missing value (no Adjusted) must stay missing: patch the engine's inspection.
MISSING = """() => {
  const C = window.TradeValueCurveControls;
  const real = C.getInspection.bind(C);
  window.__topKey = window.DDFAuditSource.current().rows[0].key;
  C.getInspection = () => {
    const i = real();
    const key = window.__topKey;
    i.rows[key].adjusted.fantasycalc = null;
    i.rows[key].indexed.fantasycalc = null;
    window.__missingKey = key;
    return i;
  };
  window.DDFAuditSource.render();
  C.getInspection = real;
  const m = window.DDFAuditSource.current();
  const row = m.rows.find(r => r.key === window.__missingKey);
  const tr = document.querySelector(`#audit-source-root tr[data-player-key="${window.__missingKey}"]`);
  return {row: row && {adjusted: row.adjusted, indexed: row.indexed},
    inSeries: m.series.adjusted.some(p => p.key === window.__missingKey) || m.series.indexed.some(p => p.key === window.__missingKey),
    texts: tr ? [...tr.querySelectorAll('td[data-stage]')].map(td => [td.dataset.stage, td.textContent.trim()]) : null};
}"""

SETTINGS = """() => {
  const C = window.TradeValueCurveControls;
  const before = window.DDFAuditSource.current().setting.teams;
  C.setTeams(before === 10 ? 14 : 10);
  window.dispatchEvent(new CustomEvent('trade-value-rows-change'));
  return {before, after: window.DDFAuditSource.current().setting.teams, active: C.getActiveSources()};
}"""


def run_checks(audit_js=None, sources=SOURCES) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    js = audit_js if audit_js is not None else AUDIT_JS.read_text(encoding="utf-8")
    css = AUDIT_CSS.read_text(encoding="utf-8")
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 900), (375, 812)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.add_init_script(STUB)
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueCurveControls.isReady()", timeout=40000)
                page.add_style_tag(content=css)
                page.add_script_tag(content=js)
                page.evaluate(MOUNT)
                active_before = page.evaluate("() => window.TradeValueCurveControls.getActiveSources()")
                if width == 1440:
                    for src in sources:
                        errors += check_source(page, src)
                    page.evaluate(SELECT, "fantasycalc")
                    missing = page.evaluate(MISSING)
                    if not missing["row"] or missing["row"]["adjusted"] is not None or missing["row"]["indexed"] is not None:
                        errors.append(f"missing value not kept missing: {missing['row']}")
                    if missing["inSeries"]:
                        errors.append("a missing value is drawn in a series")
                    if missing["texts"] is None or any(t != "—" for s, t in missing["texts"] if s in ("indexed", "adjusted")):
                        errors.append(f"missing value cells do not show a dash: {missing['texts']}")
                    page.evaluate(SELECT, "fantasycalc")
                    settings = page.evaluate(SETTINGS)
                    if settings["after"] == settings["before"]:
                        errors.append("the view did not follow a league settings change")
                    else:
                        errors += [f"after teams change: {e}" for e in check_source(page, "fantasycalc")]
                        errors += [f"after teams change: {e}" for e in check_source(page, "espn")]
                if page.evaluate("() => window.TradeValueCurveControls.getActiveSources()") != active_before and width == 1440:
                    errors.append("toggling sources changed the engine's selection")
                # Layout: the view itself never overflows the viewport; the chart sits inside it.
                page.evaluate(SELECT, "fantasycalc")
                layout = page.evaluate("""() => {
                  const root = document.getElementById('audit-source-root').getBoundingClientRect();
                  const svg = document.querySelector('#audit-source-root .as-svg').getBoundingClientRect();
                  const wide = [...document.querySelectorAll('#audit-source-root *')].filter(e => !e.closest('.as-scroll') && e.getBoundingClientRect().right > window.innerWidth + 1).length;
                  return {root: root.width, svg: svg.width, vw: window.innerWidth, wide, h: svg.height};
                }""")
                if layout["wide"] or layout["svg"] > layout["root"] + 1 or layout["h"] < 120:
                    errors.append(f"{width}px layout: {layout}")
                if page_errors:
                    errors.append(f"page errors at {width}px: {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class AuditSourceRenderTest(unittest.TestCase):
    def test_single_source_view(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = AUDIT_JS.read_text(encoding="utf-8")
        broken = {
            "missing value shown as zero": js.replace(
                'const finite = v => (typeof v === "number" && Number.isFinite(v) ? v : null);',
                'const finite = v => (typeof v === "number" && Number.isFinite(v) ? v : 0);', 1),
            "estimated flag dropped": js.replace("estimated: Boolean(p.estimated),", "estimated: false,", 1),
            "indexed faked for projections": js.replace(
                "const indexed = isChart ? finite(row.indexed && row.indexed[meta.key]) : null;",
                "const indexed = finite(row.indexed && row.indexed[meta.key]);", 1),
            "adjusted reads the wrong stage": js.replace(
                "const adjusted = finite(row.adjusted && row.adjusted[meta.key]);",
                "const adjusted = finite(row.vorp && row.vorp[meta.key]);", 1),
            "published reads the indexed number": js.replace(
                "const published = finite(p.native);",
                "const published = finite(rows[key] && rows[key].indexed && rows[key].indexed[meta.key]);", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(audit_js=body, sources=["fantasycalc", "espn"]), [],
                                    f"render checks did not catch: {name}")


def setUpModule():
    _render_env.ensure_built()


if __name__ == "__main__":
    unittest.main()
