"""JEG-480 fidelity pulse, ESPN: stored rows must equal what ESPN projects.

Found by the pulse on 2026-10-09 (ops-alert #434):

  * GAP-ESPN-ZEROED-STORED: 7 players ESPN projects were stored as 0
    (Alec Ingold 12.82 half PPR rest of season), while the chart showed
    ESPN's number. The puller's `eligible` rule was per position (an RB
    needed rushing yards), so fullbacks projected only as receivers and a WR
    projected only on rushes were flagged ineligible, and the saver forced
    every ineligible row to 0.
  * 16 players ESPN projects (Joshua Palmer, Tyler Goodson, Austin Ekeler,
    Chris Moore, ...) never reached the CSV: the puller resolved names only
    through the static identity snapshot and dropped the rest silently.

Hermetic: no network, no Supabase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


saver = _load("save_espn_cbs_references_jeg480", ROOT / "pipelines" / "save_espn_cbs_references.py")
puller = _load("pull_espn_projections_jeg480", ROOT / "pipelines" / "pull_espn_projections.py")
import canonical_players  # noqa: E402
import identity_queue  # noqa: E402

PLAYERS = [
    {"player_key": 3446, "full_name": "Alec Ingold", "position": "RB", "active": True},
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 822, "full_name": "Josh Palmer", "position": "WR", "active": False},
    {"player_key": 9001, "full_name": "Brady Russell", "position": "TE", "active": True},
]

HEADER = ("player,player_norm,pos,team,has_espn_projection,eligible,"
          "r_pass_yds,r_pass_tds,r_rush_yds,r_rush_tds,r_receptions,r_rec_yds,r_rec_tds,"
          "ros_half_ppr,weeks_covered,espn_snapshot_date")


class _NoAudit:
    def __init__(self, *a, **k):
        self.run_id = "t"

    def start(self):
        return self.run_id

    def complete(self, row_count):
        pass

    def fail(self, msg):
        pass

    def audit_rows(self, rows):
        return rows


class StoredEqualsEspnTest(unittest.TestCase):
    def setUp(self):
        self.saved = (saver.fetch_players, saver.upsert_rows, saver.count_rows, saver.WriterAudit)
        self.writes = []
        saver.fetch_players = lambda: PLAYERS
        saver.upsert_rows = lambda t, rows, c: self.writes.append(rows)
        saver.count_rows = lambda t, p: sum(len(r) for r in self.writes)
        saver.WriterAudit = _NoAudit
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        saver.fetch_players, saver.upsert_rows, saver.count_rows, saver.WriterAudit = self.saved

    def _save(self, rows, meta=None):
        csv_path = self.tmp / "espn.csv"
        csv_path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        meta_path = self.tmp / "meta.json"
        meta_path.write_text(json.dumps({"vintage": "2026-10-08", **(meta or {})}), encoding="utf-8")
        return saver.save_source("espn", dry_run=False, espn_csv=csv_path, espn_meta=meta_path,
                                 cbs_json=self.tmp / "none.json")

    def test_an_ineligible_row_keeps_espns_projection(self):
        # Alec Ingold as the 2026-10-08 CSV carried him: eligible=False
        # (no rushing yards) but ESPN projects 12.82 half PPR.
        result = self._save([
            "Alec Ingold,alec ingold,RB,MIA,True,False,0.0,0.0,0.0,0.0,8.6,66.2,0.3,12.82,5-18,2026-10-08",
        ])
        self.assertEqual(result["written"], 1)
        row = self.writes[0][0]
        self.assertEqual(row["player_key"], 3446)
        self.assertEqual(row["ros_half_ppr"], 12.82)
        self.assertEqual(row["r_receptions"], 8.6)
        self.assertEqual(row["r_rec_yds"], 66.2)

    def test_a_true_zero_stays_zero(self):
        self._save([
            "Alec Ingold,alec ingold,RB,MIA,True,False,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.00,5-18,2026-10-08",
        ])
        self.assertEqual(self.writes[0][0]["ros_half_ppr"], 0.0)

    def test_names_resolve_through_the_canonical_resolver(self):
        # "Joshua Palmer" (ESPN) is players row "Josh Palmer": the canonical
        # rule folds the nickname; the legacy matcher did not.
        self._save([
            "Joshua Palmer,joshua palmer,WR,BUF,True,True,0,0,0,0,30.1,350.0,1.0,25.69,5-18,2026-10-08",
        ])
        self.assertEqual(self.writes[0][0]["player_key"], 822)

    def test_puller_unresolved_names_are_identity_misses(self):
        result = self._save(
            ["Josh Allen,josh allen,QB,BUF,True,True,3000,20,400,4,0,0,0,250.0,5-18,2026-10-08"],
            meta={"identity_unresolved": [
                {"player": "Brady Russell", "pos": "RB", "team": "SEA", "ros_half_ppr": 7.97}]},
        )
        misses = identity_queue.identity_misses(result["review"])
        self.assertEqual([(m["name"], m["pos"]) for m in misses], [("Brady Russell", "RB")])
        self.assertEqual(saver.warn_identity_misses("espn", result["review"]), 1)


class PullerEligibilityTest(unittest.TestCase):
    def test_receiving_only_fullback_is_eligible(self):
        ros = {"r_pass_yds": 0.0, "r_pass_tds": 0.0, "r_rush_yds": 0.0, "r_rush_tds": 0.0,
               "r_receptions": 8.0, "r_rec_yds": 61.6, "r_rec_tds": 0.3}
        self.assertTrue(puller.espn_eligible(ros))

    def test_rushing_only_receiver_is_eligible(self):
        ros = {"r_pass_yds": 0.0, "r_pass_tds": 0.0, "r_rush_yds": 15.7, "r_rush_tds": 0.1,
               "r_receptions": 0.0, "r_rec_yds": 0.0, "r_rec_tds": 0.0}
        self.assertTrue(puller.espn_eligible(ros))

    def test_nothing_projected_is_ineligible(self):
        self.assertFalse(puller.espn_eligible({"r_rush_yds": 0.0, "r_receptions": 0.0}))


class _EmptySnapshot:
    alias_to_canonical: dict = {}
    chart_keys: set = set()
    canonical: dict = {}

    def heuristic(self, key):
        return None


class PullerIdentityTest(unittest.TestCase):
    def setUp(self):
        self.reg = canonical_players.load_registry(rows=PLAYERS)

    def test_snapshot_miss_resolves_through_canonical_players(self):
        problems = []
        got = puller.resolve_identity(_EmptySnapshot(), "Joshua Palmer", "WR", problems, self.reg)
        self.assertEqual(got, ("josh palmer", "Josh Palmer"))
        self.assertTrue(any(p.startswith("canonical-identity") for p in problems))

    def test_position_conflict_stays_unresolved(self):
        problems = []
        got = puller.resolve_identity(_EmptySnapshot(), "Brady Russell", "RB", problems, self.reg)
        self.assertIsNone(got)
        self.assertIn("position_conflict", problems[-1])

    def test_without_a_registry_the_snapshot_rule_is_unchanged(self):
        problems = []
        self.assertIsNone(puller.resolve_identity(_EmptySnapshot(), "Joshua Palmer", "WR", problems))

    def test_unresolved_projection_sums_rest_of_season_weekly_blocks(self):
        pl = {"stats": [
            {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 5,
             "stats": {"53": 2.0, "42": 20.0}},  # played week: excluded
            {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 6,
             "stats": {"53": 2.0, "42": 20.0}},  # 1 + 2 = 3.0
            {"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 6,
             "stats": {"53": 9.0}},  # duplicate week: first wins
            {"seasonId": 2025, "statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 7,
             "stats": {"53": 9.0}},  # other season
        ]}
        self.assertEqual(puller.unresolved_ros_half_ppr(pl, list(range(6, 19))), 3.0)


if __name__ == "__main__":
    unittest.main()
