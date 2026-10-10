"""JEG-480 follow-ups found by the fidelity pulse after the ESPN / USA Today
fixes reached the live chart (pulse run 2026-10-09T18:00Z):

  1. USA Today: Josh Palmer (822) was stored (native 1) and in the chart
     roster, but match_source_snapshot re-resolves names through the identity
     table and Sleeper, which do not name him, so the chain dropped him.
     A Supabase row carries its saver's canonical player_key; a name miss now
     joins the roster on that key.
  2. ESPN: the CSV carried Riley Nowakowski and Jackson Meeks (snapshot
     match, position differs from public.players) while the saver, on the
     canonical resolver, did not store them: "chart players not stored".
     The puller now drops a snapshot match the canonical resolver rejects.
  3. The pulse compared the chart's 2-decimal natives with the stored value
     rounded half-up; on an exact tie (Tyler Warren 141.66 / 12 = 11.805)
     the chart printed 11.8. Both roundings of a tie are the stored number.

Hermetic: no network, no Supabase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import canonical_players  # noqa: E402
import fidelity_pulse as FP  # noqa: E402
import match_source_snapshot as M  # noqa: E402

_spec = importlib.util.spec_from_file_location("pull_espn_projections_followups",
                                               ROOT / "pipelines" / "pull_espn_projections.py")
puller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(puller)


def run_match(rows, roster):
    with TemporaryDirectory() as tmp:
        players = Path(tmp) / "players.json"
        snapshot = Path(tmp) / "snapshot.json"
        idmap = Path(tmp) / "idmap.json"
        players.write_text(json.dumps({"players": roster}), encoding="utf-8")
        idmap.write_text(json.dumps({"canonical": {}, "alias_to_canonical": {}}), encoding="utf-8")
        snapshot.write_text(json.dumps({
            "schema": M.INPUT_SCHEMA, "source": "usatoday", "fetched_at": "2026-10-06T00:00:00Z",
            "default_scoring": "ppr", "default_teams": 12, "rows": rows}), encoding="utf-8")
        return M.match_snapshot(snapshot, players, idmap, use_sleeper=False)


class MatchJoinsOnTheStoredKeyTest(unittest.TestCase):
    ROSTER = [{"player_key": 822, "name": "Josh Palmer", "team": "BUF", "pos": "WR"},
              {"player_key": 1347, "name": "Trey Palmer", "team": "TB", "pos": "WR"}]

    def test_a_name_miss_joins_the_roster_on_the_saved_player_key(self):
        out = run_match([{"player_name": "Josh Palmer", "pos": "WR", "native_value": 1.0, "value": 1.0,
                          "scoring": "ppr", "teams": 12, "source_player_id": 822}], self.ROSTER)
        self.assertEqual([(r["player_key"], r["identity_source"], r["native_value"]) for r in out["matched_rows"]],
                         [(822, "player_key", 1.0)])
        self.assertEqual(out["review_rows"], [])
        self.assertEqual(out["identity_layers"]["player_key"], 1)

    def test_without_a_roster_key_the_row_still_goes_to_review(self):
        out = run_match([{"player_name": "Josh Palmer", "pos": "WR", "value": 1.0, "source_player_id": 99999},
                         {"player_name": "Josh Palmer", "pos": "WR", "value": 1.0}], self.ROSTER)
        self.assertEqual(out["matched_rows"], [])
        self.assertEqual([r["reason"] for r in out["review_rows"]], ["unknown_identity", "unknown_identity"])


class _Snapshot:
    def __init__(self, entries):
        self.alias_to_canonical = {}
        self.chart_keys = set(entries)
        self.canonical = entries

    def heuristic(self, key):
        return None


class PullerAgreesWithTheSaverTest(unittest.TestCase):
    def setUp(self):
        self.reg = canonical_players.load_registry(rows=[
            {"player_key": 3963, "full_name": "Riley Nowakowski", "position": "TE", "active": True},
            {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
        ])
        self.snap = _Snapshot({"riley nowakowski": {"name": "Riley Nowakowski"},
                               "josh allen": {"name": "Josh Allen", "pos": "QB"}})

    def test_a_snapshot_match_the_canonical_resolver_rejects_is_dropped(self):
        problems = []
        self.assertIsNone(puller.resolve_identity(self.snap, "Riley Nowakowski", "RB", problems, self.reg))
        self.assertIn("position_conflict", problems[-1])

    def test_an_agreeing_snapshot_match_keeps_its_label(self):
        self.assertEqual(puller.resolve_identity(self.snap, "Josh Allen", "QB", [], self.reg),
                         ("josh allen", "Josh Allen"))

    def test_without_a_registry_the_snapshot_rule_is_unchanged(self):
        self.assertEqual(puller.resolve_identity(self.snap, "Riley Nowakowski", "RB", []),
                         ("riley nowakowski", "Riley Nowakowski"))


class RazzballCanonicalFallbackTest(unittest.TestCase):
    """2026-10-09 23:40 pulse: Razzball's "Scotty Miller" (0.1 / game) was not
    stored; the legacy matcher folds no nicknames, the canonical resolver
    gives public.players 399 "Scott Miller".

    JEG-539 (Jeremy 2026-10-10, "Use canonical resolver"): the saver now
    resolves only canonically. Rule changed by that decision: a legacy
    single-candidate hit at another position (Ben VanSumeren listed RB, LB in
    public.players) is a position conflict, not a match."""

    PLAYERS = [
        {"player_key": 399, "full_name": "Scott Miller", "position": "WR", "active": False},
        {"player_key": 1155, "full_name": "Ben VanSumeren", "position": "LB", "active": False},
        {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    ]

    def setUp(self):
        import save_razzball_references as rz
        self.rz = rz
        self.reg = rz.build_registry(self.PLAYERS)

    def test_a_nickname_resolves_canonically(self):
        self.assertEqual(self.rz.resolve_name("Scotty Miller", "WR", self.reg, "scotty miller"), (399, None))

    def test_a_position_the_table_does_not_hold_is_a_conflict(self):
        self.assertEqual(self.rz.resolve_name("Ben VanSumeren", "RB", self.reg), (None, "position_conflict"))

    def test_the_resolver_fails_closed_on_position(self):
        self.assertEqual(self.rz.resolve_name("Scotty Miller", "TE", self.reg), (None, "position_conflict"))

    def test_the_saver_passes_the_registry(self):
        rows = [{"player_name": "Scotty Miller", "player_norm": "scotty miller", "pos": "WR", "team": "PIT",
                 "rz_std_ppg": 0.1, "rz_half_ppr_ppg": 0.1, "rz_ppr_ppg": 0.1}]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            path.write_text(json.dumps({"schema": "trade-value-razzball-snapshot-v1",
                                        "vintage_date": "2026-10-09", "rows": rows}), encoding="utf-8")
            saved = self.rz.fetch_players
            self.rz.fetch_players = lambda: self.PLAYERS
            try:
                clean, review, _ = self.rz.build_razzball_rows(path)
            finally:
                self.rz.fetch_players = saved
        self.assertEqual([r["player_key"] for r in clean], [399])
        self.assertEqual(review, [])


class PulseTieTest(unittest.TestCase):
    def _cmp(self, stored, chart):
        left = FP.projection_grains([{"player_key": 1860}], lambda r: {"full|1": stored}, 2)
        right = {"full|1": {1860: {"value": chart, "name": "Tyler Warren"}}}
        return FP.compare(left, right, printed=True)

    def test_either_rounding_of_an_exact_tie_matches(self):
        stored = (109.86 + 0.5 * 63.6) / 12  # 11.805 printed, 11.80499... in binary
        self.assertEqual(self._cmp(stored, 11.8)["matched"], 1)
        self.assertEqual(self._cmp(stored, 11.81)["matched"], 1)

    def test_off_a_tie_the_rule_stays_exact(self):
        self.assertEqual(self._cmp(11.806, 11.8)["matched"], 0)
        self.assertEqual(self._cmp(11.805, 11.79)["matched"], 0)
        self.assertEqual(self._cmp(11.804, 11.81)["matched"], 0)


if __name__ == "__main__":
    unittest.main()
