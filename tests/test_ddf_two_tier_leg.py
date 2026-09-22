"""Stage 2: the DDF two-tier value-above-waivers leg.

Covers pipelines/build_ddf_two_tier_leg.py:

- The Python port of the two-tier math is bit-exact against the browser's
  own TwoTier implementation (the Node harness): pinned hand-solved
  vectors, AND the full tier + calibration pipeline on the real ESPN
  inputs (worst abs diff asserted at 1e-9 relative).
- The built leg honors the locked guarantees: 85/15 pie identity
  pre-rounding, normalize-then-round with max == 70 exactly, ESPN content
  vintage recorded, ESPN-pure rescoring arithmetic.
- Fail-closed paths are negative-tested: infeasible shares, non-positive
  pies, missing positions, mixed-vintage CSVs, and unresolvable identities
  (review rows, never guesses).

The tests read the real inputs (ESPN CSV, pies, fixture) but never write
outside a temp dir.
"""
import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "two_tier_harness.js"
PIPELINES = REPO / "pipelines"
sys.path.insert(0, str(PIPELINES))

from build_ddf_two_tier_leg import (  # noqa: E402
    DEFAULT_BENCH_SHARE,
    DEFAULT_CSV,
    DEFAULT_FIXTURE,
    DEFAULT_PIES,
    POSITIONS,
    REF_FLEX_COUNT,
    REF_FLEX_ELIGIBLE,
    REF_SLOTS,
    bench_mix_for_teams,
    build_leg,
    build_position_tiers,
    calibrate_position,
    check_share,
    load_espn_lists,
    load_pies,
    price_for_projection,
    resolve_identities,
    solve_tier_prices,
)

TOL = 1e-9

# Hand-solved vectors vendored from tests/test_two_tier_frontend.py.
HAND_SOLVE = [
    {"pos": "QB", "bench_share": 0.15,
     "exposures": {"a_b": 10.0, "b_b": 0.0, "a_s": 0.0, "b_s": 10.0, "pie": 100.0},
     "expected": {"pb": 1.5, "ps": 8.5}},
    {"pos": "QB", "bench_share": 0.25,
     "exposures": {"a_b": 10.0, "b_b": 2.0, "a_s": 5.0, "b_s": 20.0, "pie": 100.0},
     "expected": {"pb": 1.8421052631578947, "ps": 3.289473684210526}},
]
HAND_SLICE = [
    {"x": 25.0, "rw": 10.0, "rs": 20.0, "tau": 1e-9, "expected": {"a": 10.0, "b": 5.0}},
    {"x": 15.0, "rw": 10.0, "rs": 20.0, "tau": 1e-9, "expected": {"a": 5.0, "b": 0.0}},
    {"x": 5.0, "rw": 10.0, "rs": 20.0, "tau": 1e-9, "expected": {"a": 0.0, "b": 0.0}},
]


