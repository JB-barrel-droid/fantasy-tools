"""JEG-1081 PR 6: the Waivers view selector, pure rules in app/v2/waivers.js (and the noise floor in finder.js).

The user picks the view that decides each verdict: DDF Value (default), DDF Value (projections), Trade chart average, any single
source, or the Overrides basis (the DDF Value key). Verdicts, drops, the headline and the combos recompute for that view; the
other views are shown as context ("+2.1 on projections, +1.8 on market"). Noise floor per choice: DDF Value, half the gap between
its chart and projection versions; projections, the standard error of ESPN / CBS rest of season / Razzball; market, the standard
error of the four charts; one source: 0, so the net floor 0.05 decides.

Frozen fixture "view-switch" (written here, never edited to pass): a thin-RB roster (QB 20/12, RB 30/20, WR 20/18/10/8, TE 6, full
roster) and three RB candidates priced in every view:
  * Cdd  DDF Value 40, projections 3, market 40: DDF Value says pick up, the projections say it is not a gain (3 is below what he replaces);
  * Pro  DDF Value 3, projections 40, market 3: the projections say pick up, DDF Value says not;
  * Both 40 / 40 / 40: every view says pick up;
  * Tiny 40 / 40 / 0.02: no market price (a value that shows 0.0 is no price): Not evaluated on the market view only.
Cases: the selector flips verdicts; the context names the other views; a single source has tau 0.05; a candidate with no value in the
chosen view is Not evaluated (never 0); the default view's output is identical to calling without a view; the basis choice judges
on the DDF Value key but says so; combos and the headline follow the view.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of the rules with one broken.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_balance import ALLOC, SHAPE

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_JS = ROOT / "app" / "v2" / "waivers.js"
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

PRELUDE = """
const fs = require('fs');
const W = require(process.argv[1]);
const F = require(process.argv[2]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const row = p => { const v = {ddf_value: p.ddf, ddf_value_charts: p.ddf, ddf_value_projections: p.proj, chart_avg: p.market,
  usatoday: p.market, fantasycalc: p.market, fantasypros: p.market, cbs: p.market, espn: p.proj, cbsros: p.proj, razzball: p.proj};
  Object.keys(v).forEach(k => { if (v[k] === null) delete v[k]; });
  return {player_key: p.key, name: p.name, pos: p.pos, team: '', values: v}; };
const ctxFor = (viewId, extra) => ({shape: input.shape, expected: F.expectedDepth(input.alloc, 12), chartKeys: input.charts, rosterSize: W.rosterSizeOf(input.shape),
  weights: {QB: 0.15, RB: 0.15, WR: 0.15, TE: 0.15, overall: 0.15}, view: viewId === undefined ? undefined : W.viewFor(viewId, input.basisName), ...(extra || {})});
const mine = input.mine.map(row), cands = input.cands.map(row);
const out = (function () { %s })();
console.log(JSON.stringify(out));
"""


def node(js: Path, body: str, payload: dict):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    result = subprocess.run(["node", "-e", PRELUDE % body, str(js), str(js.parent / "finder.js")], input=json.dumps(payload), check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def p(key, pos, ddf, proj="same", market="same"):
    return {"key": key, "name": key, "pos": pos, "ddf": ddf, "proj": ddf if proj == "same" else proj, "market": ddf if market == "same" else market}


MINE = [p("q1", "QB", 20), p("q2", "QB", 12), p("r1", "RB", 30), p("r2", "RB", 20), p("w1", "WR", 20), p("w2", "WR", 18), p("w3", "WR", 10), p("w4", "WR", 8), p("t1", "TE", 6), p("bx", "WR", 1, 45, 50)]
CANDS = [p("Cdd", "RB", 40, 3, 40), p("Pro", "RB", 3, 40, 3), p("Both", "RB", 40, 40, 40), p("Tiny", "RB", 40, 40, 0.02)]
PAYLOAD = {"shape": SHAPE, "alloc": ALLOC, "charts": CHARTS, "mine": MINE, "cands": CANDS, "basisName": "FantasyCalc"}

RUN = """
const ids = ['ddf', 'projections', 'market', 'basis', 'src:fantasycalc', 'src:espn'];
const res = {};
ids.forEach(id => {
  const r = W.evaluateAll(ctxFor(id), mine, cands);
  res[id] = {verdicts: Object.fromEntries(r.results.map(x => [x.name, x.verdict])), tau: Object.fromEntries(r.results.map(x => [x.name, x.tau])),
    total: Object.fromEntries(r.results.map(x => [x.name, x.totalDelta])), starter: Object.fromEntries(r.results.map(x => [x.name, x.starterDelta])),
    drop: Object.fromEntries(r.results.map(x => [x.name, x.drop ? x.drop.name : null])), context: Object.fromEntries(r.results.map(x => [x.name, x.context])),
    reasons: Object.fromEntries(r.results.map(x => [x.name, x.reason])), headline: r.headline.text, headlineContext: r.headline.context, view: r.view.id, combos: r.combos.length};
});
const plain = W.evaluateAll(ctxFor(undefined), mine, cands);
const dflt = W.evaluateAll(ctxFor('ddf'), mine, cands);
res.plainSame = JSON.stringify(plain.results.map(x => [x.name, x.verdict, x.totalDelta, x.reason])) === JSON.stringify(dflt.results.map(x => [x.name, x.verdict, x.totalDelta, x.reason]))
  && plain.headline.text === dflt.headline.text;
res.viewFor = {unknown: W.viewFor('nonsense').id, srcBad: W.viewFor('src:nope').id, key: W.viewFor('src:fantasycalc').key, proj: W.viewFor('projections').key, market: W.viewFor('market').key, basis: W.viewFor('basis').key};
// a candidate with no projection: Not evaluated on the projections view, evaluated on DDF Value
const nop = W.evaluateAll(ctxFor('projections'), mine, [row({key: 'NoP', name: 'NoP', pos: 'RB', ddf: 40, proj: null, market: 40})]);
const nod = W.evaluateAll(ctxFor('ddf'), mine, [row({key: 'NoP', name: 'NoP', pos: 'RB', ddf: 40, proj: null, market: 40})]);
res.noProj = {projections: nop.results[0].verdict, kind: nop.results[0].reasonKind, total: nop.results[0].totalDelta, ddf: nod.results[0].verdict, ddfContext: nod.results[0].context};
return res;
"""


COMBO = """
const out = {};
['ddf', 'projections', 'src:fantasycalc'].forEach(id => {
  const r = W.evaluateAll(ctxFor(id), mine, cands);
  out[id] = r.combos.map(k => k.candidates.map(c => c.name).sort().join('+'));
});
return out;
"""
# A roster with no RB: adding two RBs fills two starting slots, so a pair beats either single. CaCb are priced 40 in DDF Value and 0.5 in
# the projections; PaPb the other way round; MaMb are priced 18 in DDF Value and the market but -20 in the projections, so DDF Value's own noise
# (half the charts-vs-projections gap) hides the pair that a single source, with no spread, shows. A pair exists only in the view that prices it.
COMBO_PAYLOAD = {"shape": SHAPE, "alloc": ALLOC, "charts": CHARTS, "basisName": "x",
                 "mine": [m for m in MINE if m["pos"] != "RB" and m["key"] != "bx"] + [p("w5", "WR", 9), p("w6", "WR", 7), p("q3", "QB", 4)],
                 "cands": [p("Ca", "RB", 40, 0.5, 40), p("Cb", "RB", 40, 0.5, 40), p("Pa", "RB", 0.5, 40, 0.5), p("Pb", "RB", 0.5, 40, 0.5),
                           p("Ma", "RB", 18, -20, 18), p("Mb", "RB", 18, -20, 18)]}


def check(waivers_js: Path) -> list[str]:
    errors = []
    say = errors.append
    r = node(waivers_js, RUN, PAYLOAD)
    pick, skip = "Pick up", "Skip"
    # 1. The disagreement flips verdicts both ways: the selector changes the answer.
    if r["ddf"]["verdicts"]["Cdd"] != pick or r["projections"]["verdicts"]["Cdd"] == pick:
        say(f"Cdd (DDF 40, proj 3): DDF Value {r['ddf']['verdicts']['Cdd']}, projections {r['projections']['verdicts']['Cdd']}; want Pick up then not")
    if r["ddf"]["verdicts"]["Pro"] == pick or r["projections"]["verdicts"]["Pro"] != pick:
        say(f"Pro (DDF 3, proj 40): DDF Value {r['ddf']['verdicts']['Pro']}, projections {r['projections']['verdicts']['Pro']}; want not then Pick up")
    if any(r[v]["verdicts"]["Both"] != pick for v in ("ddf", "projections", "market", "basis", "src:fantasycalc")):
        say(f"Both (40 everywhere): {[(v, r[v]['verdicts']['Both']) for v in ('ddf', 'projections', 'market')]}")
    if r["market"]["verdicts"]["Cdd"] != pick or r["market"]["verdicts"]["Pro"] == pick:
        say(f"market view follows the market column: {r['market']['verdicts']}")
    # 2. The context names the other views with the same swap (and never the view that decides).
    ctx = r["ddf"]["context"]["Cdd"]
    if "on projections" not in ctx or "on market" not in ctx or "on DDF Value" in ctx:
        say(f"DDF Value view context {ctx!r}")
    ctx = r["projections"]["context"]["Cdd"]
    if "on DDF Value" not in ctx or "on market" not in ctx or "on projections" in ctx:
        say(f"projections view context {ctx!r}")
    ctx = r["market"]["context"]["Pro"]
    if "on DDF Value" not in ctx or "on projections" not in ctx or "on market" in ctx:
        say(f"market view context {ctx!r}")
    if r["projections"]["total"]["Cdd"] >= r["ddf"]["total"]["Cdd"]:
        say("the projections view should read the swap lower than DDF Value for Cdd")
    # 2b. The swap itself (starter change) and the best drop are read in the deciding view.
    if abs(r["projections"]["starter"]["Cdd"] - r["ddf"]["starter"]["Cdd"]) < 1:
        say(f"starter change identical in both views: {r['projections']['starter']['Cdd']} vs {r['ddf']['starter']['Cdd']}")
    if r["ddf"]["drop"]["Both"] == r["projections"]["drop"]["Both"]:
        say(f"the best drop is the same in both views ({r['ddf']['drop']['Both']}); bx is priced 1 in DDF Value and 45 in the projections")
    if "on DDF Value" in r["basis"]["context"]["Cdd"] or "on projections" not in r["basis"]["context"]["Cdd"]:
        say(f"basis view context {r['basis']['context']['Cdd']!r}")
    if r["market"]["verdicts"]["Tiny"] != "Not evaluated" or r["ddf"]["verdicts"]["Tiny"] != pick:
        say(f"Tiny (market 0.02): market {r['market']['verdicts']['Tiny']}, DDF Value {r['ddf']['verdicts']['Tiny']}")
    # 2c. A roster player the deciding view cannot price is not the first drop while a priced player is (a good player with no projection).
    gh = node(waivers_js, RUN, {**PAYLOAD, "mine": MINE + [{"key": "gh", "name": "gh", "pos": "WR", "ddf": 25, "proj": None, "market": 25}]})
    if gh["projections"]["drop"]["Both"] == "gh":
        say("a roster player with no projection value was chosen as the first drop on the projections view")
    # 3. Noise floor per choice: a single source has no spread, so the net floor 0.05 decides.
    if any(abs(r["src:fantasycalc"]["tau"][n] - 0.05) > 1e-9 for n in ("Cdd", "Pro", "Both")):
        say(f"single source tau {r['src:fantasycalc']['tau']}, want 0.05")
    if any(abs(r["src:espn"]["tau"][n] - 0.05) > 1e-9 for n in ("Cdd", "Pro", "Both")):
        say(f"single projection source tau {r['src:espn']['tau']}, want 0.05")
    if not r["ddf"]["tau"]["Cdd"] > 1:
        say(f"DDF Value tau for Cdd (charts 40, projections 3) should be well above the floor: {r['ddf']['tau']['Cdd']}")
    flat = node(waivers_js, RUN, {**PAYLOAD, "mine": [m for m in MINE if m["key"] != "bx"]})
    if abs(flat["ddf"]["tau"]["Both"] - 0.05) > 1e-9:
        say(f"DDF Value tau where the two readings agree: {flat['ddf']['tau']['Both']}, want 0.05")
    # 4. A candidate no view prices is Not evaluated in that view, never 0; the DDF view still judges him.
    n = r["noProj"]
    if n["projections"] != "Not evaluated" or n["kind"] != "noview" or n["total"] is not None or n["ddf"] != pick:
        say(f"no projection value: {n}")
    if "on projections" in (n["ddfContext"] or ""):
        say(f"context printed a projections reading for a player with none: {n['ddfContext']!r}")
    # 5. The default view is the old behaviour byte for byte; unknown ids fall back to it.
    if not r["plainSame"]:
        say("evaluateAll with no view differs from the DDF Value view")
    v = r["viewFor"]
    if v != {"unknown": "ddf", "srcBad": "ddf", "key": "fantasycalc", "proj": "ddf_value_projections", "market": "chart_avg", "basis": "ddf_value"}:
        say(f"viewFor {v}")
    # 6. Basis: DDF Value's key, said in the reason and headline; headline and views carry through.
    if r["basis"]["verdicts"] != r["ddf"]["verdicts"] or "Overrides basis (FantasyCalc)" not in r["basis"]["reasons"]["Both"] or "Overrides basis" not in r["basis"]["headline"]:
        say(f"basis view: {r['basis']['headline']!r} {r['basis']['reasons']['Both'][:120]!r}")
    if "judged on" in r["ddf"]["headline"] or "(judged on DDF Value (projections))" not in r["projections"]["headline"]:
        say(f"headline view note: ddf {r['ddf']['headline']!r}, projections {r['projections']['headline']!r}")
    if not r["ddf"]["headlineContext"] or "on projections" not in r["ddf"]["headlineContext"]:
        say(f"headline context {r['ddf']['headlineContext']!r}")
    # 7. Combos follow the view: a pair that only one view prices is a combo in that view only.
    combos = node(waivers_js, COMBO, COMBO_PAYLOAD)
    if "Ca+Cb" not in combos["ddf"] or "Ca+Cb" in combos["projections"] or "Pa+Pb" not in combos["projections"] or "Pa+Pb" in combos["ddf"]:
        say(f"combos by view {combos}: want Ca+Cb in DDF Value only and Pa+Pb in the projections only")
    if "Ma+Mb" in combos["ddf"] or "Ma+Mb" not in combos["src:fantasycalc"]:
        say(f"combos by view {combos}: want Ma+Mb in the single source (no noise) and not in DDF Value (noise {18 + 20} apart)")
    return errors


MUTANTS = {
    "combos ignore the view": ("const key = (ctx.view || viewFor(VIEW_DEFAULT)).key;\n    const out = [];", "const key = OUR_KEY;\n    const out = [];"),
    "combo noise ignores the view": ("Math.pow(valueNoise(r, key, ctx.chartKeys || undefined), 2)", "Math.pow(valueNoise(r, OUR_KEY, ctx.chartKeys || undefined), 2)"),
    "unpriced players dropped first": ("Number(unpriced(a.row)) - Number(unpriced(b.row)) || a.marginal - b.marginal", "a.marginal - b.marginal"),
    "no market price read as a price": ("return finite(v) && (key !== MARKET_KEY || v >= USABLE_MIN) ? v : null;", "return finite(v) ? v : null;"),
    "view ignored in the swap": ("const impact = rosterImpact(roster, leaving, [candidate], ctx.shape, key);", "const impact = rosterImpact(roster, leaving, [candidate], ctx.shape, OUR_KEY);"),
    "view ignored in the fit": ("z: FIT_Z}, key);", "z: FIT_Z}, OUR_KEY);"),
    "view ignored in the drop": ("dropRanking(roster, ctx.shape, key, weights)[0]", "dropRanking(roster, ctx.shape, OUR_KEY, weights)[0]"),
    "no value in the view read as a value": ("if (viewValueOf(candidate, key) === null) {", "if (false) {"),
    "context includes the deciding view": ("v.key !== view.key && (v.key", "(v.key"),
    "context reads the wrong view": ("worthChange(roster, leaving, candidate, ctx.shape, v.key, weights)", "worthChange(roster, leaving, candidate, ctx.shape, OUR_KEY, weights)"),
    "single source keeps a chart noise": ("    return 0;   // one source", "    return 1;   // one source"),
    "headline without the view note": ('const on = view && (view.key !== OUR_KEY || view.id === "basis") ? ` (judged on ${view.label})` : "";', 'const on = "";'),
    "basis not said": ('if (key !== OUR_KEY || view.id === "basis") reason +=', 'if (key !== OUR_KEY) reason +='),
    "unknown view not defaulted": ('return {id: VIEW_DEFAULT, key: OUR_KEY, label: "DDF Value", short: "DDF Value"};', 'return {id, key: id, label: id, short: id};'),
}


class WaiversViewTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(WAIVERS_JS), [])

    def test_checks_fail_on_broken_builds(self):
        files = {name: (WAIVERS_JS.parent / name).read_text(encoding="utf-8") for name in ("waivers.js", "finder.js")}
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                target = "finder.js" if "one source" in old else "waivers.js"
                self.assertIn(old, files[target], f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    for fname, text in files.items():
                        (Path(tmp) / fname).write_text(text.replace(old, new, 1) if fname == target else text, encoding="utf-8")
                    try:
                        caught = check(Path(tmp) / "waivers.js")
                    except (subprocess.CalledProcessError, KeyError, TypeError, ValueError):
                        caught = ["the broken build crashed"]
                    self.assertTrue(caught, f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
