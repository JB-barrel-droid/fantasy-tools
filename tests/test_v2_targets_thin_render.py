"""v2 Trade targets, rendered: a DDF Value backed by fewer than 2 sources gets no Buy/Sell call, and the page says why (JEG-1186).

Jeremy, 2026-10-27 ("Suppress"): a player whose DDF Value rests on one source is left off Buy and Sell. app/v2/targets.js
(`thinSupport`, MIN_DDF_SOURCES = 2) drops him from both lists and returns `thinSource` / `thinSourceNames`; app/v2/v2.js adds
"N player(s) left off Buy and Sell: only 1 source backs his/their DDF Value (names). A Buy or Sell call needs at least 2." to the
notes. tests/test_v2_targets.py covers the pure rule; this test renders it, at 1366 x 768 and 390 x 844.

The data. Two SYNTHETIC players, "Test Solo Source" (1 source) and "Test Duo Source" (2 sources), are injected as DATA into this
test's own copy of the build (comparison-sources-data.json and the engine page's player rows, the way tests/test_v2_finder_fit_render.py
injects its rows). Nothing is stubbed: targets.js, v2.js and the engine run unchanged.

Why the DDF Value (projections) version. Every real row has ddfCount 3 (blended and charts versions): the blend's sources are the same
trade charts the page compares, and a chart that does not list a player prices him at its waiver line (0), which still counts as a source.
So no player can be given "one source" on the default DDF Value from data alone while two charts still price him. The projections
version is different: its sources (ESPN, CBS rest-of-season, Razzball) are projections, and a projection that does not list a player leaves
him unpriced, so ddfProjectionsCount is really 1 or 2 for many players (about 200 in the current data). The Our value picker offers it
("DDF Value (projections)", ddf_value_projections) and targets.js reads its count from ddfProjectionsCount, so the test picks that
version. The trade charts, which feed the market side, are unchanged.

The pair. A real Sell target P is picked from the page (a clear Sell under the projections version: all three charts above our value,
3 projection sources). Both players are clones of P's entry in every trade chart, so the market side is identical. The thin player keeps
one projection source s1 (ddfProjectionsCount 1); the twin keeps s1 and s2 (count 2), so his value is the mean of the two. s1 and s2 are
chosen from P's three projection values so that the two players' values are as close as they can be and both stay clear Sells (the page
asserts this, and that each has the intended count, before anything else). Without the rule the thin player would be a Sell: the page
also runs the real buildTargets on a copy of the rows with his count set to 2 and requires him in that Sell list.

Discrimination: test_guard_fails_on_broken_builds serves targets.js with thinSupport always false, v2.js with the note removed, and
targets.js with MIN_DDF_SOURCES = 3 (the twin then drops too), and requires the checks to fail on each. JEG-1186 notes the same test
fails against origin/main's targets.js and v2.js.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from tests import _render_env
from tests._holds import pin_holds_in_dist
from tests.test_v2_targets_render import DIST, TARGETS_JS, V2_JS, _chromium_executable, _serve, build_v2_page, setUpModule  # noqa: F401

ENGINE_PAGE = DIST.resolve().parent / "build" / "engine" / "index.html"
PLAYERS_ISLAND = re.compile(r'(<script id="players-data" type="application/json">)(.*?)(</script>)', re.S)
OURS = "ddf_value_projections"
PROJECTIONS = ("espn", "cbsros", "razzball")
PROJECTION_FIELDS = {"espn": ("espn_ppg", "espn_ros"), "cbsros": ("cbsros_ppg",), "razzball": ("rz_ppg", "rz_ros", "rz_filled_ppg", "rz_filled_ros")}
SOLO, DUO = "Test Solo Source", "Test Duo Source"
SYN_KEYS = {SOLO: 9000011, DUO: 9000012}
SELL_FLOOR = 5.0   # TradeValueTargets.SELL_FLOOR
VIEWPORTS = ((1366, 768), (390, 844))


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower())


# The case, from the unmodified build: a Sell target under the projections version, three projection sources, every compared chart
# above our value, and the pair (s1 for the solo player; s1 and s2 for the duo) that keeps the two values closest.
PICK = """(floor) => {
  const t = window.TradeValueV2.targets();
  const rows = window.TradeValueCurveControls.getRows();
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  let best = null;
  t.sell.slice(0, 40).forEach(p => {
    const r = p.row;
    if (r.ddfProjectionsCount !== 3 || rows.filter(x => x.name === r.name).length !== 1) return;
    const charts = t.used.map(c => r.values[c]);
    if (charts.length < 3 || !charts.every(v => fin(v) && v > 0)) return;
    const v = {espn: r.values.espn, cbsros: r.values.cbsros, razzball: r.values.razzball};
    if (!Object.values(v).every(fin)) return;
    const names = Object.keys(v);
    names.forEach(s1 => names.forEach(s2 => {
      if (s1 === s2) return;
      const solo = v[s1], duo = (v[s1] + v[s2]) / 2, top = Math.max(solo, duo);
      const room = Math.min(...charts) - top;
      if (Math.min(solo, duo) < floor + 2 || room < 3) return;
      const cost = Math.abs(solo - duo) / room;
      if (!best || cost < best.cost) best = {name: r.name, key: r.player_key, s1, s2, cost, solo, duo, charts};
    }));
  });
  return best;
}"""


def _inject(dist: Path, engine_out: Path, spec: dict) -> None:
    """Add the solo and duo players to this test's own copy of the build: DATA only, no code is touched."""
    path = dist / "assets" / "comparison-sources-data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    old = {v: k for k, v in data["display"].items()}[spec["name"]]
    keep = {SOLO: {spec["s1"]}, DUO: {spec["s1"], spec["s2"]}}

    def clone(node, new_key):
        if isinstance(node, dict):
            if old in node:
                node[new_key] = json.loads(json.dumps(node[old]))
            for child in list(node.values()):
                clone(child, new_key)
        elif isinstance(node, list):
            for child in node:
                clone(child, new_key)

    for name, key in SYN_KEYS.items():
        new = _norm(name)
        for root, section in data["sources"].items():
            if root in PROJECTIONS and root not in keep[name]:
                continue   # this source does not list him: that is what makes his count 1 or 2
            clone(section, new)
            pids = section.get("espn_priced_pids") if isinstance(section, dict) else None
            if isinstance(pids, list) and spec["key"] in pids:
                pids.append(key)
        data["player_keys"][new] = key
        data["teams"][new] = data["teams"][old]
        data["display"][new] = name
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    page = ENGINE_PAGE.read_text(encoding="utf-8")
    match = PLAYERS_ISLAND.search(page)
    players = json.loads(match.group(2))
    real = next(r for r in players["players"] if r["name"] == spec["name"])
    for name, key in SYN_KEYS.items():
        row = json.loads(json.dumps(real))
        row.update({"player_key": key, "name": name})
        row.pop("sleeper_id", None)
        # A projection source lists a player when its per-game field is set (curve-widget PPG_FIELD_OF): clear the sources he is not in.
        for source in PROJECTIONS:
            if source not in keep[name]:
                row.update({field: None for field in PROJECTION_FIELDS[source]})
        players["players"].append(row)
    engine_out.write_text(page[:match.start(2)] + json.dumps(players, separators=(",", ":")) + page[match.end(2):], encoding="utf-8")


