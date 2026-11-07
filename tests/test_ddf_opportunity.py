"""JEG-1558: opportunity tiers and the roster-improvement percent (app/next/ddf-opportunity.js).

Synthetic fixtures only (no real league data). Guards:
- tiers at 3 / 6 / 10% of worth, exact comparison, shown truncated toward zero (2.9/3.0/5.99/6.0/9.99/10.0);
- the noise rule: a gain at or below its noise floor (tau) counts as none; a waiver gain never beats a bigger trade;
- partner bands at +1 / -1 / -3% with sign handling; sender and partner symmetric for the same valuation;
- tiny-denominator guard: a roster worth under MIN_BASE gives no percent;
- parity: worth() equals waivers.js netOf(lineupValue(...)) and the delta equals finder.js teamFit's net.
Discrimination: test_checks_fail_on_broken_module runs the tier checks on mutated copies.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "next" / "ddf-opportunity.js"
WAIVERS = ROOT / "app" / "v2" / "waivers.js"
FINDER = ROOT / "app" / "v2" / "finder.js"

HARNESS = """
const O = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const extra = input.extra ? require(input.extra) : null;
const F = require(input.finder);
(async () => {
const out = [];
for (const [fn, ...args] of input.fns) out.push(await (async () => {
  if (fn === '__negZero') return Object.is(O.shownPct(args[0]), -0);
  if (fn === '__computeTeamSettles') {
    const timeout = new Promise(r => setTimeout(() => r('hang'), 2000));
    return Promise.race([O.computeTeam({teams: []}, {index: 0}).then(() => 'resolved', () => 'rejected'), timeout]);
  }
  if (fn === '__netOf') { const [rows, shape, key, weights] = args; return extra.netOf(F.lineupValue(rows, shape, key), key, weights); }
  if (fn === '__teamFit') { const [team, ctx, key] = args; return F.teamFit(team, ctx, key).net; }
  return O[fn](...args);
})());
console.log(JSON.stringify(out));
})();
"""

SHAPE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "BENCH": 5, "K": 0, "DST": 0}
WEIGHTS = {"overall": 0.1, "QB": 0.04, "RB": 0.09, "WR": 0.08, "TE": 0.09}
CTX = {"shape": SHAPE, "weights": WEIGHTS}


def p(key, pos, ddf, chart=None):
    chart = ddf if chart is None else chart
    return {"player_key": key, "name": key, "pos": pos,
            "values": {"ddf_value": ddf, "cbs": chart, "usatoday": chart, "fantasypros": chart}}


MINE = [p("m1", "QB", 30), p("m2", "RB", 40), p("m3", "RB", 20), p("m4", "WR", 35), p("m5", "WR", 25),
        p("m6", "TE", 15), p("m7", "WR", 18), p("m8", "RB", 8)]
THEIRS = [p("t1", "QB", 28), p("t2", "RB", 30), p("t3", "RB", 25), p("t4", "WR", 40), p("t5", "WR", 30),
          p("t6", "TE", 12), p("t7", "RB", 22), p("t8", "WR", 10)]


def run(*fns, module=MODULE):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    payload = {"fns": [list(f) for f in fns], "extra": str(WAIVERS), "finder": str(FINDER)}
    out = subprocess.run(["node", "-e", HARNESS, str(module), json.dumps(payload)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


TIER_CASES = [(None, "none"), (0, "none"), (2.9, "none"), (2.999, "none"), (3.0, "marginal"), (5.99, "marginal"),
              (6.0, "medium"), (9.99, "medium"), (10.0, "big"), (25, "big")]
BAND_CASES = [(None, "unsized"), (5, "better"), (1.0, "better"), (0.99, "unchanged"), (0, "unchanged"), (-0.99, "unchanged"),
              (-1.0, "slightly_worse"), (-2.99, "slightly_worse"), (-3.0, "clearly_worse"), (-12, "clearly_worse")]


def tier_problems(module=MODULE) -> list[str]:
    got = run(*[("tierOf", pct) for pct, _ in TIER_CASES], module=module)
    return [f"tierOf({pct}) = {g}, want {want}" for (pct, want), g in zip(TIER_CASES, got) if g != want]


class Tiers(unittest.TestCase):
    def test_tier_boundaries(self):
        self.assertEqual(tier_problems(), [])

    def test_band_boundaries(self):
        got = run(*[("bandOf", pct) for pct, _ in BAND_CASES])
        self.assertEqual(got, [want for _, want in BAND_CASES])

    def test_shown_pct_never_crosses_a_boundary(self):
        got = run(("shownPct", 5.99), ("shownPct", 9.99), ("shownPct", 2.95), ("shownPct", -2.95), ("shownPct", 6.0), ("shownPct", -0.04))
        self.assertEqual(got, [5.9, 9.9, 2.9, -2.9, 6.0, 0.0])

    def test_shown_and_tier_always_agree(self):
        near = [2.9999999999999, 3.00000000001, 5.99999999999995, 5.9999999999995, 9.9999999999999, 10.0000000001, 6.04, 0.04]
        got = run(*[("tierOf", v) for v in near], *[("tierOf", v) for v in [math.floor(v * 10 + 1e-9) / 10 for v in near]])
        self.assertEqual(got[:len(near)], got[len(near):])
        bands = [-0.9999999999999, -2.99999999999995, 0.99999999999995, -1.04]
        got = run(*[("bandOf", v) for v in bands], *[("bandOf", -math.floor(-v * 10 + 1e-9) / 10 if v < 0 else math.floor(v * 10 + 1e-9) / 10) for v in bands])
        self.assertEqual(got[:len(bands)], got[len(bands):])

    def test_no_negative_zero(self):
        self.assertEqual(run(("__negZero", -0.04), ("__negZero", -0.0), ("__negZero", -1.5)), [False, False, False])

    def test_none_reasons_are_honest(self):
        cases = [({"worth": 200, "trade": {"gain": 4, "tau": 1}}, "small", "too small to be worth chasing"),
                 ({"worth": 200, "trade": {"gain": 2, "tau": 3}}, "sharp", "already sharp"),
                 ({"worth": 200, "checked": False}, "unchecked", "no move was sized"),
                 ({"worth": 10, "trade": {"gain": 5, "tau": 1}}, "unsized", "could not size")]
        got = run(*[("assess", c) for c, *_ in cases])
        for (case, reason, text), g in zip(cases, got):
            with self.subTest(case=case):
                self.assertEqual(g["tier"], "none")
                self.assertEqual(g["reason"], reason)
                self.assertIn(text, g["line"])
                if reason != "sharp":
                    self.assertNotIn("already sharp", g["line"])
        self.assertIsNone(got[3]["source"])

    def test_compute_team_never_hangs_on_error(self):
        self.assertEqual(run(("__computeTeamSettles",)), ["rejected"])

    def test_assess_cases(self):
        # Shaped like the experiment's three reads (synthetic numbers): a medium trade, a gain under its noise floor,
        # a marginal trade; plus the boundaries on a 200-point roster and the waiver / trade choice.
        cases = [
            ({"worth": 200, "trade": {"gain": 14.2, "tau": 1.3}, "waiver": {"gain": 0.4, "tau": 3.0}}, "medium", "trade", True),
            ({"worth": 215, "trade": {"gain": 6.4, "tau": 8.8}, "waiver": {"gain": 0.2, "tau": 0.4}}, "none", None, True),
            ({"worth": 240, "trade": {"gain": 8.2, "tau": 3.3}, "waiver": None}, "marginal", "trade", True),
            ({"worth": 200, "trade": {"gain": 5.8, "tau": 1}}, "none", "trade", True),        # 2.9%
            ({"worth": 200, "trade": {"gain": 6.0, "tau": 1}}, "marginal", "trade", True),    # 3.0%
            ({"worth": 200, "trade": {"gain": 11.98, "tau": 1}}, "marginal", "trade", True),  # 5.99%
            ({"worth": 200, "trade": {"gain": 12.0, "tau": 1}}, "medium", "trade", True),     # 6.0%
            ({"worth": 200, "trade": {"gain": 19.98, "tau": 1}}, "medium", "trade", True),    # 9.99%
            ({"worth": 200, "trade": {"gain": 20.0, "tau": 1}}, "big", "trade", True),        # 10.0%
            ({"worth": 200, "trade": {"gain": 4, "tau": 1}, "waiver": {"gain": 9, "tau": 2}}, "marginal", "waiver", False),
            ({"worth": 200, "trade": {"gain": 3, "tau": 3}, "waiver": {"gain": 2, "tau": 2}}, "none", None, True),  # at the floor = none
            ({"worth": 10, "trade": {"gain": 5, "tau": 1}}, "none", None, True),             # tiny base: no percent, no move named
            ({"worth": 200}, "none", None, True),
        ]
        got = run(*[("assess", c) for c, *_ in cases])
        for (case, tier, source, empty), g in zip(cases, got):
            with self.subTest(case=case):
                self.assertEqual((g["tier"], g["source"], g["waiversEmpty"]), (tier, source, empty))
        self.assertIsNone(got[11]["pct"])
        self.assertIn("roughly two places", got[8]["line"])
        self.assertIn("about one place", got[6]["line"])
        self.assertIn("close to its best", got[4]["line"])
        self.assertEqual(got[1]["headline"], "No meaningful move right now")
        self.assertIn("5.9%", got[5]["line"])  # 5.99% shows as 5.9%, never 6.0% on a marginal read

    def test_checks_fail_on_broken_module(self):
        src = MODULE.read_text()
        for old, new in (("min: 10}", "min: 11}"), ('min: 3}]', 'min: 2.9}]'), ("pct >= TIERS[i].min", "pct > TIERS[i].min")):
            self.assertIn(old, src)
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "next").mkdir()
                (Path(d) / "v2").mkdir()
                shutil.copy(FINDER, Path(d) / "v2" / "finder.js")
                if (ROOT / "app" / "v2" / "trade.js").exists():
                    shutil.copy(ROOT / "app" / "v2" / "trade.js", Path(d) / "v2" / "trade.js")
                bad = Path(d) / "next" / "ddf-opportunity.js"
                bad.write_text(src.replace(old, new, 1))
                self.assertNotEqual(tier_problems(bad), [], f"tier checks pass with {old!r} -> {new!r}")


class RosterImprovement(unittest.TestCase):
    def test_sender_and_partner_signs(self):
        trade = {"mine": MINE, "theirs": THEIRS, "give": [MINE[6]], "receive": [THEIRS[6]]}
        s, q = run(("rosterImprovementPct", trade, "sender", CTX), ("rosterImprovementPct", trade, "partner", CTX))
        self.assertGreater(s["pct"], 0)
        self.assertLess(q["pct"], 0)
        self.assertEqual(s["band"], "better")
        self.assertEqual(q["key"], "chart_avg")
        self.assertTrue(q["label"].startswith("Their roster gets about"))
        self.assertIn("worse", q["label"])
        self.assertAlmostEqual(s["pct"], 100 * s["delta"] / s["before"])

    def test_symmetry(self):
        ctx = dict(CTX, partnerKey="ddf_value")
        trade = {"mine": MINE, "theirs": THEIRS, "give": [MINE[1]], "receive": [THEIRS[3], THEIRS[7]]}
        back = {"mine": THEIRS, "theirs": MINE, "give": [THEIRS[3], THEIRS[7]], "receive": [MINE[1]]}
        s, q, s2, q2 = run(("rosterImprovementPct", trade, "sender", ctx), ("rosterImprovementPct", trade, "partner", ctx),
                           ("rosterImprovementPct", back, "sender", ctx), ("rosterImprovementPct", back, "partner", ctx))
        self.assertAlmostEqual(s["pct"], q2["pct"])
        self.assertAlmostEqual(q["pct"], s2["pct"])
        self.assertEqual(s["band"], q2["band"])

    def test_partner_band_sentences(self):
        # One trade per band, built so the partner's percent lands just inside each band on a 200-point roster.
        base = [p("b1", "QB", 40), p("b2", "RB", 40), p("b3", "RB", 30), p("b4", "WR", 40), p("b5", "WR", 30), p("b6", "TE", 20)]
        ctx = dict(CTX, partnerKey="ddf_value", weights={"overall": 0})

        def band_for(delta):  # their RB2 (30) leaves, an RB worth 30 + delta arrives: delta / 200 of their roster
            return {"mine": [p("x", "QB", 0)], "theirs": base, "give": [p("g", "RB", 30 + delta)], "receive": [base[2]]}
        deltas = [(2.4, "better"), (1.6, "unchanged"), (-1.6, "unchanged"), (-2.4, "slightly_worse"), (-5.8, "slightly_worse"), (-6.2, "clearly_worse")]
        got = run(*[("rosterImprovementPct", band_for(d), "partner", ctx) for d, _ in deltas])
        for (d, want), g in zip(deltas, got):
            with self.subTest(delta=d):
                self.assertEqual(g["band"], want, g)
        self.assertIn("may still say yes", got[1]["sentence"])
        self.assertIn("small cost", got[3]["sentence"])
        self.assertIn("unlikely to accept", got[5]["sentence"])
        self.assertNotIn("will accept", " ".join(g["sentence"] for g in got))

    def test_tiny_denominator_guard(self):
        tiny = [p("a", "QB", 6), p("b", "RB", 5)]
        trade = {"mine": tiny, "theirs": THEIRS, "give": [tiny[1]], "receive": [THEIRS[7]]}
        s, = run(("rosterImprovementPct", trade, "sender", CTX))
        self.assertIsNone(s["pct"])
        self.assertEqual(s["band"], "unsized")

    def test_no_change_is_zero_not_signed(self):
        trade = {"mine": MINE, "theirs": THEIRS, "give": [], "receive": []}
        s, = run(("rosterImprovementPct", trade, "sender", CTX))
        self.assertEqual((s["delta"], s["pct"], s["band"]), (0, 0, "unchanged"))
        self.assertNotIn("-0.0", s["label"])

    def test_parity_with_engine_worth(self):
        net, fit_net, mine_worth, s = run(("__netOf", MINE, SHAPE, "ddf_value", WEIGHTS),
                                         ("__teamFit", {"roster": MINE, "leaving": [MINE[6]], "arriving": [THEIRS[6]]},
                                          {"shape": SHAPE, "weights": WEIGHTS, "expected": None}, "ddf_value"),
                                         ("worth", MINE, CTX, "ddf_value"),
                                         ("rosterImprovementPct", {"mine": MINE, "theirs": THEIRS, "give": [MINE[6]], "receive": [THEIRS[6]]}, "sender", CTX))
        self.assertAlmostEqual(mine_worth, net, places=9)
        self.assertAlmostEqual(s["delta"], fit_net, places=9)


if __name__ == "__main__":
    unittest.main()
