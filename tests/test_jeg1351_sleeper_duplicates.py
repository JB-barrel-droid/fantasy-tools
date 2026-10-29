"""JEG-1351 path B: verified duplicate rows resolve to the original.

Three Sleeper spellings landed on gsis-less duplicate rows that the Sleeper
identity refresh inserted (4653, 4655, 4660). Path B keeps those rows in
public.players and lists them in data/inputs/player_key_merges.json; the name
resolver and the id index then answer with the original row. This pins each
entry to the committed id evidence (sleeper_projection_idmap.csv: Sleeper id
-> gsis -> player_key, status matched) and checks the layer fails closed.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import canonical_players  # noqa: E402
from canonical_players import Registry, resolve_with_reason  # noqa: E402
from player_key_index import PlayerIndex  # noqa: E402

MERGES = ROOT / "data" / "inputs" / "player_key_merges.json"
IDMAP = ROOT / "data" / "inputs" / "sleeper_projection_idmap.csv"

ROWS = [
    {"player_key": 2785, "id": "a", "full_name": "Nyheim Hines", "position": "RB", "active": False,
     "metadata": {"gsis_id": "00-0034367"}},
    {"player_key": 4653, "id": "b", "full_name": "Nyheim Miller-Hines", "position": "RB", "active": True,
     "metadata": {"sleeper_id": "5347"}},
    {"player_key": 4363, "id": "c", "full_name": "Mitchell Tinsley", "position": "WR", "active": False,
     "metadata": {"gsis_id": "00-0038839"}},
    {"player_key": 4660, "id": "d", "full_name": "Mitch Tinsley", "position": "WR", "active": True,
     "metadata": {"sleeper_id": "11068"}},
]


def entries() -> list[dict]:
    return json.loads(MERGES.read_text(encoding="utf-8"))["merges"]


class MergeListMatchesTheIdEvidence(unittest.TestCase):
    def test_the_three_pairs_are_the_ticket_pairs(self):
        self.assertEqual({4653: 2785, 4655: 437, 4660: 4363}, canonical_players.load_key_merges())

    def test_each_sleeper_id_maps_through_gsis_to_the_original(self):
        with IDMAP.open(encoding="utf-8", newline="") as fh:
            idmap = {r["sleeper_id"]: r for r in csv.DictReader(fh)}
        for m in entries():
            with self.subTest(dup=m["duplicate_key"]):
                row = idmap[m["sleeper_id"]]
                self.assertEqual("matched", row["status"])
                self.assertEqual(m["gsis_id"], row["gsis_id"])
                self.assertEqual(str(m["original_key"]), row["player_key"])
                self.assertEqual(m["duplicate_name"], row["name"])
                self.assertTrue(m["verified"])


class ResolversAnswerWithTheOriginal(unittest.TestCase):
    def test_the_duplicates_name_finds_the_original_with_or_without_position(self):
        reg = Registry(ROWS)
        self.assertEqual((2785, "ok"), resolve_with_reason("Nyheim Miller-Hines", "RB", registry=reg))
        self.assertEqual((2785, "ok"), resolve_with_reason("Nyheim Miller-Hines", registry=reg))
        self.assertEqual((4363, "ok"), resolve_with_reason("Mitch Tinsley", "WR", registry=reg))
        self.assertEqual((4363, "ok"), resolve_with_reason("Mitchell Tinsley", "WR", registry=reg))
        self.assertEqual(4363, reg.canonical_key(4660))
        self.assertEqual(4363, reg.canonical_key(4363))

    def test_the_sleeper_id_on_the_duplicate_finds_the_original(self):
        idx = PlayerIndex(ROWS)
        e, how = idx.resolve_sleeper("11068", "Mitch Tinsley", "WR")
        self.assertEqual((4363, "sleeper_id"), (e["player_key"], how))

    def test_a_merge_across_positions_or_with_a_row_missing_is_ignored(self):
        rows = [dict(r) for r in ROWS]
        rows[3] = dict(rows[3], position="TE")
        reg = Registry(rows)
        self.assertEqual((4660, "ok"), resolve_with_reason("Mitch Tinsley", "TE", registry=reg))
        reg = Registry(ROWS[2:3] + ROWS[3:])
        self.assertEqual(4363, reg.canonical_key(4660))
        reg = Registry(ROWS[3:])
        self.assertEqual((4660, "ok"), resolve_with_reason("Mitch Tinsley", "WR", registry=reg))

    def test_a_chained_or_self_merge_fails_closed(self):
        for merges in ([{"duplicate_key": 1, "original_key": 1}],
                       [{"duplicate_key": 1, "original_key": 2}, {"duplicate_key": 2, "original_key": 3}]):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "m.json"
                p.write_text(json.dumps({"schema": "player-key-merges-v1", "merges": merges}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    canonical_players.load_key_merges(str(p))

    def test_no_merge_file_means_no_merges(self):
        with mock.patch.object(canonical_players, "KEY_MERGES", "/nonexistent/merges.json"):
            self.assertEqual({}, canonical_players.load_key_merges())
            self.assertEqual((4660, "ok"), resolve_with_reason("Mitch Tinsley", "WR", registry=Registry(ROWS)))


if __name__ == "__main__":
    unittest.main()