@contextlib.contextmanager
def _served(spec=None):
    """A temp copy of the built dist (holds pinned, JEG-675), with the injected pair when `spec` is given, on a local server."""
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        engine_page = ENGINE_PAGE
        if spec:
            engine_page = Path(tmp) / "engine.html"
            _inject(dist, engine_page, spec)
        build_v2_page.build(dist, engine_page=engine_page)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#trade-targets"
            finally:
                server.shutdown()


def _open(browser, url, width, height, targets_js=None, v2_js=None):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.add_init_script(_render_env.pin_data_week_script())   # JEG-1152: the data's week, not the wall clock
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    for pattern, body in (("**/v2/targets.js*", targets_js), ("**/v2/v2.js*", v2_js)):
        if body is not None:
            page.route(pattern, functools.partial(_serve, body, "text/javascript"))
    page.goto(url, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=40000)
    page.select_option("#v2TOurs", OURS)
    page.wait_for_function("(k) => window.TradeValueV2.targets().ours === k", arg=OURS, timeout=10000)
    return page, errors


@functools.lru_cache(maxsize=None)
def _spec():
    """The real player to clone and the two projection sources to keep, read once from the unmodified build."""
    from playwright.sync_api import sync_playwright
    with _served() as url, sync_playwright() as pw:
        browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        try:
            page, _ = _open(browser, url, 1366, 768)
            spec = page.evaluate(PICK, SELL_FLOOR)
        finally:
            browser.close()
    if not spec:
        raise AssertionError("no Sell target under DDF Value (projections) has three projection sources, charts above it and room to spare: "
                             "the thin-source case cannot be built from this week's data")
    return json.dumps(spec)


