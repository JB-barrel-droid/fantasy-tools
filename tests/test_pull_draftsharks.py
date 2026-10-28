#!/usr/bin/env python3
"""JEG-620: Draft Sharks puller fails closed and never zero-fills. Hermetic."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "pipelines"))
import pull_draftsharks as ds  # noqa: E402

COLS = ds.format_columns()


def player(pid, first, last, pos, half=None, market=None, dyn=None):
    row = {"id": pid, "first_name": first, "last_name": last, "fantasy_position": pos, "abbr": "XXX"}
    for dc, mc in COLS.values():
        row[dc] = 0
        row[mc] = 0
    if half is not None:
        row["dsValueRedraftHalfPpr"] = half
    if market is not None:
        row["marketValueRedraftHalfPpr"] = market
    if dyn is not None:
        row["dsValueDynastyHalfPpr"] = dyn
    return row


def roster(extra=()):
    ps, pid = [], 0
    for pos, n in ds.PRICED_FLOORS.items():
        for i in range(n):
            pid += 1
            ps.append(player(pid, "Pat", f"{pos}{i}", pos, half=10 + i, market=5, dyn=3))
    ps.extend(extra)
    return ps


def page(players):
    return "<html>" + "x" * ds.MIN_BODY + '{"picks":[],"players":' + json.dumps(players) + "}</html>"


class TestDraftSharksPull(unittest.TestCase):
    def test_happy_path_nulls_zero_and_keeps_negative(self):
        extra = [
            player(900, "Dee", "Pth", "DB", half=-90),                     # IDP: dropped
            player(901, "Un", "Priced", "WR"),                             # all zero: dropped, not zero-filled
            player(902, "Dep", "Th", "RB", half=-40.5),                    # negative is a real value
            player(903, "Only", "Dynasty", "TE", dyn=12),                  # redraft null, dynasty kept
        ]
        snap = ds.build_snapshot(ds.extract_players(page(roster(extra))))
        by = {r["draftsharks_id"]: r for r in snap["rows"]}
        self.assertNotIn(900, by)
        self.assertNotIn(901, by)
        self.assertEqual(snap["dropped"], {"non_skill_position": 1, "unpriced": 1})
        self.assertEqual(by[902]["ds"]["redraft_half_ppr"], -40.5)
        self.assertIsNone(by[903]["ds"]["redraft_half_ppr"])
        self.assertEqual(by[903]["ds"]["dynasty_half_ppr"], 12)
        self.assertIsNone(by[903]["market"]["redraft_half_ppr"])
        self.assertIsNone(by[902]["ds"]["redraft_one_ppr"])  # 0 -> null, never 0
        self.assertEqual(by[902]["player_norm"], "dep th")

    def test_fingerprint_moves_with_values(self):
        a = ds.build_snapshot(roster_players := ds.extract_players(page(roster())))["fingerprint"]
        roster_players[0]["dsValueRedraftHalfPpr"] += 1
        b = ds.build_snapshot(roster_players)["fingerprint"]
        self.assertNotEqual(a, b)

    def test_distinct_players_with_same_chart_value_are_retained(self):
        ps = roster()
        ps[0]["dsValueRedraftHalfPpr"] = 69
        ps[1]["dsValueRedraftHalfPpr"] = 69
        snap = ds.build_snapshot(ps)
        same_value = [r for r in snap["rows"] if r["ds"]["redraft_half_ppr"] == 69]
        self.assertEqual({r["draftsharks_id"] for r in same_value}, {1, 2})
        self.assertEqual(snap["vintage_basis"], "fetch_date_not_publisher_chart_date")

    def test_tiny_body_is_blocked(self):
        with self.assertRaises(ds.PullError) as c:
            ds.extract_players("<html>login</html>")
        self.assertEqual(c.exception.code, "SOURCE_BLOCKED")

    def test_missing_players_array_is_layout(self):
        with self.assertRaises(ds.PullError) as c:
            ds.extract_players("<html>" + "x" * ds.MIN_BODY + "</html>")
        self.assertEqual(c.exception.code, "SOURCE_LAYOUT")

    def test_missing_column_is_layout(self):
        ps = roster()
        del ps[0]["marketValueRedraftHalfPpr"]
        with self.assertRaises(ds.PullError) as c:
            ds.build_snapshot(ps)
        self.assertEqual(c.exception.code, "SOURCE_LAYOUT")

    def test_missing_column_in_later_player_is_layout(self):
        ps = roster()
        del ps[-1]["marketValueRedraftHalfPpr"]
        with self.assertRaises(ds.PullError) as c:
            ds.build_snapshot(ps)
        self.assertEqual(c.exception.code, "SOURCE_LAYOUT")

    def test_missing_and_duplicate_player_identity_fail(self):
        ps = roster()
        ps[-1]["id"] = ps[0]["id"]
        with self.assertRaises(ds.PullError) as c:
            ds.build_snapshot(ps)
        self.assertEqual(c.exception.code, "SOURCE_LAYOUT")
        ps[-1]["id"] = 999
        ps[-1]["first_name"] = ""
        ps[-1]["last_name"] = None
        with self.assertRaises(ds.PullError) as c:
            ds.build_snapshot(ps)
        self.assertEqual(c.exception.code, "SOURCE_LAYOUT")

    def test_saved_embedded_array_fixture_accepts_json_whitespace(self):
        fixture = os.path.join(ROOT, "tests", "fixtures", "draftsharks", "embedded_chart.html")
        with mock.patch.object(ds, "MIN_BODY", 0):
            with open(fixture, encoding="utf-8") as f:
                players = ds.extract_players(f.read())
        self.assertEqual(players[0]["id"], 101)

    def test_truncated_position_fails(self):
        ps = [p for p in roster() if p["fantasy_position"] != "TE"]
        with self.assertRaises(ds.PullError) as c:
            ds.build_snapshot(ps)
        self.assertEqual(c.exception.code, "SOURCE_TRUNCATED")

    def test_scale_change_fails(self):
        ps = roster()
        ps[0]["dsValueRedraftHalfPpr"] = 4500  # e.g. a 0-10000 scale
        with self.assertRaises(ds.PullError) as c:
            ds.build_snapshot(ps)
        self.assertEqual(c.exception.code, "VALUE_RANGE")

    def test_cli_writes_nothing_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            html = os.path.join(d, "p.html")
            open(html, "w").write("<html>nope</html>")
            self.assertEqual(ds.main(["--out-dir", os.path.join(d, "out"), "--html", html]), 1)
            self.assertFalse(os.path.exists(os.path.join(d, "out", "snapshot.json")))

    def test_cli_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            html = os.path.join(d, "p.html")
            open(html, "w").write(page(roster()))
            self.assertEqual(ds.main(["--out-dir", d, "--html", html]), 0)
            snap = json.load(open(os.path.join(d, "snapshot.json")))
            self.assertEqual(snap["schema"], ds.SCHEMA)
            self.assertEqual(snap["row_count"], sum(ds.PRICED_FLOORS.values()))


if __name__ == "__main__":
    unittest.main()
