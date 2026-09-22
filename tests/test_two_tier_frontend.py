"""Two-tier frontend port tests: curve-widget.js <-> starter_model.py.

The widget's pure two-tier helpers (globalThis.TradeValueTwoTier) are loaded
in Node with no DOM. Pinned vectors come from the shared golden file
(tests/golden/two_tier_vectors.json in the football-signal repo); hand-
computed vectors are vendored here so the core parity tests stand alone.
"""
import json
import math
import os
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIDGET = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
HARNESS = Path(__file__).resolve().parent / "two_tier_harness.js"
GOLDEN = Path(os.path.expanduser(
    "~/workspace/goals/football-signal-database-and-app/tests/golden/two_tier_vectors.json"))
PLAYERS = REPO / "data" / "fixtures" / "current" / "players.json"
COMPARE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"

TOL = 1e-9

# Hand-computed pinned vectors (vendored; also present in the golden file).
HAND_SOLVE = [
    {"pos": "QB", "bench_share": 0.15,
     "exposures": {"a_b": 10.0, "b_b": 0.0, "a_s": 0.0, "b_s": 10.0, "pie": 100.0},
     "expected": {"pb": 1.5, "ps": 8.5}},
    {"pos": "QB", "bench_share": 0.25,
     "exposures": {"a_b": 10.0, "b_b": 2.0, "a_s": 5.0, "b_s": 20.0, "pie": 100.0},
     "expected": {"pb": 1.8421052631578947, "ps": 3.289473684210526}},
]
HAND_SOLVE_INFEASIBLE_SHARES = [0.0, 1.0, -0.1, 1.5]
HAND_SLICE = [
    {"x": 25.0, "rw": 10.0, "rs": 20.0, "tau": 1e-9, "expected": {"a": 10.0, "b": 5.0}},
    {"x": 15.0, "rw": 10.0, "rs": 20.0, "tau": 1e-9, "expected": {"a": 5.0, "b": 0.0}},
    {"x": 5.0, "rw": 10.0, "rs": 20.0, "tau": 1e-9, "expected": {"a": 0.0, "b": 0.0}},
]
HAND_INTERVAL = {
    "pos": "QB",
    "exposures": {"a_b": 10.0, "b_b": 0.0, "a_s": 0.0, "b_s": 10.0, "pie": 100.0},
    # p_b = 10*share > 0; p_s = 10*(1-share) > p_b iff share < 0.5
    "expected": {"lo": 7.424169921875001e-05, "hi": 0.4999812777099608},
}
HAND_SLIDER = {
    "intervals": {"QB": [0.0669439130859375, 0.22257987066650392],
                  "RB": [0.045557336914062496, 0.18994746276855468],
                  "WR": [0.058228150878906246, 0.20353997607421875],
                  "TE": [0.041309318359375, 0.18117977288818354]},
    "expected": [0.0669439130859375, 0.18117977288818354],
}
HAND_DISPLAY = {
    "raw": {"a": 40.3, "b": 39.9, "c": 10.0},
    "expected": {"values": {"a": 70, "b": 69, "c": 17},
                 "scale": 1.7369727047146404},
}


