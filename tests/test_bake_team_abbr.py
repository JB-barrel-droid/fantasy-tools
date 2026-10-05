"""Regression tests for team-abbreviation handling in the players bake.

2026-10-05: the JEG-ECR-EXIT bake (pipelines/bake_players.py) fail-closed on
its source-accounting audit — 13 players had complete Razzball coverage but
no rz_filled_ros. Root cause: two team-resolution gaps in the games-remaining
lookup.

1. ESPN's CSV uses WSH for Washington; the teams table (games-remaining
   source) uses WAS. The bake's variant map only had LAR->LA / JAC->JAX, so
   every WSH player got gr=None -> no per-game fields -> audit violation.
   canonical_players already documents ESPN's LAR/WSH vs canonical LA/WAS.
2. One eligible CSV row (Xavier Smith) had a blank team. The module
   docstring promised a canonical-registry fallback for silent teams, but
   the loop took espn_row["team"] verbatim -> gr=None -> same audit
   violation.

Discrimination: reverting _TEAM_ABBR_FIX to the pre-fix map (dropping
WSH->WAS) turns test_wsh_normalizes_to_was red; bypassing
_resolve_team_abbr in the bake loop (team = espn_row["team"] verbatim)
turns test_empty_team_falls_back_to_registry red. Verified by stashing
the fix.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import bake_players
from bake_players import _resolve_team_abbr, _TEAM_ABBR_FIX


def _reg():
    """Synthetic registry: key 777 on team_id 10, key 888 with no team."""
    return bake_players.load_registry(rows=[
        {"player_key": 777, "id": "u1", "full_name": "Test Player",
         "position": "QB", "active": True, "team_id": 10},
        {"player_key": 888, "id": "u2", "full_name": "Other Player",
         "position": "RB", "active": True, "team_id": None},
    ])


_TEAM_ABBR = {10: "LA", 20: "WAS"}


class TestTeamAbbrFix(unittest.TestCase):
    def test_wsh_normalizes_to_was(self):
        # The 2026-10-05 audit failure: ESPN CSV says WSH, games table says
        # WAS. Without this mapping the player gets no games_remaining and
        # the rz_filled_ros audit fail-closes the bake.
        self.assertEqual("WAS", _TEAM_ABBR_FIX.get("WSH"))
        self.assertEqual("WAS", _resolve_team_abbr("WSH", 777, _reg(),
                                                  _TEAM_ABBR))

    def test_known_variants_preserved(self):
        self.assertEqual("LA", _resolve_team_abbr("LAR", 777, _reg(),
                                                 _TEAM_ABBR))
        self.assertEqual("JAX", _resolve_team_abbr("JAC", 777, _reg(),
                                                  _TEAM_ABBR))
        self.assertEqual("BUF", _resolve_team_abbr("BUF", 777, _reg(),
                                                  _TEAM_ABBR))

    def test_empty_team_falls_back_to_registry(self):
        # Xavier Smith (2026-10-05): blank CSV team, registry team_id 10
        # -> LA. The old verbatim path returned "" -> no per-game fields.
        self.assertEqual("LA", _resolve_team_abbr("", 777, _reg(),
                                                 _TEAM_ABBR))
        self.assertEqual("LA", _resolve_team_abbr(None, 777, _reg(),
                                                  _TEAM_ABBR))
        self.assertEqual("LA", _resolve_team_abbr("   ", 777, _reg(),
                                                  _TEAM_ABBR))

    def test_empty_team_unknown_key_stays_empty(self):
        # Fail-closed: no CSV team and no registry entry -> "" (unknown),
        # never a guessed team. The caller skips per-game fields.
        self.assertEqual("", _resolve_team_abbr("", 999, _reg(),
                                                _TEAM_ABBR))
        self.assertEqual("", _resolve_team_abbr("", 888, _reg(),
                                                _TEAM_ABBR))

    def test_registry_abbr_stale_variants_normalized(self):
        # teams-table stale rows (STL/SD/OAK) map to current abbreviations
        # before the games-remaining lookup.
        reg = _reg()
        self.assertEqual("LA", _resolve_team_abbr("", 777, reg,
                                                  {10: "STL"}))
        self.assertEqual("LV", _resolve_team_abbr("", 777, reg,
                                                  {10: "OAK"}))

    def test_csv_team_wins_over_registry(self):
        # A present CSV team is authoritative (normalized); the registry
        # fallback only fires when the CSV is silent.
        self.assertEqual("WAS", _resolve_team_abbr("wsh", 777, _reg(),
                                                  _TEAM_ABBR))


if __name__ == "__main__":
    unittest.main()
