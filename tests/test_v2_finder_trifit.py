"""JEG-1081 PR 2: the tri-view fit rule in tradeFit (app/v2/finder.js), with its text and headline.

Your team is judged in DDF Value (the adjusted trade charts) AND in DDF Value (projections); they are judged in the trade
chart average. The base label keeps its meaning (natural / value / force); it is served on your side when either of your two
views serves you. `variant` says which: natural, natural-charts (only DDF Value serves you), natural-projections (only the
projections serve you), value, force. Projections count only when every player moving on your side has a projection value.

Frozen fixtures (rosters from the thin/deep teams of test_v2_finder_fit, case 5; values below are the fixtures):
  * THIN-RB / DEEP-WR: the thin team gives its RB1 for two RB2s (fills two slots), the deep team is deep at RB;
  * agreeing: projections equal DDF Value, so natural;
  * disagree trade: DDF Value says the two RB2s are worth 5 (you lose), projections and the market say 16: the two-view rule
    labels it force, the tri-view rule natural (projections only);
  * charts only: DDF Value says 16, projections say 2: natural (charts only);
  * missing projections: no projection values on the arriving players, so the two-view rule applies unchanged;
  * value: a balanced one-for-one gain for both sides stays value; force stays force when neither of your views serves you.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of finder.js with a rule broken.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call
from tests.test_v2_finder_balance import ALLOC, SHAPE

CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
PK = "ddf_value_projections"


def p(key, pos, ddf, proj="same", market="same"):
    proj = ddf if proj == "same" else proj
    market = ddf if market == "same" else market
    values = {"ddf_value": ddf, "ddf_value_charts": ddf, PK: proj, "chart_avg": market}
    values.update({k: market for k in CH})
    if proj is not None:
        values.update({"espn": proj, "cbsros": proj, "razzball": proj})
    else:
        values.pop(PK)
    return {"player_key": key, "pos": pos, "name": key, "values": values}


def team(prefix, qb, rb, wr, te):
    rows = []
    for pos, vals in (("QB", qb), ("RB", rb), ("WR", wr), ("TE", te)):
        rows += [p(f"{prefix}{pos}{i}", pos, v) for i, v in enumerate(vals)]
    return rows


def pick(rows, *keys):
    return [r for r in rows if r["player_key"] in keys]


def fit(finder_js, mine, theirs, give, get, **kw):
    expected = call(finder_js, "expectedDepth", ALLOC, 12)
    ctx = {"shape": SHAPE, "weights": {"QB": 0.15, "RB": 0.15, "WR": 0.15, "TE": 0.15, "overall": 0.15}, "ourKey": "ddf_value",
           "marketKey": "chart_avg", "chartKeys": CH, "z": 1, "expected": expected}
    ctx.update(kw)
    return call(finder_js, "tradeFit", {"mine": {"roster": mine, "leaving": give, "arriving": get}, "theirs": {"roster": theirs, "leaving": get, "arriving": give}}, ctx)


THIN = team("n", [20, 12], [30], [20, 18, 10, 8], [6])
DEEP = team("d", [20, 14], [35, 16, 16, 12, 9, 7, 6], [25, 22, 21, 9, 5], [11, 6])


def scenario(finder_js, ddf, proj, market="same", **kw):
    """THIN gives nRB0 (30 everywhere) for dRB1 + dRB2 priced (ddf, proj, market) in the three views."""
    deep = [p(r["player_key"], r["pos"], *(ddf, proj, ddf if market == "same" else market)) if r["player_key"] in ("dRB1", "dRB2") else r for r in DEEP]
    return fit(finder_js, THIN, deep, pick(THIN, "nRB0"), pick(deep, "dRB1", "dRB2"), **kw)


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append
    # 1. Agreeing views: natural, no qualifier.
    f = scenario(finder_js, 16, 16)
    if f["label"] != "natural" or f["variant"] != "natural" or f["qualifier"] is not None or not (f["us"]["ok"] and f["usProj"]["ok"]):
        say(f"agreeing views: {f['label']}/{f['variant']} qualifier {f['qualifier']}")
    # 2. Charts only: DDF Value (16) serves you, projections (2) do not.
    f = scenario(finder_js, 16, 2, market=16)
    if f["label"] != "natural" or f["variant"] != "natural-charts" or f["qualifier"] != "charts only" or f["usProj"]["ok"]:
        say(f"charts only: {f['label']}/{f['variant']} qualifier {f['qualifier']} proj ok {f['usProj'] and f['usProj']['ok']}")
    # 3. The disagree trade: DDF Value says lose, projections and market say gain.
    f = scenario(finder_js, 5, 16, market=16)
    if f["us"]["ok"] or not f["usProj"]["ok"] or f["label"] != "natural" or f["variant"] != "natural-projections" or f["qualifier"] != "projections only":
        say(f"disagree trade: {f['label']}/{f['variant']} us ok {f['us']['ok']} proj ok {f['usProj'] and f['usProj']['ok']}")
    # 3b. The same trade under the two-view rule (projections key = DDF Value): force. The projections view is what changes the label.
    f2 = scenario(finder_js, 5, 16, market=16, projectionsKey="ddf_value")
    if f2["label"] != "force" or f2["usProj"] is not None or f2["variant"] != "force":
        say(f"disagree trade, two-view rule: {f2['label']}/{f2['variant']}")
    # 4. Missing projections on the arriving players: the two-view rule applies unchanged (here natural, charts serve you).
    f = scenario(finder_js, 16, None, market=16)
    if f["projected"] or f["usProj"] is not None or f["label"] != "natural" or f["variant"] != "natural" or f["qualifier"] is not None:
        say(f"no projections: {f['label']}/{f['variant']} projected {f['projected']}")
    # 5. Neither of your views serves you: force, even if they gain.
    f = scenario(finder_js, 5, 5, market=16)
    if f["label"] != "force" or f["variant"] != "force":
        say(f"neither view serves you: {f['label']}/{f['variant']}")
    # 6. Them: the market still decides their side (they lose on the market): force whatever your views say.
    thin = [p("nRB0", "RB", 30, market=2) if r["player_key"] == "nRB0" else r for r in THIN]
    deep = [p(r["player_key"], r["pos"], 16, 16, 16) if r["player_key"] in ("dRB1", "dRB2") else r for r in DEEP]
    f = fit(finder_js, thin, deep, pick(thin, "nRB0"), pick(deep, "dRB1", "dRB2"))
    if f["them"]["ok"] or f["label"] != "force":
        say(f"market says they lose (they receive a market-2 player for market-16 players): {f['label']} them ok {f['them']['ok']}")
    # 7. A balanced one-for-one gain for both sides stays value (no depth change), also with projections agreeing.
    bal_a = team("a", [20, 12], [30, 15, 12, 9, 7], [30, 28, 15, 9, 8, 7], [10, 5])
    bal_b = team("b", [22, 11], [35, 14, 12, 9, 8], [26, 20, 9, 8, 7, 6], [11, 6])
    x, y = p("aX", "RB", 25, market=40), p("bY", "RB", 30, market=20)
    f = fit(finder_js, bal_a + [x], bal_b + [y], [x], [y])
    if f["label"] != "value" or f["variant"] != "value" or f["fillsNeed"]:
        say(f"balanced one-for-one: {f['label']}/{f['variant']}")
    # 7b. Depth in either serving view: DDF Value gains but fills no slot (dRB2 is 0.04 there, shown as 0.0), the projections fill a slot.
    thin2 = team("n", [20, 12], [30, 20], [20, 18, 10, 8], [6])
    mid = team("d", [20, 14], [35, 16, 16, 16, 16], [25, 22, 21, 9, 5], [11, 6])   # their RB room is in band: no need of their own filled
    deep = [p("dRB1", "RB", 50, 50, 12), p("dRB2", "RB", 0.04, 16, 5)] + [r for r in mid if r["player_key"] not in ("dRB1", "dRB2")]
    f = fit(finder_js, thin2, deep, pick(thin2, "nRB1"), pick(deep, "dRB1", "dRB2"))
    if not (f["us"]["ok"] and not f["us"]["toward"] and f["usProj"]["ok"] and f["usProj"]["toward"]) or f["label"] != "natural" or f["variant"] != "natural" or f["them"]["toward"]:
        say(f"charts view serves with no depth, projections fill a slot: {f['label']}/{f['variant']} us toward {f['us']['toward']} proj toward {f['usProj']['toward']}")
    text = call(finder_js, "fitText", f)
    if "It moves you at " not in text:
        say(f"text names the view that moves toward depth: {text!r}")
    # 7c. Opportunities reads our side from the view that serves us (projections only: not "force").
    opp = Path(finder_js).parent / "opportunities.js"
    if opp.exists():
        fake = {"us": {"ok": False, "down": True, "away": False, "toward": False, "towardAt": [], "awayAt": []},
                "usProj": {"ok": True, "down": False, "away": False, "toward": True, "towardAt": ["RB"], "awayAt": []}}
        out = subprocess.run(["node", "-e", "const O = require(process.argv[1]); console.log(JSON.stringify(O.ourFitOf(JSON.parse(process.argv[2]))))", str(opp), json.dumps(fake)],
                             capture_output=True, text=True)
        got = json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {"error": out.stderr[-200:]}
        if got.get("label") != "natural" or got.get("detail") != "fills RB":
            say(f"opportunities label when only projections serve us: {got}")
    # 8. Text.
    text = call(finder_js, "fitText", scenario(finder_js, 16, 2, market=16))
    if not text.startswith("Natural fit (charts only):") or "The projections do not back it: you lose" not in text:
        say(f"charts-only text: {text!r}")
    text = call(finder_js, "fitText", scenario(finder_js, 5, 16, market=16))
    if not text.startswith("Natural fit (projections only):") or "DDF Value (projections)" not in text or "The trade charts do not back it:" not in text:
        say(f"projections-only text: {text!r}")
    text = call(finder_js, "fitText", scenario(finder_js, 16, 16))
    if not text.startswith("Natural fit: ") or "(" in text.split(":")[0]:
        say(f"agreeing text: {text!r}")
    # 9. Headline: unchanged text, qualifier as subtitle.
    h = call(finder_js, "fitHeadline", "natural", {"count": 3})
    if h["text"] != "Natural fit found: 3 groups" or h["subtitle"] is not None:
        say(f"plain headline: {h}")
    h = call(finder_js, "fitHeadline", "natural", {"count": 1, "chartsOnly": 1, "projectionsOnly": 2})
    if h["text"] != "Natural fit found: 1 group" or h["subtitle"] != "1 is backed by the trade charts but not the projections; 2 are backed by the projections but not the trade charts":
        say(f"qualified headline: {h}")
    return errors


MUTANTS = {
    "projections never serve you": ("const projOk = Boolean(usProj && usProj.ok);", "const projOk = false;"),
    "projections always serve you": ("const projOk = Boolean(usProj && usProj.ok);", "const projOk = Boolean(usProj);"),
    "us_proj forced not ok (spec mutation)": ("const qualifier = !projected", "if (usProj) usProj.ok = false; const qualifier = !projected"),
    "projections key equal to ours still projected": ("projKey !== ctx.ourKey && moving", "moving"),
    "charts view ignored": ("const chartsOk = us.ok;", "const chartsOk = false;"),
    "market ignored for them": ("const label = yourOk && them.ok ?", "const label = yourOk ?"),
    "missing projections counted": ("const projected = projKey !== ctx.ourKey && moving.length > 0 && moving.every(r => r && r.values && finite(r.values[projKey]));", "const projected = projKey !== ctx.ourKey;"),
    "both agree still qualified": ("chartsOk && projOk ? null : chartsOk", "chartsOk"),
    "depth read only in the charts view": ("const usToward = (chartsOk && us.toward) || (projOk && usProj.toward);", "const usToward = us.toward;"),
    "text names the charts view only": ("const yours = fit.usServing && fit.usServing.toward ? fit.usServing : fit.usProj && fit.usProj.ok && fit.usProj.toward ? fit.usProj : us;", "const yours = us;"),
    "no qualifier": ('chartsOk ? "charts only" : "projections only"', "null"),
    "headline without subtitle": ("subtitle: parts.join(\"; \") || null", "subtitle: null"),
}


class TriViewFitTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, source, f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")
        # The opportunities half: its label must read the projections view when only it serves us.
        opp_src = (FINDER_JS.parent / "opportunities.js").read_text(encoding="utf-8")
        old = "const us = !fit.us.ok && fit.usProj && fit.usProj.ok ? fit.usProj : fit.us;"
        self.assertIn(old, opp_src)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "finder.js").write_text(source, encoding="utf-8")
            (Path(tmp) / "opportunities.js").write_text(opp_src.replace(old, "const us = fit.us;", 1), encoding="utf-8")
            self.assertTrue(check(Path(tmp) / "finder.js"), "checks passed on opportunities.js reading DDF Value only")


if __name__ == "__main__":
    unittest.main()
