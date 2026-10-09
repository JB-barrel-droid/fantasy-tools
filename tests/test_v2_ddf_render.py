"""v2 DDF Value foundation (JEG-471 v2 side, JEG-466 defaults, JEG-455 decisions), rendered.

Builds dist/v2 into a temp copy of the built dist/, loads /v2/#player-values
headless at 1440 and 390 with empty storage, and checks against the engine
(TradeValueCurveControls):

  * defaults: the shown series are the DDF Value plus every available
    as-published chart; the engine ranks by "ddf_value" and Rank by says so;
    the Showing line leads with "DDF Value";
  * table: every row's DDF Value cell equals the engine row's
    values.ddf_value to one decimal, "—" where the engine has none;
  * chart: the DDF Value line is drawn, last (on top) and heavier than the
    others;
  * Customize: the DDF Value inputs list getCompositeInputs().allowed, ticked
    exactly where the engine uses them; unticking one and pressing Done
    reaches setCompositeInputs, and the table then shows the engine's new
    values;
  * remembered on this device: after a reload the inputs, the shown series
    and the ranking are the reader's choice; Reset to default + Done brings
    back the engine's default inputs; hiding the DDF Value survives a reload;
  * Reset (toolbar) puts Rank by back to the DDF Value;
  * Δ Prior week on the DDF Value cell is getPriorWeek("ddf_value")
    currentValues − values (both sides over the same inputs);
  * Tier (Jeremy, 2026-10-08: the tier follows the Rank by series): ranked by
    DDF Value, each row's tier is the engine's row.ddfTier; ranked by another
    series, it is the row's rank (engine order) against getZones();
  * a missing value shows "—" with the engine's own reason when the row has
    row.missingReasons[key] (simulated), and a finite 0 shows "0.0";
  * a one-source DDF Value (row.ddfLowConfidence, simulated) shows "◐ 1 source"
    in its DDF Value cell with the engine's note as the tooltip;
  * no page errors, no horizontal overflow at 390.

Discrimination: test_guard_fails_on_broken_builds serves v2.js / movers.js /
v2.css with one fault each (including the tier read from espnRole and the
engine's missing reason ignored) and requires the checks to fail on each.
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
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
MOVERS_JS = ROOT / "app" / "v2" / "movers.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
DDF = "ddf_value"

READ = """() => {
  const C = window.TradeValueCurveControls, V2 = window.TradeValueV2;
  const engine = Object.fromEntries(C.getRows().map(r => [String(r.player_key), r.values.ddf_value]));
  const info = C.getSourceInfo();
  const projection = new Set(['espn', 'cbsros', 'razzball']);
  const published = info.filter(i => i.available && !/_(vorp|adjusted)$/.test(i.key) && !projection.has(i.key)).map(i => i.key);
  const cells = [...document.querySelectorAll('#v2Table tbody tr')].map(tr => {
    const td = tr.querySelector('td[data-source="ddf_value"]');
    return {key: tr.dataset.playerKey, text: td ? (td.firstChild ? td.firstChild.textContent : '').trim() : null,
      delta: td && td.querySelector('.delta') ? td.querySelector('.delta').textContent : null};
  });
  const paths = [...document.querySelectorAll('#v2Chart path.series')];
  const ddfPath = paths.find(p => p.dataset.source === 'ddf_value');
  const width = p => p ? parseFloat(getComputedStyle(p).strokeWidth) : 0;
  const ci = C.getCompositeInputs();
  return {shown: V2.shown(), published, rank: C.getRankSource(), rankBy: document.getElementById('v2RankBy').value,
    showing: document.getElementById('v2ShowingText').textContent, engine, cells,
    ddfPath: Boolean(ddfPath), lastPath: paths.length ? paths[paths.length - 1].dataset.source : null,
    ddfWidth: width(ddfPath), otherWidth: Math.max(0, ...paths.filter(p => p !== ddfPath).map(width)),
    inputs: ci.inputs, isDefault: ci.isDefault, allowed: ci.allowed, defaults: ci.defaults,
    overflow: document.documentElement.scrollWidth - innerWidth};
}"""


def fmt(value):
    return "—" if value is None else f"{value:.1f}"


def check_table(snap, tag) -> list[str]:
    errors = []
    if not snap["cells"]:
        return [tag + "no table rows"]
    for cell in snap["cells"]:
        want = fmt(snap["engine"].get(cell["key"]))
        if cell["text"] is None:
            errors.append(tag + f"row {cell['key']} has no DDF Value cell")
        elif cell["text"] != want:
            errors.append(tag + f"row {cell['key']} DDF Value {cell['text']!r}, engine {want!r}")
    return errors[:5]


def check_defaults(snap, tag) -> list[str]:
    errors = []
    if snap["shown"] != [DDF] + [k for k in snap["shown"] if k != DDF] or sorted(snap["shown"]) != sorted([DDF] + snap["published"]):
        errors.append(tag + f"default shown {snap['shown']}, want DDF Value + {snap['published']}")
    if snap["rank"] != DDF or snap["rankBy"] != DDF:
        errors.append(tag + f"default ranking {snap['rank']} / Rank by {snap['rankBy']}, want ddf_value")
    if not snap["showing"].startswith("DDF Value"):
        errors.append(tag + f"Showing line does not lead with DDF Value: {snap['showing']!r}")
    if not snap["ddfPath"] or snap["lastPath"] != DDF:
        errors.append(tag + f"DDF Value line missing or not on top (last path {snap['lastPath']})")
    if not snap["ddfWidth"] > snap["otherWidth"]:
        errors.append(tag + f"DDF Value line not heavier: {snap['ddfWidth']} vs {snap['otherWidth']}")
    if not snap["isDefault"]:
        errors.append(tag + "first visit does not use the engine's default inputs")
    return errors


def ready(page):
    page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
    page.wait_for_timeout(250)


def check_customize(page, tag) -> list[str]:
    errors = []
    before = page.evaluate(READ)
    page.click("#v2EditSources")
    boxes = page.evaluate("""() => [...document.querySelectorAll('#v2Popover [data-ddf-input]')].map(b => ({key: b.dataset.ddfInput,
      on: b.checked, disabled: b.disabled}))""")
    if [b["key"] for b in boxes] != before["allowed"]:
        errors.append(tag + f"DDF inputs {[b['key'] for b in boxes]} != engine allowed {before['allowed']}")
    if sorted(b["key"] for b in boxes if b["on"]) != sorted(before["inputs"]):
        errors.append(tag + f"ticked inputs {[b['key'] for b in boxes if b['on']]} != engine inputs {before['inputs']}")
    drop = next((b["key"] for b in boxes if b["on"] and not b["disabled"]), None)
    if not drop:
        return errors + [tag + "no DDF input to untick"]
    page.click(f'#v2Popover [data-ddf-input="{drop}"]')
    page.click('#v2Popover [data-apply="sources"]')
    page.wait_for_timeout(300)
    after = page.evaluate(READ)
    if drop in after["inputs"] or after["isDefault"]:
        errors.append(tag + f"Done did not drop {drop} from the DDF inputs: {after['inputs']}")
    errors += check_table(after, tag + "after inputs: ")
    if after["engine"] == before["engine"]:
        errors.append(tag + f"dropping {drop} changed no DDF Value; the check is not discriminating")
    # Remembered on this device.
    page.reload(wait_until="networkidle")
    ready(page)
    again = page.evaluate(READ)
    if sorted(again["inputs"]) != sorted(after["inputs"]) or again["isDefault"]:
        errors.append(tag + f"inputs after reload {again['inputs']}, want {after['inputs']}")
    if again["shown"] != after["shown"] or again["rank"] != DDF:
        errors.append(tag + f"after reload shown {again['shown']} rank {again['rank']}, want {after['shown']} / ddf_value")
    errors += check_table(again, tag + "after reload: ")
    # Reset to default restores the engine's inputs.
    page.click("#v2EditSources")
    page.click("#v2Popover button:has-text('Reset to default')")
    page.click('#v2Popover [data-apply="sources"]')
    page.wait_for_timeout(300)
    reset = page.evaluate(READ)
    if sorted(reset["inputs"]) != sorted(reset["defaults"]):
        errors.append(tag + f"Reset to default left inputs {reset['inputs']}, defaults {reset['defaults']}")
    # Hiding the DDF Value is remembered too.
    page.click("#v2EditSources")
    page.click(f'#v2Popover [data-series="{DDF}"]')
    page.click('#v2Popover [data-apply="sources"]')
    page.reload(wait_until="networkidle")
    ready(page)
    hidden = page.evaluate(READ)
    if DDF in hidden["shown"]:
        errors.append(tag + f"hidden DDF Value is back after reload: {hidden['shown']}")
    page.evaluate("() => window.TradeValueV2.setShown(['ddf_value'].concat(window.TradeValueV2.shown()))")
    return errors


def check_reset_and_delta(page, tag) -> list[str]:
    errors = []
    other = page.evaluate("() => window.TradeValueV2.view().plotKeys.find(k => k !== 'ddf_value')")
    page.select_option("#v2RankBy", other)
    page.wait_for_timeout(200)
    page.click("#v2Reset")
    page.wait_for_timeout(300)
    snap = page.evaluate(READ)
    if snap["rank"] != DDF or snap["rankBy"] != DDF:
        errors.append(tag + f"Reset left Rank by on {snap['rank']}")
    # Simulate a prior week that lacks one input: the engine's current side (currentValues) then differs
    # from the row's DDF Value, and only currentValues − values is right.
    page.evaluate("""() => { const C = window.TradeValueCurveControls; const real = C.getPriorWeek;
      C.getPriorWeek = async key => { const r = await real(key);
        if (key !== 'ddf_value' || !r || !r.currentValues) return r;
        return {...r, currentValues: Object.fromEntries(Object.entries(r.currentValues).map(([k, v]) => [k, Number.isFinite(v) ? v + 1.5 : v]))}; }; }""")
    page.click("#v2DeltaBtn")
    page.wait_for_function("() => document.querySelector('#v2Table td[data-source=\"ddf_value\"] .delta') && "
                           "!/…/.test(document.querySelector('#v2Table td[data-source=\"ddf_value\"] .delta').textContent)",
                           timeout=60000)
    page.wait_for_timeout(200)
    want = page.evaluate("""async () => {
      const prior = await window.TradeValueCurveControls.getPriorWeek('ddf_value');
      return [...document.querySelectorAll('#v2Table tbody tr')].slice(0, 25).map(tr => {
        const k = tr.dataset.playerKey;
        const now = prior && prior.currentValues ? prior.currentValues[k] : undefined;
        const was = prior && prior.values ? prior.values[k] : undefined;
        const d = Number.isFinite(now) && Number.isFinite(was) ? now - was : null;
        const t = d === null ? '—' : Math.abs(d).toFixed(1) === '0.0' ? '0.0' : `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(1)}`;
        return {k, want: `Δ ${t}`, got: tr.querySelector('td[data-source="ddf_value"] .delta')?.textContent};
      });
    }""")
    bad = [w for w in want if w["got"] != w["want"]]
    if bad:
        errors.append(tag + f"DDF Δ differs from currentValues − values: {bad[:3]}")
    return errors


TIER_READ = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getRows();
  const z = C.getZones();
  const label = {starter: 'Starter', bench: 'Bench', waiver: 'Waiver'};
  const rank = C.getRankSource();
  const want = Object.fromEntries(rows.map((r, i) => [String(r.player_key), rank === 'ddf_value' ? (label[r.ddfTier] || '—')
    : !Number.isFinite(r.values[rank]) ? '—' : i + 1 < z.starter_to_bench ? 'Starter' : i + 1 < z.bench_to_waiver ? 'Bench' : 'Waiver']));
  // Tier is the last meta column when those show (1600 px and up), else the last part of the player sub-line.
  const got = [...document.querySelectorAll('#v2Table tbody tr')].map(tr => {
    const sub = tr.querySelector('td.player .player-sub');
    const metas = tr.querySelectorAll('td.col-meta');
    return {key: tr.dataset.playerKey, tier: metas.length ? metas[metas.length - 1].textContent.trim() : sub ? sub.textContent.split(' · ').pop() : null};
  });
  const espnDiffers = rows.some(r => (label[r.espnRole] || '—') !== want[String(r.player_key)]);
  return {rank, want, got, espnDiffers};
}"""