def run_harness(cmd, payload):
    proc = subprocess.run(["node", str(HARNESS), cmd], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise AssertionError(f"harness {cmd} failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


def real_inputs():
    lists, _, _ = load_espn_lists(DEFAULT_CSV, "ppr")
    pies, _ = load_pies(DEFAULT_PIES, "ppr", 12)
    resolved, _, _ = resolve_identities(lists, DEFAULT_FIXTURE)
    pool_lists = {pos: [{"id": d["player_key"], "x": d["x"]} for d in resolved[pos]]
                  for pos in POSITIONS}
    return resolved, pool_lists, pies


def rel_close(a, b, tol=TOL):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


class TestPythonPortMatchesBrowser(unittest.TestCase):
    def test_pinned_solve_vectors(self):
        for vec in HAND_SOLVE:
            e = vec["exposures"]
            pb, ps = solve_tier_prices(e["a_b"], e["b_b"], e["a_s"], e["b_s"],
                                       e["pie"], vec["pos"], vec["bench_share"])
            self.assertTrue(rel_close(pb, vec["expected"]["pb"]), vec)
            self.assertTrue(rel_close(ps, vec["expected"]["ps"]), vec)
            got = run_harness("solve", {"vectors": [{
                "a_b": e["a_b"], "b_b": e["b_b"], "a_s": e["a_s"],
                "b_s": e["b_s"], "pie": e["pie"],
                "pos": vec["pos"], "bench_share": vec["bench_share"]}]})[0]
            self.assertNotIn("error", got, vec)
            self.assertTrue(rel_close(pb, got["pb"]), vec)
            self.assertTrue(rel_close(ps, got["ps"]), vec)

    def test_pinned_slice_vectors(self):
        from build_ddf_two_tier_leg import slice_exposures
        for vec in HAND_SLICE:
            a, b = slice_exposures(vec["x"], vec["rw"], vec["rs"], vec["tau"])
            self.assertTrue(rel_close(a, vec["expected"]["a"]), vec)
            self.assertTrue(rel_close(b, vec["expected"]["b"]), vec)

    def test_full_pipeline_parity_on_real_espn_inputs(self):
        """Tiers AND calibrations at 0.15 bit-exact vs the browser code."""
        _, pool_lists, pies = real_inputs()
        bench_mix = bench_mix_for_teams(12)
        pool = build_position_tiers(pool_lists, 12, dict(REF_SLOTS),
                                    REF_FLEX_COUNT, list(REF_FLEX_ELIGIBLE), bench_mix)
        cfg = {"teams": 12, "slots": dict(REF_SLOTS), "flexCount": REF_FLEX_COUNT,
               "flexEligible": list(REF_FLEX_ELIGIBLE), "benchMix": bench_mix}
        js_lists = {pos: [{"id": str(d["id"]), "x": d["x"]} for d in pool_lists[pos]]
                    for pos in POSITIONS}
        out = run_harness("pooltier", {"lists": js_lists, "cfg": cfg})
        self.assertIsNone(out["error"], out["error"])
        keys = (("rw", "rw"), ("rs", "rs"), ("tau", "tau"),
                ("aBench", "a_bench"), ("bBench", "b_bench"),
                ("aStart", "a_start"), ("bStart", "b_start"), ("surplus", "surplus"))
        for pos in POSITIONS:
            jt, pt = out["tiers"][pos], pool["tiers"][pos]
            for jk, pk in keys:
                self.assertTrue(rel_close(jt[jk], pt[pk]), (pos, jk, jt[jk], pt[pk]))
            py_cal = calibrate_position(pt, pies[pos], DEFAULT_BENCH_SHARE)
            js_cal = run_harness("calibrate", {"tier": jt, "pie": pies[pos],
                                               "share": DEFAULT_BENCH_SHARE})
            self.assertFalse(js_cal["invalid"], (pos, js_cal.get("reason")))
            for k in ("pb", "ps"):
                self.assertTrue(rel_close(js_cal[k], py_cal[k]), (pos, k, js_cal[k], py_cal[k]))
            # And the priced projections agree player-by-player.
            for d in pool_lists[pos][:25]:
                js_price = run_harness("calibrate", {"tier": jt, "pie": pies[pos],
                                                     "share": DEFAULT_BENCH_SHARE,
                                                     "probeX": d["x"]})["priceAt"]
                py_price = price_for_projection(d["x"], py_cal)
                self.assertTrue(rel_close(js_price, py_price), (pos, d))


class TestLegGuarantees(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.leg = build_leg(DEFAULT_CSV, DEFAULT_PIES, DEFAULT_FIXTURE,
                            "ppr", 12, DEFAULT_BENCH_SHARE)
        pies, _ = load_pies(DEFAULT_PIES, "ppr", 12)
        cls.pies = pies

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_espn_vintage_recorded(self):
        self.assertEqual(self.leg["inputs"]["espn_snapshot_date"], "2026-09-22")
        self.assertEqual(self.leg["schema"], "trade-value-ddf-leg-v1")

    def test_pie_identity_pre_rounding(self):
        for pos in POSITIONS:
            cal = self.leg["calibration"][pos]
            pie = self.pies[pos]
            self.assertTrue(
                abs(cal["bench_raw"] - DEFAULT_BENCH_SHARE * pie) <= 1e-9 * pie, pos)
            self.assertTrue(
                abs(cal["starter_raw"] - (1 - DEFAULT_BENCH_SHARE) * pie) <= 1e-9 * pie, pos)

    def test_normalize_then_round_max_is_70(self):
        values = [v["value"] for v in self.leg["values"]]
        self.assertEqual(max(values), 70.0)
        for v in self.leg["values"]:
            self.assertTrue(math.isfinite(v["value"]) and v["value"] >= 0)

    def test_full_precision_not_rounded(self):
        # At least one value must carry sub-display precision (proves the
        # artifact was not rounded to integers or 1dp).
        frac = [abs(v["value"] - round(v["value"], 1)) > 1e-12 for v in self.leg["values"]]
        self.assertTrue(any(frac))

    def test_espn_pure_rescoring(self):
        """Reception points are the only scoring difference; the rescoring
        is arithmetic on ESPN components, never expert blending."""
        rows = {}
        with DEFAULT_CSV.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["player_norm"] and row["has_espn_projection"] == "True" and row["eligible"] == "True":
                    rows[row["player_norm"]] = row
        lists_ppr, _, _ = load_espn_lists(DEFAULT_CSV, "ppr")
        lists_half, _, _ = load_espn_lists(DEFAULT_CSV, "half_ppr")
        ppr = {d["id"]: d["x"] for pos in POSITIONS for d in lists_ppr[pos]}
        half = {d["id"]: d["x"] for pos in POSITIONS for d in lists_half[pos]}
        checked = 0
        for norm, row in rows.items():
            if norm not in ppr:
                continue
            expected_gap = 0.5 * float(row["r_receptions"]) / 16
            self.assertTrue(rel_close(ppr[norm] - half[norm], expected_gap), norm)
            checked += 1
        self.assertGreater(checked, 300)

    def test_alias_map_resolves_verified_variants(self):
        by_pos = {pos: [] for pos in POSITIONS}
        by_pos["QB"].append({"id": "cameron ward", "name": "Cameron Ward",
                             "team": None, "x": 10.0})
        by_pos["RB"].append({"id": "cameron skattebo", "name": "Cameron Skattebo",
                             "team": None, "x": 10.0})
        by_pos["RB"].append({"id": "travis etienne jr", "name": "Travis Etienne Jr",
                             "team": None, "x": 10.0})
        by_pos["WR"].append({"id": "michael pittman jr", "name": "Michael Pittman Jr",
                             "team": None, "x": 10.0})
        resolved, review, aliases_used = resolve_identities(by_pos, DEFAULT_FIXTURE)
        keys = {d["player_key"] for pos in POSITIONS for d in resolved[pos]}
        self.assertEqual(keys, {697, 3664, 810, 561})
        self.assertEqual(len(aliases_used), 4)
        self.assertEqual(review, [])

    def test_unresolved_identity_goes_to_review(self):
        resolved, review, _ = resolve_identities(
            {"QB": [{"id": "not a real player", "name": "Not A Real Player",
                     "team": None, "x": 10.0}],
             "RB": [], "WR": [], "TE": []}, DEFAULT_FIXTURE)
        self.assertEqual(resolved["QB"], [])
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["reason"], "unresolved_identity")


class TestFailClosed(unittest.TestCase):
    def test_infeasible_shares_raise(self):
        for bad in (0.0, 1.0, -0.1, 1.5, float("nan"), float("inf")):
            with self.assertRaises(ValueError, msg=f"share={bad}"):
                check_share(bad)
        # Starter-must-exceed-bench is enforced even at a legal share:
        # degenerate exposures cannot calibrate.
        with self.assertRaises(ValueError):
            solve_tier_prices(0.0, 0.0, 0.0, 0.0, 100.0, "QB", 0.15)

    def test_nonpositive_pie_raises(self):
        _, pool_lists, _ = real_inputs()
        pool = build_position_tiers(pool_lists, 12, dict(REF_SLOTS), REF_FLEX_COUNT,
                                    list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(12))
        for bad_pie in (0.0, -5.0):
            with self.assertRaises(ValueError, msg=f"pie={bad_pie}"):
                calibrate_position(pool["tiers"]["QB"], bad_pie, DEFAULT_BENCH_SHARE)

    def test_missing_position_raises(self):
        with self.assertRaises(ValueError):
            calibrate_position(None, 100.0, DEFAULT_BENCH_SHARE)

    def test_mixed_vintage_csv_fails_closed(self):
        tmp = Path(tempfile.mkdtemp())
        src = DEFAULT_CSV.read_text(encoding="utf-8").splitlines(keepends=True)
        header, rows = src[0], src[1:]
        half = len(rows) // 2
        doctored = [header] + rows[:half] + [
            r.replace("2026-09-22", "2026-09-20") for r in rows[half:]]
        bad = tmp / "mixed.csv"
        bad.write_text("".join(doctored), encoding="utf-8")
        with self.assertRaises(SystemExit):
            load_espn_lists(bad, "ppr")

    def test_unknown_scoring_fails_closed(self):
        with self.assertRaises(SystemExit):
            load_espn_lists(DEFAULT_CSV, "superflex")

    def test_missing_pies_fail_closed(self):
        with self.assertRaises(SystemExit):
            load_pies(DEFAULT_PIES, "ppr", 16)  # file only ships 8/10/12/14-team pies

    def test_empty_surplus_position_fails_closed(self):
        # Zero above-waiver surplus (everyone tied at the waiver line) is
        # unpriceable: the economics have no pie to split.
        with self.assertRaises(ValueError):
            calibrate_position({"surplus": 0.0}, 59.0, DEFAULT_BENCH_SHARE)


if __name__ == "__main__":
    unittest.main()
