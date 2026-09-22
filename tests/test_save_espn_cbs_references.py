#!/usr/bin/env python3
"""Tests for pipelines/save_espn_cbs_references.py.

Each guard is negative-tested against its named defect. Supabase access is
injected via module-level callables, so these run offline with recorded
fixtures. The CBS QB scoring decision (one 1QB-4 column, no per-scoring
split, but a NOT NULL CHECK on scoring) is pinned here.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"

spec = importlib.util.spec_from_file_location(
    "save_espn_cbs_references", PIPELINES / "save_espn_cbs_references.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB"},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB"},
    {"player_key": 9991, "full_name": "Alex Smith", "position": "QB"},
    {"player_key": 9992, "full_name": "Alex Smith", "position": "TE"},  # position-disambiguable twin
    {"player_key": 9993, "full_name": "Jordan Davis", "position": "QB"},
    {"player_key": 9994, "full_name": "Jordan Davis", "position": "QB"},  # genuinely ambiguous twin
    {"player_key": 9995, "full_name": "Brock Purdy", "position": "QB"},
    # Verified alias targets (players.full_name 2026-09-22): the ESPN CSV
    # spells these "Cameron Ward" / "Cameron Skattebo".
    {"player_key": 697, "full_name": "Cam Ward", "position": "QB"},
    {"player_key": 3664, "full_name": "Cam Skattebo", "position": "RB"},
]


def espn_csv_text(rows):
    header = (
        "player,player_norm,pos,team,has_espn_projection,eligible,"
        "r_pass_yds,r_pass_tds,r_rush_yds,r_rush_tds,r_receptions,r_rec_yds,r_rec_tds,"
        "ros_half_ppr,weeks_covered,espn_snapshot_date"
    )
    return header + "\n" + "\n".join(rows) + "\n"


def cbs_json(tables):
    return {
        "fetched_at": "2026-09-21T14:08:49Z",
        "url": "https://example.com/dave-richards-week-2-trade-chart",
        "tables": tables,
    }


class SaveEspnCbsReferencesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").TemporaryDirectory().name)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self._fetch = mod.fetch_players
        self._upsert = mod.upsert_rows
        self._count = mod.count_rows
        self.writes = []
        mod.fetch_players = lambda: PLAYERS
        mod.upsert_rows = lambda table, rows, conflict: self.writes.append((table, rows, conflict))
        mod.count_rows = lambda table, params: sum(len(rows) for t, rows, _ in self.writes if t == table)

    def tearDown(self):
        mod.fetch_players = self._fetch
        mod.upsert_rows = self._upsert
        mod.count_rows = self._count

    def write_inputs(self, csv_rows=None, tables=None, meta_vintage="2026-09-21"):
        csv_path = self.tmp / "espn.csv"
        csv_path.write_text(espn_csv_text(csv_rows or []))
        meta_path = self.tmp / "meta.json"
        meta_path.write_text(json.dumps({"vintage": meta_vintage}))
        json_path = self.tmp / "cbs.json"
        json_path.write_text(json.dumps(cbs_json(tables or [])))
        return csv_path, meta_path, json_path

    def save(self, source, **kwargs):
        csv_path, meta_path, json_path = self.write_inputs(**kwargs)
        return mod.save_source(
            source, dry_run=False, espn_csv=csv_path, espn_meta=meta_path, cbs_json=json_path
        )

    # -- guard: unknown source -------------------------------------------------
    # defect: the save script writing a table it does not own
    def test_unknown_source_fails_closed(self):
        csv_path, meta_path, json_path = self.write_inputs()
        with self.assertRaises(SystemExit):
            mod.save_source("fantasycalc", dry_run=False, espn_csv=csv_path,
                            espn_meta=meta_path, cbs_json=json_path)
        self.assertEqual(self.writes, [])

    # -- guard: zero clean rows -------------------------------------------------
    # defect: an empty save masquerading as a reference load
    def test_espn_zero_clean_rows_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.save("espn", csv_rows=[])
        self.assertEqual(self.writes, [])

    def test_cbs_zero_clean_rows_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.save("cbs", tables=[])
        self.assertEqual(self.writes, [])

    # -- guard: undeterminable vintage ------------------------------------------
    # defect: a vintage-less save resetting freshness downstream
    def test_espn_vintage_undeterminable_fails_closed(self):
        csv_path, meta_path, json_path = self.write_inputs(
            csv_rows=[
                "Josh Allen,josh allen,QB,BUF,True,True,1,2,3,4,0,0,0,100.0,3-18,2026-09-20",
                "Jahmyr Gibbs,jahmyr gibbs,RB,DET,True,True,0,0,5,6,7,8,9,200.0,3-18,2026-09-21",
            ],
            meta_vintage="",
        )
        meta_path.write_text(json.dumps({}))  # no vintage key either
        with self.assertRaises(SystemExit):
            mod.save_source("espn", dry_run=False, espn_csv=csv_path,
                            espn_meta=meta_path, cbs_json=json_path)
        self.assertEqual(self.writes, [])

    # -- guard: non-numeric key can never reach the table ------------------------
    # (identity is resolved from names; an unresolvable name is review, never
    # a fabricated key)
    def test_unresolved_name_goes_to_review_not_guessed(self):
        result = self.save(
            "espn",
            csv_rows=[
                "Josh Allen,josh allen,QB,BUF,True,True,1,2,3,4,0,0,0,366.13,3-18,2026-09-21",
                "Nobody Here,nobody here,QB,XXX,True,True,1,2,3,4,0,0,0,10.0,3-18,2026-09-21",
            ],
        )
        self.assertEqual(result["written"], 1)
        table, rows, _ = self.writes[0]
        self.assertEqual(table, "espn_season_projections")
        self.assertEqual(rows[0]["player_key"], 869)
        self.assertEqual(result["review_count"], 1)
        self.assertEqual(result["review"][0]["reason"], "unresolved_name")

    # -- guard: verified spelling aliases resolve to canonical identities -------
    # defect: the import landing fewer identities than the DDF leg (the
    # 347-vs-348 gap: "Cameron Ward"/"Cameron Skattebo" unresolved here while
    # the leg resolved them via the same map). The map is shared with
    # build_ddf_two_tier_leg.ALIASES -- this pins that the import applies it.
    def test_verified_alias_spellings_resolve(self):
        result = self.save(
            "espn",
            csv_rows=[
                "Cameron Ward,cameron ward,QB,TEN,True,True,1,2,3,4,0,0,0,300.0,3-18,2026-09-21",
                "Cameron Skattebo,cameron skattebo,RB,NYG,True,True,0,0,5,6,7,8,9,150.0,3-18,2026-09-21",
            ],
        )
        self.assertEqual(result["written"], 2)
        self.assertEqual(result["review_count"], 0)
        _, rows, _ = self.writes[0]
        by_key = {r["player_key"] for r in rows}
        self.assertEqual(by_key, {697, 3664})

    # -- guard: the alias map is exact-match only, never fuzzy -------------------
    # defect: the alias map silently becoming a fuzzy matcher and guessing
    # identities ("Cameron Wards" is NOT "Cameron Ward"). Anything not in the
    # map is looked up verbatim and must fail closed. Exercised through
    # build_espn_rows directly: a zero-clean save raises SystemExit before a
    # result dict exists, so the review is inspected at the builder level.
    def test_alias_map_does_not_fuzzy_match(self):
        csv_path, meta_path, _ = self.write_inputs(
            csv_rows=[
                "Cameron Wards,cameron wards,QB,TEN,True,True,1,2,3,4,0,0,0,300.0,3-18,2026-09-21",
                "Cam Wardle,cam wardle,QB,TEN,True,True,1,2,3,4,0,0,0,299.0,3-18,2026-09-21",
            ]
        )
        clean, review, _vintage = mod.build_espn_rows(csv_path, meta_path)
        self.assertEqual(clean, [])
        self.assertEqual(len(review), 2)
        self.assertTrue(
            all(r["reason"] == "unresolved_name" for r in review),
            review,
        )
        # And the save path still refuses to write an empty load.
        with self.assertRaises(SystemExit):
            mod.save_source("espn", dry_run=False, espn_csv=csv_path,
                            espn_meta=meta_path, cbs_json=self.tmp / "cbs.json")
    # defect: silently resolving an ambiguous name to one identity. The
    # position-aware disambiguation (Alex Smith QB vs TE) is legitimate --
    # this pins the case position cannot settle.
    def test_ambiguous_name_goes_to_review(self):
        result = self.save(
            "cbs",
            tables=[
                {"title": "Quarterback", "headers": ["Player", "tm", "1QB-4", "1QB-6", "2QB"],
                 "rows": [["Jordan Davis", "PHI", "10", "10", "20"],
                          ["Josh Allen", "BUF", "20", "20", "44"]]},
            ],
        )
        self.assertEqual(result["written"], 3)  # Allen only
        self.assertEqual(result["review_count"], 1)
        self.assertEqual(result["review"][0]["reason"], "unresolved_name")
        _, rows, _ = self.writes[0]
        self.assertTrue(all(r["player_key"] == 869 for r in rows))

    def test_position_disambiguation_is_not_guessing(self):
        # Alex Smith exists as QB and TE; the QB table's position settles it.
        result = self.save(
            "cbs",
            tables=[
                {"title": "Quarterback", "headers": ["Player", "tm", "1QB-4", "1QB-6", "2QB"],
                 "rows": [["Alex Smith", "KC", "10", "10", "20"]]},
            ],
        )
        self.assertEqual(result["written"], 3)
        _, rows, _ = self.writes[0]
        self.assertTrue(all(r["player_key"] == 9991 for r in rows))

    # -- ESPN row shape -----------------------------------------------------------
    def test_espn_row_shape_and_grain(self):
        result = self.save(
            "espn",
            csv_rows=[
                "Josh Allen,josh allen,QB,BUF,True,True,3674.1,24.6,517.7,11.5,0,0,0,366.13,3-18,2026-09-21",
            ],
        )
        self.assertEqual(result["written"], 1)
        self.assertEqual(result["vintage"], "2026-09-21")
        table, rows, conflict = self.writes[0]
        self.assertEqual(table, "espn_season_projections")
        self.assertEqual(conflict, "season,week,player_key")
        row = rows[0]
        self.assertEqual(row["player_key"], 869)
        self.assertEqual(row["season"], 2026)
        self.assertEqual(row["week"], 2)
        self.assertEqual(row["scoring"], "half_ppr")
        self.assertEqual(row["ros_half_ppr"], 366.13)
        self.assertEqual(row["r_pass_yds"], 3674.1)
        self.assertEqual(row["weeks_covered"], "3-18")
        self.assertEqual(row["espn_snapshot_date"], "2026-09-21")
        self.assertIn("pulled_at", row)

    # -- CBS QB scoring decision ---------------------------------------------------
    # defect: storing scoring=NULL (violates the CHECK) or silently fabricating
    # a per-scoring split. The documented decision: the single published 1QB-4
    # column is written once per scoring, labeled IMPLIED.
    def test_cbs_qb_gets_one_row_per_scoring_with_1qb4_value(self):
        result = self.save(
            "cbs",
            tables=[
                {"title": "Quarterback", "headers": ["Player", "tm", "1QB-4", "1QB-6", "2QB"],
                 "rows": [["Josh Allen", "BUF", "20", "20", "44"]]},
            ],
        )
        self.assertEqual(result["written"], 3)
        table, rows, conflict = self.writes[0]
        self.assertEqual(table, "cbs_trade_values")
        self.assertIn("scoring", conflict)
        by_scoring = {r["scoring"]: r for r in rows}
        self.assertEqual(set(by_scoring), {"standard", "half_ppr", "ppr"})
        for scoring, row in by_scoring.items():
            self.assertEqual(row["value"], 20.0, scoring)  # the 1QB-4 column, not 2QB
            self.assertEqual(row["player_key"], 869)
            self.assertEqual(row["source"], "cbs")
            self.assertEqual(row["variant"], "as_published")
            self.assertEqual(row["season"], 2026)
            self.assertEqual(row["week"], 2)

    def test_cbs_skill_positions_map_columns_to_scoring(self):
        result = self.save(
            "cbs",
            tables=[
                {"title": "Running back", "headers": ["Player", "tm", "non", "0.5", "PPR"],
                 "rows": [["Jahmyr Gibbs", "DET", "45", "46", "47"]]},
            ],
        )
        self.assertEqual(result["written"], 3)
        _, rows, _ = self.writes[0]
        by_scoring = {r["scoring"]: r["value"] for r in rows}
        self.assertEqual(by_scoring, {"standard": 45.0, "half_ppr": 46.0, "ppr": 47.0})

    def test_cbs_dashed_qbs_are_review_not_written(self):
        # QBs with '--' in the 1QB columns carry 2QB-only value; the save must
        # not invent a 1QB value for them. Purdy's dashed cell goes to review
        # while Allen's clean row is still written.
        result = self.save(
            "cbs",
            tables=[
                {"title": "Quarterback", "headers": ["Player", "tm", "1QB-4", "1QB-6", "2QB"],
                 "rows": [["Josh Allen", "BUF", "20", "20", "44"],
                          ["Brock Purdy", "SF", "--", "--", "38"]]},
            ],
        )
        self.assertEqual(result["written"], 3)  # Allen only, all three scorings
        self.assertEqual(result["review_count"], 3)  # Purdy's 3 implied cells
        _, rows, _ = self.writes[0]
        self.assertTrue(all(r["player_key"] == 869 for r in rows))
        self.assertTrue(all(r["reason"] == "missing_or_non_numeric_value" for r in result["review"]))

    # -- dry run writes nothing ------------------------------------------------------
    def test_dry_run_writes_nothing(self):
        csv_path, meta_path, json_path = self.write_inputs(
            csv_rows=["Josh Allen,josh allen,QB,BUF,True,True,1,2,3,4,0,0,0,366.13,3-18,2026-09-21"]
        )
        result = mod.save_source("espn", dry_run=True, espn_csv=csv_path,
                                 espn_meta=meta_path, cbs_json=json_path)
        self.assertTrue(result["dry_run"])
        self.assertEqual(self.writes, [])

    # -- idempotency: upsert on the grain ----------------------------------------------
    # defect: a re-run duplicating rows instead of merging on the grain
    def test_upsert_uses_grain_conflict(self):
        self.save("cbs", tables=[
            {"title": "Running back", "headers": ["Player", "tm", "non", "0.5", "PPR"],
             "rows": [["Jahmyr Gibbs", "DET", "45", "46", "47"]]},
        ])
        _, _, conflict = self.writes[0]
        self.assertEqual(
            conflict,
            "source,variant,scoring,league_teams,qb_slots,season,week,player_key",
        )


if __name__ == "__main__":
    unittest.main()
