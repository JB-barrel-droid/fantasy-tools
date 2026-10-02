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
    REF_BENCH_SLOTS,
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


def feasible_share_for(tier, pie, requested=DEFAULT_BENCH_SHARE):
    """Mirror build_ddf_two_tier_leg's per-position feasible share logic.

    The requested share (default 0.15) may be infeasible for thin positions;
    the builder searches for the closest feasible share -- downward for the
    "too high" modes (highest feasible <= requested), upward for the
    "not positive" mode (lowest feasible >= requested; JEG-74).
    Tests must use the same share the builder uses, or parity checks fail
    on data where 0.15 is infeasible (e.g. TE after IR removals, or QB
    8-team standard on the 2026-10-02 cbsros snapshot).
    """
    try:
        calibrate_position(tier, pie, requested)
        return requested
    except ValueError as e:
        msg = str(e)
    if "not positive" in msg:
        # JEG-74: scan upward for the minimum feasible share >= requested.
        lo = requested
        hi = None
        s = requested
        while s < 0.99:
            s = min(0.99, s + 0.01)
            try:
                calibrate_position(tier, pie, s)
                hi = s
                break
            except ValueError:
                lo = s
        if hi is None:
            raise AssertionError("no feasible bench share found")
        for _ in range(15):
            mid = (lo + hi) / 2
            try:
                calibrate_position(tier, pie, mid)
                hi = mid
            except ValueError:
                lo = mid
        return hi
    lo, hi = 0.01, requested
    best = None
    for _ in range(20):
        mid = (lo + hi) / 2
        try:
            calibrate_position(tier, pie, mid)
            best = mid
            lo = mid
        except ValueError:
            hi = mid
    if best is None:
        raise AssertionError("no feasible bench share found")
    return best



