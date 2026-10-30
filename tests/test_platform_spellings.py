"""JEG-1202: each player's ESPN, Sleeper and Yahoo spelling as name-table rows.

pipelines/build_platform_spellings.py turns the JEG-1202 audit's grounded
spellings into data/inputs/player_platform_spellings.json and the NOT APPLIED
migration supabase/migrations/jeg1202_platform_spellings.sql. Offline: no
network, no Supabase.

    python3 -m unittest tests.test_platform_spellings
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import build_platform_spellings as bps  # noqa: E402
import player_aliases  # noqa: E402
from canonical_players import norm_player_name  # noqa: E402

JSON_PATH = ROOT / bps.OUT_JSON
SQL_PATH = ROOT / bps.OUT_SQL
# public.players rows JEG-1351 deletes as duplicates of 2785, 437 and 4363.
JEG1351_DUPLICATES = {4653, 4655, 4660}


def _doc():
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _snapshot_keys():
    s = json.loads((ROOT / "data/inputs/players_identity_snapshot.json").read_text(encoding="utf-8"))
    rows = s if isinstance(s, list) else (s.get("rows") or s.get("players"))
    return {int(r["player_key"]): r for r in rows}


class CommittedRows(unittest.TestCase):
    def test_committed_files_match_a_rebuild(self):
        self.assertEqual(bps.main(["--check"]), 0,
                         "run python3 pipelines/build_platform_spellings.py")

    def test_every_platform_has_rows(self):
        counts = _doc()["counts"]
        for src in bps.SOURCES:
            self.assertGreater(counts[src], 0, src)

    def test_rows_use_the_shared_normalization_and_one_row_per_grain(self):
        seen = set()
        for r in _doc()["rows"]:
            self.assertEqual(r["norm_name"], norm_player_name(r["source_player_name"]), r)
            grain = (r["source"], r["norm_name"], r["position"])
            self.assertNotIn(grain, seen, grain)
            seen.add(grain)

    def test_every_row_is_a_grounded_audit_spelling_for_its_key(self):
        matrix = {int(m["player_key"]): m for m in csv.DictReader(
            (ROOT / bps.MATRIX).read_text(encoding="utf-8").splitlines())}
        snap = _snapshot_keys()
        for r in _doc()["rows"]:
            m = matrix[r["player_key"]]
            self.assertIn(m[f"{r['source']}_status"], bps.GROUNDED, r)
            self.assertIn(r["source_player_name"], m[f"{r['source']}_spelling"].split(" | "), r)
            self.assertEqual(snap[r["player_key"]]["full_name"], r["canonical_full_name"], r)
            self.assertEqual(snap[r["player_key"]]["position"], r["position"], r)
            self.assertTrue(r["ground"] and r["evidence"], r)

    def test_sleeper_rows_carry_the_sleeper_id(self):
        for r in _doc()["rows"]:
            if r["source"] == "sleeper":
                self.assertRegex(r["source_player_id"] or "", r"^\d+$", r)

    def test_known_platform_spellings_land_on_the_right_player(self):
        rows = {(r["source"], r["source_player_name"]): r["player_key"] for r in _doc()["rows"]}
        # Ground: Sleeper id through the gsis chain (JEG-1202 audit); 2785, 437
        # and 4363 are the rows JEG-1351 keeps.
        self.assertEqual(rows[("sleeper", "Nyheim Miller-Hines")], 2785)
        self.assertEqual(rows[("sleeper", "Jody Fortson")], 437)
        self.assertEqual(rows[("sleeper", "Mitch Tinsley")], 4363)
        self.assertEqual(rows[("sleeper", "Tyron Billy-Johnson")], 423)
        self.assertEqual(rows[("espn", "Broncos D/ST")], 60)
        self.assertEqual(rows[("yahoo", "Chiefs")], 132)

    def test_no_row_points_at_a_jeg1351_duplicate(self):
        keys = {r["player_key"] for r in _doc()["rows"]}
        self.assertFalse(keys & JEG1351_DUPLICATES)

    def test_ungrounded_paste_spellings_are_not_stored(self):
        names = {(r["source"], r["source_player_name"]) for r in _doc()["rows"]}
        for n in (("espn", "Aaron Jones Sr."), ("yahoo", "Aaron Jones Sr."), ("espn", "Kyle Pitts Sr.")):
            self.assertNotIn(n, names)


class Migration(unittest.TestCase):
    def setUp(self):
        self.sql = SQL_PATH.read_text(encoding="utf-8")

    def test_not_applied_and_one_transaction(self):
        self.assertIn("NOT APPLIED", self.sql)
        self.assertRegex(self.sql, r"(?m)^begin;$")
        self.assertRegex(self.sql, r"(?m)^commit;$")

    def test_holds_every_json_row(self):
        rows = _doc()["rows"]
        self.assertEqual(len(re.findall(r"(?m)^    \('(sleeper|espn|yahoo)', ", self.sql)), len(rows))

    def test_stops_on_a_row_naming_another_player_and_never_overwrites(self):
        self.assertIn("existing rows name another player", self.sql)
        self.assertIn("player_key not in public.players", self.sql)
        self.assertIn("on conflict (source, norm_name, position) do nothing", self.sql)
        self.assertNotIn("do update", self.sql)

    def test_rows_stay_out_of_the_curated_alias_list(self):
        # lib/player_aliases reads only source '*' method 'curated' rows, so
        # storing platform spellings moves no value.
        for method in bps.METHOD.values():
            self.assertNotEqual(method, player_aliases.CURATED_METHOD)
        self.assertNotIn("'*'", self.sql.split("insert into jeg1202_platform_rows values", 1)[1]
                         .split(";", 1)[0])


class SharedSpellingsAreHeld(unittest.TestCase):
    """Two players that share (source, norm_name, position) get no row."""

    def test_two_players_one_grain_are_held_not_guessed(self):
        header = ("player_key,canonical_full_name,position,gsis_id,sleeper_status,sleeper_spelling,"
                  "sleeper_ids,sleeper_link,sleeper_source,sleeper_resolver,espn_status,espn_spelling,"
                  "espn_ground,espn_evidence,espn_resolver,yahoo_status,yahoo_spelling,yahoo_ground,"
                  "yahoo_evidence,yahoo_resolver")
        matrix = "\n".join([
            header,
            "1,Josh Smith,WR,,same,Josh Smith,11,idmap,base,ok,missing,,,,,missing,,,,",
            "2,Joshua Smith,WR,,differs,Josh Smith,22,idmap,base,ok,missing,,,,,missing,,,,",
            "3,Al Jones,RB,,same,Al Jones,33,gsis,base,ok,missing,,,,,missing,,,,",
        ])
        files = {bps.MATRIX: matrix, bps.OBSERVATIONS: json.dumps({"observations": []})}
        with mock.patch.object(bps, "_read", lambda rel: files[rel]):
            rows, held = bps.build()
        self.assertEqual([(r["player_key"], r["source_player_name"]) for r in rows], [(3, "Al Jones")])
        self.assertEqual(sorted(r["player_key"] for r in held), [1, 2])


if __name__ == "__main__":
    unittest.main()