REASON = "Not enough players to fit an adjustment"


def check_tiers(page, tag) -> list[str]:
    """Tier follows Rank by: DDF Value, then one other series."""
    errors = []
    other = page.evaluate("() => window.TradeValueV2.view().plotKeys.find(k => k !== 'ddf_value')")
    for key in (DDF, other):
        page.select_option("#v2RankBy", key)
        page.wait_for_timeout(250)
        snap = page.evaluate(TIER_READ)
        if snap["rank"] != key:
            errors.append(tag + f"Rank by {key} left the engine on {snap['rank']}")
            continue
        if not snap["got"]:
            errors.append(tag + f"ranked by {key}: no rows")
        bad = [(g["key"], g["tier"], snap["want"].get(g["key"])) for g in snap["got"] if g["tier"] != snap["want"].get(g["key"])]
        if bad:
            errors.append(tag + f"ranked by {key}: tier differs from that series' zones, e.g. {bad[:3]} (key, shown, want)")
        if key == DDF and not snap["espnDiffers"]:
            errors.append(tag + "ESPN roles equal the DDF tiers for every row: the tier check is not discriminating")
    page.select_option("#v2RankBy", DDF)
    page.wait_for_timeout(250)
    return errors


def check_missing_reason(page, tag) -> list[str]:
    """Simulate the engine's row.missingReasons (and a finite 0) on two shown rows."""
    errors = []
    probe = page.evaluate("""(reason) => {
      const C = window.TradeValueCurveControls, V2 = window.TradeValueV2;
      const key = V2.view().plotKeys.find(k => k !== 'ddf_value');
      const trs = [...document.querySelectorAll('#v2Table tbody tr')];
      if (!key || trs.length < 2) return null;
      const [gone, zero, low] = [trs[0].dataset.playerKey, trs[1].dataset.playerKey, trs[2]?.dataset.playerKey];
      const real = C.getRows;
      window.__realGetRows = real;
      C.getRows = () => real().map(r => {
        const k = String(r.player_key);
        if (k === gone) return {...r, values: {...r.values, [key]: null}, missingReasons: {[key]: reason}};
        if (k === zero) return {...r, values: {...r.values, [key]: 0}};
        if (k === low) return {...r, ddfCount: 1, ddfLowConfidence: true, ddfConfidenceNote: 'Only one source prices this player'};
        return r;
      });
      V2.setShown(V2.shown());
      return {key, gone, zero, low};
    }""", REASON)
    if not probe:
        return [tag + "no rows to simulate a missing reason on"]
    page.wait_for_timeout(250)
    got = page.evaluate("""({key, gone, zero, low}) => {
      const cell = k => document.querySelector(`#v2Table tbody tr[data-player-key="${k}"] td[data-source="${key}"]`);
      const g = cell(gone), z = cell(zero);
      return {goneTitle: g?.querySelector('.missing')?.title ?? null, goneText: g?.querySelector('.missing')?.firstChild?.textContent ?? null,
        zeroText: z ? (z.firstChild ? z.firstChild.textContent : '').trim() : null, zeroMissing: Boolean(z?.querySelector('.missing')),
        low: (() => { const m = document.querySelector(`#v2Table tbody tr[data-player-key="${low}"] td[data-source="ddf_value"] [data-low-confidence]`);
          return m ? {text: m.textContent, title: m.title, aria: m.getAttribute('aria-label')} : null; })(),
        lowOnZero: Boolean(document.querySelector(`#v2Table tbody tr[data-player-key="${zero}"] [data-low-confidence]`))};
    }""", probe)
    if got["goneText"] != "—" or got["goneTitle"] != REASON:
        errors.append(tag + f"missing value shows {got['goneText']!r} with reason {got['goneTitle']!r}, want '—' with {REASON!r}")
    if got["low"] != {"text": "◐ 1 source", "title": "Only one source prices this player",
                      "aria": "1 source: Only one source prices this player"} or got["lowOnZero"]:
        errors.append(tag + f"one-source DDF Value marker {got['low']} (also on a normal row: {got['lowOnZero']}), want '◐ 1 source'")
    if got["zeroText"] != "0.0" or got["zeroMissing"]:
        errors.append(tag + f"a finite 0 shows {got['zeroText']!r} (missing={got['zeroMissing']}), want '0.0'")
    page.evaluate("() => { const C = window.TradeValueCurveControls; C.getRows = window.__realGetRows; window.TradeValueV2.setShown(window.TradeValueV2.shown()); }")
    return errors


