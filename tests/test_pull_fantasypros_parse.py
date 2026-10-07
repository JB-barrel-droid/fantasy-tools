"""FantasyPros chart parse + saver inputs (2026-10-07).

The lottery puller that wrote fantasypros_trade_chart.csv is gone, so
ops/watchdog/pull_fantasypros.py now parses the chart itself. These pin the
parts that decide which numbers land in Supabase.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))
sys.path.insert(0, str(ROOT / "pipelines"))

import pull_fantasypros as fp  # noqa: E402


def _table(rows, extra=()):
    head = ["Name", "Team", "Value", "Change", *extra]
    out = "<table><tr>" + "".join(f"<td>{h}</td>" for h in head) + "</tr>"
    for r in rows:
        out += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return out + "</table>"


def _page(positions=("Quarterback", "Running Back", "Wide Receiver", "Tight End")):
    body = {
        "Quarterback": _table([["Josh Allen", "BUF", "29.1", "0", "69.5", "0"]],
                              extra=("2QB Value", "2QB Change")),
        "Running Back": _table([["D&#8217;Andre Swift", "CHI", "41.6", "0"]]),
        "Wide Receiver": _table([["Ja’Marr Chase", "CIN", "57.1", "0"]]),
        "Tight End": _table([["Brock Bowers", "LV", "28.0", "0", "33.1", "0.0"]],
                            extra=("TEP Value", "TEP Change")),
    }
    html = ('<meta property="article:published_time" content="2026-10-06 16:27:55">'
            "<h1>Fantasy Football Trade Value Chart: Week 5</h1>")
    for p in positions:
        html += f"<h2>{p} Fantasy Football Trade Value Chart</h2>" + body[p]
    return html + "<h2>More Articles</h2>"


PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB"},
    {"player_key": 2606, "full_name": "D'Andre Swift", "position": "RB"},
    {"player_key": 2730, "full_name": "Ja'Marr Chase", "position": "WR"},
    {"player_key": 1, "full_name": "Brock Bowers", "position": "TE"},
]


class ParseTablesTest(unittest.TestCase):
    def test_positions_from_headings_and_1qb_value(self):
        rows = fp.parse_tables(_page())
        self.assertEqual(rows[0], ("QB", "Josh Allen", "BUF", 29.1))  # not the 2QB 69.5
        self.assertEqual(rows[-1], ("TE", "Brock Bowers", "LV", 28.0))  # not TEP 33.1
        self.assertEqual([r[0] for r in rows], ["QB", "RB", "WR", "TE"])

    def test_missing_position_table_fails_closed(self):
        with self.assertRaises(RuntimeError):
            fp.parse_tables(_page(positions=("Quarterback", "Running Back", "Wide Receiver")))

    def test_published_date(self):
        self.assertEqual(fp.published_date(_page()), "2026-10-06")


class SaverInputsTest(unittest.TestCase):
    def test_curly_apostrophes_resolve(self):
        """Defect: FantasyPros prints D’Andre / Ja’Marr with curly quotes,
        which normalize differently from the players table's straight ones,
        so Swift (RB 41.6) and Chase (WR 57.1) silently dropped."""
        with tempfile.TemporaryDirectory() as d:
            clean, review = fp.write_saver_inputs(
                "u", _page(), 5, f"{d}/fp.csv", f"{d}/log.jsonl", players=PLAYERS)
            self.assertEqual(review, [])
            keys = {r["player_key"] for r in clean}
            self.assertIn(2606, keys)
            self.assertIn(2730, keys)
            with open(f"{d}/fp.csv", newline="") as fh:
                self.assertEqual(len(list(csv.DictReader(fh))), 4)
            log = [json.loads(l) for l in open(f"{d}/log.jsonl")]
            self.assertEqual(log[-1]["week"], 5)
            self.assertEqual(log[-1]["published"], "2026-10-06")

    def test_unknown_player_goes_to_review_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            clean, review = fp.write_saver_inputs(
                "u", _page(), 5, f"{d}/fp.csv", f"{d}/log.jsonl", players=PLAYERS[:3])
            self.assertEqual([r[1] for r in review], ["Brock Bowers"])
            self.assertNotIn(1, {r["player_key"] for r in clean})


if __name__ == "__main__":
    unittest.main()
