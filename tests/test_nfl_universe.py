"""JEG-502 (Jeremy GL-20, 2026-10-09): every active NFL QB/RB/WR/TE is in
players.json, priced or not.

  "All players in the active NFL universe should be available in the search;
   even if they are not rostered, on practice squads, etc. The user knowing
   they are a 0 is better than the user questioning why they aren't in the
   tool."

Before this change the bake's rows were ESPN's list plus whatever a chart or
projection priced (676 rows on 2026-10-09); a practice-squad player nobody
prices had no row, so search said "not found". These tests pin:
  - the definition of "active" (pipelines/lib/nfl_universe.py) and the roster
    status of each kind of player;
  - the bake gives an unpriced practice-squad player a row with his status, a
    reason and ESPN-absent zero legs, keyed on the players table when he is on
    it and on a synthetic Sleeper key when he is not;
  - meta.universe.nfl_active carries the count by roster status, and the
    fidelity pulse reports it;
  - the committed players.json (what the page searches) has them.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT))

import bake_players  # noqa: E402
import fidelity_pulse as fp  # noqa: E402
import nfl_universe  # noqa: E402
from tests import test_bake_today_unboundlocal as bake_harness  # noqa: E402

PULLED = "2026-10-08T09:17:11+00:00"


def _entry(name, pos, team, status="Active", active=True, **kw):
    e = {"name": name, "pos": pos, "team": team, "active": active, "status": status}
    e.update(kw)
    return e


BASE = {
    "schema": "sleeper-identity-base-v2",
    "meta": {"pulled_at": PULLED},
    "by_name": {},
    "by_sleeper_id": {
        # on the players table (key 777) and priced by ESPN in the harness
        "100": _entry("Test Player", "QB", "BUF", depth_chart_position="QB", depth_chart_order=1),
        # practice squad, inferred: on a team, Active, no depth-chart slot
        "200": _entry("Squad Guy", "WR", "KC"),
        # practice squad, Sleeper's own status
        "300": _entry("Listed Squad", "TE", "KC", status="Practice Squad", depth_chart_position="TE",
                      depth_chart_order=4),
        # injured reserve (Sleeper keeps the team, status Inactive)
        "400": _entry("Ir Guy", "RB", "MIA", status="Inactive", injury_status="IR", depth_chart_order=3),
        # free agent with news this season
        "500": _entry("Recent Fa", "WR", None, last_news="2026-09-01"),
        # free agent with no news for over a year: not active
        "600": _entry("Old Fa", "WR", None, last_news="2024-01-01"),
        # retired
        "700": _entry("Retired Guy", "WR", None, status="Inactive", active=False),
        # kicker: not a universe position
        "800": _entry("Some Kicker", "K", "BUF", depth_chart_order=1),
        # on the players table (key 888) under Sleeper's LAR code
        "900": _entry("Other Player", "RB", "LAR", depth_chart_position="RB", depth_chart_order=1),
    },
}


class DefinitionTest(unittest.TestCase):
    def test_who_is_in_and_their_status(self):
        u = nfl_universe.active_universe(BASE)
        self.assertEqual({"100", "200", "300", "400", "500", "900"}, set(u))
        self.assertEqual("active_roster", u["100"]["roster_status"])
        self.assertEqual(("practice_squad", True), (u["200"]["roster_status"], u["200"]["roster_status_inferred"]))
        self.assertEqual(("practice_squad", False), (u["300"]["roster_status"], u["300"]["roster_status_inferred"]))
        self.assertEqual("injured_reserve", u["400"]["roster_status"])
        self.assertEqual(("free_agent", ""), (u["500"]["roster_status"], u["500"]["team"]))
        self.assertEqual("LA", u["900"]["team"])  # the board's team code

    def test_free_agent_window_is_measured_from_the_pull(self):
        base = json.loads(json.dumps(BASE))
        base["by_sleeper_id"]["600"]["last_news"] = "2025-10-09"  # 364 days before the pull
        self.assertIn("600", nfl_universe.active_universe(base))
        base["by_sleeper_id"]["600"]["last_news"] = "2025-10-07"  # 366 days
        self.assertNotIn("600", nfl_universe.active_universe(base))

    def test_shared_canonical_key_goes_to_the_rostered_player(self):
        u = {"1": {"name": "Same Name", "pos": "WR", "team": "KC"},
             "2": {"name": "Same Name", "pos": "WR", "team": ""}}
        keys = nfl_universe.assign_keys(u, lambda name, pos: 42)
        self.assertEqual(42, keys["1"])
        self.assertEqual(nfl_universe.SLEEPER_KEY_BASE + 2, keys["2"])
        self.assertEqual(len(set(keys.values())), 2)


class BakeCarriesTheUniverseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmpdir = Path(self.tmp.name)
        self._saved = (bake_players.SNAPSHOT_DIR, bake_players.FIXTURE_DIR, bake_players.CBSROS_SNAPSHOT_DIR)
        bake_players.SNAPSHOT_DIR = tmpdir / "snapshots"
        bake_players.SNAPSHOT_DIR.mkdir()
        bake_players.FIXTURE_DIR = tmpdir / "current"
        bake_players.FIXTURE_DIR.mkdir()
        bake_players.CBSROS_SNAPSHOT_DIR = tmpdir / "cbsros"
        self.args = bake_harness._args(self.tmp.name)
        base_path = tmpdir / "base.json"
        base_path.write_text(json.dumps(BASE), encoding="utf-8")
        self.args.identity_base = str(base_path)
        self.args.raw_sources_dir = str(tmpdir / "raw")
        self.args.comparison_fixture = None
        with patch.object(bake_players, "load_registry", return_value=bake_harness._test_registry()), \
             patch.object(bake_players, "query_all", side_effect=bake_harness._fake_query_all), \
             patch.object(bake_players, "load_preseason_ecr_ranks", return_value=({}, {"resolved": 0, "unmatched": 0})), \
             patch.object(bake_players, "annotate_rows", lambda players, ranks: None), \
             patch.object(bake_players, "build_dataset_status", side_effect=bake_harness._stub_dataset_status):
            bake_players.bake(self.args)
        self.payload = json.loads((bake_players.FIXTURE_DIR / "players.json").read_text(encoding="utf-8"))
        self.rows = {p["player_key"]: p for p in self.payload["players"]}

    def tearDown(self):
        bake_players.SNAPSHOT_DIR, bake_players.FIXTURE_DIR, bake_players.CBSROS_SNAPSHOT_DIR = self._saved
        self.tmp.cleanup()

    def test_unpriced_practice_squad_player_has_a_row_status_and_reason(self):
        key = nfl_universe.SLEEPER_KEY_BASE + 300
        self.assertIn(key, self.rows, "practice-squad player missing from players.json")
        row = self.rows[key]
        self.assertEqual("Listed Squad", row["name"])
        self.assertEqual("TE", row["pos"])
        self.assertEqual("KC", row["team"])
        self.assertEqual("practice_squad", row["roster_status"])
        self.assertEqual("Practice squad", row["roster_status_label"])
        self.assertEqual("Practice squad (KC). No chart or projection prices this player.", row["unpriced_reason"])
        self.assertTrue(row["universe_only"])
        self.assertEqual("sleeper", row["identity"])
        self.assertEqual("300", row["sleeper_id"])
        # ESPN has no row for him: absent (shown as missing with a reason), zero legs, no projection.
        self.assertEqual("absent", row["espn_status"])
        self.assertEqual({"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0}, row["espn_ros"])
        for field in ("espn_ppg", "blend_ppg", "rz_ppg", "cbsros_ppg"):
            self.assertNotIn(field, row)
        self.assertTrue(self.rows[nfl_universe.SLEEPER_KEY_BASE + 200]["roster_status_inferred"])

    def test_every_universe_player_once_and_nobody_else(self):
        sb = nfl_universe.SLEEPER_KEY_BASE
        self.assertEqual({777, 888, sb + 200, sb + 300, sb + 400, sb + 500}, set(self.rows))
        self.assertEqual("injured_reserve", self.rows[sb + 400]["roster_status"])
        self.assertEqual("free_agent", self.rows[sb + 500]["roster_status"])
        self.assertEqual("", self.rows[sb + 500]["team"])

    def test_priced_players_keep_their_key_and_gain_roster_fields(self):
        row = self.rows[777]
        self.assertEqual("Test Player", row["name"])
        self.assertEqual("active_roster", row["roster_status"])
        self.assertEqual(1, row["depth_chart_order"])
        self.assertNotIn("universe_only", row)
        self.assertNotIn("unpriced_reason", row)
        self.assertGreater(row["espn_ros"]["ppr"], 0)

    def test_universe_count_by_status_in_meta(self):
        nfl = self.payload["meta"]["universe"]["nfl_active"]
        self.assertEqual(6, nfl["n_nfl_active"])
        self.assertEqual({"active_roster": 2, "practice_squad": 2, "injured_reserve": 1, "pup": 0,
                          "reserve": 0, "free_agent": 1}, nfl["by_roster_status"])
        self.assertEqual(4, nfl["n_universe_only"])
        self.assertEqual(4, nfl["n_sleeper_identity"])
        self.assertEqual(PULLED, nfl["identity_base_pulled_at"])
        self.assertTrue(nfl["definition"])

    def test_fidelity_pulse_reports_the_universe(self):
        report = fp.universe_report(bake_players.FIXTURE_DIR / "players.json")
        self.assertEqual("green", report["status"])
        self.assertEqual(6, report["n_rows"])
        self.assertEqual(6, report["n_nfl_active"])
        self.assertEqual(2, report["by_roster_status"]["practice_squad"])
        self.assertIn("6 active NFL players", report["summary"])


class PulseWithoutCountTest(unittest.TestCase):
    def test_a_bake_without_the_count_is_amber_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "players.json"
            path.write_text(json.dumps({"meta": {"universe": {}}, "players": [{}, {}]}), encoding="utf-8")
            report = fp.universe_report(path)
        self.assertEqual("amber", report["status"])
        self.assertEqual(2, report["n_rows"])


class CommittedPlayersJsonTest(unittest.TestCase):
    """What the page searches: the committed bake."""

    def setUp(self):
        self.payload = json.loads((ROOT / "data" / "fixtures" / "current" / "players.json").read_text(encoding="utf-8"))

    def test_practice_squad_players_are_searchable_with_status_and_reason(self):
        squad = [p for p in self.payload["players"] if p.get("roster_status") == "practice_squad"]
        self.assertGreater(len(squad), 100, "practice-squad players missing from players.json")
        unpriced = [p for p in squad if p.get("universe_only")]
        self.assertTrue(unpriced)
        for p in unpriced:
            self.assertTrue(p.get("unpriced_reason", "").startswith("Practice squad"), p)
            self.assertEqual("Practice squad", p["roster_status_label"])

    def test_universe_count_is_reported(self):
        nfl = self.payload["meta"]["universe"]["nfl_active"]
        self.assertGreater(nfl["n_nfl_active"], 1000)
        self.assertEqual(nfl["n_nfl_active"], sum(nfl["by_roster_status"].values()))
        keys = [p["player_key"] for p in self.payload["players"]]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
