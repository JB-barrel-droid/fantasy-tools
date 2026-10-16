#!/usr/bin/env python3
"""JEG-669: KeepTradeCut puller fails closed and never zero-fills. Hermetic (saved fixture)."""
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "pipelines"))
import pull_keeptradecut as ktc  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "keeptradecut_sample.html")
SMALL = {pos: 1 for pos in ktc.POSITIONS}


def fixture_players():
    with open(FIXTURE, encoding="utf-8") as f:
        return _extract(f.read())


def _extract(body):
    old = ktc.MIN_BODY
    ktc.MIN_BODY = 0
    try:
        return ktc.extract_players(body)
    finally:
        ktc.MIN_BODY = old


class TestKeepTradeCutPull(unittest.TestCase):
    def test_real_sample_parses_drops_picks_and_keeps_formats(self):
        snap = ktc.build_snapshot(fixture_players(), floors=SMALL)
        self.assertEqual(snap["dropped"]["non_skill_position"], 4)  # rookie draft picks
        self.assertEqual(snap["row_count"], 16)
        self.assertEqual({r["pos"] for r in snap["rows"]}, set(ktc.POSITIONS))
        row = snap["rows"][0]
        self.assertEqual(set(row["values"]), set(ktc.format_keys()))
        self.assertEqual(row["values"]["1qb"]["rank"], 1)
        self.assertTrue(row["player_norm"])

    def test_zero_value_is_null_not_zero(self):
        players = fixture_players()
        players[0]["superflexValues"]["tep"]["value"] = 0
        players[0]["superflexValues"].pop("tepp")
        snap = ktc.build_snapshot(players, floors=SMALL)
        v = snap["rows"][0]["values"]
        self.assertIsNone(v["sf_tep"])
        self.assertIsNone(v["sf_tepp"])
        self.assertIsNotNone(v["sf"])

    def test_unpriced_row_dropped_not_zero_filled(self):
        players = fixture_players()
        ghost = copy.deepcopy(players[0])
        ghost["playerName"], ghost["playerID"] = "Ghost Player", 99999
        for lg in ("oneQBValues", "superflexValues"):
            ghost[lg]["value"] = 0
            for t in ("tep", "tepp", "teppp"):
                ghost[lg][t]["value"] = 0
        snap = ktc.build_snapshot(players + [ghost], floors=SMALL)
        self.assertEqual(snap["dropped"]["unpriced"], 1)
        self.assertNotIn("Ghost Player", [r["player_name"] for r in snap["rows"]])

    def test_value_out_of_range_fails_closed(self):
        players = fixture_players()
        players[0]["oneQBValues"]["value"] = 12000
        with self.assertRaises(ktc.PullError) as cm:
            ktc.build_snapshot(players, floors=SMALL)
        self.assertEqual(cm.exception.code, "VALUE_RANGE")

    def test_position_below_floor_fails_closed(self):
        with self.assertRaises(ktc.PullError) as cm:
            ktc.build_snapshot(fixture_players())  # real floors, 4-row sample
        self.assertEqual(cm.exception.code, "SOURCE_TRUNCATED")

    def test_required_field_gone_fails_closed(self):
        players = fixture_players()
        for p in players:
            p.pop("superflexValues", None)
        with self.assertRaises(ktc.PullError) as cm:
            ktc.build_snapshot(players, floors=SMALL)
        self.assertEqual(cm.exception.code, "SOURCE_LAYOUT")

    def test_tiny_body_and_missing_script_fail_closed(self):
        with self.assertRaises(ktc.PullError) as cm:
            ktc.extract_players("<html>login</html>")
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")
        with self.assertRaises(ktc.PullError) as cm:
            ktc.extract_players("<html>" + "x" * ktc.MIN_BODY + "</html>")
        self.assertEqual(cm.exception.code, "SOURCE_LAYOUT")

    def test_fingerprint_moves_with_value_and_is_stable_otherwise(self):
        a = ktc.build_snapshot(fixture_players(), floors=SMALL)["fingerprint"]
        self.assertEqual(a, ktc.build_snapshot(fixture_players(), floors=SMALL)["fingerprint"])
        moved = fixture_players()
        moved[0]["oneQBValues"]["value"] -= 1
        self.assertNotEqual(a, ktc.build_snapshot(moved, floors=SMALL)["fingerprint"])

    def test_cli_writes_nothing_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.html")
            with open(bad, "w") as f:
                f.write("<html>nothing</html>")
            out = os.path.join(d, "out")
            self.assertEqual(ktc.main(["--out-dir", out, "--html", bad]), 1)
            self.assertFalse(os.path.exists(os.path.join(out, "snapshot.json")))


if __name__ == "__main__":
    unittest.main()
