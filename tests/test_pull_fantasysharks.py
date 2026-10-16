#!/usr/bin/env python3
"""JEG-621: Fantasy Sharks puller fails closed and never zero-fills. Hermetic."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "pipelines"))
import pull_fantasysharks as fs  # noqa: E402

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
META = {"vintage_date": date(2026, 10, 15)}
HEADER = "Rank,Player ID,Player Name,Team,Position,Pass Yds,Pts\n"


def csv_body(rows):
    lines = [f'{i},{pid},"{name}",XXX,{pos},0,{pts}' for i, (pid, name, pos, pts) in enumerate(rows, 1)]
    return HEADER + "\n".join(lines) + "\n"


def tables(extra=(), bump=None):
    """A roster that clears every floor; extra = (pid, name, pos, (non, half, ppr))."""
    base, pid = [], 0
    for pos, n in fs.ROW_FLOORS.items():
        for i in range(n):
            pid += 1
            base.append((pid, f"Last{pos}{i}, Pat", pos, (10 + i, 11 + i, 12 + i)))
    base.extend(extra)
    out = {}
    for k, scoring in enumerate(fs.SCORINGS):
        out[scoring] = fs.parse_csv(csv_body([(p, n, pos, v[k]) for p, n, pos, v in base]), scoring)
    if bump:
        bump(out)
    return out


PAGE = ('<select name="Segment"><option value="874">2026 NFL Season</option>'
        '<option value="877" selected>2026 Rest of Year</option></select>'
        '<select name="Position"><option value="97" selected>All Offense</option></select>'
        '<td>Quarterback projections last updated 10-15</td>')


class TestFantasySharksPull(unittest.TestCase):
    def test_happy_path_nulls_zero_swaps_name_drops_idp(self):
        extra = [
            (900, "Lineman, Dee", "DL", (5, 5, 5)),            # IDP-style position: dropped
            (901, "Nothing, Un", "WR", (0, 0, 0)),              # all zero: dropped, not zero-filled
            (902, "Partial, Pat", "RB", (0, 0, 7.5)),           # only PPR projected: others null
        ]
        snap = fs.build_snapshot(tables(extra), META, NOW)
        by_id = {r["fantasysharks_id"]: r for r in snap["rows"]}
        self.assertNotIn(900, by_id)
        self.assertNotIn(901, by_id)
        self.assertEqual(by_id[902]["pts"], {"non_ppr": None, "half_ppr": None, "ppr": 7.5})
        self.assertEqual(by_id[1]["player_name"], "Pat LastQB0")
        self.assertEqual(snap["dropped"]["unprojected"], 1)
        self.assertEqual(snap["dropped"]["non_skill_position"], 3)
        self.assertEqual(snap["vintage_date"], "2026-10-15")
        self.assertTrue(snap["fingerprint"])

    def test_non_csv_body_is_blocked(self):
        with self.assertRaises(fs.PullError) as cm:
            fs.parse_csv("<html>please log in</html>", "half_ppr")
        self.assertEqual(cm.exception.code, "SOURCE_BLOCKED")

    def test_missing_pts_column_is_layout(self):
        with self.assertRaises(fs.PullError) as cm:
            fs.parse_csv("Rank,Player ID,Player Name,Team,Position\n1,1,\"A, B\",X,QB\n", "ppr")
        self.assertEqual(cm.exception.code, "SOURCE_LAYOUT")

    def test_truncated_position(self):
        t = tables()
        t["half_ppr"] = [r for r in t["half_ppr"] if r["Position"] != "TE"]
        with self.assertRaises(fs.PullError) as cm:
            fs.build_snapshot(t, META, NOW)
        self.assertEqual(cm.exception.code, "SOURCE_TRUNCATED")

    def test_value_range(self):
        def bump(t):
            t["ppr"][0]["Pts"] = "5000"
        with self.assertRaises(fs.PullError) as cm:
            fs.build_snapshot(tables(bump=bump), META, NOW)
        self.assertEqual(cm.exception.code, "VALUE_RANGE")

    def test_non_numeric_pts(self):
        def bump(t):
            t["ppr"][0]["Pts"] = "n/a"
        with self.assertRaises(fs.PullError) as cm:
            fs.build_snapshot(tables(bump=bump), META, NOW)
        self.assertEqual(cm.exception.code, "VALUE_RANGE")

    def test_swapped_scorings_are_caught(self):
        def bump(t):
            t["non_ppr"], t["ppr"] = t["ppr"], t["non_ppr"]
        with self.assertRaises(fs.PullError) as cm:
            fs.build_snapshot(tables(bump=bump), META, NOW)
        self.assertEqual(cm.exception.code, "VALUE_RANGE")

    def test_stale_vintage(self):
        with self.assertRaises(fs.PullError) as cm:
            fs.build_snapshot(tables(), {"vintage_date": date(2026, 9, 1)}, NOW)
        self.assertEqual(cm.exception.code, "SOURCE_STALE")

    def test_page_meta_reads_stamp_and_pins_period(self):
        self.assertEqual(fs.parse_page_meta(PAGE, date(2026, 10, 15))["vintage_date"], date(2026, 10, 15))
        self.assertEqual(fs.parse_page_meta(PAGE, date(2027, 1, 3))["vintage_date"], date(2026, 10, 15))

    def test_page_meta_fails_when_period_or_stamp_changes(self):
        for broken in (PAGE.replace('value="877" selected', 'value="877"'),          # period moved
                       PAGE.replace("2026 Rest of Year", "Week 7"),                     # relabelled
                       PAGE.replace('value="97" selected', 'value="97"'),               # position moved
                       PAGE.replace("last updated 10-15", "")):                          # no stamp
            with self.assertRaises(fs.PullError) as cm:
                fs.parse_page_meta(broken, date(2026, 10, 15))
            self.assertEqual(cm.exception.code, "SOURCE_LAYOUT")

    def test_cli_writes_nothing_on_failure(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            with open(os.path.join(d, "page.html"), "w") as f:
                f.write(PAGE.replace("last updated 10-15", ""))
            self.assertEqual(fs.main(["--out-dir", out, "--replay-dir", d]), 1)
            self.assertEqual(os.listdir(out), [])

    def test_cli_replay_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
            today = datetime.now(timezone.utc).date()
            with open(os.path.join(d, "page.html"), "w") as f:
                f.write(PAGE.replace("10-15", f"{today.month}-{today.day}"))
            t = tables()
            for scoring in fs.SCORINGS:
                rows = [(r["Player ID"], r["Player Name"], r["Position"], r["Pts"]) for r in t[scoring]]
                with open(os.path.join(d, f"{scoring}.csv"), "w") as f:
                    f.write(csv_body(rows))
            self.assertEqual(fs.main(["--out-dir", out, "--replay-dir", d]), 0)
            snap = json.load(open(os.path.join(out, "snapshot.json")))
            self.assertEqual(snap["schema"], fs.SCHEMA)
            self.assertEqual(snap["row_count"], sum(fs.ROW_FLOORS.values()))


if __name__ == "__main__":
    unittest.main()
