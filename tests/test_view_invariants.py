"""The three chart views hold Jeremy's invariants (views-invariants-001).

Jeremy, 2026-10-08:
  * Indexed: "the positions and bench/starter have different weights but the
    total pies are the same."
  * VORP vs waivers: "the differences in deconstructed values of each player
    on the same exact scale."
  * Adjusted values: "the differences in value of each player, when their
    positional and bench/starter weights have been normalized."

As implemented (docs/methodology.md "The Three Views"), with one basis for
every source in every view -- the players the source and the ESPN anchor both
price (QB/RB/WR/TE):

  * Indexed: every source shown (published charts, CBS ROS, Razzball, the
    *_adjusted series, the raw value-above-waivers series) totals exactly the
    anchor's total there; every published chart keeps its own position x
    starter/bench split (not the anchor's).
  * VORP vs waivers: every value-above-waivers series (the four published
    charts and ESPN / CBS ROS / Razzball raw) totals exactly the anchor's
    total there -- one scale. The published values are, independently
    recomputed here, unified.translate_ranked's value above waivers times that
    one factor.
  * Adjusted values: every published chart's eight position x starter/bench
    group totals equal the anchor's (the DDF weights); independently
    recomputed here from translate_ranked's roles and value above waivers.

Read live from the real page (window.TradeValueCurveHarness.sourceMaps) at the
3 scorings x 8/10/12/14 teams, a custom roster, and two non-default bench
shares, plus the page's own TradeValueCurveDiagnostics.viewInvariants.

Discrimination (test_guard_fails_on_broken_engines): broken engines served in
place of the real assets -- Indexed without its total factor, VORP vs waivers
on the old per-chart budget basis, Adjusted capped at 70, Adjusted with one
factor instead of eight groups -- must each fail.

Also hosts health_sweep(), the rendered Chart Health reader used by
tests/test_jeg69_direction_check.py.
"""
from __future__ import annotations

import json
import unittest

from pipelines.vorp_translation import unified
from tests.test_published_league_settings_engine import INDEX as _INDEX
from tests.test_published_league_settings_engine import (
    FIXTURE, POSITIONS, SAVED_SHAPE, browser_inputs, browser_players, peers_ranked,
)
from tests.test_published_league_settings_render import APP, _server
import re

