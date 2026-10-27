"""v2 Waivers tab (JEG-1022), the rules in app/v2/waivers.js (T1-T8, T13, T14 of the spec), on six frozen fixtures.

Fixtures (tests/fixtures/waiver-*.json) are PROTECTED: the first three are the training set (the noise floor and the
verdict boundaries were checked against them), the last three are held out (their verdicts must come out right with
no change to a threshold). Each fixture carries the expected verdicts, drops and numbers, worked out by hand from the
rows in the file before the code was run; nothing here is read back from the code's own output.

  * T1 marginal value: a bench player leaves less behind than a starter; a kicker or defense leaves 0;
  * T2 best drop: the lowest marginal value; a surplus kicker is the first drop, a required one is never offered;
  * T3 the add / drop swap equals finder.js rosterImpact (starter, bench, total) and the numbers match the fixtures;
  * T4 verdict: pick up / force / consider / hold / skip / not evaluated flip at the noise floor (tau);
  * T5 order: pick up first (biggest gain first), skip after hold, not evaluated last;
  * T6 two-for-two: a pair that beats both singles by more than the noise is listed; a pair that does not is not;
    at most 100 pairs are searched;
  * T7 a candidate already on the roster is dropped, a repeat is dropped once;
  * T8 kickers, defenses and players with no DDF Value are Not evaluated; market value is shown when the charts price them;
  * T13 the share link round-trips roster keys, candidate keys and the league settings;
  * T14 a candidate who enters the lineup says where he starts; one who stays on the bench says "Bench stash".

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of waivers.js with one rule broken.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_JS = ROOT / "app" / "v2" / "waivers.js"
FIXTURES = ROOT / "tests" / "fixtures"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

PRELUDE = """
const fs = require('fs');
const W = require(process.argv[1]);
const F = require(process.argv[1].replace(/waivers\\.js$/, 'finder.js'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const row = p => ({player_key: p.key, name: p.name, pos: p.pos, team: p.team, notEvaluated: Boolean(p.notEvaluated),
  values: p.ddf === null ? {usatoday: p.market, fantasycalc: p.market, fantasypros: p.market, cbs: p.market}
    : {ddf_value: p.ddf, ddf_value_charts: p.ddf - p.noise, ddf_value_projections: p.ddf + p.noise, usatoday: p.market, fantasycalc: p.market, fantasypros: p.market, cbs: p.market}});
const ctxOf = fx => ({shape: fx.shape, expected: F.expectedDepth(fx.alloc, fx.teams), chartKeys: %s, rosterSize: W.rosterSizeOf(fx.shape), weights: fx.weights});
const out = (function () { %s })();
console.log(JSON.stringify(out));
"""


def node(js: Path, body: str, payload: dict):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    result = subprocess.run(["node", "-e", PRELUDE % (json.dumps(CHARTS), body), str(js)], input=json.dumps(payload),
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"waiver-{name}.json").read_text(encoding="utf-8"))


EVALUATE = """
const fx = input.fx;
const c = W.evaluateAll(ctxOf(fx), fx.roster.map(row), fx.candidates.map(row));
return {results: c.results.map(r => ({name: r.name, verdict: r.verdict, drop: r.drop ? r.drop.name : null, openSlot: Boolean(r.openSlot),
  starter: r.starterDelta, bench: r.benchDelta, total: r.totalDelta, tau: r.tau, market: r.market, slot: r.slot, starts: r.starts, reason: r.reason})),
  combos: c.combos.map(k => ({names: k.candidates.map(x => x.name), drops: k.drops.map(x => x.name), total: k.totalDelta})),
  headline: c.headline.text, state: c.headline.state};
"""


def evaluate(js, fx):
    return node(js, EVALUATE, {"fx": fx})


def close(a, b):
    return a is not None and abs(a - b) < 1e-6


def check_fixtures(js: Path) -> list[str]:
    errors = []
    for name in ("thin-rb", "deep-wr", "qb-streaming", "empty-slot-kdef", "no-chart-value", "all-worse"):
        fx = load(name)
        want = fx["expect"]
        got = evaluate(js, fx)
        by = {r["name"]: r for r in got["results"]}
        tag = f"[{name}] "
        for who, verdict in want["verdicts"].items():
            if by[who]["verdict"] != verdict:
                errors.append(tag + f"{who}: verdict {by[who]['verdict']!r}, want {verdict!r}")
        for who, drop in (want.get("drops") or {}).items():
            if by[who]["drop"] != drop:
                errors.append(tag + f"{who}: best drop {by[who]['drop']!r}, want {drop!r}")
        for who, flag in (want.get("openSlot") or {}).items():
            if by[who]["openSlot"] != flag:
                errors.append(tag + f"{who}: open slot {by[who]['openSlot']}, want {flag}")
        for key, field in (("starter", "starter"), ("total", "total"), ("tau", "tau")):
            for who, value in (want.get(key) or {}).items():
                if not close(by[who][field], value):
                    errors.append(tag + f"{who}: {field} {by[who][field]}, want {value}")
        for who, slot in (want.get("slot") or {}).items():
            if by[who]["slot"] != slot:
                errors.append(tag + f"{who}: slot {by[who]['slot']!r}, want {slot!r}")
        for who in (want.get("market") or {}):
            if by[who]["market"] is not None:
                errors.append(tag + f"{who}: market {by[who]['market']} where no chart prices him (want a dash)")
        for who, text in (want.get("reason_has") or {}).items():
            if text not in by[who]["reason"]:
                errors.append(tag + f"{who}: reason lacks {text!r}: {by[who]['reason']!r}")
        if [r["name"] for r in got["results"]] != want["order"]:
            errors.append(tag + f"order {[r['name'] for r in got['results']]}, want {want['order']}")
        if got["headline"] != want["headline"]:
            errors.append(tag + f"headline {got['headline']!r}, want {want['headline']!r}")
        if "combo_top" in want:
            top = got["combos"][0] if got["combos"] else None
            if not top or top["names"] != want["combo_top"] or not close(top["total"], want["combo_total"]):
                errors.append(tag + f"top combo {top}, want {want['combo_top']} at {want['combo_total']}")
        if want.get("combo") is False and got["combos"]:
            errors.append(tag + f"a combo is listed where none beats a single: {got['combos'][:1]}")
        if "combos" in want and [c["names"] for c in got["combos"]] != want["combos"]:
            errors.append(tag + f"combos {[c['names'] for c in got['combos']]}, want {want['combos']}")
    return errors


def check_unit(js: Path) -> list[str]:
    errors = []
    fx = load("thin-rb")
    # T1: marginal value. Tim TightTwo (bench TE, 2.0 at the TE bench weight 0.1) leaves 0.2 behind; Rex RunOne (starter 30) leaves more; the kicker 0.
    body = """
    const fx = input.fx; const rows = fx.roster.map(row); const shape = fx.shape;
    const by = n => rows.find(r => r.name === n);
    const m = n => W.marginalValue(rows, by(n), shape, 'ddf_value', input.fx.weights);
    return {bench: m('Tim TightTwo'), starter: m('Rex RunOne'), kicker: m('Kyle Kicker'), defense: m('Boston Defense'),
      ranking: W.dropRanking(rows, shape, 'ddf_value', input.fx.weights).map(x => [x.row.name, x.marginal])};
    """
    got = node(js, body, {"fx": fx})
    if not close(got["bench"], 0.2) or not (got["starter"] > got["bench"]):
        errors.append(f"T1 marginal: bench {got['bench']} starter {got['starter']}")
    if got["kicker"] != 0 or got["defense"] != 0:
        errors.append(f"T1 a kicker or defense has marginal {got['kicker']}/{got['defense']}, want 0")
    # T2: best drop is the lowest marginal; the required kicker / defense are not offered; a surplus kicker is first.
    names = [n for n, _ in got["ranking"]]
    if names[0] != "Tim TightTwo" or any(n in names for n in ("Kyle Kicker", "Boston Defense")):
        errors.append(f"T2 drop ranking {names}: want Tim TightTwo first and the required kicker and defense left out")
    if any(got["ranking"][i][1] > got["ranking"][i + 1][1] for i in range(len(got["ranking"]) - 1)):
        errors.append("T2 drop ranking is not in ascending marginal order")
    body2 = """
    const fx = input.fx; const rows = fx.roster.map(row); rows.push(row({key: 'x:K:ZZZ', name: 'Spare Kicker', pos: 'K', team: 'ZZZ', ddf: null, market: null, notEvaluated: true}));
    return W.dropRanking(rows, fx.shape, 'ddf_value', fx.weights).slice(0, 2).map(x => x.row.name);
    """
    first = node(js, body2, {"fx": fx})
    if first[0] not in ("Spare Kicker", "Kyle Kicker"):
        errors.append(f"T2 a surplus kicker is not the first drop: {first}")
    shape0 = dict(fx["shape"], K=0, DST=0)
    body3 = """
    const fx = input.fx; const rows = fx.roster.map(row);
    return W.dropRanking(rows, Object.assign({}, fx.shape, {K: 0, DST: 0}), 'ddf_value', fx.weights).slice(0, 2).map(x => x.row.name);
    """
    first = node(js, body3, {"fx": fx})
    if set(first) != {"Kyle Kicker", "Boston Defense"}:
        errors.append(f"T2 with no kicker or defense slot they are the first drops, got {first} ({shape0['K']})")
    # T3: the swap equals rosterImpact.
    body4 = """
    const fx = input.fx; const ctx = ctxOf(fx); const rows = fx.roster.map(row); const cands = fx.candidates.map(row);
    const res = W.evaluateCandidate(ctx, rows, cands[0]);
    const imp = F.rosterImpact(rows, [res.drop], [cands[0]], fx.shape, 'ddf_value');
    return {s: res.starterDelta, b: res.benchDelta, rb: res.rawBenchDelta, t: res.totalDelta, is: imp.starterDelta, ib: imp.benchDelta, it: imp.totalDelta};
    """
    g = node(js, body4, {"fx": fx})
    if not (close(g["s"], g["is"]) and close(g["b"], 1.0) and close(g["rb"], g["ib"]) and close(g["t"], g["s"] + g["b"]) and close(g["t"], 11.0)):
        errors.append(f"T3 swap {g} does not match rosterImpact (starters) / the hand sums: starters +10.0, weighted bench +1.0")
    # T4: the verdict flips at tau. Same swap, the candidate's gain moved across the noise floor.
    body5 = """
    const fx = input.fx; const ctx = ctxOf(fx);
    const mine = fx.roster.map(row);
    const probe = (value, noise) => { const c = row({key: 'P1', name: 'Probe', pos: 'RB', team: 'XXX', ddf: value, noise, market: value}); return W.evaluateCandidate(ctx, mine, c); };
    // The drop is Tim TightTwo (a bench TE, 2.0 x 0.1 = 0.2 of worth). A bench-level RB worth v adds 0.2 v at the RB bench
    // weight 0.2, so the gain is 0.2 v - 0.2. Noise n gives tau = max(0.05, n).
    return {tau: probe(5, 1.0).tau, below: probe(5.95, 1.0).verdict, above: probe(6.05, 1.0).verdict,
      lowBelow: probe(1.2, 0).verdict, lowAbove: probe(1.3, 0).verdict, neg: probe(0.5, 0).verdict, negIn: probe(0.9, 0).verdict, negNoisy: probe(0.0, 1.0).verdict};
    """
    g = node(js, body5, {"fx": fx})
    if not close(g["tau"], 1.0):
        errors.append(f"T4 tau {g['tau']}, want the 1.0 disagreement of the sources")
    if g["above"] != "Pick up" or g["below"] == "Pick up":
        errors.append(f"T4 pick-up boundary at tau: just above {g['above']!r}, just below {g['below']!r}")
    if g["lowAbove"] != "Pick up" or g["lowBelow"] == "Pick up":
        errors.append(f"T4 the 0.05 floor: {g['lowAbove']!r} above, {g['lowBelow']!r} below")
    if g["neg"] != "Skip" or g["negIn"] == "Skip":
        errors.append(f"T4 skip boundary: {g['neg']!r} below -tau, {g['negIn']!r} inside it")
    if g["below"] not in ("Consider", "Hold") or g["negIn"] not in ("Consider", "Hold") or g["negNoisy"] == "Skip":
        errors.append(f"T4 inside the noise floor the verdict is Consider or Hold, got {g['below']!r} / {g['negIn']!r} / {g['negNoisy']!r}")
    # T5: order of tiers (also checked per fixture above): pick up before skip before not evaluated.
    body6 = """
    const rank = W.TIER; const list = ['Not evaluated', 'Skip', 'Hold', 'Consider', 'Pick up (force)', 'Pick up'].map((v, i) => ({verdict: v, totalDelta: v === 'Not evaluated' ? null : i, ddf: 1}));
    return W.orderResults(list).map(r => r.verdict);
    """
    g = node(js, body6, {})
    if g != ["Pick up", "Pick up (force)", "Consider", "Hold", "Skip", "Not evaluated"]:
        errors.append(f"T5 verdict order {g}")
    # T6: the pair cap, and a pair that does not beat the better single is not listed (checked per fixture: all-worse has none).
    body7 = """
    const singles = Array.from({length: 30}, (_, i) => ({name: 'c' + i, totalDelta: 30 - i, ddf: 1}));
    const pairs = W.pairsOf(singles);
    return {n: pairs.length, first: pairs[0].map(c => c.name), cap: W.MAX_PAIRS, distinct: new Set(pairs.map(p => p.map(c => c.name).join('|'))).size};
    """
    g = node(js, body7, {})
    if g["n"] != 100 or g["cap"] != 100 or g["distinct"] != 100 or g["first"] != ["c0", "c1"]:
        errors.append(f"T6 pair cap/selection: {g}")
    # T6b: a combo is listed only if it is itself a gain; the singles here are given (falsely) as very bad, so only the
    # "beats the better single" test could let a losing pair through.
    body7b = """
    const fx = input.fx; const ctx = ctxOf(fx); const rows = F.withChartAverage(fx.roster.map(row), ctx.chartKeys);
    const cands = F.withChartAverage(fx.candidates.map(row), ctx.chartKeys);
    const singles = cands.map(c => ({candidate: c, name: c.name, totalDelta: -50, ddf: c.values.ddf_value}));
    return W.evaluateCombos(ctx, rows, singles).map(k => [k.candidates.map(c => c.name), k.totalDelta]);
    """
    g = node(js, body7b, {"fx": load("all-worse")})
    if g:
        errors.append(f"T6b a pair that loses value is listed because the singles were worse: {g}")
    # T7: de-duplication.
    body8 = """
    const roster = [{key: 'a'}, {key: 'b'}]; const cands = [{key: 'b'}, {key: 'c'}, {key: 'c'}, {key: 'd'}];
    const d = W.dedupe(cands, roster); return {kept: d.kept.map(x => x.key), onRoster: d.onRoster, repeats: d.repeats};
    """
    g = node(js, body8, {})
    if g != {"kept": ["c", "d"], "onRoster": 1, "repeats": 1}:
        errors.append(f"T7 dedupe {g}")
    # T8: kickers, defenses, no-DDF players.
    kd = load("empty-slot-kdef")
    got = evaluate(js, kd)
    kicker = next(r for r in got["results"] if r["name"] == "Kirk Kicker")
    if kicker["verdict"] != "Not evaluated" or kicker["total"] is not None or "kickers and defenses are not evaluated" not in kicker["reason"]:
        errors.append(f"T8 kicker candidate: {kicker}")
    body9 = """
    const fx = input.fx; const ctx = ctxOf(fx); const mine = fx.roster.map(row);
    const none = (market) => W.evaluateCandidate(ctx, F.withChartAverage(mine, ctx.chartKeys), F.withChartAverage([row({key: 'N1', name: 'NoDdf', pos: 'WR', team: 'XXX', ddf: null, market})], ctx.chartKeys)[0]);
    const withDdf = W.evaluateCandidate(ctx, F.withChartAverage(mine, ctx.chartKeys), F.withChartAverage([row({key: 'N2', name: 'HasDdf', pos: 'RB', team: 'XXX', ddf: 14, noise: 0, market: null})], ctx.chartKeys)[0]);
    return {priced: [none(7.5).verdict, none(7.5).market, none(7.5).reason], unpriced: [none(null).verdict, none(null).market], zero: none(0.0).market, withDdf: [withDdf.verdict, withDdf.market]};
    """
    g = node(js, body9, {"fx": load("no-chart-value")})
    if g["priced"][0] != "Not evaluated" or g["priced"][1] != 7.5 or "7.5" not in g["priced"][2]:
        errors.append(f"T8 a player with no DDF Value but a chart price: {g['priced']}")
    if g["zero"] is not None:
        errors.append(f"T8 a chart price that shows as 0.0 is shown as {g['zero']}, want a dash")
    if g["unpriced"] != ["Not evaluated", None]:
        errors.append(f"T8 a player nothing prices: {g['unpriced']}")
    if g["withDdf"][0] == "Not evaluated" or g["withDdf"][1] is not None:
        errors.append(f"T8 giving him a DDF Value must evaluate him (and no chart is a dash): {g['withDdf']}")
    # Bench weights: a bench stash counts at the bench weight, never in full. Bo Wideout (WR 4.0) takes the bench seat of a
    # TE worth 2.0: 4.0 x 0.15 - 2.0 x 0.1 = +0.4, not the raw +2.0; the raw change is kept for the detail.
    res = {r["name"]: r for r in evaluate(js, load("thin-rb"))["results"]}
    if not close(res["Bo Wideout"]["bench"], 0.4) or not close(res["Bo Wideout"]["total"], 0.4):
        errors.append(f"bench weights: Bo Wideout bench {res['Bo Wideout']['bench']} total {res['Bo Wideout']['total']}, want 0.4 and 0.4")
    # T14: starts vs stash.
    res = {r["name"]: r for r in evaluate(js, load("thin-rb"))["results"]}
    if res["Akers Alpha"]["slot"] != "RB" or "Starts immediately at RB." not in res["Akers Alpha"]["reason"]:
        errors.append(f"T14 a starter: {res['Akers Alpha']['slot']!r} / {res['Akers Alpha']['reason']!r}")
    if res["Bo Wideout"]["slot"] is not None or "Bench stash; starts if a WR is injured or on bye." not in res["Bo Wideout"]["reason"]:
        errors.append(f"T14 a stash: {res['Bo Wideout']['slot']!r} / {res['Bo Wideout']['reason']!r}")
    # T13: the share link.
    body10 = """
    const h = W.encodeHash(['869', 'x:DEF:KC', '12'], ['5', '6'], 'scoring=ppr&roster=QB1.RB2.WR2.TE1.FLEX1.SF0.BN7');
    const d = W.decodeHash(h);
    const empty = W.encodeHash([], [], 'scoring=ppr');
    return {h, mine: d.mine, cands: d.cands, scoring: d.params.get('scoring'), roster: d.params.get('roster'), empty, wrong: W.decodeHash('#compare-trade?mine=1').mine};
    """
    g = node(js, body10, {})
    if g["mine"] != ["869", "x:DEF:KC", "12"] or g["cands"] != ["5", "6"] or g["scoring"] != "ppr" or g["roster"] != "QB1.RB2.WR2.TE1.FLEX1.SF0.BN7":
        errors.append(f"T13 share link round trip: {g}")
    if g["empty"] != "#waivers" or g["wrong"] != []:
        errors.append(f"T13 empty link / other route: {g['empty']!r} {g['wrong']}")
    return errors


def check(js: Path) -> list[str]:
    return check_fixtures(js) + check_unit(js)


MUTANTS = {
    "pick up needs only a gain above minus tau": ("const up = total > tau;", "const up = total > -tau;"),
    "noise floor ignored": ("const tau = fit.tau;", "const tau = NET_FLOOR;"),
    "skip never fires": ("const down = total < -tau;", "const down = false;"),
    "force never fires": ("up ? (fit.away ? VERDICT.force : VERDICT.pick)", "up ? VERDICT.pick"),
    "drops the highest marginal": ("a.marginal - b.marginal\n", "b.marginal - a.marginal\n"),
    "required kicker offered as a drop": ("return have <= need;", "return false;"),
    "a drop is taken even with an open slot": ("const drop = free > 0 ? null :", "const drop = "),
    "tiers out of order": ("const TIER = {[VERDICT.pick]: 0, [VERDICT.force]: 1,", "const TIER = {[VERDICT.pick]: 1, [VERDICT.force]: 0,"),
    "not evaluated first": ("[VERDICT.skip]: 4, [VERDICT.none]: 5}", "[VERDICT.skip]: 4, [VERDICT.none]: -1}"),
    "pair cap raised": ("const MAX_PAIRS = 100;", "const MAX_PAIRS = 1000;"),
    "combo needs only the floor": ("!(net - best > tau)", "false"),
    "combo ignores the single pickup": ("!(net > tau) ||", "false ||"),
    "roster players kept as candidates": ("if (mine.has(key)) { onRoster += 1; return; }", ""),
    "repeats kept": ("if (seen.has(key)) { repeats += 1; return; }", ""),
    "a kicker is evaluated": ("if (isNotEvaluated(candidate)) {", "if (false) {"),
    "no DDF Value read as zero": ("if (viewValueOf(candidate, key) === null) {", "if (false) {"),
    "zero market shown": ("row.values[MARKET_KEY] >= USABLE_MIN ? row.values[MARKET_KEY] : null", "true ? row.values[MARKET_KEY] : null"),
    "stash called a start": ("const slot = slotOf(impact.after, candidate);", "const slot = SLOT_KEYS[0];"),
    "share link loses the candidates": ("if (candKeys.length) parts.push(`cands=${enc(candKeys)}`);", ""),
    "headline picks the worst": ("const pick = first(VERDICT.pick);", "const pick = results.filter(r => r.verdict === VERDICT.pick).pop();"),
    "bench counted at full weight": ("F.benchWeight(weights, r.pos) * r.values[key]", "1 * r.values[key]"),
    "bench weights not passed to the fit": ("weights, chartKeys: charts || undefined, z: FIT_Z}", "weights: {}, chartKeys: charts || undefined, z: FIT_Z}"),
    "marginal counts the bench twice": ("return Math.max(0, settle(before - after));", "return Math.max(0, settle((before - after) * 2));"),
}


class WaiversMathTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(WAIVERS_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = WAIVERS_JS.read_text(encoding="utf-8")
        finder = (ROOT / "app" / "v2" / "finder.js").read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, source, f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "waivers.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    (Path(tmp) / "finder.js").write_text(finder, encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
