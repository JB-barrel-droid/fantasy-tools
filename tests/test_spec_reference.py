"""Clean-room spec reference (pipelines/spec_reference, part of JEG-479).

Unit tests built from the written spec's own statements (docs/methodology.md,
the QB8 investigation log, the leg artifact's pies_method), plus one data
check: on the built ESPN legs the spec's two-tier pricing reproduces the leg
wherever the requested bench share is inside every position's window.
No browser; runs in test-unit.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

from spec_reference import compare as sc  # noqa: E402
from spec_reference import twotier as tt  # noqa: E402
from spec_reference import value_model as vm  # noqa: E402


def _pool(teams=2):
    """A small two-team league: QB, RB, WR, TE descending projections."""
    rows = []
    key = 1
    for pos, n, top, step in (("QB", 8, 22.0, 1.1), ("RB", 14, 18.0, 1.0),
                              ("WR", 18, 16.0, 0.7), ("TE", 8, 12.0, 1.3)):
        for i in range(n):
            rows.append((key, pos, round(top - i * step, 3)))
            key += 1
    return rows


class TwoTierSpec(unittest.TestCase):
    def setUp(self):
        self.tiers = tt.build_pool(_pool(), teams=2)

    def test_bench_mix_scaled_round_half_up(self):
        self.assertEqual(tt.bench_counts(12), {"QB": 10, "RB": 27, "WR": 33, "TE": 10})
        self.assertEqual(tt.bench_counts(8), {"QB": 7, "RB": 18, "WR": 22, "TE": 7})
        self.assertEqual(tt.bench_counts(14), {"QB": 12, "RB": 32, "WR": 39, "TE": 12})

    def test_pool_counts_flex_and_waiver_line_is_next_unrostered(self):
        qb = self.tiers["QB"]
        self.assertEqual(len(qb.starters), 2)  # 2 teams x QB1, QB not flex-eligible
        flex_starters = sum(len(self.tiers[p].starters) for p in tt.FLEX_ELIGIBLE)
        self.assertEqual(flex_starters, 2 * (2 + 3 + 1) + 2)  # dedicated + 2 x FLEX1
        for t in self.tiers.values():
            self.assertEqual(t.rw, t.waiver[0][1])
            self.assertAlmostEqual(t.pie, sum(max(0, p - t.rw) for _, p in t.rostered))

    def test_window_edges_match_their_definitions(self):
        for pos, tier in self.tiers.items():
            sums = tt._group_sums(tier)
            lo, hi = tt.feasible_window(sums)
            sa, sb, ba, bb = sums
            # hi = bench surplus / total surplus, where pb = ps
            self.assertAlmostEqual(hi, (ba + bb) / (sa + sb + ba + bb))
            ps, pb = tt.solve_rates(sums, tier.pie, hi)
            self.assertAlmostEqual(ps, pb, places=9)
            # below lo the bench rate goes non-positive
            _, pb_lo = tt.solve_rates(sums, tier.pie, lo)
            self.assertAlmostEqual(pb_lo, 0.0, places=9)

    def test_calibration_splits_the_pie_by_share(self):
        for pos, tier in self.tiers.items():
            cal = tt.calibrate(tier, 0.15)
            self.assertTrue(cal.valid, (pos, cal.error))
            starter = sum(cal.ps * a + cal.pb * b for a, b in (tt.exposures(p, tier) for _, p in tier.starters))
            bench = sum(cal.ps * a + cal.pb * b for a, b in (tt.exposures(p, tier) for _, p in tier.bench))
            self.assertAlmostEqual(starter, (1 - cal.share_used) * tier.pie, places=9)
            self.assertAlmostEqual(bench, cal.share_used * tier.pie, places=9)
            self.assertGreater(cal.ps, cal.pb)
            self.assertGreater(cal.pb, 0)

    def test_below_window_steps_one_point_inside_lower_edge(self):
        tier = self.tiers["RB"]
        lo, hi = tt.feasible_window(tt._group_sums(tier))
        cal = tt.calibrate(tier, lo / 2)
        self.assertAlmostEqual(cal.share_used, lo + 0.01)
        self.assertTrue(cal.valid)

    def test_step_halves_when_window_is_narrow(self):
        self.assertAlmostEqual(tt._step_inside(0.10, 0.012, +1), 0.11)
        self.assertAlmostEqual(tt._step_inside(0.10, 0.008, +1), 0.105)
        self.assertAlmostEqual(tt._step_inside(0.10, 0.004, +1), 0.10 + 0.0025)

    def test_display_top_is_70_and_waiver_players_are_zero_not_missing(self):
        disp, _, tiers, _, tier_of = tt.price_leg(_pool(), teams=2)
        self.assertAlmostEqual(max(disp.values()), 70.0)
        for pos, tier in tiers.items():
            for key, _ in tier.waiver:
                self.assertEqual(disp[key], 0.0)
                self.assertEqual(tier_of[key], "waiver")

    def test_value_rises_with_projection_within_a_position(self):
        disp, _, tiers, _, _ = tt.price_leg(_pool(), teams=2)
        for tier in tiers.values():
            vals = [disp[k] for k, _ in tier.rostered]
            self.assertEqual(vals, sorted(vals, reverse=True))


class ValueModelSpec(unittest.TestCase):
    def test_dhondt_exact_totals_and_monotone(self):
        w = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
        prev = None
        for seats in range(0, 120, 7):
            a = vm.dhondt(seats, w)
            self.assertEqual(sum(a.values()), seats)
            if prev:
                self.assertTrue(all(a[p] >= prev[p] for p in w))
            prev = a

    def test_short_chart_extension_is_capped_and_needs_three_tail_players(self):
        chart = {1: 50, 2: 40, 3: 30, 4: 20, 5: 10, 6: 8}
        peer = {1: 100, 2: 80, 3: 60, 4: 40, 5: 20, 6: 16, 7: 14, 8: 30}
        ext = vm.extend_position(chart, [peer])
        # tail = values <= median (25): 4, 5, 6 -> ratio (20+10+8)/(40+20+16) = 0.5
        self.assertEqual([k for k, _ in ext], [8, 7])
        self.assertEqual(dict(ext)[7], 7.0)
        self.assertEqual(dict(ext)[8], 8.0)  # 15.0 capped at the last listed value
        self.assertEqual(vm.extend_position(chart, [{4: 40, 5: 20}]), [])

    def test_translate_reads_waiver_at_rostered_count(self):
        pos_of, natives = {}, {}
        k = 1
        for pos, n in (("QB", 40), ("RB", 80), ("WR", 100), ("TE", 40)):
            for i in range(n):
                pos_of[k] = pos
                natives[k] = 100.0 - i
                k += 1
        tr = vm.translate(natives, pos_of, teams=12)
        self.assertEqual(sum(tr["flex"].values()), 12)
        self.assertEqual(sum(tr["bench"].values()), 72)
        for pos in tt.POSITIONS:
            ranked = sorted((v for kk, v in natives.items() if pos_of[kk] == pos), reverse=True)
            self.assertEqual(tr["waiver"][pos], ranked[tr["rostered"][pos]])
            self.assertEqual(tr["waiver_method"][pos], "rostered_count")
        weights = [v for v in tr["implied_weights"].values() if v is not None]
        self.assertAlmostEqual(sum(weights), 1.0)

    def test_indexed_is_one_factor_and_keeps_order(self):
        natives = {1: 10.0, 2: 8.0, 3: 2.0, 4: 1.0}
        anchor = {1: 30.0, 2: 10.0, 3: 0.0}
        out = vm.indexed_published(natives, anchor, None, 9.0, teams=10)
        self.assertEqual(out, {k: 9.0 * v for k, v in natives.items()})  # < 40 shared: saved factor
        many = {i: float(100 - i) for i in range(60)}
        anc = {i: float(200 - 2 * i) for i in range(60)}
        out = vm.indexed_published(many, anc, None, None, teams=10)
        self.assertAlmostEqual(sum(out.values()), sum(anc.values()))
        self.assertEqual(sorted(out, key=out.get), sorted(many, key=many.get))
        saved = {1: 5.0}
        self.assertEqual(vm.indexed_published(natives, anchor, saved, 9.0, teams=12), saved)

    def test_adjusted_groups_share_budget_then_top_is_70(self):
        pos_of = {1: "RB", 2: "RB", 3: "RB", 4: "QB"}
        tr = {"vaw": {1: 6.0, 2: 2.0, 3: 1.0, 4: 3.0},
              "role": {1: "starter", 2: "starter", 3: "bench", 4: "starter"}}
        budgets = {f"{p}|{g}": 0.0 for p in tt.POSITIONS for g in ("starter", "bench")}
        budgets.update({"RB|starter": 40.0, "RB|bench": 5.0, "QB|starter": 10.0})
        out = vm.adjusted_published({"c": tr}, budgets, pos_of)["c"]
        lam = 70.0 / 30.0  # pre-scale top: 40 x 6/8 = 30
        self.assertAlmostEqual(out[1], 70.0)
        self.assertAlmostEqual(out[1] + out[2], 40.0 * lam)
        self.assertAlmostEqual(out[3], 5.0 * lam)
        self.assertAlmostEqual(out[4], 10.0 * lam)

    def test_raw_projection_series_totals_the_anchor(self):
        pos_of = {i: ("RB" if i % 2 else "WR") for i in range(200)}
        ppg = {i: 20.0 - i * 0.1 for i in range(200)}
        res = vm.projection_vaw(ppg, pos_of, teams=10)
        anchor = {i: max(0.0, 50 - i) for i in range(150)}
        series = vm.match_total(res["vaw"], anchor)
        shared = [k for k in series if k in anchor]
        self.assertAlmostEqual(sum(series[k] for k in shared), sum(anchor[k] for k in shared))


class SpecVsBuiltLeg(unittest.TestCase):
    """Data check: the spec's two-tier pricing on a built ESPN leg's own pool
    reproduces the leg where the default share is inside every window. The
    remaining gap is the unwritten glide (SG-1/SG-2), bounded at 0.25."""

    def test_reproduces_built_legs(self):
        legs = sorted((REPO / "data" / "ddf-two-tier").glob("ddf-*-espn-*-0p15/ddf_leg.json"))
        if not legs:
            self.skipTest("no built ESPN legs")
        latest = {}
        for p in legs:
            latest[p.parent.name.split("-", 2)[2]] = p
        checked = 0
        for name, path in sorted(latest.items()):
            leg = json.loads(path.read_text(encoding="utf-8"))
            if any(abs((c.get("bench_share_used") or 0) - 0.15) > 1e-9 for c in leg["calibration"].values()
                   if isinstance(c, dict) and c.get("pie")):
                continue
            pool = [(r["player_key"], r["pos"], r["ppg"]) for r in leg["values"] if r["pos"] in tt.POSITIONS]
            disp, _, _, cals, _ = tt.price_leg(pool, leg["inputs"]["teams"])
            for pos, cal in cals.items():
                self.assertAlmostEqual(cal.pie, leg["calibration"][pos]["pie"], places=6, msg=(name, pos))
            worst = max(abs(disp[r["player_key"]] - r["value"]) for r in leg["values"] if r["player_key"] in disp)
            self.assertLess(worst, 0.25, name)
            checked += 1
        self.assertGreater(checked, 0)


class Wiring(unittest.TestCase):
    def test_value_check_section_is_non_blocking(self):
        import value_check
        sec = value_check.spec_reference_section({})
        self.assertFalse(sec["blocking"])
        self.assertEqual(sec["values_compared"], 0)
        self.assertIn("SG-1", sec["spec_gaps"])

    def test_diff_counts_presence_and_missing_rows_apart(self):
        engine = {"1": {"x": 10.0}, "2": {"x": None}, "3": {"x": 5.0}}
        spec = {1: 10.04, 2: 0.0, 3: 5.2, 9: 0.0}
        d = sc.diff_setting(engine, spec, "x")
        self.assertEqual((d["compared"], d["mismatches"], d["presence"], d["no_engine_row"]), (3, 2, 1, 1))


if __name__ == "__main__":
    unittest.main()
