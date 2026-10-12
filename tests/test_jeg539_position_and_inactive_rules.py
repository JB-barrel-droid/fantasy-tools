"""JEG-539, Jeremy's decisions of 2026-10-12.

Q2 (Connor Heyward): when a projection or ranker source's position conflicts
with the player's, the position is ESPN's or Sleeper's (where the game is
played), as public.players holds it. No per-source exception: CBS rest of
season prints Heyward in its TE table, public.players says RB, so that row is a
position conflict like any other source's, and the CBS ROS saver resolves
through the one canonical resolver.

Q3 (Max Hurleman): inactive or irrelevant players never raise a review flag.
A source row for an inactive player at a position the table does not hold is
skipped without a review row, an identity-queue row, a workflow warning or a
pulse "unresolved" count. An ACTIVE player at the wrong position still does.

Each test fails on the code before this change (the reason was
position_conflict for both, and the CBS ROS saver took Heyward through the
legacy matcher).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import canonical_players  # noqa: E402
import fidelity_pulse as fp  # noqa: E402
import identity_queue  # noqa: E402
import save_cbsros_references as cbsros  # noqa: E402
import save_razzball_references as razzball  # noqa: E402

HURLEMAN = {"player_key": 2100, "full_name": "Max Hurleman", "position": "RB", "active": False}
HEYWARD = {"player_key": 914, "full_name": "Connor Heyward", "position": "RB", "active": True}
PLAYERS = [HURLEMAN, HEYWARD]


class ResolverReasons(unittest.TestCase):
    def setUp(self):
        self.reg = canonical_players.Registry(PLAYERS)

    def test_inactive_player_at_another_position_is_inactive_not_a_conflict(self):
        self.assertEqual((None, "inactive"),
                         canonical_players.resolve_with_reason("Max Hurleman", "WR", registry=self.reg))
        self.assertIn("inactive", canonical_players.SILENT_REASONS)

    def test_active_player_at_another_position_is_still_a_conflict(self):
        self.assertEqual((None, "position_conflict"),
                         canonical_players.resolve_with_reason("Connor Heyward", "TE", registry=self.reg))

    def test_the_players_own_position_still_resolves_even_when_inactive(self):
        self.assertEqual((2100, "ok"), canonical_players.resolve_with_reason("Max Hurleman", "RB", registry=self.reg))
        self.assertEqual((914, "ok"), canonical_players.resolve_with_reason("Connor Heyward", "RB", registry=self.reg))


class NothingIsFlagged(unittest.TestCase):
    def test_identity_queue_ignores_an_inactive_miss_even_with_the_identity_detail(self):
        review = [{"name": "Max Hurleman", "position": "WR", "reason": "inactive",
                   "detail": identity_queue.IDENTITY_DETAIL}]
        self.assertEqual([], identity_queue.identity_misses(review))
        # the same row for an active player is a miss
        review[0]["reason"] = "position_conflict"
        self.assertEqual(1, len(identity_queue.identity_misses(review)))

    def test_pulse_does_not_count_an_inactive_publisher_name_as_unresolved(self):
        ident = fp.Identity(canonical_players.Registry(PLAYERS))
        rows = [fp.PubRow("Max Hurleman", "WR", None, {"half|1": "3.0"}),
                fp.PubRow("Connor Heyward", "TE", None, {"half|1": "9.6"})]
        grains, unresolved = fp.publisher_grains(rows, ident)
        self.assertEqual({}, grains)
        self.assertEqual(["Connor Heyward"], [u["name"] for u in unresolved])

    def _razzball_review(self, name, pos):
        row = {"player_name": name, "player_norm": name.lower(), "pos": pos, "team": "X",
               "rz_std_ppg": 1.0, "rz_half_ppr_ppg": 1.0, "rz_ppr_ppg": 1.0}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps({"schema": "trade-value-razzball-snapshot-v1",
                                        "vintage_date": "2026-10-09", "rows": [row]}), encoding="utf-8")
            saved = razzball.fetch_players
            razzball.fetch_players = lambda: PLAYERS
            try:
                clean, review, _ = razzball.build_razzball_rows(path)
            finally:
                razzball.fetch_players = saved
        return clean, review

    def test_razzball_saver_skips_an_inactive_player_without_a_review_row(self):
        clean, review = self._razzball_review("Max Hurleman", "WR")
        self.assertEqual(([], []), (clean, review))

    def test_razzball_saver_still_reviews_an_active_player_at_the_wrong_position(self):
        clean, review = self._razzball_review("Connor Heyward", "TE")
        self.assertEqual([], clean)
        self.assertEqual(["position_conflict"], [r["reason"] for r in review])


class CbsRestOfSeasonUsesTheSameRule(unittest.TestCase):
    """No per-source exception: CBS ROS's TE-table Heyward is a position conflict like Razzball's."""

    def _build(self, name, pos):
        row = {"player_name": name, "player_norm": name.lower(), "pos": pos, "ros_half_ppr": 90.0,
               "ros_standard": 80.0, "ros_ppr": 100.0, "per_game_half_ppr": 9.0, "per_game_standard": 8.0,
               "per_game_ppr": 10.0, "gp": 10.0, "receptions": 3.0, "raw_stats": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps({"vintage_date": "2026-10-09", "rows": [row]}), encoding="utf-8")
            saved = cbsros.fetch_players
            cbsros.fetch_players = lambda: PLAYERS
            try:
                clean, review, _ = cbsros.build_cbsros_rows(path)
            finally:
                cbsros.fetch_players = saved
        return clean, review

    def test_heyward_in_the_te_table_is_a_position_conflict(self):
        clean, review = self._build("Connor Heyward", "TE")
        self.assertEqual([], clean)
        self.assertEqual(["position_conflict"], [r["reason"] for r in review])

    def test_heyward_at_his_espn_and_sleeper_position_is_stored_under_his_key(self):
        clean, review = self._build("Connor Heyward", "RB")
        self.assertEqual([914], [r["player_key"] for r in clean])
        self.assertEqual([], review)

    def test_an_inactive_player_at_another_position_leaves_no_review_row(self):
        clean, review = self._build("Max Hurleman", "WR")
        self.assertEqual(([], []), (clean, review))

    def test_the_saver_no_longer_builds_a_legacy_name_index(self):
        self.assertFalse(hasattr(cbsros, "build_name_index"))


if __name__ == "__main__":
    unittest.main()
