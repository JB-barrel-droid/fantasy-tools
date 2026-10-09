"""Hermetic tests for the Razzball fidelity-pulse reader (JEG-480)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "pipelines", ROOT / "pipelines" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fidelity_sources import razzball  # noqa: E402

STAMP = ('<p>Updated:  <abbr class="entry-date" title="2026-10-08 06:44:22 PM">'
         '2026-10-08 06:44:22 PM EST</abbr> | Maintained by Rudy</p>')
SIDEBAR = ("<table><tr><th>#</th><th>Name</th><th>Team</th><th>Pos</th><th>PTS/G</th></tr>"
           "<tr><td></td><td>James Houston</td><td>DAL</td><td>LB</td><td>0.7</td></tr>"
           "<tr><td></td><td>A</td><td>B</td><td>C</td><td>1</td></tr>"
           "<tr><td></td><td>D</td><td>E</td><td>F</td><td>2</td></tr></table>")


def qb_page(stamp=STAMP):
    return (f"<html><head><title>2026 QB Fantasy Football Projections &amp; Rankings | Razzball</title></head>"
            f"<body><h1>2026 QB Fantasy Football Projections</h1>{stamp}"
            "<table><tr><th>#</th><th>Name</th><th>Team</th><th>Games</th><th>STD PTS</th><th>STD PPG</th></tr>"
            "<tr><td></td><td><a href='/p/1'>Josh Allen</a></td><td>BUF</td><td>13</td><td>279.6</td><td>21.5</td></tr>"
            "<tr><td></td><td>Joe Burrow</td><td>CIN</td><td>26</td><td>452.8</td><td>17.4</td></tr>"
            "<tr><td></td><td>Hurt Guy</td><td>NYJ</td><td>0</td><td>0</td><td>-</td></tr>"
            f"</table>{SIDEBAR}</body></html>")


def skill_page(pos, rows, stamp=STAMP, year=2026):
    head = ("<tr><th>#</th><th>Name</th><th>Team</th><th>G</th><th>STD PTS</th>"
            "<th>STD PPG</th><th>1/2 PPR PPG</th><th>PPR PPG</th></tr>")
    body = "".join("<tr><td></td>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f"<html><head><title>{year} {pos} Fantasy Football Projections | Razzball</title></head>"
            f"<body><h1>{year} {pos} Fantasy Football Projections</h1>{stamp}"
            f"<table>{head}{body}</table>{SIDEBAR}</body></html>")


PAGES = {
    "qb": qb_page(),
    "rb": skill_page("RB", [("Aaron Jones", "MIN", "13", "139.1", "10.7", "12.1", "13.4"),
                            ("Jahmyr Gibbs", "DET", "13", "256.1", "19.7", "21.9", "24.2")]),
    "wr": skill_page("WR", [("Puka Nacua", "LAR", "13", "175.4", "13.5", "17.2", "20.9"),
                            ("No Proj", "FA", "13", "0", "N/A", "", "1.0")], year=2025),
    "te": skill_page("TE", [("Brock Bowers", "LV", "13", "118.0", "9.1", "12.1", "15.2")],
                     stamp=STAMP.replace("2026-10-08 06:44:22 PM EST", "2026-10-07 11:05:00 AM EST")),
}


class FakeFetch:
    def __init__(self, pages, status=None):
        self.pages = pages
        self.status = status or {}
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        pos = url.split("projections-")[1].split("-")[0]
        return self.status.get(pos, 200), self.pages.get(pos, ""), url


def by_name(result):
    return {r.name: r for r in result["rows"]}


class ReadPublisher(unittest.TestCase):
    def test_reads_every_scoring_as_printed(self):
        res = razzball.read_publisher(FakeFetch(PAGES))
        self.assertIsNone(res["error"])
        rows = by_name(res)
        self.assertEqual(rows["Aaron Jones"].values, {"std|1": "10.7", "half|1": "12.1", "full|1": "13.4"})
        self.assertEqual((rows["Aaron Jones"].pos, rows["Aaron Jones"].team), ("RB", "MIN"))
        self.assertEqual(rows["Brock Bowers"].pos, "TE")
        self.assertEqual(rows["Puka Nacua"].values["full|1"], "20.9")

    def test_qb_page_prints_std_only_and_the_rule_fills_half_and_full(self):
        rows = by_name(razzball.read_publisher(FakeFetch(PAGES)))
        self.assertEqual(rows["Josh Allen"].values, {"std|1": "21.5", "half|1": "21.5", "full|1": "21.5"})
        self.assertEqual(rows["Josh Allen"].pos, "QB")

    def test_doubled_games_do_not_change_the_printed_ppg(self):
        # Burrow's Games (26) and STD PTS (452.8) are doubled; STD PPG 17.4 is read verbatim.
        res = razzball.read_publisher(FakeFetch(PAGES))
        self.assertEqual(by_name(res)["Joe Burrow"].values["std|1"], "17.4")
        self.assertFalse(any("disagrees" in n for n in res["notes"]))

    def test_non_numeric_cells_are_skipped_not_zeroed(self):
        res = razzball.read_publisher(FakeFetch(PAGES))
        rows = by_name(res)
        self.assertEqual(rows["Hurt Guy"].values, {})
        self.assertEqual(rows["No Proj"].values, {"full|1": "1.0"})
        self.assertTrue(any("WR: 1 rows" in n for n in res["notes"]))

    def test_sidebar_table_is_ignored(self):
        names = {r.name for r in razzball.read_publisher(FakeFetch(PAGES))["rows"]}
        self.assertNotIn("James Houston", names)
        self.assertEqual(len(names), 8)

    def test_vintage_is_oldest_stamp_and_modified_is_newest(self):
        res = razzball.read_publisher(FakeFetch(PAGES))
        self.assertEqual(res["vintage"], "2026-10-07")
        self.assertEqual(res["dates"]["dateModified"], "2026-10-08T18:44:22-05:00")
        self.assertTrue(any("different Updated stamps" in n for n in res["notes"]))

    def test_fetches_the_four_position_pages(self):
        fetch = FakeFetch(PAGES)
        razzball.read_publisher(fetch)
        self.assertEqual(fetch.urls, [razzball.URL.format(pos=p) for p in ("qb", "rb", "wr", "te")])

    def test_missing_projection_table_fails_loudly(self):
        pages = dict(PAGES, rb=f"<html><h1>2026 RB Projections</h1>{STAMP}{SIDEBAR}</html>")
        res = razzball.read_publisher(FakeFetch(pages))
        self.assertEqual(res["rows"], [])
        self.assertIn("no table with both a Name and a STD PPG column", res["error"])

    def test_missing_ppr_columns_on_a_skill_page_fails_loudly(self):
        page = PAGES["wr"].replace("<th>1/2 PPR PPG</th>", "<th>Half</th>")
        res = razzball.read_publisher(FakeFetch(dict(PAGES, wr=page)))
        self.assertEqual(res["rows"], [])
        self.assertIn("expected STD, 1/2 PPR and PPR PPG columns", res["error"])

    def test_page_for_another_position_fails_loudly(self):
        res = razzball.read_publisher(FakeFetch(dict(PAGES, te=PAGES["wr"])))
        self.assertEqual(res["rows"], [])
        self.assertIn("TE page says it lists WR", res["error"])

    def test_http_error_fails_loudly(self):
        res = razzball.read_publisher(FakeFetch(PAGES, status={"wr": 403}))
        self.assertEqual(res["rows"], [])
        self.assertIn("HTTP 403", res["error"])

    def test_missing_stamp_is_a_note_not_a_failure(self):
        pages = {k: v.replace("Updated:", "Changed") for k, v in PAGES.items()}
        res = razzball.read_publisher(FakeFetch(pages))
        self.assertIsNone(res["error"])
        self.assertIsNone(res["vintage"])
        self.assertEqual(sum("no 'Updated" in n for n in res["notes"]), 4)


class StoredValues(unittest.TestCase):
    ROW = {"player_key": 7, "pos": "RB", "per_game_standard": 10.7, "per_game_half_ppr": "12.1",
           "per_game_ppr": 13.4, "razzball_snapshot_date": "2026-10-08", "created_at": "2026-10-08T23:00:00Z"}

    def test_stage1_is_the_stored_per_game_columns(self):
        self.assertEqual(razzball.stored_publisher_values(self.ROW),
                         {"std|1": 10.7, "half|1": 12.1, "full|1": 13.4})

    def test_stage2_chart_native_is_the_same_per_game_value(self):
        self.assertEqual(razzball.stored_chart_values(self.ROW, {}),
                         {"std|1": 10.7, "half|1": 12.1, "full|1": 13.4})
        self.assertEqual(razzball.CHART_DECIMALS, 1)

    def test_returns_only_what_the_row_carries(self):
        self.assertEqual(razzball.stored_publisher_values({"per_game_standard": 21.5, "per_game_ppr": None}),
                         {"std|1": 21.5})

    def test_select_names_the_contract_columns(self):
        cols = razzball.STORED_SELECT.split(",")
        for c in ("player_key", razzball.SNAPSHOT_COLUMN, "created_at", "per_game_standard",
                  "per_game_half_ppr", "per_game_ppr"):
            self.assertIn(c, cols)


if __name__ == "__main__":
    unittest.main()
