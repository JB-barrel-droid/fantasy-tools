"""`build_source_value_lineage.py --merge` (JEG-35).

The lineage artifact is built locally (it needs gitignored raw snapshots and the
live-page scrape), so a session without them cannot rebuild it. Razzball, ESPN and
CBS ROS have no live page and no snapshot, so their blocks can be rebuilt from the
fixture alone and merged in. The merge must never disturb any other source, and must
refuse anything that would publish a degraded file.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import build_source_value_lineage as bsvl  # noqa: E402


def fixture(n=30):
    values = {f"player {i}": 70.0 - i for i in range(n)}
    native = {f"player {i}": 20.0 - i / 10 for i in range(n)}
    return {"built_at": "2026-10-01T00:00:00+00:00",
            "sources": {k: {"combos": {"half_12": {"values": values, "native": native}}}
                        for k in ("espn", "cbsros", "razzball")}}


EXISTING = {"generated_at": "OLD", "live_scraped_at": "OLD-LIVE",
            "sources": {"fantasypros": {"top25": [{"rank": 1, "player_key": "keep me"}]},
                        "usatoday": {"top25": [{"rank": 1, "player_key": "keep me too"}]}}}


class LineageMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data, self.out = self.tmp / "data.json", self.tmp / "lineage.json"
        self.saved = (bsvl.DATA_PATH, bsvl.OUT_PATH)
        bsvl.DATA_PATH, bsvl.OUT_PATH = str(self.data), str(self.out)
        self.data.write_text(json.dumps(fixture()))
        self.out.write_text(json.dumps(EXISTING))

    def tearDown(self):
        bsvl.DATA_PATH, bsvl.OUT_PATH = self.saved

    def merged(self):
        return json.loads(self.out.read_text())

    def test_adds_razzball_top25_and_leaves_everything_else_untouched(self):
        bsvl.merge_fixture_only(["razzball"])
        got = self.merged()
        rz = got["sources"]["razzball"]
        self.assertEqual(25, len(rz["top25"]))
        self.assertEqual("player 0", rz["top25"][0]["player_key"])
        self.assertEqual(70.0, rz["top25"][0]["chart_value"])
        self.assertEqual("2026-10-01T00:00:00+00:00", rz["built_from_fixture_at"])
        self.assertFalse(rz["live_scraped"])
        for key in ("generated_at", "live_scraped_at"):
            self.assertEqual(EXISTING[key], got[key])
        for src in ("fantasypros", "usatoday"):
            self.assertEqual(EXISTING["sources"][src], got["sources"][src])

    def test_rerun_replaces_the_block_instead_of_duplicating(self):
        bsvl.merge_fixture_only(["razzball"])
        first = self.merged()
        bsvl.merge_fixture_only(["razzball"])
        self.assertEqual(first, self.merged())

    def test_refuses_sources_that_need_live_pages_or_snapshots(self):
        before = self.out.read_text()
        for src in ("fantasypros", "usatoday", "fantasycalc", "cbs", "nonsense"):
            with self.assertRaises(SystemExit):
                bsvl.merge_fixture_only([src])
        self.assertEqual(before, self.out.read_text())

    def test_refuses_without_an_existing_artifact(self):
        self.out.unlink()
        with self.assertRaises(SystemExit):
            bsvl.merge_fixture_only(["razzball"])
        self.assertFalse(self.out.exists())

    def test_refuses_to_write_an_empty_block(self):
        doc = fixture()
        doc["sources"]["razzball"]["combos"]["half_12"]["values"] = {}
        self.data.write_text(json.dumps(doc))
        before = self.out.read_text()
        with self.assertRaises(SystemExit):
            bsvl.merge_fixture_only(["razzball"])
        self.assertEqual(before, self.out.read_text())


if __name__ == "__main__":
    unittest.main()