def _serve(body, ctype, route, *_):
    route.fulfill(status=200, content_type=ctype, body=body)


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


def run_checks(overrides=None, viewports=((1440, 900), (390, 844))) -> list[str]:
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
            for width, height in viewports:
                tag = f"[{width}px] "
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#player-values", wait_until="networkidle")
                ready(page)
                snap = page.evaluate(READ)
                errors += check_defaults(snap, tag)
                errors += check_table(snap, tag)
                if width >= 1280:
                    errors += check_tiers(page, tag)
                    errors += check_missing_reason(page, tag)
                    errors += check_customize(page, tag)
                    errors += check_reset_and_delta(page, tag)
                if width <= 390 and snap["overflow"] > 0:
                    errors.append(tag + f"horizontal overflow {snap['overflow']}px")
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class DdfRenderTest(unittest.TestCase):
    def test_ddf_value_is_the_default_and_equals_the_engine(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        movers = MOVERS_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        js, cs = "text/javascript", "text/css"
        broken = {
            "DDF Value hidden by default": {"v2.js": (v2.replace("    return [DDF_KEY].concat(info.filter(", "    return [].concat(info.filter(", 1), js)},
            "ranked by the engine's own default": {"v2.js": (v2.replace(
                "const rank = saved && saved.rank ? saved.rank : (hasDdf ? DDF_KEY : null);",
                "const rank = saved && saved.rank ? saved.rank : null;", 1), js)},
            "inputs never reach the engine": {"v2.js": (v2.replace(
                "if (changed) C.setCompositeInputs([...inputsDraft]);", "if (false) C.setCompositeInputs([...inputsDraft]);", 1), js)},
            "choice not remembered": {"v2.js": (v2.replace("localStorage.setItem(SAVE_KEY,", "void (SAVE_KEY,", 1), js)},
            "Reset keeps Rank by": {"v2.js": (v2.replace(
                "    if (view && view.infoByKey[DDF_KEY] && C.getRankSource() !== DDF_KEY) C.setLockOrder(DDF_KEY);\n", "", 1), js)},
            "DDF line not on top": {"v2.js": (v2.replace(
                "keys.filter(key => key !== DDF_KEY).concat(keys.includes(DDF_KEY) ? [DDF_KEY] : []).forEach(key => {",
                "keys.forEach(key => {", 1), js)},
            "DDF line not heavier": {"v2.css": (css.replace(".v2-chart .series.is-ddf { stroke-width: 3.5; }", "", 1), cs)},
            "DDF table value rounded down": {"v2.js": (v2.replace(
                "if (key === DDF_KEY) return \"ddf\";\n    const meta = sourceMeta(key);",
                "if (key === DDF_KEY) return \"ddf\";\n    const meta = sourceMeta(key);", 1).replace(
                "            td.textContent = fmt(v);", "            td.textContent = fmt(col.source === DDF_KEY ? Math.floor(v * 10 - 1) / 10 : v);", 1), js)},
            "tier read from espnRole": {"v2.js": (v2.replace(
                "const tierText = (row, key, scope) => tierLabel(tierFor(row, key, scope));",
                "const tierText = row => tierLabel(row.espnRole);", 1), js)},
            "low-confidence marker missing": {"v2.js": (v2.replace(
                "    if (isLowConfidence(row, key)) parent.appendChild(lowConfidenceNode(row));", "", 1), js)},
            "engine missing reason ignored": {"v2.js": (v2.replace(
                '    if (typeof own === "string" && own.trim()) return own;\n', "", 1), js)},
            "DDF Δ from the row value": {"movers.js": (movers.replace(
                "    if (prior.currentValues) current = prior.currentValues[playerKey];\n", "", 1), js)},
        }
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                for file, (body, _) in overrides.items():
                    source = {"v2.js": v2, "movers.js": movers, "v2.css": css}[file]
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides, viewports=((1440, 900),)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
