"""Hermetic tests for the Draft Sharks and Fantasy Sharks fidelity-pulse readers (JEG-620, JEG-621)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "pipelines", ROOT / "pipelines" / "lib"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fidelity_pulse  # noqa: E402
from fidelity_sources import draftsharks, fantasysharks  # noqa: E402


class FakeFetch:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, **_):
        for needle, resp in self.pages.items():
            if url.endswith(needle) or (needle.endswith("com") and needle in url):
                return resp
        return 404, "", url


def ds_page(players, pad=draftsharks.MIN_BODY):
    body = '<html>"players":' + json.dumps(players) + "</html>"
    return body + " " * max(0, pad - len(body))


def ds_player(first, last, pos, no, half, one, team="BUF"):
    return {"first_name": first, "last_name": last, "fantasy_position": pos, "abbr": team,
            "dsValueRedraftNoPpr": no, "dsValueRedraftHalfPpr": half, "dsValueRedraftOnePpr": one}


class DraftSharksReaderTest(unittest.TestCase):
    def read(self, players, **kw):
        return draftsharks.read_publisher(FakeFetch({"draftsharks.com": (200, ds_page(players, **kw), "")}))

    def test_reads_each_scoring_and_skips_unpriced_and_non_skill(self):
        out = self.read([ds_player("Josh", "Allen", "QB", 80, 81.5, 83),
                         ds_player("Nobody", "Priced", "WR", 0, 0, 0),
                         ds_player("Some", "Kicker", "K", 5, 5, 5),
                         ds_player("Half", "Only", "RB", 0, 12, 0)])
        self.assertIsNone(out["error"])
        by = {r.name: r for r in out["rows"]}
        self.assertEqual({"Josh Allen", "Half Only"}, set(by))
        self.assertEqual({"std|1": "80", "half|1": "81.5", "full|1": "83"}, by["Josh Allen"].values)
        self.assertEqual({"half|1": "12"}, by["Half Only"].values)

    def test_fails_loudly(self):
        for body, why in (("x" * 10, "bot wall"), ('<html>no array</html>'.ljust(draftsharks.MIN_BODY), "no players"),
                          (ds_page([{"first_name": "A", "dsValueRedraftNoPpr": 1}]), "columns gone")):
            out = draftsharks.read_publisher(FakeFetch({"draftsharks.com": (200, body, "")}))
            self.assertTrue(out["error"], why)
            self.assertEqual([], out["rows"])
        out = draftsharks.read_publisher(FakeFetch({"draftsharks.com": (503, "", "")}))
        self.assertIn("503", out["error"])

    def test_stored_values_skip_nulls_and_chart_is_empty(self):
        row = {"ds_redraft_no_ppr": None, "ds_redraft_half_ppr": "81.5", "ds_redraft_one_ppr": 83}
        self.assertEqual({"half|1": 81.5, "full|1": 83.0}, draftsharks.stored_publisher_values(row))
        self.assertEqual({}, draftsharks.stored_chart_values(row, {}))


def fs_csv(rows):
    return "Rank,Player ID,Player Name,Team,Position,Pts\n" + "".join(
        f'{i},{pid},"{name}",BUF,{pos},{pts}\n' for i, (pid, name, pos, pts) in enumerate(rows, 1))


FS_PAGE = "<html>Fantasy Sharks projections. Last updated 10-15</html>"


class FantasySharksReaderTest(unittest.TestCase):
    def fetch(self, non, half, ppr, page=FS_PAGE):
        return FakeFetch({"csv=1&Segment=877&Position=97&scoring=1": (200, non, ""),
                          "csv=1&Segment=877&Position=97&scoring=18": (200, half, ""),
                          "csv=1&Segment=877&Position=97&scoring=2": (200, ppr, ""),
                          "projections.php?Segment=877&Position=97&scoring=18": (200, page, "")})

    def test_totals_per_scoring_name_swap_and_zero_means_unprojected(self):
        rows = [(1, "Allen, Josh", "QB", "200.5"), (2, "Idp, Guy", "LB", "90"), (3, "Zero, Pat", "WR", "0")]
        out = fantasysharks.read_publisher(self.fetch(fs_csv(rows), fs_csv(rows), fs_csv(rows)))
        self.assertIsNone(out["error"])
        self.assertEqual(["Josh Allen"], [r.name for r in out["rows"]])
        self.assertEqual({"std|1": "200.5", "half|1": "200.5", "full|1": "200.5"}, out["rows"][0].values)
        self.assertRegex(out["vintage"], r"^\d{4}-10-15$")

    def test_fails_loudly(self):
        good = fs_csv([(1, "Allen, Josh", "QB", "200")])
        out = fantasysharks.read_publisher(self.fetch("<html>login</html>", good, good))
        self.assertIn("not the projections CSV", out["error"])
        bad = "Rank,Player ID,Player Name,Team,Position\n1,1,\"A, B\",X,QB\n"
        self.assertIn("columns gone", fantasysharks.read_publisher(self.fetch(good, bad, good))["error"])
        self.assertIn("HTTP 404", fantasysharks.read_publisher(FakeFetch({}))["error"])

    def test_stored_values_are_totals_and_no_chart_conversion_exists(self):
        row = {"ros_total_non_ppr": 150.5, "ros_total_half_ppr": None, "ros_total_ppr": "170"}
        self.assertEqual({"std|1": 150.5, "full|1": 170.0}, fantasysharks.stored_publisher_values(row))
        self.assertEqual({}, fantasysharks.stored_chart_values(row, {}))


class RegistrationTest(unittest.TestCase):
    def test_registered_as_projection_sources_with_labels_and_no_chart_section(self):
        for s in ("draftsharks", "fantasysharks"):
            self.assertIn(s, fidelity_pulse.PROJECTIONS)
            self.assertIn(s, fidelity_pulse.SOURCES)
            self.assertIn(s, fidelity_pulse.LABEL)
            self.assertEqual(s, fidelity_pulse.projection_module(s).SOURCE)

    def test_a_source_absent_from_the_chart_cannot_be_green(self):
        """Neither source is wired into the chart; the chart stage must be red, never green."""
        for s in ("draftsharks", "fantasysharks"):
            mod = fidelity_pulse.projection_module(s)
            res, _ = fidelity_pulse.stage_projection_chart(
                s, mod, {"sources": {}}, None, None, None, None, None, None)
            self.assertEqual("red", res["status"], s)


if __name__ == "__main__":
    unittest.main()
