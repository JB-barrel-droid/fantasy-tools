"""JEG-667: the coverage triage brief parses the reviewer's text, classifies
each dropped player from roster status, and `accept` writes a decision the
reviewer honours (and refuses names it cannot list)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import coverage_triage as ct  # noqa: E402

TEXT = ("HELD ... Failing checks: native_drift:half_12:warn -- x; coverage:half_12/WR:fail -- candidate priced 41 < "
        "fixture 43 (dropped: a one, b two; added: c three) -- live verification skipped; 2 players left > tolerance 1 "
        "(dropped: a one, b two); coverage:half_12/TE:fail -- candidate priced 10 < fixture 14 (dropped: t one; "
        "added: none) -- 1 dropped player(s) still priced live (e.g. t one) -- pipeline loss. A hold means a human")


def player(key, name, pos, rs, depth, team="AAA"):
    return {"player_key": key, "name": name, "pos": pos, "team": team,
            "roster_status": rs, "depth_chart_order": depth}


def directory():
    d = ct.Directory.__new__(ct.Directory)
    d.keys = {"a one": 1, "b two": 2, "w3": 3, "w4": 4, "w5": 5}
    d.players = {1: player(1, "A One", "WR", "injured_reserve", 2),
                 2: player(2, "B Two", "WR", "active_roster", 1),
                 3: player(3, "W Three", "WR", "active_roster", 1),
                 4: player(4, "W Four", "WR", "active_roster", 2),
                 5: player(5, "W Five", "WR", "active_roster", 5)}
    d.sleeper = {}
    vals = {"w3": 50.0, "w4": 40.0, "b two": 30.0, "w5": 10.0, "a one": 1.0}
    d.section = {"combos": {"half_12": {"reindexed": dict(vals), "native": dict(vals)}}}
    return d


class TriageTest(unittest.TestCase):
    def test_parse_status_text(self):
        rows = ct.drops_from_status("cbs", {"sources": {"cbs": TEXT}})
        self.assertEqual([(r[0], r[1], r[2], r[3], r[4]) for r in rows],
                         [("half_12", "WR", 41, 43, ["a one", "b two"]),
                          ("half_12", "TE", 10, 14, ["t one"])])
        self.assertIn("still priced live", ct.VERIFY[("half_12", "TE")])

    def test_classification(self):
        d = directory()
        kind = lambda slug: ct.classify(d.describe("half_12", "WR", slug))[0]  # noqa: E731
        self.assertEqual(kind("a one"), "rotation")   # injured reserve
        self.assertEqual(kind("b two"), "scrape")     # active depth-1 starter, mid-list
        self.assertEqual(kind("w5"), "unclear")       # deep bench, mid-list
        self.assertEqual(kind("nobody"), "unclear")   # no status to check

    def test_accept_roundtrip_and_incomplete_names(self):
        tmp = Path(tempfile.mkdtemp()) / "acc.json"
        rows = [("half_12", "WR", 41, 43, ["a one"], [], False)]
        ct.accept("cbs", rows, 6, "Jeremy 2026-10-16 rotation", "names", tmp)
        e = json.loads(tmp.read_text())["entries"][0]
        self.assertEqual((e["week"], e["names"], e["approved_by"]), (6, ["a one"], "Jeremy"))
        truncated = [("half_12", "WR", 41, 43, ["a one"], [], True)]
        with self.assertRaises(SystemExit):
            ct.accept("cbs", truncated, 6, "Jeremy 2026-10-16 x", "names", tmp)
        with self.assertRaises(SystemExit):
            ct.accept("cbs", rows, 6, "no date here", "floor", tmp)


if __name__ == "__main__":
    unittest.main()