# Arrival: both players reached the page with the intended source counts and numbers, and (run through the real buildTargets with his count
# raised to 2) the solo player would be a Sell, so it is the rule that keeps him off. Then the lists as the engine built them.
STATE = """([solo, duo, ours, floor]) => {
  const C = window.TradeValueCurveControls, V2 = window.TradeValueV2, TT = window.TradeValueTargets;
  const t = V2.targets();
  const rows = C.getRows();
  const by = name => rows.filter(r => r.name === name);
  const one = name => { const r = by(name); return r.length === 1 ? r[0] : null; };
  const brief = r => r && {key: r.player_key, count: r.ddfProjectionsCount, sources: r.ddfByVersion.projections.sources,
    ours: r.values[ours], charts: t.used.map(c => r.values[c]), blended: r.ddfCount, estimated: Object.keys(r.estimated || {}).length};
  const s = one(solo), d = one(duo);
  let wouldBe = null;
  if (s) {
    const lifted = rows.map(r => r === s ? {...r, ddfProjectionsCount: 2} : r);
    const w = TT.buildTargets(lifted, t.used, {ours});
    wouldBe = {sell: w.sell.some(p => p.row.player_key === s.player_key), buy: w.buy.some(p => p.row.player_key === s.player_key)};
  }
  const keys = list => list.map(p => p.row.name);
  return {solo: brief(s), duo: brief(d), copies: [by(solo).length, by(duo).length], wouldBe,
    sell: keys(t.sell), buy: keys(t.buy), thinSource: t.thinSource, thinSourceNames: t.thinSourceNames};
}"""

# What the page draws once the search is on a name: the rows of each list, and the notes line.
DRAW = """(key) => {
  const has = id => document.querySelectorAll(`#${id} [data-player-key="${key}"]`).length;
  return {sell: has('v2TSell'), buy: has('v2TBuy'), note: document.getElementById('v2TNote').textContent, noteHidden: document.getElementById('v2TNote').hidden};
}"""


def _search(page, text):
    page.fill("#v2TSearch", text)
    page.wait_for_function("(t) => window.TradeValueV2.targets() && document.getElementById('v2TSearch').value === t", arg=text, timeout=10000)
    page.wait_for_timeout(500)   # the search is debounced (120 ms) before the lists redraw