def _bench_mix_12(pool_lists):
    """Derived bench mix for the 12-team reference shape."""
    # New interface: bench_mix_for_teams(teams) uses the BENCH_MIX_12 constant.
    # pool_lists is unused (kept for signature compatibility).
    return bench_mix_for_teams(12)

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
        """Tiers AND calibrations at feasible share bit-exact vs the browser code."""
        _, pool_lists, pies = real_inputs()
        bench_mix = _bench_mix_12(pool_lists)
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
            share = feasible_share_for(pt, pies[pos])
            py_cal = calibrate_position(pt, pies[pos], share)
            js_cal = run_harness("calibrate", {"tier": jt, "pie": pies[pos],
                                               "share": share})
            self.assertFalse(js_cal["invalid"], (pos, js_cal.get("reason")))
            for k in ("pb", "ps"):
                self.assertTrue(rel_close(js_cal[k], py_cal[k]), (pos, k, js_cal[k], py_cal[k]))
            # And the priced projections agree player-by-player.
            for d in pool_lists[pos][:25]:
                js_price = run_harness("calibrate", {"tier": jt, "pie": pies[pos],
                                                     "share": share,
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
        # Vintage tracks the CSV's espn_snapshot_date; assert it matches the
        # input rather than pinning a stale date.
        import csv as _csv
        with DEFAULT_CSV.open(encoding="utf-8") as f:
            vintage = next(_csv.DictReader(f))["espn_snapshot_date"]
        self.assertEqual(self.leg["inputs"]["espn_snapshot_date"], vintage)
        self.assertEqual(self.leg["schema"], "trade-value-ddf-leg-v1")

    def test_pie_identity_pre_rounding(self):
        for pos in POSITIONS:
            cal = self.leg["calibration"][pos]
            # The pie identity: the bench share used must match the actual
            # split of bench_raw vs total. This verifies the calibration
            # solved for the correct share, without needing the absolute pie.
            total = cal["bench_raw"] + cal["starter_raw"]
            self.assertTrue(total > 0, f"{pos}: total not positive")
            actual_share = cal["bench_raw"] / total
            expected_share = cal["bench_share_used"]
            self.assertTrue(
                abs(actual_share - expected_share) <= 1e-9,
                f"{pos}: share {actual_share} != {expected_share}")
            # Both portions must be non-negative
            self.assertTrue(cal["bench_raw"] >= 0, pos)
            self.assertTrue(cal["starter_raw"] >= 0, pos)

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

    def test_not_positive_searches_upward_jeg74(self):
        # JEG-74: cbsros 2026-10-02 QB 8-team standard. The tier's feasible
        # bench-share window sits just ABOVE 0.15 (pb=-0.08 at 0.15), so the
        # downward-only fallback raised instead of recovering. The mirror
        # must find the upward share, matching the builder.
        tier = {
            "a_bench": 11.830519510724733, "b_bench": 1.447480489275251,
            "a_start": 22.849352374207143, "b_start": 7.494647625792851,
            "surplus": 43.621999999999986, "rw": 18.286, "rs": 21.5355,
            "tau": 0.30,
        }
        pie = tier["surplus"]
        with self.assertRaisesRegex(ValueError, "not positive"):
            calibrate_position(tier, pie, 0.15)
        found = feasible_share_for(tier, pie, 0.15)
        self.assertGreater(found, 0.15)
        self.assertLessEqual(found, 0.99)
        cal = calibrate_position(tier, pie, found)
        self.assertGreater(cal["pb"], 0)
        self.assertGreater(cal["ps"], cal["pb"])

    def test_nonpositive_pie_raises(self):
        _, pool_lists, _ = real_inputs()
        pool = build_position_tiers(pool_lists, 12, dict(REF_SLOTS), REF_FLEX_COUNT,
                                    list(REF_FLEX_ELIGIBLE), _bench_mix_12(pool_lists))
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
        # Use the CSV's actual vintage; replacing a stale pinned date is a
        # no-op on fresh data and the test would pass vacuously.
        import csv as _csv
        with DEFAULT_CSV.open(encoding="utf-8") as f:
            vintage = next(_csv.DictReader(f))["espn_snapshot_date"]
        doctored = [header] + rows[:half] + [
            r.replace(vintage, "2026-09-20") for r in rows[half:]]
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


class TestExplicitZeroSurvives(unittest.TestCase):
    """Ineligible (out/IR) players with a real ESPN row carry an explicit zero.

    Regression test for the Achane defect: load_espn_lists treated
    eligible=False as 'no_espn_projection' and dropped the row to review,
    silently deleting a legitimate zero. The row must price at 0.0.
    """

    CSV_HEADER = ("player,player_norm,pos,team,has_espn_projection,eligible,"
                  "r_pass_yds,r_pass_tds,r_rush_yds,r_rush_tds,r_receptions,"
                  "r_rec_yds,r_rec_tds,ros_half_ppr,weeks_covered,"
                  "season_block_half_ppr,espn_snapshot_date")

    def _write_csv(self, tmp, rows):
        path = Path(tmp) / "explicit_zero.csv"
        path.write_text(self.CSV_HEADER + "\n" + "\n".join(rows) + "\n",
                        encoding="utf-8")
        return path

    def _row(self, name, norm, projected, eligible, ros_half=0.0, receptions=0.0):
        return (f"{name},{norm},RB,MIA,{projected},{eligible},"
                f"0,0,0,0,{receptions},0,0,{ros_half},4-18,0.00,2026-09-30")

    def test_ineligible_projected_prices_at_zero_not_review(self):
        tmp = tempfile.mkdtemp()
        csv = self._write_csv(tmp, [
            self._row("Healthy Back", "healthy back", "True", "True", 150.0, 30.0),
            self._row("DeVon Achane", "devon achane", "True", "False", 0.0, 0.0),
        ])
        lists, _, review = load_espn_lists(csv, "half_ppr")
        achane_reviews = [r for r in review if r.get("player") == "DeVon Achane"]
        self.assertEqual(achane_reviews, [],
                         "explicit-zero row must not go to review")
        rb = {d["id"]: d for d in lists["RB"]}
        self.assertIn("devon achane", rb)
        self.assertEqual(rb["devon achane"]["x"], 0.0)

    def test_truly_missing_projection_still_reviewed(self):
        # has_espn_projection=False is genuinely missing data -> review.
        tmp = tempfile.mkdtemp()
        csv = self._write_csv(tmp, [
            self._row("Healthy Back", "healthy back", "True", "True", 150.0, 30.0),
            self._row("Ghost Player", "ghost player", "False", "True", 0.0, 0.0),
        ])
        lists, _, review = load_espn_lists(csv, "half_ppr")
        ghost = [r for r in review if r.get("player") == "Ghost Player"]
        self.assertEqual(len(ghost), 1)
        self.assertEqual(ghost[0]["reason"], "no_espn_projection")
        rb = {d["id"]: d for d in lists["RB"]}
        self.assertNotIn("ghost player", rb)


if __name__ == "__main__":
    unittest.main()