def run_harness(cmd, payload):
    proc = subprocess.run(["node", str(HARNESS), cmd],
                          input=json.dumps(payload), capture_output=True,
                          text=True, timeout=180)
    if proc.returncode != 0:
        raise AssertionError(f"harness {cmd} failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


def load_golden():
    if not GOLDEN.exists():
        return None
    return json.loads(GOLDEN.read_text())


def extract_function(text, name):
    """Extract a top-level `function name(...) {...}` body by brace matching."""
    m = re.search(r"function %s\(.*?\) \{" % re.escape(name), text)
    if not m:
        return None
    depth = 0
    for i in range(m.start(), len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[m.start():i + 1]
    return None


class TestTwoTierPort(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden()

    def assertSolveMatches(self, vec):
        e = vec["exposures"]
        got = run_harness("solve", {"vectors": [{
            "a_b": e["a_b"], "b_b": e["b_b"], "a_s": e["a_s"],
            "b_s": e["b_s"], "pie": e["pie"],
            "pos": vec.get("pos", "?"), "bench_share": vec["bench_share"]}]})[0]
        self.assertNotIn("error", got, f"solve raised for {vec}")
        self.assertLess(abs(got["pb"] - vec["expected"]["pb"]), TOL)
        self.assertLess(abs(got["ps"] - vec["expected"]["ps"]), TOL)

    def test_pinned_solve_vectors_hand(self):
        for vec in HAND_SOLVE:
            self.assertSolveMatches(vec)

    def test_pinned_solve_vectors_golden(self):
        if self.golden is None:
            self.skipTest("golden vectors file absent")
        for vec in self.golden["solve"]:
            self.assertSolveMatches(vec)

    def test_pinned_solve_infeasible(self):
        e = HAND_SOLVE[0]["exposures"]
        vectors = [{"a_b": e["a_b"], "b_b": e["b_b"], "a_s": e["a_s"],
                    "b_s": e["b_s"], "pie": e["pie"], "pos": "QB",
                    "bench_share": s} for s in HAND_SOLVE_INFEASIBLE_SHARES]
        for got in run_harness("solve", {"vectors": vectors}):
            self.assertIn("error", got)
        if self.golden is None:
            self.skipTest("golden vectors file absent")
        gv = [{"a_b": v["exposures"]["a_b"], "b_b": v["exposures"]["b_b"],
               "a_s": v["exposures"]["a_s"], "b_s": v["exposures"]["b_s"],
               "pie": v["exposures"]["pie"], "pos": v["pos"],
               "bench_share": v["bench_share"]} for v in self.golden["solve_infeasible"]]
        for got in run_harness("solve", {"vectors": gv}):
            self.assertIn("error", got)

    def assertSliceMatches(self, vec):
        a, b = run_harness("slice", {"vectors": [vec]})[0]
        self.assertLess(abs(a - vec["expected"]["a"]), TOL)
        self.assertLess(abs(b - vec["expected"]["b"]), TOL)

    def test_pinned_slice_vectors_hand(self):
        for vec in HAND_SLICE:
            self.assertSliceMatches(vec)

    def test_pinned_slice_vectors_golden(self):
        if self.golden is None:
            self.skipTest("golden vectors file absent")
        for vec in self.golden["slice_exposures"]:
            self.assertSliceMatches(vec)

    def assertIntervalMatches(self, vec):
        e = vec["exposures"]
        got = run_harness("interval", {"vectors": [{
            "a_b": e["a_b"], "b_b": e["b_b"], "a_s": e["a_s"],
            "b_s": e["b_s"], "pie": e["pie"],
            "pos": vec.get("pos", "?")}]})[0]
        self.assertIsNotNone(got, f"interval came back null for {vec}")
        self.assertLess(abs(got[0] - vec["expected"]["lo"]), TOL)
        self.assertLess(abs(got[1] - vec["expected"]["hi"]), TOL)

    def test_pinned_feasible_intervals_hand(self):
        self.assertIntervalMatches(HAND_INTERVAL)

    def test_pinned_feasible_intervals_golden(self):
        if self.golden is None:
            self.skipTest("golden vectors file absent")
        for vec in self.golden["feasible_intervals"]:
            self.assertIntervalMatches(vec)

    def test_pinned_slider_bounds_hand(self):
        got = run_harness("slider", {"intervals": HAND_SLIDER["intervals"]})
        self.assertIsNotNone(got)
        self.assertLess(abs(got[0] - HAND_SLIDER["expected"][0]), TOL)
        self.assertLess(abs(got[1] - HAND_SLIDER["expected"][1]), TOL)
        empty = run_harness("slider", {"intervals": {"QB": [0.4, 0.5], "RB": [0.1, 0.2]}})
        self.assertIsNone(empty)

    def test_pinned_slider_bounds_golden(self):
        if self.golden is None:
            self.skipTest("golden vectors file absent")
        got = run_harness("slider", {"intervals": self.golden["slider_bounds"]["intervals"]})
        exp = self.golden["slider_bounds"]["expected"]
        self.assertLess(abs(got[0] - exp["lo"]), TOL)
        self.assertLess(abs(got[1] - exp["hi"]), TOL)

    def test_pinned_display_hand(self):
        got = run_harness("display", {"raw": HAND_DISPLAY["raw"]})
        exp = HAND_DISPLAY["expected"]
        self.assertEqual(got["values"], exp["values"])
        self.assertLess(abs(got["scale"] - exp["scale"]), TOL)

    def test_pinned_display_golden(self):
        if self.golden is None:
            self.skipTest("golden vectors file absent")
        d = self.golden["display"]
        got = run_harness("display", {"raw": d["raw"]})
        self.assertEqual(got["values"], d["expected"]["values"])
        self.assertLess(abs(got["scale"] - d["expected"]["scale"]), TOL)
        self.assertTrue(d["expected"]["top_is_70"])
        self.assertTrue(d["expected"]["order_preserved"])

    def test_normalize_then_round_negative(self):
        # The named defect: rounding raw values FIRST, then scaling. On a
        # pool whose max raw value is below 70 the scale (> 1) amplifies the
        # rounding error and the top displayed player misses 70.
        # Normalize-then-round must land the top player exactly on 70.
        got = run_harness("display", {"raw": {"a": 40.3, "b": 39.9, "c": 10.0}})
        self.assertEqual(got["values"]["a"], 70)
        self.assertGreater(got["scale"], 1.0)
        vals = [got["values"]["a"], got["values"]["b"], got["values"]["c"]]
        self.assertEqual(vals, sorted(vals, reverse=True), "rounding must not invert order")

    # ---- bench mix: invariants, not pinned magic numbers -------------------
    # The previous version of this test pinned the exact output of the
    # hardcoded BENCH_MIX_12. That constant summed to 80 across 12 teams --
    # 6.67 bench spots per team, a league nobody can field -- and the pin
    # asserted it as correct. These guards assert the properties that decide
    # whether the mix is RIGHT, and each is negative-tested below against the
    # constant it replaced.

    @staticmethod
    def _pools():
        with PLAYERS.open() as f:
            players = json.load(f)["players"]
        pools = {}
        for pos in ("QB", "RB", "WR", "TE"):
            xs = [max(0.0, p["ecr_ppg"]["half_ppr"]) for p in players
                  if p["pos"] == pos
                  and isinstance((p.get("ecr_ppg") or {}).get("half_ppr"), (int, float))]
            pools[pos] = sorted(xs, reverse=True)
        return pools

    def test_bench_mix_sums_to_league_bench_capacity(self):
        """The parts must partition teams * bench_slots exactly."""
        pools = self._pools()
        for teams in (8, 10, 12, 14):
            for bench in (4, 6, 8):
                mix = run_harness("benchmix", {"teams": teams, "benchSlots": bench,
                                               "pools": pools})
                self.assertEqual(sum(mix.values()), teams * bench,
                                 f"teams={teams} bench={bench} mix={mix}")

    def test_legacy_constant_fails_the_capacity_invariant(self):
        """Negative test: the guard above must REJECT the constant it replaced."""
        legacy = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
        self.assertNotEqual(sum(legacy.values()), 12 * 6,
                            "legacy mix would have passed -- guard proves nothing")
        self.assertEqual(sum(legacy.values()), 80)

    def test_bench_mix_never_rosters_past_the_irrelevance_floor(self):
        """ROSTERED depth (starters + bench) must stay at or above the floor rank.

        Comparing the bench COUNT to the floor RANK is vacuously true -- the
        counts are far smaller than the ranks either way. The cap binds on the
        rostered total, so that is what this asserts.
        """
        pools = self._pools()
        for teams in (10, 12):
            d = run_harness("benchmixdetail", {"teams": teams, "benchSlots": 6, "pools": pools})
            bound = False
            for pos, n in d["mix"].items():
                rostered = d["starters"][pos] + n
                self.assertLessEqual(
                    rostered, d["floor"][pos],
                    f"{pos}: rostered {rostered} passes irrelevance floor #{d['floor'][pos]}")
                if rostered == d["floor"][pos]:
                    bound = True
            if teams == 12:
                self.assertTrue(bound, "no position reached its floor -- cap is untested here")

    def test_bench_mix_responds_to_roster_shape(self):
        """Superflex must raise bench QB; a pinned constant cannot."""
        pools = self._pools()
        base = run_harness("benchmix", {"teams": 12, "benchSlots": 6, "pools": pools})
        sflex = run_harness("benchmix", {"teams": 12, "benchSlots": 6, "pools": pools,
                                         "flexEligible": ["QB", "RB", "WR", "TE"]})
        self.assertGreater(sflex["QB"], base["QB"],
                           f"superflex did not deepen QB: {base} -> {sflex}")

    def test_tail_floor_scans_from_the_bottom(self):
        """A top-down scan returns the UPPER plateau; this must not."""
        # steep head, long flat tail: the floor belongs at the end of the decline
        # steep head, decline ending at rank 10, then a long flat tail
        xs = [20.0, 19.9, 19.8, 19.7, 19.6, 15.0, 10.0, 6.0, 3.0, 1.0] + [0.9] * 30
        floor = run_harness("tailfloor", {"xs": xs})
        self.assertGreater(floor, 5, "floor landed on the head plateau (top-down scan)")
        # The smoothing window makes the floor land at most FLOOR_WINDOW ranks
        # into the flat zone. It errs deep, which is the safe direction for a
        # cap -- it never truncates live players.
        self.assertLessEqual(floor, 10 + 5, f"floor {floor} is more than a window past the decline")
        self.assertTrue(all(x <= 1.0 for x in xs[floor - 1:]),
                        "everything at or below the floor must be flat-tail value")


def build_configs():
    """The 12 supported scoring x teams configs from fixture data."""
    with PLAYERS.open() as f:
        players = json.load(f)["players"]
    with COMPARE.open() as f:
        compare = json.load(f)["sources"]["espn"]["combos"]
    compact = {"ppr": "full", "half_ppr": "half", "standard": "standard"}
    ref_slots = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
    ref_mix12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
    configs = []
    for scoring in ["standard", "half_ppr", "ppr"]:
        for teams in [8, 10, 12, 14]:
            lists = {"QB": [], "RB": [], "WR": [], "TE": []}
            for i, pl in enumerate(players):
                if pl.get("pos") not in lists:
                    continue
                x = (pl.get("espn_ppg") or {}).get(scoring)
                if not isinstance(x, (int, float)):
                    continue
                lists[pl["pos"]].append({"id": i, "x": float(x)})
            combo = compare[f"{compact[scoring]}_{teams}"]
            pies = {p: combo["index_total"][p]["target_total"] for p in lists}
            bench_mix = {p: math.floor(ref_mix12[p] * teams / 12 + 0.5) for p in lists}
            configs.append({
                "name": f"{scoring}/{teams}",
                "lists": lists,
                "cfg": {"teams": teams, "slots": ref_slots, "flexCount": 1,
                        "flexEligible": ["RB", "WR", "TE"], "benchMix": bench_mix},
                "pies": pies,
                "shares": [0.15, 0.1],
            })
    return configs


class TestTwoTierConfigs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_harness("multipool", {"configs": build_configs()})
        cls.by_name = {r["name"]: r for r in cls.results}

    def test_all_configs_contain_recommended_share(self):
        blockers = []
        for name, r in sorted(self.by_name.items()):
            with self.subTest(config=name):
                self.assertIsNone(r["poolError"], f"pool build failed: {r['poolError']}")
                for pos in ["QB", "RB", "WR", "TE"]:
                    self.assertIsNotNone(r["intervals"][pos], f"{pos} has no feasible interval")
                    self.assertFalse(r["cals"]["0.15"][pos]["invalid"],
                                     f"{pos} invalid at 0.15: {r['cals']['0.15'][pos]['reason']}")
                self.assertIsNotNone(r["bounds"], "empty slider intersection")
                lo, hi = r["bounds"]
                if not (lo <= 0.15 <= hi):
                    blockers.append(name)
                self.assertLessEqual(lo, 0.15)
                self.assertGreaterEqual(hi, 0.15)
                # Inward-rounded endpoints stay strictly feasible, and the
                # recommended tick stays reachable.
                self.assertEqual(r["endpointsFeasible"], [True, True])
                self.assertTrue(r["recInside"])
        self.assertEqual(blockers, [], "BLOCKER: 0.15 infeasible for supported combos")

    def test_slider_change_recomputes_rates(self):
        for name, r in sorted(self.by_name.items()):
            with self.subTest(config=name):
                for pos in ["QB", "RB", "WR", "TE"]:
                    a = r["cals"]["0.15"][pos]
                    b = r["cals"]["0.1"][pos]
                    self.assertFalse(a["invalid"])
                    self.assertFalse(b["invalid"])
                    self.assertGreater(a["ps"], a["pb"])
                    self.assertGreater(b["ps"], b["pb"])
                    # The solve is parametric in the share: rates move.
                    self.assertFalse(
                        abs(a["pb"] - b["pb"]) < 1e-12 and abs(a["ps"] - b["ps"]) < 1e-12,
                        f"{pos} rates did not move with the share")


class TestCurveCollapseGuard(unittest.TestCase):
    """Negative tests for the curve collapse guard.

    The guard was loosened on 2026-09-22 (it had been a literal `> 70`, which
    the ESPN leg legitimately falls below after Week 2 re-anchoring, so it
    threw on every load and left the chart blank). Loosening a guard is only
    safe if something proves it still fails closed -- the module dashboard
    called that out as the gap. These are that proof.
    """

    def peaks(self, cases):
        return run_harness("collapse", {"cases": cases})

    def test_floor_is_below_live_curves_and_far_above_collapse(self):
        floor = self.peaks([{"peaks": {}}])["floor"]
        # Live ESPN leg peaks ~67.8; a fixed pie of ~3197 over ~596 players
        # means a collapsed curve peaks near the ~5.4 mean.
        self.assertLess(floor, 60, "floor is close enough to live peaks to trip on real data")
        self.assertGreater(floor, 12, "floor is so low a collapsed curve would pass")

    def test_healthy_peaks_pass(self):
        got = self.peaks([{"peaks": {
            "espn": 67.8, "fantasycalc_adjusted": 84.7,
            "usatoday_adjusted": 92.0, "fantasypros_adjusted": 87.4,
            "cbs_adjusted": 92.1,
        }}])
        self.assertEqual([True], got["results"])

    def test_collapsed_curve_trips_the_guard(self):
        cases = [
            {"peaks": {"espn": 5.4, "usatoday_adjusted": 92.0}},   # collapsed to the pie mean
            {"peaks": {"espn": 0, "usatoday_adjusted": 92.0}},     # zeroed out entirely
            {"peaks": {"espn": 0.94, "usatoday_adjusted": 92.0}},  # normalized to 0-1 by mistake
            {"peaks": {"espn": 67.8, "usatoday_adjusted": 1.0}},   # a single bad source is enough
        ]
        self.assertEqual([False, False, False, False], self.peaks(cases)["results"])

    def test_non_finite_peaks_trip_the_guard(self):
        # A NaN peak means every value in that map was NaN or the map was
        # empty; `NaN > floor` is false, but assert it rather than rely on it.
        got = self.peaks([{"peaks": {"espn": None}}, {"peaks": {"espn": 67.8, "cbs_adjusted": None}}])
        self.assertEqual([False, False], got["results"])

    def test_empty_peak_set_is_vacuously_true(self):
        # No active source with data is a different failure (validValues /
        # eightSources); the collapse guard must not double-report it.
        self.assertEqual([True], self.peaks([{"peaks": {}}])["results"])

    def test_live_fixture_curves_clear_the_floor(self):
        """The shipped fixture must not be anywhere near the floor.

        Catches the inverse of the old bug: a future re-anchor that quietly
        pushes a real curve down toward collapse territory.
        """
        comparison = json.loads(COMPARE.read_text(encoding="utf-8"))
        floor = self.peaks([{"peaks": {}}])["floor"]
        for key, source in comparison["sources"].items():
            combos = source.get("combos") or {}
            combo = combos.get("full_12") or combos.get("full_12_qb1")
            if not combo:
                continue
            values = combo.get("values") or combo.get("reindexed") or {}
            if not values:
                continue
            peak = max(values.values())
            self.assertGreater(peak, floor * 1.5,
                               f"{key} peaks at {peak}, uncomfortably close to the collapse floor {floor}")


class TestTwoTierFailClosed(unittest.TestCase):
    def test_global_share_object_shape_and_fallback(self):
        # The slider writes one global object to all skill positions; each
        # position falls back to default; K/DST are excluded (default).
        got = run_harness("shares", {"share": 0.15})
        self.assertEqual(got["object"],
                         {"default": 0.15, "QB": 0.15, "RB": 0.15, "WR": 0.15, "TE": 0.15})
        self.assertNotIn("K", got["object"])
        self.assertNotIn("DST", got["object"])
        for pos in ["QB", "RB", "WR", "TE", "K", "DST"]:
            self.assertEqual(got["lookups"][pos], 0.15)
        # A sparse object (future per-position slider) still falls back.
        self.assertEqual(got["sparse"], 0.2)

    def test_degenerate_pool_withholds_position(self):
        # Exposures whose economics run backwards (ps <= pb at any share):
        # the position must be withheld with the visible flag, never priced.
        tier = {"rw": 0.0, "rs": 10.0, "tau": 1.0,
                "aBench": 450.0, "bBench": 50.0, "aStart": 50.0, "bStart": 450.0,
                "surplus": 100.0}
        got = run_harness("calibrate", {"tier": tier, "pie": 1000.0,
                                        "share": 0.5, "probeX": 20.0})
        self.assertTrue(got["invalid"])
        self.assertIn("does not exceed", got["reason"])
        self.assertIsNone(got["pb"])
        self.assertIsNone(got["ps"])
        self.assertEqual(got["priceAt"], 0, "withheld position must price at zero")
        self.assertEqual(got["withheldFlag"], "withheld: calibration failed closed")


class TestStage1FallbackFrozen(unittest.TestCase):
    # The stage-1 fallback contract: when the adjustment asset carries no
    # cells (all four sources are pending stage 2), the widget must render
    # the exact inherited fallback branch. The original /tmp baseline was
    # lost to /tmp cleanup; the three fallback function bodies were pinned
    # byte-for-byte into tests/stage1_fallback_golden.json from the stage-1
    # code, and the byte-identical check passed against the /tmp baseline
    # while it still existed.
    GOLDEN_PATH = Path(__file__).resolve().parent / "stage1_fallback_golden.json"
    LIVE_IDS = ["DISPLAY_BENCH_SHARE", "benchShare", "TwoTier",
                "refitLiveCells", "liveCellsCache", "ddfTwoTierValues"]

    def test_fallback_branch_functions_unchanged(self):
        golden = json.loads(self.GOLDEN_PATH.read_text())
        current = WIDGET.read_text()
        for name, body in golden.items():
            new = extract_function(current, name)
            self.assertIsNotNone(new, f"{name} missing from widget")
            self.assertEqual(new, body,
                             f"{name} body changed: stage-1 fallback must stay byte-identical")
            for ident in self.LIVE_IDS:
                self.assertIsNone(
                    re.search(r"(?<![A-Za-z_$])" + re.escape(ident) + r"(?![A-Za-z_$])", new),
                    f"{name} references live machinery {ident}: empty-cell fallback is not independent")

    def test_display_share_frozen(self):
        text = WIDGET.read_text()
        self.assertIn("const DISPLAY_BENCH_SHARE = DEFAULT_BENCH_SHARE;", text)
        self.assertIn("function normalizeTradeChartToFixedPie(values, share = DISPLAY_BENCH_SHARE)", text)
        body = extract_function(text, "buildEspnRows")
        self.assertIsNotNone(body)
        self.assertNotRegex(body, r"(?<!DISPLAY_)benchShare",
                            "buildEspnRows must not read the live slider share")
        self.assertIn("DISPLAY_BENCH_SHARE", body)

    def test_espn_rows_use_raw_projection_vorp(self):
        # Negative-tested 2026-09-22: buildEspnRows used the modeled
        # "ESPN-implied" combo values (buildPublishedSourceMap("espn")) as the
        # raw input. Those already carry a ~91% starter share, so the 85/15
        # fixed-pie inverted: starters were marked DOWN (Achane 54.8 -> 51.0).
        # The ESPN curves must use the true raw projection-minus-waiver VORP
        # (rawProjectionVorp from ESPN projections only), whose ~69% starter
        # share makes the fixed-pie correctly mark starters up and bench down.
        # Reintroducing `publishedVorp` into buildEspnRows must fail this test.
        text = WIDGET.read_text()
        body = extract_function(text, "buildEspnRows")
        self.assertIsNotNone(body, "buildEspnRows missing from widget")
        self.assertNotIn("publishedVorp", body,
                         "buildEspnRows must not use modeled published ESPN values")
        self.assertNotIn('buildPublishedSourceMap("espn")', body,
                         "buildEspnRows must not read the ESPN-implied combo")
        self.assertIn("rawProjectionVorp", body,
                      "buildEspnRows must compute raw projection-minus-waiver VORP")
        self.assertRegex(body, r"rawVorp:\s*row\.rawProjectionVorp",
                         "rawVorp must be the raw projection-minus-waiver value")


if __name__ == "__main__":
    unittest.main()
