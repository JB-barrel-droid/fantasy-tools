"""Regression tests for the methodology payload behind 'How we make the charts comparable'.

Guards the 2026-09-30 rework:
  - Payload is baked per (scoring x teams) combo, not pinned to Full PPR / 12 teams.
  - Every combo carries position shares derived from the same fixture the curves render.
  - Sources without a combo (e.g. USA Today only ships 12-team) are omitted, never fabricated.
  - bench_share / roster describe the actual two-tier split so the copy can't drift.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from sync_dashboard_artifacts import (  # noqa: E402
    METHODOLOGY_SCORINGS,
    METHODOLOGY_TEAMS,
    build_methodology_payload,
    read_json,
)

FIXTURES = ROOT / "data" / "fixtures" / "current"


def _payload() -> dict:
    players = read_json(FIXTURES / "players.json")
    return build_methodology_payload(FIXTURES, players)


class TestMethodologyPayload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = _payload()

    def test_has_all_scoring_x_teams_combos(self):
        expected = {f"{s}_{t}" for s in METHODOLOGY_SCORINGS for t in METHODOLOGY_TEAMS}
        self.assertEqual(set(self.payload["combos"].keys()), expected)
        self.assertEqual(self.payload["default_combo"], "full_12")

    def test_full_12_combo_has_all_five_sources(self):
        combo = self.payload["combos"]["full_12"]
        self.assertEqual(combo["scoring_label"], "Full PPR")
        self.assertEqual(combo["teams"], 12)
        self.assertEqual(
            set(combo["position_shares"].keys()),
            {"usatoday", "fantasycalc", "fantasypros", "cbs", "espn"},
        )
        self.assertEqual(
            set(combo["adjustments"].keys()),
            {"usatoday", "fantasycalc", "fantasypros", "cbs"},
        )

    def test_partial_sources_omitted_not_fabricated(self):
        # USA Today / FantasyPros / CBS only ship 12-team combos in the fixture.
        combo = self.payload["combos"]["half_10"]
        self.assertEqual(set(combo["position_shares"].keys()), {"fantasycalc", "espn"})
        self.assertEqual(set(combo["adjustments"].keys()), {"fantasycalc"})

    def test_position_shares_sum_to_100(self):
        for key, combo in self.payload["combos"].items():
            for src, d in combo["position_shares"].items():
                total = sum(d["shares"].values())
                self.assertTrue(
                    99 <= total <= 101, f"{key}/{src} shares sum to {total}"
                )

    def test_movers_reference_real_players(self):
        for key, combo in self.payload["combos"].items():
            for src, d in combo["adjustments"].items():
                for m in d["movers"]:
                    self.assertTrue(m["name"], f"{key}/{src}: unnamed mover")
                    self.assertIn(m["pos"], {"QB", "RB", "WR", "TE"})
                    self.assertNotEqual(
                        m["before"], m["after"], f"{key}/{src}: zero-delta mover {m}"
                    )

    def test_two_tier_parameters_present(self):
        self.assertEqual(self.payload["bench_share"], 0.15)
        self.assertEqual(
            self.payload["roster"],
            {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6},
        )

    def test_no_legacy_single_combo_keys(self):
        for legacy in ("scoring", "teams", "position_shares", "adjustments"):
            self.assertNotIn(legacy, self.payload)


if __name__ == "__main__":
    unittest.main()
