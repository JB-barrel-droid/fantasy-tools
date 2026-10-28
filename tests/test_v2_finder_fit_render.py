"""v2 Find a trade v2 (JEG-988), commit 4: natural / market supported / force fit on the groups, rendered.

Two real roster pages (the Yahoo and ESPN team fixtures) go through Find trades at 1440 and 390 wide, with packages of up
to 3. Checked against the finder's own pure functions run in the page:

  * every group card carries a fit line ("Natural fit:", "Market supported:" or "Force fit:") that names both teams' net change in
    their own view (you: DDF Value, they: the trade chart average);
  * the order is natural fits first, then market supported, then force; inside a tier the groups keep the edge ranking; and nothing
    else changes: with every group shown, the set of group edges equals the groups the search finds without the tiering
    (no group added, dropped or re-valued);
  * the thin-roster case: a team whose only RB1 is a star gives him for two RB2s from a deep team. The search lists the
    1-for-2 package, the roster impact shows the thin team's best-lineup starter value rising, and the card says why.
    This case uses three SYNTHETIC rows ("Test Star RB", "Test RB2 A", "Test RB2 B"): weekly data has no such pair (a star
    whose two real RB2s the DDF Value prefers while at least three of four charts price them level or lower; JEG-1185), so
    the test injects them as data (player and chart entries in its own copy of the build, projections cloned from three
    real RBs) and the real page and finder code run unchanged. The test asserts the rows reached the page with the numbers
    the case needs, so a broken injection fails loudly;
  * no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the tier ordering off, with the fit line not drawn
and with the 1-for-2 package left out of the search, and requires each to fail.
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
from tests._holds import HOLD_FIELDS, pin_holds_in_dist
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_eval_render import ESPN
from tests.test_v2_finder_render import FINDER_JS, add, build_v2_page
from tests.test_v2_modules_render import DIST, _serve


# The synthetic thin-roster case (JEG-1185): names, keys (far above any real player_key) and the real RBs whose projections they clone.
SYN_NAMES = {"star": "Test Star RB", "a": "Test RB2 A", "b": "Test RB2 B"}
SYN_KEYS = {"star": 9000001, "a": 9000002, "b": 9000003}
CHART_ROOTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
ENGINE_PAGE = Path(DIST).resolve().parent / "build" / "engine" / "index.html"
PLAYERS_ISLAND = re.compile(r'(<script id="players-data" type="application/json">)(.*?)(</script>)', re.S)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower())


def _inject_thin_case(dist: Path, engine_out: Path, spec: dict) -> None:
    """Add the three synthetic RBs to this test's own copy of the build: DATA only, no code is touched.

    Each is a clone of a real RB (the player row and every per-source entry) under a fake name and key. The two RB2s keep the
    clones' numbers. The star's entries on the four trade charts are set to the RB2s' combined entries, except that CBS is
    scaled by spec["cbs_factor"]: at least three charts then price the two RB2s level or lower than the star, while the DDF Value
    (which follows the charts) still prefers the two RB2s. The factor is found per week by _synthetic_spec."""
    path = dist / "assets" / "comparison-sources-data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    clones = spec["clones"]
    by_display = {v: k for k, v in data["display"].items()}
    new_key = {role: _norm(SYN_NAMES[role]) for role in SYN_NAMES}
    old_key = {role: by_display[clones[role]] for role in clones}

    def clone_entries(node):
        if isinstance(node, dict):
            for role in SYN_NAMES:
                if old_key[role] in node:
                    node[new_key[role]] = json.loads(json.dumps(node[old_key[role]]))
            for child in list(node.values()):
                clone_entries(child)
        elif isinstance(node, list):
            for child in node:
                clone_entries(child)

    clone_entries(data["sources"])
    for role in SYN_NAMES:
        data["player_keys"][new_key[role]] = SYN_KEYS[role]
        data["teams"][new_key[role]] = data["teams"][old_key[role]]
        data["display"][new_key[role]] = SYN_NAMES[role]

    def set_star(node, factor):
        if isinstance(node, dict):
            star, a, b = (new_key[r] for r in ("star", "a", "b"))
            if all(isinstance(node.get(k), (int, float)) for k in (star, a, b)):
                node[star] = round((node[a] + node[b]) * factor, 6)
            for child in node.values():
                set_star(child, factor)
        elif isinstance(node, list):
            for child in node:
                set_star(child, factor)

    for root in CHART_ROOTS:
        if root in data["sources"]:
            set_star(data["sources"][root], spec["cbs_factor"] if root == "cbs" else 1.0)
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    page = ENGINE_PAGE.read_text(encoding="utf-8")
    match = PLAYERS_ISLAND.search(page)
    players = json.loads(match.group(2))
    for role in SYN_NAMES:
        real = next(r for r in players["players"] if r["name"] == clones[role])
        row = json.loads(json.dumps(real))
        row.update({"player_key": SYN_KEYS[role], "name": SYN_NAMES[role]})
        row.pop("sleeper_id", None)
        players["players"].append(row)
    engine_out.write_text(page[:match.start(2)] + json.dumps(players, separators=(",", ":")) + page[match.end(2):], encoding="utf-8")


@contextlib.contextmanager
def _built_dist(spec=None):
    """Built dist with all four trade charts open, unlike tests.test_v2_finder_render._built_dist, which pins CBS held (JEG-881).

    The fit guards (two different fit labels; a star RB for two RB2s) need the four-chart state: with CBS held only three
    charts are available and the finder needs all three to agree, which the data does not give (JEG-1185). The plain
    committed fixture holds every chart (all Week 7 against Week 8), so the helper still pins the same open set as the
    shared one (tests._holds, JEG-675) and then also clears the CBS hold in its own copy. With `spec` (from _synthetic_spec)
    the three synthetic thin-case rows are added to that copy."""
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        path = dist / "assets" / "comparison-sources-data.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for sec in ("cbs", "cbs_adjusted", "cbs_vorp"):
            section = (data.get("sources") or {}).get(sec)
            if isinstance(section, dict):
                for field in HOLD_FIELDS:
                    section.pop(field, None)
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        engine_page = ENGINE_PAGE
        if spec:
            engine_page = Path(tmp) / "engine.html"
            _inject_thin_case(dist, engine_page, spec)
        build_v2_page.build(dist, engine_page=engine_page)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


# Three real RBs to clone for the synthetic case, by property from the week's rows: the 3rd best by DDF Value (the star) and the 6th and
# 14th (the RB2s, both required to be 8 or more).
CLONE_PICK = """() => {
  const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.pos === 'RB');
  const rbs = rows.filter(r => rows.filter(x => x.name === r.name).length === 1).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  return [rbs[2], rbs[5], rbs[13]].map(r => r && {name: r.name, ddf: r.values.ddf_value});
}"""
# The DDF Value gap the case needs (RB2s combined minus the star), aimed at the middle of the 0.2 to 4 window.
GAP_AIM = 1.5


def _read_gap(spec) -> float:
    """Build with the synthetic rows for this spec and return the DDF Value gap (a + b - star) the page computes."""
    from playwright.sync_api import sync_playwright
    with _built_dist(spec) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            page = browser.new_page()
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(base + "#find-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls", timeout=60000)
            return page.evaluate("""(names) => {
              const by = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r.values.ddf_value]));
              return by.get(names[1]) + by.get(names[2]) - by.get(names[0]);
            }""", [SYN_NAMES["star"], SYN_NAMES["a"], SYN_NAMES["b"]])
        finally:
            browser.close()


@functools.lru_cache(maxsize=None)
def _synthetic_spec():
    """Which real RBs to clone and how far to scale the star's CBS entries, found once per process.

    DDF Value follows the charts, so the star's DDF Value is tuned with its CBS entry (the other three charts sit at the RB2s'
    sum): two builds fix a straight line through (factor, gap), the factor that aims at GAP_AIM is read off it. The final numbers
    are asserted in the page (THIN), so a week where this does not land fails loudly."""
    from playwright.sync_api import sync_playwright
    with _built_dist() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            page = browser.new_page()
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(base + "#find-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls", timeout=60000)
            picked = page.evaluate(CLONE_PICK)
        finally:
            browser.close()
    if not all(picked) or picked[1]["ddf"] < 8 or picked[2]["ddf"] < 8:
        raise AssertionError(f"fewer than 14 RBs with a DDF Value, or the 14th below 8, to clone for the thin-roster case: {picked}")
    clones = {"star": picked[0]["name"], "a": picked[1]["name"], "b": picked[2]["name"]}
    f1, f2 = 0.6, 0.3
    g1, g2 = _read_gap({"clones": clones, "cbs_factor": f1}), _read_gap({"clones": clones, "cbs_factor": f2})
    if g2 == g1:
        raise AssertionError(f"the star's DDF Value does not respond to its CBS entry (gap {g1:.2f} at {f1} and {g2:.2f} at {f2})")
    factor = min(1.0, max(0.0, f1 + (GAP_AIM - g1) * (f2 - f1) / (g2 - g1)))
    return {"clones": clones, "cbs_factor": round(factor, 4)}


# The four trade charts the finder judges on, available and held (getSourceInfo).
CHARTS = """() => {
  const info = window.TradeValueCurveControls.getSourceInfo().filter(i => ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].includes(i.key));
  return {available: info.filter(i => i.available).map(i => i.key), held: info.filter(i => !i.available).map(i => i.key)};
}"""


def setUpModule():
    _render_env.ensure_built()


# Groups as the search finds them, with no tiering: the edges to compare against, from the page's own pure functions.
BASELINE = """() => {
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder;
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  const names = id => [...document.querySelectorAll(`#${id} li.v2-find-row b`)].map(b => b.textContent).filter(n => byName.has(n));
  const mine = names('v2FindMinePlayers').map(n => byName.get(n)), theirs = names('v2FindTheirsPlayers').map(n => byName.get(n));
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = F.CHART_KEYS.filter(k => avail.has(k));
  const shape = C.getRosterShape();
  const size = Number(document.getElementById('v2FindSize').value);
  const res = F.findTrades(mine, theirs, {chartKeys: charts, maxSize: size, limit: 1e7, sanity: {shape, mine, theirs, keepMine: true, keepTheirs: true}});
  return F.groupTrades(res.trades, {ourKey: res.ourKey}).map(g => g.bestEdge);
}"""
SHOWN = """() => [...document.querySelectorAll('#v2FindList li.v2-find-group')].map(li => ({fit: li.dataset.findFit || null, edge: Number(li.dataset.findEdge),
  line: (li.querySelector('.v2-find-fit') || {}).textContent || '', visible: Boolean(li.querySelector('.v2-find-fit')) && li.querySelector('.v2-find-fit').getBoundingClientRect().height > 0}))"""
# The synthetic star RB and two RB2s (names passed in): checks they reached the page with a DDF Value that sums 0.2 to 4 above the star's,
# both RB2s at 8 or more, and at least three charts saying the thin team breaks even or wins; then builds the two rosters around them.
THIN = """(names) => {
  const C = window.TradeValueCurveControls;
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => avail.has(k));
  const all = C.getAllRows();
  const found = names.map(n => all.filter(r => r.name === n));
  if (found.some(f => f.length !== 1)) return {error: `the synthetic rows did not reach the page exactly once: ${names.map((n, i) => `${n} x${found[i].length}`).join(', ')}`};
  const [s, a, b] = found.map(f => f[0]);
  if (![s, a, b].every(r => r.pos === 'RB' && r.values && Number.isFinite(r.values.ddf_value) && charts.every(k => Number.isFinite(r.values[k])))) return {error: 'a synthetic row lacks a position of RB or a DDF Value or a chart value'};
  const dd = a.values.ddf_value + b.values.ddf_value - s.values.ddf_value;
  const level = charts.filter(k => a.values[k] + b.values[k] - s.values[k] <= 0.05).length;
  if (a.values.ddf_value < 8 || b.values.ddf_value < 8 || dd <= 0.2 || dd > 4 || level < 3) return {error: `the synthetic rows do not have the numbers the case needs: RB2s ${a.values.ddf_value.toFixed(1)} and ${b.values.ddf_value.toFixed(1)}, DDF Value gap ${dd.toFixed(2)}, ${level} of ${charts.length} charts level or lower`};
  const rows = all.filter(r => r.values && Number.isFinite(r.values.ddf_value) && charts.every(k => Number.isFinite(r.values[k])));
  const uniq = rows.filter(r => !names.includes(r.name) && rows.filter(x => x.name === r.name).length === 1);
  const by = pos => uniq.filter(r => r.pos === pos).sort((x, y) => y.values.ddf_value - x.values.ddf_value);
  const rbs = by('RB'), wrs = by('WR'), qbs = by('QB'), tes = by('TE');
  const used = new Set(names);
  const take = (list, n, from) => list.filter(r => !used.has(r.name)).slice(from, from + n).map(r => { used.add(r.name); return r.name; });
  // The thin team has exactly its starting slots and no bench: a team receiving more players adds its own cheapest bench player as a
  // throw-in (JEG-1108), which would swallow the 1-for-2 edge; a team with no bench is left unbalanced and the 1-for-2 stays listed.
  const sh = C.getRosterShape();
  const thin = [s.name].concat(take(qbs, (sh.QB || 0) + (sh.SUPERFLEX || 0), 6), take(wrs, (sh.WR || 0) + (sh.FLEX || 0), 8), take(tes, sh.TE || 0, 8));
  const deep = [a.name, b.name].concat(take(rbs, 4, 3), take(wrs, 4, 0), take(qbs, 2, 0), take(tes, 2, 0));
  return {star: s.name, a: a.name, b: b.name, thin, deep};
}"""


def orientation(page, tag, swap) -> list[str]:
    """Yahoo as mine and ESPN as theirs has no natural group on current data; the swap lists groups of at least two different fits,
    which is what makes the tier-order assertion test something."""
    errors = []
    tag = f"{tag}{'ESPN mine / Yahoo theirs: ' if swap else 'Yahoo mine / ESPN theirs: '}"
    say = lambda what: errors.append(tag + what)
    if swap:
        if page.locator("#v2FindInput").is_hidden():
            page.click("#v2FindEdit")
        for side in ("Mine", "Theirs"):
            page.click(f"#v2Find{side}Clear")
    page.fill("#v2FindMineSearch", (ESPN if swap else FIXTURE).read_text(encoding="utf-8"))
    page.fill("#v2FindTheirsSearch", (FIXTURE if swap else ESPN).read_text(encoding="utf-8"))
    page.wait_for_timeout(400)
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(1200)
    more = page.locator("#v2FindMoreGroups")
    if more.count():
        more.click()
        page.wait_for_timeout(300)
    shown = page.evaluate(SHOWN)
    base = page.evaluate(BASELINE)
    if not shown:
        say("no groups listed")
        return errors
    kinds = {g["fit"] for g in shown}
    if swap and len(kinds & {"natural", "market", "force"}) < 2:
        say(f"the swapped rosters must list groups of at least two different fits so the tier order is exercised, got {sorted(map(str, kinds))}: the guard would test nothing")
    if not all(g["visible"] for g in shown):
        say("a group's fit line is not visible")
    if any(g["fit"] is None or not re.match(r"^(Natural fit|Market supported|Force fit)(?: · [A-Za-z -]+ viability)?:", g["line"]) for g in shown):
        say(f"a group has no fit line: {[g['line'][:30] for g in shown if g['fit'] is None][:3]}")
    for g in shown:
        if g["fit"] == "natural" and ("DDF Value" not in g["line"] or "trade chart average" not in g["line"]):
            say(f"a natural line does not name both views: {g['line'][:140]}")
        if g["fit"] == "market" and "trade charts favor them" not in g["line"]:
            say(f"a market supported line does not say the charts favor them: {g['line'][:140]}")
    tiers = [{"natural": 0, "market": 1, "force": 2}[g["fit"]] for g in shown if g["fit"]]
    if tiers != sorted(tiers):
        say(f"tiers are not natural, market supported, force in order: {[g['fit'] for g in shown]}")
    for tier in (0, 1, 2):
        edges = [g["edge"] for g, t in zip(shown, tiers) if t == tier]
        if edges != sorted(edges, reverse=True):
            say(f"tier {tier} is not in edge order: {[round(e, 2) for e in edges]}")
    # The finder lists at most two groups per received player and folds the rest into a "N more for <player>" note, so
    # the shown groups are a subset of the search's groups (none added, none re-valued) and every missing group is
    # counted in those notes (none lost silently).
    base_left = [round(e, 6) for e in base]
    added = []
    for g in shown:
        edge = round(g["edge"], 6)
        if edge in base_left:
            base_left.remove(edge)
        else:
            added.append(round(g["edge"], 2))
    if added:
        say(f"shown group edges {added} are not in the search's groups: values changed or groups invented")
    folded = sum(int(n) for n in re.findall(r"(\d+) more for ", page.locator("#v2FindOut").inner_text()))
    if len(base_left) != folded:
        say(f"{len(base_left)} groups are in the search but not listed, and the notes fold {folded}: groups lost or miscounted")
    return errors


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste && window.TradeValueFinder", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    charts = page.evaluate(CHARTS)
    if len(charts["available"]) < 4:
        say(f"fewer than 4 trade charts are available (available {charts['available']}, held or unavailable {charts['held']}): the fit guards need the four-chart state")
        return errors
    errors += orientation(page, tag, False)
    errors += orientation(page, tag, True)
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow")
    if width > 390:
        errors += thin_case(page, tag)
    return errors


def thin_case(page, tag) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    case = page.evaluate(THIN, [SYN_NAMES["star"], SYN_NAMES["a"], SYN_NAMES["b"]])
    if case.get("error"):
        say(case["error"])
        return errors
    if page.locator("#v2FindInput").is_hidden():
        page.click("#v2FindEdit")
    for side in ("Mine", "Theirs"):
        page.click(f"#v2Find{side}Clear")
    for name in case["thin"]:
        add(page, "Mine", name)
    for name in case["deep"]:
        add(page, "Theirs", name)
    page.select_option("#v2FindSize", "2")
    page.click("#v2FindGo")
    page.wait_for_timeout(1200)
    listed = page.evaluate("""([star, a, b]) => {
      const F = window.TradeValueFinder, C = window.TradeValueCurveControls;
      const byName = new Map(C.getAllRows().map(r => [r.name, r]));
      const names = id => [...document.querySelectorAll(`#${id} li.v2-find-row b`)].map(x => x.textContent).filter(n => byName.has(n));
      const mine = names('v2FindMinePlayers').map(n => byName.get(n)), theirs = names('v2FindTheirsPlayers').map(n => byName.get(n));
      const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
      // The same call the page makes (roster sanity with the league shape): the throw-in is the cheapest BENCH player, not any player (JEG-1108).
      const res = F.findTrades(mine, theirs, {chartKeys: F.CHART_KEYS.filter(k => avail.has(k)), maxSize: 2, limit: 1e7, sanity: {shape: C.getRosterShape(), mine, theirs, keepMine: true, keepTheirs: true}});
      return res.trades.some(t => t.give.length === 1 && t.give[0].name === star && t.receive.length === 2 && t.receive.some(r => r.name === a) && t.receive.some(r => r.name === b));
    }""", [case["star"], case["a"], case["b"]])
    if not listed:
        say(f"the search does not generate the 1-for-2 package {case['star']} for {case['a']} + {case['b']}")
        return errors
    if page.locator("#v2FindMoreGroups").count():
        page.click("#v2FindMoreGroups")
        page.wait_for_timeout(300)
    # The group whose core is the better RB2: tick exactly the star on your side and both RB2s on theirs, then read the card.
    # A group's target names its whole received core: the better RB2 alone, or both RB2s when the package is searched as the core.
    card = page.locator(f"li.v2-find-group:has(.v2-find-target-name:text-is('{case['a']}'))").or_(
        page.locator(f"li.v2-find-group:has(.v2-find-target-name:text-is('{case['a']} + {case['b']}'))")).first
    if not card.count():
        say(f"no group for the target {case['a']}")
        return errors
    for box in card.locator("fieldset:has(legend:text-is('You give')) input[type=checkbox]").all():
        label = box.get_attribute("aria-label") or ""
        want = case["star"] in label
        if want and not box.is_checked():
            box.check()
        elif not want and box.is_checked() and not box.is_disabled():
            box.uncheck()
    for box in card.locator("fieldset:has(legend:has-text('You also receive')) input[type=checkbox]").all():
        label = box.get_attribute("aria-label") or ""
        want = case["b"] in label
        if want and not box.is_checked():
            box.check()
        elif not want and box.is_checked():
            box.uncheck()
    page.wait_for_timeout(300)
    label = card.locator(".v2-find-trade").text_content()
    if label != f"You give {case['star']}; you receive {case['a']} + {case['b']}":
        say(f"the card reads {label!r}, not the 1-for-2 package")
        return errors
    impact = card.locator(".v2-find-impact-line").first.text_content()
    m = re.search(r"DDF Value ([0-9.]+) → ([0-9.]+) \(([+-][0-9.]+)\)", impact)
    if not m or float(m.group(3)) <= 0 or float(m.group(2)) <= float(m.group(1)):
        say(f"the thin team's starter value does not rise in the impact lines: {impact!r}")
    fit = card.locator(".v2-find-fit").text_content()
    if not re.match(r"^(Natural fit|Market supported|Force fit)(?: · [A-Za-z -]+ viability)?:", fit) or "DDF Value" not in fit:
        say(f"the 1-for-2 card has no fit reading: {fit[:120]!r}")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844), (320, 640))) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    spec = _synthetic_spec()
    with _built_dist(spec) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


def broken(overrides) -> bool:
    try:
        return bool(run_checks(overrides, viewports=((1440, 900),)))
    except Exception:
        return True


class FinderFitRenderTest(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        cases = {
            "tier ordering off": ("if (fitCtx) groups = tierGroups(", "if (false) groups = tierGroups("),
            "fit line not drawn": ("fitLine.hidden = !fit;", "fitLine.hidden = true;"),
            "tier order reversed": ("a.t - b.t || a.i - b.i", "b.t - a.t || a.i - b.i"),
            "folded groups not counted in the note": ("folded.set(ck, (folded.get(ck) || 0) + 1);", "void 0;"),
            "two-player packages not searched": ("const mineSubs = subsets(mineP.rows.length, maxSize)", "const mineSubs = subsets(mineP.rows.length, 1)"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.assertIn(old, js, f"stale anchor for {name!r}")
                self.assertTrue(broken({"finder.js": js.replace(old, new, 1)}), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
