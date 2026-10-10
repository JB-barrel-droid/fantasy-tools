"""Hermetic tests for pipelines/fidelity_sources/cbsros.py (JEG-480).

Synthetic HTML shaped like the live CBS rest-of-season pages (one table per
position page, a group-header row, then "abbr Tooltip" header cells, player
cells "<short> POS TEAM <full> POS TEAM") and a fake fetch. No network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from fidelity_sources import cbsros  # noqa: E402

import fidelity_pulse as fp  # noqa: E402

HEADINGS = {"QB": "Quarterbacks", "RB": "Running Backs", "WR": "Wide Receivers", "TE": "Tight Ends"}


def cell(short, full, pos, team):
    return (f'<td><span class="CellPlayerName--short">{short}</span> <span>{pos}</span> <span>{team}</span>\n'
            f'<span class="CellPlayerName--long"><a href="#">{full}</a> <span>{pos}</span> <span>{team}</span></span></td>')


def page(pos, header, rows, heading=None):
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join("<tr>" + cell(*r[:4]) + "".join(f"<td>{v}</td>" for v in r[4:]) + "</tr>" for r in rows)
    return (f"<html><head><title>Rest of Season Proj - {pos}</title></head><body>"
            f"<h2>{heading or HEADINGS[pos]}</h2><table><thead>"
            f"<tr><th></th><th></th><th>Receiving</th><th>Misc</th></tr><tr>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table><svg><title>ChevronDown</title></svg></body></html>")


QB_HEADER = ["Player", "gp Games Played", "att Pass Attempts", "td Touchdowns Passes", "att Rushing Attempts",
             "td Rushing Touchdowns", "fl Fumbles Lost", "fpts Fantasy Points", "fppg Fantasy Points Per Game"]
FLEX_HEADER = ["Player", "gp Games Played", "tgt Targets", "rec Receptions", "yds Receiving Yards",
               "fl Fumbles Lost", "fpts Fantasy Points", "fppg Fantasy Points Per Game"]


def live_like_pages():
    return {
        "QB": page("QB", QB_HEADER, [
            ("J. Allen", "Josh Allen", "QB", "BUF", "13", "379", "24", "100", "9", "3", "328.6", "25.3"),
            ("C. Keenum", "Case Keenum", "QB", "CHI", "1", "4", "0", "0", "0", "0", "0", "0.0"),
        ]),
        "RB": page("RB", FLEX_HEADER, [
            ("J. Gibbs", "Jahmyr Gibbs", "RB", "DET", "13", "73", "58", "514", "2", "264.7", "20.4"),
            ("A. Jones", "Aaron Jones", "RB", "MIN", "13", "40", "30", "250", "0", "103.4", "8.0"),
            ("X. Hurt", "Hurt Player", "RB", "NYG", "0", "0", "0", "0", "0", "0", "0.0"),
            ("A. Beck", "Andrew Beck", "FB", "NYJ", "13", "4", "3", "22", "0", "8.8", "0.7"),
        ]),
        "WR": page("WR", FLEX_HEADER, [
            ("J. Smith-Njigba", "Jaxon Smith-Njigba", "WR", "SEA", "13", "125", "91", "1323", "0", "202.8", "15.6"),
            ("M. Harrison", "Marvin Harrison Jr.", "WR", "ARI", "13", "90", "60", "800", "0", "--", "--"),
        ]),
        "TE": page("TE", FLEX_HEADER, [
            ("B. Bowers", "Brock Bowers", "TE", "LV", "13", "102", "73", "806", "0", "139.5", "10.7"),
        ]),
    }


def fake_fetch(pages, status=None):
    calls = []

    def fetch(url):
        calls.append(url)
        pos = url.split("/stats/")[1].split("/")[0]
        st = (status or {}).get(pos, 200)
        return st, pages.get(pos, "") if st == 200 else "", url

    fetch.calls = calls
    return fetch


class ContractTest(unittest.TestCase):
    def test_module_names(self):
        self.assertEqual(cbsros.SOURCE, "cbsros")
        self.assertEqual(cbsros.STORED_TABLE, "cbs_ros_projections")
        self.assertEqual(cbsros.SNAPSHOT_COLUMN, "cbs_snapshot_date")
        self.assertEqual(cbsros.CHART_DECIMALS, 3)
        cols = cbsros.STORED_SELECT.split(",")
        for c in ("player_key", "cbs_snapshot_date", "created_at", "ros_standard", "ros_half_ppr", "ros_ppr",
                  "per_game_standard", "per_game_half_ppr", "per_game_ppr"):
            self.assertIn(c, cols)


class ReadPublisherTest(unittest.TestCase):
    def setUp(self):
        self.fetch = fake_fetch(live_like_pages())
        self.out = cbsros.read_publisher(self.fetch)
        self.by_name = {r.name: r for r in self.out["rows"]}

    def test_reads_all_four_pages_politely_through_fetch(self):
        self.assertIsNone(self.out["error"])
        self.assertEqual(len(self.fetch.calls), 4)
        for pos in ("QB", "RB", "WR", "TE"):
            self.assertIn(f"/stats/{pos}/2026/restofseason/projections/nonppr/", " ".join(self.fetch.calls))
        self.assertIsNone(self.out["vintage"])
        self.assertEqual(self.out["dates"], {"dateModified": None})

    def test_every_scoring_from_fpts_plus_receptions(self):
        gibbs = self.by_name["Jahmyr Gibbs"]
        self.assertEqual((gibbs.pos, gibbs.team), ("RB", "DET"))
        self.assertEqual(gibbs.values, {"std|1": "264.7", "half|1": "293.7", "full|1": "322.7"})
        self.assertEqual(self.by_name["Aaron Jones"].values, {"std|1": "103.4", "half|1": "118.4", "full|1": "133.4"})
        self.assertEqual(self.by_name["Brock Bowers"].values, {"std|1": "139.5", "half|1": "176.0", "full|1": "212.5"})
        self.assertEqual(self.by_name["Jaxon Smith-Njigba"].values,
                         {"std|1": "202.8", "half|1": "248.3", "full|1": "293.8"})

    def test_qb_page_has_no_receptions_so_all_scorings_equal_fpts(self):
        self.assertEqual(self.by_name["Josh Allen"].values, {"std|1": "328.6", "half|1": "328.6", "full|1": "328.6"})
        self.assertEqual(self.by_name["Case Keenum"].values, {"std|1": "0", "half|1": "0", "full|1": "0"})

    def test_full_name_as_printed_and_position_from_the_page(self):
        self.assertIn("Marvin Harrison Jr.", " ".join(self.out["notes"]))  # no fpts -> skipped, reported
        beck = self.by_name["Andrew Beck"]
        self.assertEqual(beck.pos, "RB")
        self.assertTrue(any("Andrew Beck (FB)" in n for n in self.out["notes"]))
        self.assertNotIn("J. Gibbs", self.by_name)

    def test_skips_non_numeric_and_zero_game_rows(self):
        self.assertNotIn("Marvin Harrison Jr.", self.by_name)
        self.assertNotIn("Hurt Player", self.by_name)
        self.assertTrue(any("0 games" in n and "Hurt Player" in n for n in self.out["notes"]))
        self.assertEqual(len(self.out["rows"]), 7)

    def test_accepts_a_fetcher_object(self):
        class F:
            def __init__(self, fn):
                self.get = fn
        out = cbsros.read_publisher(F(fake_fetch(live_like_pages())))
        self.assertIsNone(out["error"])
        self.assertEqual(len(out["rows"]), 7)


class FailLoudTest(unittest.TestCase):
    def test_page_without_tables(self):
        pages = live_like_pages()
        pages["WR"] = "<html><body><h2>Wide Receivers</h2><p>Sorry, no data.</p></body></html>"
        out = cbsros.read_publisher(fake_fetch(pages))
        self.assertEqual(out["rows"], [])
        self.assertIn("WR", out["error"])

    def test_wrong_heading(self):
        pages = live_like_pages()
        pages["TE"] = pages["TE"].replace("Tight Ends", "Kickers")
        out = cbsros.read_publisher(fake_fetch(pages))
        self.assertEqual(out["rows"], [])
        self.assertIn("TE", out["error"])

    def test_header_without_fpts(self):
        pages = live_like_pages()
        pages["RB"] = pages["RB"].replace("fpts Fantasy Points", "pts Points")
        out = cbsros.read_publisher(fake_fetch(pages))
        self.assertEqual(out["rows"], [])
        self.assertIn("RB", out["error"])
        self.assertTrue(any("fpts" in n for n in out["notes"]))

    def test_http_error(self):
        out = cbsros.read_publisher(fake_fetch(live_like_pages(), status={"QB": 403}))
        self.assertEqual(out["rows"], [])
        self.assertIn("403", out["error"])


STORED_ROW = {"player_key": 101, "ros_standard": 103.4, "ros_half_ppr": 118.4, "ros_ppr": 133.4,
              "per_game_standard": 7.954, "per_game_half_ppr": 9.108, "per_game_ppr": 10.262, "gp": 13,
              "receptions": 30, "cbs_snapshot_date": "2026-10-08", "created_at": "2026-10-08T12:00:00Z"}


class StoredTest(unittest.TestCase):
    def test_stage1_ros_totals_match_the_parsed_page(self):
        stored = cbsros.stored_publisher_values(STORED_ROW)
        self.assertEqual(stored, {"std|1": 103.4, "half|1": 118.4, "full|1": 133.4})
        pub = {r.name: r for r in cbsros.read_publisher(fake_fetch(live_like_pages()))["rows"]}["Aaron Jones"]
        for grain, text in pub.values.items():
            self.assertTrue(fp.equal_after_rounding(text, stored[grain]), grain)

    def test_stage2_per_game_columns(self):
        self.assertEqual(cbsros.stored_chart_values(STORED_ROW, {}),
                         {"std|1": 7.954, "half|1": 9.108, "full|1": 10.262})

    def test_missing_values_are_absent_not_zero(self):
        row = {"player_key": 1, "ros_standard": 50.0, "ros_half_ppr": None, "per_game_standard": None}
        self.assertEqual(cbsros.stored_publisher_values(row), {"std|1": 50.0})
        self.assertEqual(cbsros.stored_chart_values(row, {}), {})


if __name__ == "__main__":
    unittest.main()
