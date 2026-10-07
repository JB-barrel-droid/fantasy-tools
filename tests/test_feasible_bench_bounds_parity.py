"""Feasible bench bounds: browser == Python reference (JEG-432 R2).

ValueModel.feasibleBenchBounds (app/trade-value-chart/assets/value-model.js)
and pipelines/feasible_bench_bounds.feasible_bench_bounds run on identical
inputs and must agree:

  * bench-slot min/max, binding position/counts, share min/max/default,
    fallbackAbove, reasons: EXACTLY equal;
  * per-position open intervals (unrounded floats): within TOL = 1e-9.

Inputs: our ESPN per-game projections (players.json espn_ppg, what the
browser reads) for 3 scorings x 8/10/12/14 teams x several roster shapes
(default, no flex, 2 flex, superflex, 2QB, deep, all-5s), plus synthetic edge
vectors (thin pool with no feasible bench, det < 0, det == 0, an empty share
interval, a missing position, no tiers, product floor/ceiling binding).

Two comparisons per real vector:
  given -- JS run on the tiers Python built (pure rule parity);
  built -- JS run on tiers the BROWSER's TwoTier.buildPositionTiers built
           from the same pool (end-to-end parity).
And the closed-form share interval is cross-checked against TwoTier's
existing bisection (feasibleBenchShareInterval, tolerance 1e-4).

Discrimination: test_guard_catches_broken_ports mutates copies of
value-model.js in three realistic ways and requires parity to fail on each.
test_old_fixed_range_withholds proves the defect the rule fixes is real:
at the old 1% slider floor the live calibration withholds a position.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

import feasible_bench_bounds as fbb  # noqa: E402

VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = REPO / "tests" / "feasible_bench_bounds_driver.js"
TWO_TIER_HARNESS = REPO / "tests" / "two_tier_harness.js"
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
TOL = 1e-9
BISECT_TOL = 2e-4

SHAPES = [
    ("std", None),
    ("flex0", {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 0, "BENCH": 6}),
    ("flex2", {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 2, "BENCH": 6}),
    ("superflex", {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6, "SUPERFLEX": 1}),
    ("qb2", {"QB": 2, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}),
    ("deep", {"QB": 2, "RB": 3, "WR": 4, "TE": 2, "FLEX": 2, "BENCH": 6}),
    ("max5", {"QB": 5, "RB": 5, "WR": 5, "TE": 5, "FLEX": 5, "BENCH": 6}),
]

# The published example table (docs/contract/fe-v3-backend-requirements.md R2):
# default roster, today's committed projections. Pinned so a silent change to
# the rule or its inputs is a visible diff, not a quiet re-bound.
EXPECTED_DEFAULT = {
    ("standard", 8): ((0, 14), (0.06, 0.212)),
    ("standard", 10): ((0, 14), (0.045, 0.192)),
    ("standard", 12): ((0, 13), (0.053, 0.205)),
    ("standard", 14): ((0, 10), (0.058, 0.203)),
    ("half_ppr", 8): ((0, 14), (0.06, 0.212)),
    ("half_ppr", 10): ((0, 14), (0.045, 0.192)),
    ("half_ppr", 12): ((0, 13), (0.053, 0.205)),
    ("half_ppr", 14): ((0, 10), (0.058, 0.203)),
    ("ppr", 8): ((0, 14), (0.06, 0.212)),
    ("ppr", 10): ((0, 14), (0.049, 0.205)),
    ("ppr", 12): ((0, 13), (0.053, 0.21)),
    ("ppr", 14): ((0, 10), (0.058, 0.208)),
}


def _real_vectors():
    vectors = []
    for scoring in SCORINGS:
        pool = fbb.projection_pool(scoring)
        for teams in TEAMS:
            tiers = fbb.reference_tiers(pool, teams)
            for label, shape in SHAPES:
                vectors.append({"label": f"{scoring}/{teams}t/{label}", "scoring": scoring,
                                "teams": teams, "shape": shape, "pool": pool, "tiers": tiers,
                                "build_tiers": label == "std"})
    return vectors


def _synthetic_vectors():
    def pool_of(sizes):
        return {pos: [(f"{pos}{i}", float(100 - i)) for i in range(n)] for pos, n in sizes.items()}
    good = {"aBench": 40.0, "bBench": 2.0, "aStart": 30.0, "bStart": 60.0}
    vectors = []
    # Thin: 12 teams cannot even fill starters at QB -> no feasible bench.
    vectors.append({"label": "thin", "teams": 12, "shape": None,
                    "pool": pool_of({"QB": 10, "RB": 60, "WR": 90, "TE": 30}),
                    "tiers": {p: good for p in fbb.POSITION_ORDER}})
    # Mid-range cap: TE pool of 20 at 10 teams -> bench capped below 14.
    vectors.append({"label": "te-cap", "teams": 10, "shape": None,
                    "pool": pool_of({"QB": 60, "RB": 200, "WR": 200, "TE": 20}),
                    "tiers": {p: good for p in fbb.POSITION_ORDER}})
    # det < 0 (reversed inequalities), det == 0 (degenerate), empty interval.
    vectors.append({"label": "det-neg", "teams": 8, "shape": None,
                    "pool": pool_of({"QB": 60, "RB": 200, "WR": 200, "TE": 60}),
                    "tiers": {"QB": {"aBench": 1.0, "bBench": 50.0, "aStart": 40.0, "bStart": 2.0},
                              "RB": good, "WR": good, "TE": good}})
    vectors.append({"label": "det-zero", "teams": 8, "shape": None,
                    "pool": pool_of({"QB": 60, "RB": 200, "WR": 200, "TE": 60}),
                    "tiers": {"QB": {"aBench": 2.0, "bBench": 4.0, "aStart": 1.0, "bStart": 2.0},
                              "RB": good, "WR": good, "TE": good}})
    vectors.append({"label": "missing-pos", "teams": 8, "shape": None,
                    "pool": pool_of({"QB": 0, "RB": 200, "WR": 200, "TE": 60}),
                    "tiers": {"QB": None, "RB": good, "WR": good, "TE": good}})
    vectors.append({"label": "no-tiers", "teams": 12, "shape": None,
                    "pool": pool_of({"QB": 60, "RB": 200, "WR": 200, "TE": 60}), "tiers": None})
    # Wide intervals: product floor (0.01) and ceiling (0.30) bind.
    wide = {"aBench": 400.0, "bBench": 0.5, "aStart": 10.0, "bStart": 600.0}
    vectors.append({"label": "product-limits", "teams": 12, "shape": None,
                    "pool": pool_of({"QB": 60, "RB": 200, "WR": 200, "TE": 60}),
                    "tiers": {p: wide for p in fbb.POSITION_ORDER}})
    # Disjoint per-position intervals: rounded bounds empty -> fail closed.
    vectors.append({"label": "disjoint", "teams": 12, "shape": None,
                    "pool": pool_of({"QB": 60, "RB": 200, "WR": 200, "TE": 60}),
                    "tiers": {"QB": {"aBench": 30.0, "bBench": 30.0, "aStart": 5.0, "bStart": 60.0},
                              "RB": {"aBench": 5.0, "bBench": 0.1, "aStart": 60.0, "bStart": 60.0},
                              "WR": good, "TE": good}})
    return vectors


def _python(vector):
    try:
        return fbb.feasible_bench_bounds(vector["teams"], vector["shape"], vector["pool"],
                                         vector["tiers"], vector.get("scoring"))
    except (ValueError, KeyError) as error:
        return {"error": str(error)}


def _js(vectors, model_path=VALUE_MODEL):
    payload = {"vectors": [{
        "teams": v["teams"], "shape": v["shape"], "scoring": v.get("scoring"),
        "pool": {pos: [[k, val] for k, val in rows] for pos, rows in v["pool"].items()},
        "tiers": v["tiers"], "build_tiers": v.get("build_tiers", False),
    } for v in vectors]}
    proc = subprocess.run(["node", str(DRIVER), str(model_path)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)["results"]


def compare(py, js, path="", out=None):
    """Recursive diff: exact except floats under a perPosition key (TOL)."""
    out = [] if out is None else out
    loose = "perPosition" in path or "shareIntervals" in path
    if isinstance(py, dict) and isinstance(js, dict):
        if set(py) != set(js):
            out.append(f"{path}: keys {sorted(py)} vs {sorted(js)}")
        for key in set(py) & set(js):
            compare(py[key], js[key], f"{path}.{key}", out)
    elif isinstance(py, list) and isinstance(js, list):
        if len(py) != len(js):
            out.append(f"{path}: len {len(py)} vs {len(js)}")
        for i, (a, b) in enumerate(zip(py, js)):
            compare(a, b, f"{path}[{i}]", out)
    elif isinstance(py, (int, float)) and isinstance(js, (int, float)) \
            and not isinstance(py, bool) and not isinstance(js, bool):
        diff = abs(float(py) - float(js))
        if diff > (TOL if loose else 0.0):
            out.append(f"{path}: py={py!r} js={js!r}")
    elif py != js:
        out.append(f"{path}: py={py!r} js={js!r}")
    return out


def run_parity(vectors, model_path=VALUE_MODEL):
    results = _js(vectors, model_path)
    failures = []
    for vec, res in zip(vectors, results):
        py = _python(vec)
        for mode in ("given", "built"):
            if mode not in res:
                continue
            problems = compare(py, res[mode])
            if problems:
                failures.append(f"{vec['label']} [{mode}]: {problems[:3]}")
    return failures, results


_SWEEP_SCRIPT = r"""
const path = require("path");
globalThis.window = globalThis;
const VM = require(path.resolve(process.argv[2]));
globalThis.ValueModel = VM;
require(path.join(process.argv[1], "app/trade-value-chart/assets/curve-widget.js"));
const T = globalThis.TradeValueTwoTier;
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = {};
for (const c of input.combos) {
  const lists = {}, pool = {};
  Object.entries(c.pool).forEach(([p, rows]) => {
    lists[p] = rows.map(([k, v]) => ({id: String(k), x: v}));
    pool[p] = rows.map(([k, v]) => ({key: k, value: v}));
  });
  const built = T.buildPositionTiers(lists, {teams: c.teams, slots: {...T.REF_SLOTS},
    flexCount: T.REF_FLEX_COUNT, flexEligible: [...T.REF_FLEX_ELIGIBLE], benchMix: T.legacyBenchMixFor(c.teams)});
  const bs = VM.feasibleBenchBounds({teams: c.teams, scoring: c.scoring, pool, tiers: built.tiers}).benchShare;
  const bad = [];
  if (!bs) { bad.push("no bounds"); }
  else {
    for (let m = Math.round(bs.min * 1000); m <= Math.round(bs.max * 1000); m += 1) {
      const s = m / 1000;
      T.POSITIONS.forEach(p => {
        const cal = T.calibratePositionFeasible(built.tiers[p], built.tiers[p].surplus, s, p);
        if (!cal || cal.invalid) bad.push(`${s}:${p}`);
      });
    }
  }
  out[`${c.scoring}/${c.teams}`] = bad;
}
process.stdout.write(JSON.stringify(out));
"""


def _sweep_withheld(model_path):
    """{combo: ["share:POS", ...]} withheld steps across the rule's slider range."""
    combos = []
    for scoring in SCORINGS:
        pool = fbb.projection_pool(scoring)
        rows = {p: [[k, v] for k, v in r] for p, r in pool.items()}
        combos.extend({"scoring": scoring, "teams": t, "pool": rows} for t in TEAMS)
    proc = subprocess.run(["node", "-e", _SWEEP_SCRIPT, str(REPO), str(model_path)],
                          input=json.dumps({"combos": combos}), capture_output=True, text=True,
                          timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"sweep driver failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


class FeasibleBenchBoundsParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = _real_vectors() + _synthetic_vectors()
        cls.failures, cls.results = run_parity(cls.vectors)

    def test_js_matches_python_reference(self):
        self.assertEqual(self.failures, [], "\n".join(self.failures[:20]))
        built = sum(1 for r in self.results if "built" in r)
        self.assertEqual(built, len(SCORINGS) * len(TEAMS))
        self.assertGreaterEqual(len(self.vectors), 90)

    def test_synthetic_edges_take_the_branch_they_name(self):
        by = {v["label"]: _python(v) for v in _synthetic_vectors()}
        self.assertIsNone(by["thin"]["benchSlots"])
        self.assertLess(by["te-cap"]["benchSlots"]["max"], 14)
        self.assertEqual(by["te-cap"]["benchSlots"]["binding"]["pos"], "TE")
        # det < 0: QB's interval is (0.548, 0.96) -- reversed edges, and it
        # lies above the product ceiling, so the slider fails closed.
        qb = by["det-neg"]["shareIntervals"]["QB"]
        self.assertGreater(qb["lo"], 0.5)
        self.assertIsNone(by["det-neg"]["benchShare"])
        self.assertIsNone(by["det-zero"]["shareIntervals"]["QB"])
        self.assertIsNone(by["det-zero"]["benchShare"])
        self.assertIsNotNone(by["missing-pos"]["benchShare"])
        self.assertIsNone(by["no-tiers"]["benchShare"]["perPosition"])
        self.assertEqual((by["product-limits"]["benchShare"]["min"],
                          by["product-limits"]["benchShare"]["max"]), (0.01, 0.3))
        self.assertIsNone(by["disjoint"]["benchShare"])

    def test_pinned_default_bounds(self):
        """The 12 published combos at the default roster (example table)."""
        got = {}
        for vec, res in zip(self.vectors, self.results):
            if not vec.get("build_tiers"):
                continue
            b = res["built"]
            got[(vec["scoring"], vec["teams"])] = (
                (b["benchSlots"]["min"], b["benchSlots"]["max"]),
                (b["benchShare"]["min"], b["benchShare"]["max"]))
            # The recommended 0.15 must stay reachable in every combo:
            # the frozen display share (DISPLAY_BENCH_SHARE) depends on it.
            self.assertEqual(b["benchShare"]["default"], 0.15, vec["label"])
            # The saved setup's bench (6) must be feasible everywhere.
            self.assertLessEqual(b["benchSlots"]["min"], 6)
            self.assertGreaterEqual(b["benchSlots"]["max"], 6)
        self.assertEqual(got, EXPECTED_DEFAULT)

    def test_closed_form_matches_bisection(self):
        """The exact interval agrees with TwoTier's bisection where it reports one."""
        checked = 0
        for vec, res in zip(self.vectors, self.results):
            if "bisect" not in res:
                continue
            for pos, iv in res["bisect"].items():
                exact = res["built"]["benchShare"]["perPosition"][pos]
                if iv is None:
                    # Bisection needs 0.15 feasible; the closed form must agree it is not.
                    self.assertFalse(exact and exact["lo"] < 0.15 < exact["hi"],
                                     f"{vec['label']} {pos}: bisection null but 0.15 inside {exact}")
                    continue
                checked += 1
                self.assertLess(abs(iv[0] - exact["lo"]), BISECT_TOL, f"{vec['label']} {pos} lo")
                self.assertLess(abs(iv[1] - exact["hi"]), BISECT_TOL, f"{vec['label']} {pos} hi")
        self.assertGreater(checked, 20)

    def test_old_fixed_range_withholds(self):
        """The defect the rule fixes: at the old 1% floor a position is withheld.

        Runs the browser's own calibratePositionFeasible (the live slider path)
        on the 12-team half-PPR reference pool at 0.01 and at the new min.
        """
        pool = fbb.projection_pool("half_ppr")
        teams = 12
        script = r"""
const path = require("path");
globalThis.window = globalThis;
require(path.join(process.argv[1], "app/trade-value-chart/assets/value-model.js"));
require(path.join(process.argv[1], "app/trade-value-chart/assets/curve-widget.js"));
const T = globalThis.TradeValueTwoTier;
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const lists = {};
Object.entries(input.pool).forEach(([p, rows]) => { lists[p] = rows.map(([k, v]) => ({id: String(k), x: v})); });
const built = T.buildPositionTiers(lists, {teams: input.teams, slots: {...T.REF_SLOTS},
  flexCount: T.REF_FLEX_COUNT, flexEligible: [...T.REF_FLEX_ELIGIBLE], benchMix: T.legacyBenchMixFor(input.teams)});
const out = {};
input.shares.forEach(s => {
  out[s] = T.POSITIONS.filter(p => { const c = T.calibratePositionFeasible(built.tiers[p], built.tiers[p].surplus, s, p); return !c || c.invalid; });
});
process.stdout.write(JSON.stringify(out));
"""
        bounds = fbb.feasible_bench_bounds(teams, None, pool, fbb.reference_tiers(pool, teams))
        lo, hi = bounds["benchShare"]["min"], bounds["benchShare"]["max"]
        payload = {"pool": {p: [[k, v] for k, v in rows] for p, rows in pool.items()},
                   "teams": teams, "shares": [0.01, lo, 0.15, hi]}
        proc = subprocess.run(["node", "-e", script, str(REPO)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr[:2000])
        withheld = json.loads(proc.stdout)
        self.assertTrue(withheld["0.01"], "old 1% floor no longer withholds -- re-check the rule")
        for share in (lo, 0.15, hi):
            self.assertEqual(withheld[str(share)], [], f"share {share} withholds {withheld[str(share)]}")

    def test_no_slider_step_withholds_a_position(self):
        """Every 0.001 slider step in [min, max] prices all four positions.

        test_old_fixed_range_withholds checks three shares in one combo. The
        rule's claim is stronger: anywhere in [min, max], in every combo, the
        live calibratePositionFeasible either solves at the request or falls
        back to a feasible share. The fallback bisects on [0.01, requested]
        and only succeeds if a midpoint lands inside the position's interval,
        so this is data-dependent and checked on the committed projections.
        Discrimination: the same sweep on a value-model.js copy with the
        lower edge dropped (the pre-R2 0.01 floor) must find withheld steps.
        """
        withheld = _sweep_withheld(VALUE_MODEL)
        self.assertEqual(len(withheld), len(SCORINGS) * len(TEAMS))
        bad = {combo: steps[:4] for combo, steps in withheld.items() if steps}
        self.assertEqual(bad, {}, f"slider steps withhold a position: {bad}")
        src = VALUE_MODEL.read_text()
        old = "var lo = Math.max(BENCH_SHARE_PRODUCT_MIN, shareCeil(loMax));"
        self.assertIn(old, src, "mutation anchor missing")
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "value-model-floor.js"
            broken.write_text(src.replace(old, "var lo = BENCH_SHARE_PRODUCT_MIN;", 1))
            broken_withheld = _sweep_withheld(broken)
        self.assertTrue(all(broken_withheld.values()),
                        "sweep did not catch the 0.01 floor in every combo")

    def test_guard_catches_broken_ports(self):
        """Each realistic port bug must make the parity comparison fail."""
        src = VALUE_MODEL.read_text()
        mutations = {
            # Off-by-one coverage: allow rostering the whole pool.
            "coverage >= -> >": ("if (n && roster[pos].rostered >= n)", "if (n && roster[pos].rostered > n)"),
            # The old behaviour: ignore the per-position lower edges.
            "drop lower edge": ("var lo = Math.max(BENCH_SHARE_PRODUCT_MIN, shareCeil(loMax));",
                                "var lo = BENCH_SHARE_PRODUCT_MIN;"),
            # Wrong economics boundary: starter-vs-bench edge without bB.
            "wrong upper edge": ("var tE = (aB + bB) / T;", "var tE = aB / T;"),
        }
        vectors = [v for v in self.vectors if v.get("build_tiers") or "label" in v and
                   v["label"] in ("te-cap", "det-neg")]
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in mutations.items():
                self.assertIn(old, src, f"mutation anchor missing: {name}")
                broken = Path(tmp) / f"value-model-{abs(hash(name))}.js"
                broken.write_text(src.replace(old, new, 1))
                failures, _ = run_parity(vectors, broken)
                self.assertTrue(failures, f"parity did not catch mutation: {name}")


if __name__ == "__main__":
    unittest.main()
