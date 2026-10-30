"""JEG-1351 path A: the duplicate-row merge agrees with the id evidence.

Three Sleeper spellings landed on gsis-less duplicate rows that the Sleeper
identity refresh inserted (4653, 4655, 4660). The merge migration folds each
into the original row for the same person. This pins the migration's pairs to
the committed evidence (sleeper_projection_idmap.csv: Sleeper id -> gsis ->
player_key, status matched) and to the alias list, so the three files cannot
drift apart before the migration runs.
"""

from __future__ import annotations

import csv
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import player_aliases  # noqa: E402

MIGRATION = ROOT / "supabase" / "migrations" / "jeg1351_merge_sleeper_duplicate_players.sql"
IDMAP = ROOT / "data" / "inputs" / "sleeper_projection_idmap.csv"
PAIR = re.compile(r"\(\s*(\d+),\s*(\d+),\s*'((?:[^']|'')*)',\s*'(\d+)',\s*'([0-9-]+)'\s*\)")


def migration_pairs() -> list[tuple[int, int, str, str, str]]:
    sql = MIGRATION.read_text(encoding="utf-8")
    return [(int(d), int(o), n.replace("''", "'"), s, g) for d, o, n, s, g in PAIR.findall(sql)]


class MergeMatchesTheIdEvidence(unittest.TestCase):
    def test_the_three_pairs_are_the_ticket_pairs(self):
        self.assertEqual({(4653, 2785), (4655, 437), (4660, 4363)},
                         {(d, o) for d, o, *_ in migration_pairs()})

    def test_each_sleeper_id_maps_through_gsis_to_the_original(self):
        with IDMAP.open(encoding="utf-8", newline="") as fh:
            idmap = {r["sleeper_id"]: r for r in csv.DictReader(fh)}
        for dup, orig, name, sid, gsis in migration_pairs():
            with self.subTest(dup=dup):
                row = idmap[sid]
                self.assertEqual("matched", row["status"])
                self.assertEqual(gsis, row["gsis_id"])
                self.assertEqual(str(orig), row["player_key"])
                self.assertEqual(name, row["name"])

    def test_the_sleeper_spelling_is_a_verified_alias_of_the_original(self):
        for _dup, orig, name, _sid, _gsis in migration_pairs():
            with self.subTest(name=name):
                self.assertEqual(orig, player_aliases.alias_key(name))

    def test_migration_is_data_only_and_never_cascades_silently(self):
        sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8")).lower()
        self.assertNotRegex(sql, r"\b(create|alter|drop|truncate)\s+")
        for table in ("player_game_stats", "ranker_rankings", "player_value_notes"):
            self.assertIn(f"public.{table}", sql)
        self.assertIn("raise exception", sql)


if __name__ == "__main__":
    unittest.main()