def _check(page, spec, width) -> list[str]:
    errors = []
    state = page.evaluate(STATE, [SOLO, DUO, OURS, SELL_FLOOR])
    solo, duo = state["solo"], state["duo"]
    if state["copies"] != [1, 1] or not solo or not duo:
        return [f"injection failed: the page has {state['copies']} rows named {SOLO!r} / {DUO!r}, not 1 and 1"]
    # Arrival, so a broken injection fails loudly.
    if solo["count"] != 1 or solo["sources"] != [spec["s1"]]:
        errors.append(f"{SOLO} arrived with {solo['count']} projection sources {solo['sources']}, not 1 ({spec['s1']})")
    if duo["count"] != 2 or sorted(duo["sources"]) != sorted([spec["s1"], spec["s2"]]):
        errors.append(f"{DUO} arrived with {duo['count']} projection sources {duo['sources']}, not 2 ({spec['s1']}, {spec['s2']})")
    for who in (solo, duo):
        if who["estimated"]:
            errors.append(f"a chart value of {who['key']} is estimated, so the page would drop him for another reason")
        if who["ours"] is None or who["ours"] < SELL_FLOOR + 1:
            errors.append(f"{who['key']} arrived with our value {who['ours']}, too low to be a Sell")
    if solo["charts"] != duo["charts"] or len(solo["charts"]) < 3:
        errors.append(f"the two players do not have the same chart values: {solo['charts']} vs {duo['charts']}")
    elif solo["ours"] is not None and duo["ours"] is not None:
        if min(solo["charts"]) - max(solo["ours"], duo["ours"]) < 2:
            errors.append(f"the charts {solo['charts']} are not clearly above our values {solo['ours']} / {duo['ours']}")
        if abs(solo["ours"] - duo["ours"]) > max(2.0, 0.25 * max(solo["ours"], duo["ours"])):
            errors.append(f"the two players' values are not close: {solo['ours']} vs {duo['ours']}")
    if not state["wouldBe"] or not state["wouldBe"]["sell"]:
        errors.append(f"with a second source {SOLO} would not be a Sell either, so the rule is not what is under test: {state['wouldBe']}")
    if errors:
        return errors   # the premise is wrong; the checks below would only add noise
    # The engine's lists.
    for name in (SOLO,):
        if name in state["sell"] or name in state["buy"]:
            errors.append(f"{name} (1 source) is in the Buy/Sell lists")
    if DUO not in state["sell"]:
        errors.append(f"{DUO} (2 sources) is not in the Sell list")
    named = state["thinSourceNames"] or []
    if SOLO not in named or not state["thinSource"]:
        errors.append(f"buildTargets does not name {SOLO} as left off: {state['thinSource']} {named}")
    if DUO in named:
        errors.append(f"{DUO} (2 sources) is named as left off")
    # The page. Searching the name lists only that player (ranks stay over everyone), so his row and the notes are about him alone.
    _search(page, SOLO)
    drawn = page.evaluate(DRAW, solo["key"])
    if drawn["sell"] or drawn["buy"]:
        errors.append(f"{SOLO} has a row in the Sell/Buy lists on the page: {drawn}")
    expect = f"1 player left off Buy and Sell: only 1 source backs his DDF Value ({SOLO}). A Buy or Sell call needs at least 2."
    if drawn["noteHidden"] or expect not in drawn["note"]:
        errors.append(f"the notes do not say why {SOLO} is left off ({expect!r}): {drawn['note']!r}")
    _search(page, DUO)
    drawn = page.evaluate(DRAW, duo["key"])
    if not drawn["sell"] or drawn["buy"]:
        errors.append(f"{DUO} (2 sources) is not a row in the Sell list on the page, or is in Buy: {drawn}")
    if "left off Buy and Sell" in drawn["note"] or "only 1 source" in drawn["note"]:
        errors.append(f"the notes call {DUO} (2 sources) thin: {drawn['note']!r}")
    # Unfiltered, the page still carries the line (it counts every thin player the lists would otherwise have shown).
    _search(page, "")
    note = page.evaluate(DRAW, solo["key"])["note"]
    if "left off Buy and Sell: only 1 source backs" not in note:
        errors.append(f"the unfiltered notes lack the thin-source line: {note!r}")
    return errors


def collect(targets_js=None, v2_js=None, viewports=VIEWPORTS) -> list[str]:
    from playwright.sync_api import sync_playwright
    spec = json.loads(_spec())
    errors = []
    with _served(spec) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        try:
            for width, height in viewports:
                page, page_errors = _open(browser, url, width, height, targets_js, v2_js)
                errors += [f"{width}: {e}" for e in _check(page, spec, width)]
                errors += [f"{width}: page error: {e}" for e in page_errors]
                page.close()
        finally:
            browser.close()
    return errors


class TargetsThinSourceRender(unittest.TestCase):
    def test_one_source_player_gets_no_call_and_a_reason(self):
        self.maxDiff = None
        self.assertEqual(collect(), [])

    def test_guard_fails_on_broken_builds(self):
        targets, v2 = (path.read_text(encoding="utf-8").replace("\r\n", "\n") for path in (TARGETS_JS, V2_JS))
        broken = {
            "thinSupport always false": ("targets_js", targets,
                                         "const thinSupport = (row, ourKey) => { const n = ddfSourceCount(row, ourKey); return n !== null && n < MIN_DDF_SOURCES; };",
                                         "const thinSupport = () => false;"),
            "thin-source note removed": ("v2_js", v2, "    if (targetsView.thinSource && !blocked) {", "    if (false) {"),
            "minimum sources 3 (the 2-source twin drops too)": ("targets_js", targets, "const MIN_DDF_SOURCES = 2;", "const MIN_DDF_SOURCES = 3;"),
        }
        for name, (kind, source, old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name!r} is stale: {old!r}")
                self.assertNotEqual(collect(viewports=VIEWPORTS[:1], **{kind: source.replace(old, new, 1)}), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
