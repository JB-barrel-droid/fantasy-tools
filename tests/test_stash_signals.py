"""JEG-526 / JEG-529: stash signals outside the pie (pipelines/stash_signals.py).

Failing-first cases: a pure handcuff (own P(start) of 0, value 0 in the pie)
gets a nonzero stash signal; the pie and DDF Value are untouched by building
the signals; the drop bar compares like with like.
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

import stash_signals as ss  # noqa: E402
import value_reference as ref  # noqa: E402

CFG = ss.load_jump_config()


def rb(key, name, team, ppg, order=None, status="active_roster"):
    return {"player_key": key, "name": name, "pos": "RB", "team": team, "depth_chart_order": order,
            "roster_status": status, "espn_ppg": {"ppr": ppg}}


def ppg_of(p):
    return p["espn_ppg"]["ppr"]


class Pieces(unittest.TestCase):
    def test_contingent_is_the_product(self):
        # ES-13.1 worked example shape: (1-b) m_lead (1-m_i) (promoted - w) P
        got = ss.contingent_points(0.072, 0.153, 0.153, 13.4, 4.9, 0.78)
        self.assertAlmostEqual(got, 0.928 * 0.153 * 0.847 * 8.5 * 0.78, places=9)

    def test_no_surplus_above_the_waiver_line_is_zero(self):
        self.assertEqual(ss.contingent_points(0.07, 0.15, 0.15, 5.0, 6.0, 0.9), 0.0)

    def test_promoted_level_is_a_multiple_of_the_line_by_tier(self):
        top = ss.promoted_level(10.0, True, CFG)
        other = ss.promoted_level(10.0, False, CFG)
        self.assertGreater(top, other)
        self.assertAlmostEqual(top, 10.0 * CFG["promoted_to_starter_line"]["top12"])

    def test_p_start_rises_with_the_promoted_level(self):
        lo = ss.p_projected_to_start(9.0, 10.0, 0.28, 0.84)
        hi = ss.p_projected_to_start(14.0, 10.0, 0.28, 0.84)
        self.assertLess(lo, hi)
        self.assertTrue(0.0 < lo < hi < 1.0)


class TeamBacks(unittest.TestCase):
    def test_depth_chart_orders_when_projections_agree(self):
        rows = [rb(1, "Lead", "DET", 20, 1), rb(2, "Backup", "DET", 4, 2), rb(3, "Third", "DET", 3, 3)]
        t = ss.team_backs(rows, ppg_of)["DET"]
        self.assertEqual((t["lead"]["name"], t["backup"]["name"], t["basis"]), ("Lead", "Backup", "depth_chart"))

    def test_stale_chart_defers_to_projections(self):
        rows = [rb(1, "ChartLead", "PHI", 8, 1), rb(2, "RealLead", "PHI", 18, 2)]
        t = ss.team_backs(rows, ppg_of)["PHI"]
        self.assertEqual((t["lead"]["name"], t["basis"]), ("RealLead", "projection_rank"))

    def test_players_off_a_roster_are_not_leads_or_backups(self):
        rows = [rb(1, "Hurt", "BAL", 18, 1, "injured_reserve"), rb(2, "A", "BAL", 12, 2), rb(3, "B", "BAL", 5, 3)]
        t = ss.team_backs(rows, ppg_of)["BAL"]
        self.assertEqual((t["lead"]["name"], t["backup"]["name"]), ("A", "B"))

    def test_a_one_back_team_has_no_contingent(self):
        self.assertNotIn("KC", ss.team_backs([rb(1, "Solo", "KC", 15, 1)], ppg_of))


class LiveBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
        cls.players = json.loads(ref.PLAYERS.read_text(encoding="utf-8"))["players"]

    def test_a_pure_handcuff_has_a_nonzero_stash_signal(self):
        doc = ss.build("ppr", 12, CFG, self.players, inp=self.inp)
        pure = [r for r in doc["contingent"].values() if r["own_p_start"] < 0.01]
        self.assertTrue(pure, "expected handcuffs with no signal of their own")
        for r in pure:
            self.assertGreater(r["contingent_points"], 0.0)
            self.assertGreater(r["stash_signal"], r["own_p_start"])

    def test_building_the_signals_leaves_the_pie_alone(self):
        before = ref.Setting(self.inp, "ppr", 12, hist=None).result()
        snap = json.dumps({str(k): v["ddf"] for k, v in before["rows"].items()}, sort_keys=True, default=str)
        ss.build("ppr", 12, CFG, self.players, inp=self.inp)
        after = ref.Setting(self.inp, "ppr", 12, hist=None).result()
        self.assertEqual(snap, json.dumps({str(k): v["ddf"] for k, v in after["rows"].items()},
                                          sort_keys=True, default=str))

    def test_drop_candidate_means_hold_below_the_best_option(self):
        doc = ss.build("ppr", 12, CFG, self.players, inp=self.inp)
        for b in doc["waiver_bar"].values():
            for h in b["bench"].values():
                self.assertEqual(h["drop_candidate"], h["hold_with_contingent"] < b["best_option"])
                self.assertTrue(math.isfinite(h["hold"]))


if __name__ == "__main__":
    unittest.main()
