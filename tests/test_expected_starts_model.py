"""JEG-521 G1: the expected-starts analysis model (pipelines/expected_starts_model.py).

Pins the arithmetic the spec (docs/methodology.md ES-*) states: the band
probabilities and surpluses, the fill-in probability, the limits (sigma 0 is
the fill-in-only bound; m = bye = 0 with every player start-worthy is plain
value above waivers), the pie identity, and order preservation within every
source and position on the live build.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import expected_starts_model as es  # noqa: E402


class NormalPieces(unittest.TestCase):
    def test_bands_partition_the_surplus(self):
        mu, s, w = 10.0, 3.0, 4.0
        edges = [w, 6.0, 8.0, 11.0, math.inf]
        total = sum(es.band_surplus(mu, s, w, a, b) for a, b in zip(edges, edges[1:]))
        # E[(X - w)^+] for a normal
        z = (w - mu) / s
        expected = (mu - w) * (1 - es.Phi(z)) + s * es.phi(z)
        self.assertAlmostEqual(total, expected, places=12)
        probs = sum(es.prob_band(mu, s, a, b) for a, b in zip(edges, edges[1:]))
        self.assertAlmostEqual(probs, 1 - es.Phi(z), places=12)

    def test_zero_sigma_is_a_point_mass(self):
        self.assertEqual(es.prob_band(10.0, 0.0, 8.0, math.inf), 1.0)
        self.assertEqual(es.prob_band(10.0, 0.0, 11.0, math.inf), 0.0)
        self.assertEqual(es.band_surplus(10.0, 0.0, 4.0, 8.0, 12.0), 6.0)
        self.assertEqual(es.band_surplus(10.0, 0.0, 4.0, 11.0, 12.0), 0.0)

    def test_fill_probability_is_binomial_tail(self):
        q = 0.2
        self.assertAlmostEqual(es.binomial_at_least(2, q, 1), 1 - 0.8 ** 2)
        self.assertAlmostEqual(es.binomial_at_least(2, q, 2), q * q)
        self.assertEqual(es.binomial_at_least(2, q, 3), 0.0)
        self.assertEqual(es.binomial_at_least(3, q, 0), 1.0)


class Allocation(unittest.TestCase):
    def test_greedy_flex_and_lines(self):
        lists = {"QB": [20, 19, 18, 17], "RB": [15, 14, 13, 12, 11, 10, 9, 8], "WR": [12, 11, 10, 9, 8, 7, 6, 5, 4],
                 "TE": [9, 8, 7, 6]}
        a = es.alloc(lists, 2)
        self.assertEqual(a["RB"]["dedicated"], 4)
        self.assertEqual(a["WR"]["dedicated"], 6)
        # Flex candidates: RB 11, 10, 9, 8 and WR 6, 5, 4 and TE 7, 6 -> the two best are RB 11, RB 10.
        self.assertEqual(a["RB"]["flex"], 2)
        self.assertEqual(a["WR"]["flex"], 0)
        self.assertEqual(sum(v["bench"] for v in a.values()), 12)
        w, l = es.lines(lists["RB"], a["RB"]["starters"], a["RB"]["rostered"])
        self.assertEqual((w, l), (8, 9))  # 6 starters, bench RB 4 -> rostered 10 > listed 8: w = last listed


class Components(unittest.TestCase):
    VALUES = [20.0, 18.0, 16.0, 14.0, 12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0]

    def test_sigma_zero_is_the_fill_in_bound(self):
        # 2 teams, 2 starters each (S = 4), rostered 8 -> w = 8, l = 12.
        c = es.position_components(self.VALUES, 4, 8, 2, m=0.1, bye=0.05, sigma_rel=0.0, sigma_floor=0.0)
        avail = 0.95 * 0.9
        self.assertAlmostEqual(c["avail"], avail)
        p = c["players"]
        # Starters: the whole surplus at availability.
        self.assertAlmostEqual(p[0]["starter_part"], avail * 12.0)
        self.assertEqual(p[0]["bench_part"], 0.0)
        # The first non-starter (index 4, value 12 = l) is depth-1 bench, not
        # start-worthy (VP-2.5: l is his value). He fills when at least 1 of the
        # team's 2 starters is out.
        q = 0.05 + 0.95 * 0.1
        self.assertEqual(p[4]["starter_part"], 0.0)
        self.assertAlmostEqual(p[4]["bench_part"], avail * 4.0 * (1 - (1 - q) ** 2))
        self.assertAlmostEqual(p[5]["bench_part"], avail * 3.0 * (1 - (1 - q) ** 2))
        self.assertEqual(p[5]["starter_part"], 0.0)
        # Depth-2 bench (index 6, 10) needs both starters out.
        self.assertAlmostEqual(p[6]["bench_part"], avail * 2.0 * q * q)
        # At the waiver line and below: no value.
        self.assertEqual(p[8]["v"], 0.0)
        self.assertEqual(p[8]["starter_part"] + p[8]["bench_part"], 0.0)

    def test_share_form_is_bounded_by_availability_and_monotone(self):
        c = es.position_components(self.VALUES, 4, 8, 2, m=0.1, bye=0.05, sigma_rel=0.3, sigma_floor=1.0)
        prev = None
        for pl in c["players"]:
            if pl["share"] is not None:
                self.assertLessEqual(pl["share"], c["avail"] + 1e-12)
            total = pl["starter_part"] + pl["bench_part"]
            if prev is not None:
                self.assertLessEqual(total, prev + 1e-12)
            prev = total

    def test_option_form_exceeds_share_form(self):
        a = es.position_components(self.VALUES, 4, 8, 2, 0.1, 0.05, 0.3, 1.0, form="share")
        b = es.position_components(self.VALUES, 4, 8, 2, 0.1, 0.05, 0.3, 1.0, form="option")
        # Near the line the convex form pays for the upside; a borderline player gets more.
        self.assertGreater(b["players"][5]["starter_part"] + b["players"][5]["bench_part"],
                           a["players"][5]["starter_part"] + a["players"][5]["bench_part"])

    def test_slices_sum_to_the_surplus(self):
        c = es.slice_components(self.VALUES, 4, 8)
        for pl in c["players"]:
            self.assertAlmostEqual(pl["starter_part"] + pl["bench_part"], pl["v"])
        self.assertEqual(c["players"][0]["bench_part"], 4.0)  # l - w = 12 - 8


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import value_reference as ref
        cls.inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
        cls.params = es.load_params()
        cls.sources, _ = es.load_sources(cls.inp, "ppr", 12)
        cls.chart_sigma = es.chart_sigma_from(cls.sources, 12)

    def test_pie_identity_and_zero_inversions_at_12_team_ppr(self):
        run = es.run_setting(self.sources, 12, self.params, self.chart_sigma, "A")
        self.assertAlmostEqual(sum(run["weights"].values()), 1.0)
        for src in self.sources:
            self.assertAlmostEqual(sum(run["adjusted"][src.key].values()), run["pie"], places=6, msg=src.key)
        self.assertEqual(es.inversions(run["adjusted"], self.sources), 0)
        for form in ("option",):
            r2 = es.run_setting(self.sources, 12, self.params, self.chart_sigma, "A", form)
            self.assertEqual(es.inversions(r2["adjusted"], self.sources), 0)

    def test_every_setting_keeps_order(self):
        for scoring in es.SCORINGS:
            for teams in es.TEAM_COUNTS:
                sources, _ = es.load_sources(self.inp, scoring, teams)
                cs = es.chart_sigma_from(sources, teams)
                for variant in ("A", "B"):
                    run = es.run_setting(sources, teams, self.params, cs, variant)
                    self.assertEqual(es.inversions(run["adjusted"], sources), 0, (scoring, teams, variant))

    def test_chart_sigma_is_measured_on_a_common_scale(self):
        for p in es.POSITIONS:
            self.assertTrue(0.05 < self.chart_sigma[p]["sigma_rel"] < 1.5, (p, self.chart_sigma[p]))
            self.assertGreater(self.chart_sigma[p]["shared_players"], 50)



class BenchShareReadout(unittest.TestCase):
    """ES-14: the bench share is an output of the reader's settings (es-value-001)."""

    def test_readout_by_position_and_settings(self):
        import json
        import value_reference as ref
        import derive_lineup_parameters as dl
        inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
        cfg = json.loads(dl.CONFIG.read_text(encoding="utf-8"))
        base = es.bench_share_readout(inp, "ppr", 12, cfg)
        self.assertEqual(set(base["bench_share"]), set(es.POSITIONS))
        self.assertTrue(0.05 < base["bench_share_overall"] < 0.13, base["bench_share_overall"])
        for p in es.POSITIONS:
            self.assertTrue(0.0 <= base["bench_share"][p] < 0.25, (p, base["bench_share"][p]))
        late = es.bench_share_readout(inp, "ppr", 12, cfg, content_week=16)
        self.assertLess(late["fill_in_share"], base["fill_in_share"])
        surer = es.bench_share_readout(inp, "ppr", 12, cfg, projection_confidence=0.5)
        self.assertNotAlmostEqual(surer["bench_share_overall"], base["bench_share_overall"], places=4)


if __name__ == "__main__":
    unittest.main()