PUBLISHED = ("cbs", "fantasypros", "usatoday", "fantasycalc")
RAW_VORP = ("espn_vorp", "cbsros_vorp", "razzball_vorp")
CUSTOM_ROSTER = {"RB": 3, "FLEX": 2, "BENCH": 8}
MIN_SHARED = 40
REL_TOL = 1e-6
VALUE_TOL = 1e-9
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (scoring, teams, roster overrides or None, bench share in PERCENT -- the
# TradeValueCurveControls.setBenchShare unit -- or None)
SETTINGS = [(s, t, None, None) for s in ("standard", "half_ppr", "ppr") for t in (8, 10, 12, 14)]
SETTINGS += [("ppr", 12, CUSTOM_ROSTER, None), ("ppr", 12, None, 30), ("half_ppr", 10, None, 5)]

READ = """() => {
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const d = window.TradeValueCurveDiagnostics || {};
  const out = {maps: {}, viewInvariants: d.viewInvariants || null, viewMode: d.viewMode};
  maps.forEach((m, k) => { out.maps[k] = Object.fromEntries([...m.entries()]); });
  return out;
}"""
READ_HEALTH = """() => [...document.querySelectorAll('#chartHealthList li')].map(li => [
  li.querySelector('.health-name')?.textContent || '', li.className.replace('health-', '')])"""


def _chromium(playwright):
    import os
    import shutil
    from pathlib import Path
    for candidate in (os.environ.get("CHROMIUM_PATH"), playwright.chromium.executable_path,
                      CHROME, shutil.which("chromium")):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _serve(body):
    def handler(route):
        route.fulfill(status=200, content_type="text/javascript", body=body)
    return handler


def _label(scoring, teams, roster, share):
    return f"{scoring}/{teams}" + ("/custom" if roster else "") + (f"/bench{share}pct" if share is not None else "")


def _sweep(settings, overrides=None, views=("indexed", "vorp", "adj"), health=False):
    """{label: {view: READ result}} (+ {"_health": [...]}) for each setting."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    out, errors = {}, []
    with _server() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
        try:
            for scoring, teams, roster, share in settings:
                page = browser.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                for pattern, body in (overrides or {}).items():
                    page.route(pattern, _serve(body))
                page.goto(url, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveHarness && window.TradeValueCurveDiagnostics",
                                       timeout=30000)
                page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; c.setScoring(s); c.setTeams(t); }",
                              [scoring, teams])
                for key, value in (roster or {}).items():
                    page.evaluate("""([k, v]) => { const i = document.querySelector(`[data-roster-key="${k}"]`);
                                      i.value = v; i.dispatchEvent(new Event('change')); }""", [key, value])
                if share is not None:
                    page.evaluate("(s) => window.TradeValueCurveControls.setBenchShare(s)", share)
                label = _label(scoring, teams, roster, share)
                out[label] = {}
                if health:
                    out[label]["_health"] = page.evaluate(READ_HEALTH)
                for view in views:
                    page.locator(f'#viewModeTabs [data-view-mode="{view}"]').click()
                    out[label][view] = page.evaluate(READ)
                page.close()
        finally:
            browser.close()
    out["_errors"] = errors
    return out


def health_sweep(widget_body=None, shapes=None):
    """{"scoring/teams": [(check name, status)]} from the live Chart Health
    panel at each shape (default: the 12 combos), optionally with a different
    curve-widget.js served."""
    shapes = shapes or [(s, t) for s in ("standard", "half_ppr", "ppr") for t in (8, 10, 12, 14)]
    overrides = {"**/assets/curve-widget.js*": widget_body} if widget_body else None
    swept = _sweep([(s, t, None, None) for s, t in shapes], overrides, views=(), health=True)
    return {label: [tuple(row) for row in res["_health"]] for label, res in swept.items()
            if not label.startswith("_")}


# --- independent reference -------------------------------------------------

def player_names():
    html = _INDEX.read_text(encoding="utf-8")
    m = re.search(r'<script id="players-data" type="application/json">(.*?)</script>', html, re.S)
    return {p["player_key"]: str(p.get("name") or "") for p in json.loads(m.group(1))["players"]
            if isinstance(p.get("player_key"), int)}


def role_map(values, pos_of, names, teams, shape):
    """Independent port of ValueModel.roleMap: dedicated slots by value, then
    flex (RB/WR/TE, plus QB under SUPERFLEX), then bench, by value."""
    rows = [(k, v) for k, v in values.items() if pos_of.get(k) in POSITIONS and v > 0]
    rows.sort(key=lambda r: (-r[1], names.get(r[0], ""), r[0]))
    roles = {}
    for pos in POSITIONS:
        for k, _ in [r for r in rows if pos_of[r[0]] == pos][:teams * shape.get(pos, 0)]:
            roles[k] = "starter"
    elig = ("QB", "RB", "WR", "TE") if shape.get("SUPERFLEX") else ("RB", "WR", "TE")
    for k, _ in [r for r in rows if pos_of[r[0]] in elig and r[0] not in roles][:teams * shape.get("FLEX", 0)]:
        roles[k] = "starter"
    for k, _ in [r for r in rows if r[0] not in roles][:teams * shape.get("BENCH", 0)]:
        roles[k] = "bench"
    return roles



def shared_totals(values, anchor, pos_of):
    keys = [k for k in values if pos_of.get(k) in POSITIONS and k in anchor]
    return len(keys), sum(max(0.0, values[k]) for k in keys), sum(max(0.0, anchor[k]) for k in keys)


def scale_to_shared_total(values, anchor, pos_of):
    """Independent port of ValueModel.scaleToSharedTotal."""
    n, total, target = shared_totals({k: v for k, v in values.items()}, anchor, pos_of)
    if n < MIN_SHARED or not target > 0:
        return dict(values)
    positive = sum(max(0.0, values[k]) for k in values
                   if pos_of.get(k) in POSITIONS and k in anchor and values[k] > 0)
    scale = target / positive if positive > 0 else 1.0
    return {k: max(0.0, v) * scale for k, v in values.items()}


def chart_vorp_and_roles(fixture, pos_of, source, scoring, teams, shape):
    """translate_ranked's value above waivers and the chart's own roles
    (starter = dedicated + flex count at the position, then bench), for every
    player the chart saves; 0 / no role below its waiver line."""
    native, saved, _ = browser_inputs(fixture, pos_of, source, scoring)
    peers = {p: browser_inputs(fixture, pos_of, p, scoring)[0] for p in PUBLISHED if p != source}
    ranked = {p: [] for p in POSITIONS}
    for key, value in native:
        ranked[pos_of[key]].append((str(key), str(key), float(value)))
    for p in POSITIONS:
        ranked[p].sort(key=lambda r: -r[2])
    elig = ["QB", "RB", "WR", "TE"] if shape.get("SUPERFLEX") else None
    at = unified.translate_ranked(ranked, teams, shape["BENCH"], shape["FLEX"],
                                  slots={p: shape[p] for p in POSITIONS}, flex_eligible=elig,
                                  peers=peers_ranked(peers, pos_of))
    vorp, roles = {}, {}
    for p in POSITIONS:
        info = at["positions"].get(p)
        if not info:
            continue
        n_start = info["n_dedicated"] + info["n_flex"]
        for i, (key, _name, _value) in enumerate(ranked[p]):
            t = at["translated"].get(key)
            if t is not None:
                vorp[int(key)] = t["vorp"]
                roles[int(key)] = "starter" if i < n_start else "bench"
    return {k: vorp.get(k, 0.0) for k, _ in saved}, roles


def expected_adjusted(vorp, roles, anchor, anchor_roles, pos_of):
    budget, source = {}, {}
    for k, v in vorp.items():
        if k not in anchor or pos_of.get(k) not in POSITIONS:
            continue
        if anchor_roles.get(k) in ("starter", "bench"):
            g = (pos_of[k], anchor_roles[k])
            budget[g] = budget.get(g, 0.0) + max(0.0, anchor[k])
        if roles.get(k) in ("starter", "bench"):
            g = (pos_of[k], roles[k])
            source[g] = source.get(g, 0.0) + max(0.0, v)
    out = {}
    for k, v in vorp.items():
        g = (pos_of.get(k), roles.get(k))
        rate = budget.get(g, 0.0) / source[g] if source.get(g, 0.0) > 0 else 0.0
        out[k] = max(0.0, v) * rate if roles.get(k) else 0.0
    return out, budget, source


def group_shares(values, roles, pos_of):
    totals, s = {}, 0.0
    for k, v in values.items():
        if roles.get(k) in ("starter", "bench") and pos_of.get(k) in POSITIONS and v > 0:
            g = (pos_of[k], roles[k])
            totals[g] = totals.get(g, 0.0) + v
            s += v
    return {g: t / s for g, t in totals.items()} if s else {}


def verify(swept):
    """(problems, table): every invariant, recomputed from the plotted maps."""
    fixture = json.loads(FIXTURE.read_text())
    pos_of = browser_players()
    names = player_names()
    problems, table = [], {}
    problems += [f"page error: {e[:200]}" for e in swept.get("_errors", [])]
    for label, views in swept.items():
        if label.startswith("_"):
            continue
        parts = label.split("/")
        scoring, teams = parts[0], int(parts[1])
        shape = {**SAVED_SHAPE, **(CUSTOM_ROSTER if "custom" in parts else {})}
        for view, res in views.items():
            maps = {k: {int(pk): v for pk, v in m.items()} for k, m in res["maps"].items()}
            anchor = maps["espn"]
            vi = res["viewInvariants"]
            if not vi or vi.get("ok") is not True:
                bad = vi and {v: [k for k, r in vi[v]["sources"].items() if not r["ok"]]
                              for v in ("indexed", "vorp", "adjusted")}
                problems.append(f"{label} [{view} tab]: page viewInvariants not ok: {bad}")
            anchor_roles = role_map(anchor, pos_of, names, teams, shape)

            def total_check(name, values):
                n, total, target = shared_totals(values, anchor, pos_of)
                ratio = total / target if target else float("nan")
                table[(label, view, name)] = (n, round(ratio, 6))
                if n < MIN_SHARED or abs(total - target) > REL_TOL * target:
                    problems.append(f"{label} {view} {name}: shared total {total:.4f} vs anchor {target:.4f} "
                                    f"(n={n}, ratio {ratio:.6f})")

            if view == "indexed":
                for key, values in maps.items():
                    if key == "espn" or not values:
                        continue
                    total_check(key, values)
                    if key in PUBLISHED:
                        own = group_shares(values, role_map(values, pos_of, names, teams, shape), pos_of)
                        anc = group_shares({k: anchor[k] for k in values if k in anchor}, anchor_roles, pos_of)
                        diff = max(abs(own.get(g, 0) - anc.get(g, 0)) for g in set(own) | set(anc))
                        if diff <= 1e-3:
                            problems.append(f"{label} indexed {key}: split forced onto the anchor's ({diff})")
            elif view == "vorp":
                for key in PUBLISHED + RAW_VORP:
                    if maps.get(key):
                        total_check(key, maps[key])
                for key in PUBLISHED:
                    vorp, _ = chart_vorp_and_roles(fixture, pos_of, key, scoring, teams, shape)
                    want = scale_to_shared_total(vorp, anchor, pos_of)
                    got = maps.get(key, {})
                    if set(got) != set(want):
                        problems.append(f"{label} vorp {key}: player sets differ")
                        continue
                    worst = max((abs(want[k] - got[k]) for k in want), default=0.0)
                    if worst > VALUE_TOL:
                        problems.append(f"{label} vorp {key}: values off the reference by {worst:.3g}")
            elif view == "adj":
                for key in PUBLISHED:
                    vorp, roles = chart_vorp_and_roles(fixture, pos_of, key, scoring, teams, shape)
                    want, budget, source = expected_adjusted(vorp, roles, anchor, anchor_roles, pos_of)
                    got = maps.get(key, {})
                    if set(got) != set(want):
                        problems.append(f"{label} adj {key}: player sets differ")
                        continue
                    worst = max((abs(want[k] - got[k]) for k in want), default=0.0)
                    if worst > VALUE_TOL:
                        problems.append(f"{label} adj {key}: values off the reference by {worst:.3g}")
                    for g, b in budget.items():
                        if source.get(g, 0.0) <= 0:
                            continue  # unfunded: the chart puts nobody of the anchor's in g
                        shown = sum(got[k] for k in got if k in anchor and (pos_of.get(k), roles.get(k)) == g)
                        table[(label, "adj", key, g)] = (round(shown, 4), round(b, 4))
                        if abs(shown - b) > REL_TOL * max(1.0, b):
                            problems.append(f"{label} adj {key} {g}: group total {shown:.4f} vs DDF {b:.4f}")
    return problems, table


def _widget():
    return (APP / "assets" / "curve-widget.js").read_text()


def _model():
    return (APP / "assets" / "value-model.js").read_text()


class ViewInvariants(unittest.TestCase):
    def test_every_view_holds_its_invariant(self):
        swept = _sweep(SETTINGS)
        problems, table = verify(swept)
        n = sum(1 for k in table)
        print(f"\n[views-invariants-001] settings={len(SETTINGS)} checks={n} problems={len(problems)}")
        self.assertGreater(n, 400)
        self.assertEqual(problems, [], "\n".join(problems[:25]))

    def test_guard_fails_on_broken_engines(self):
        widget, model = _widget(), _model()
        broken = {
            # Indexed back to the bare translation (no total factor): the
            # pre-2026-10-08 engine, totals 0.69-1.45x the anchor's.
            "indexed-unscaled": {"**/assets/curve-widget.js*": widget.replace(
                "    return ValueModel.scaleToSharedTotal({values: buildPublishedSourceMap(key), anchor,\n"
                "      playerOf: playerKey => canonicalByKey.get(playerKey)});",
                "    return buildPublishedSourceMap(key);")},
            # VORP vs waivers on the old per-chart budget basis.
            "vorp-old-basis": {"**/assets/curve-widget.js*": widget.replace(
                "    return ValueModel.scaleToSharedTotal({values: entry.rawVorp, anchor, playerOf});",
                "    return new Map(entry.vorp);")},
            # Adjusted capped so the top player is 70 (published-views-001).
            "adj-top-70": {"**/assets/curve-widget.js*": widget.replace(
                '    if (viewKey === "adj_values") {\n',
                '    if (viewKey === "adj_values") {\n      return new Map(entry.adj);\n')},
            # Adjusted with one factor (no position x starter/bench groups).
            "adj-one-factor": {"**/assets/value-model.js*": model.replace(
                '    return role === "starter" || role === "bench" ? player.pos + "|" + role : null;',
                '    return role === "starter" || role === "bench" ? "QB|starter" : null;')},
        }
        settings = [("ppr", 12, None, None), ("standard", 10, None, None)]
        for name, overrides in broken.items():
            for pattern, body in overrides.items():
                original = widget if "curve-widget" in pattern else model
                self.assertNotEqual(body, original, f"mutation anchor for {name} moved")
            problems, _ = verify(_sweep(settings, overrides))
            print(f"\n[views-invariants-001 negative test] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"broken engine {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
