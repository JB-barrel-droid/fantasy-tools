"""JEG-479: public.consolidated_values / api.player_values carry the current
week and every served source.

What went wrong (live, 2026-10-08): every chain write landed in week 4 --
build_consolidated_values took the week from the fixture's `value_weeks`,
a block nothing has updated since Week 4 -- and CBS ROS and Razzball were
never written: their combos carry their values under `values`, and the
builder read only `reindexed`.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_consolidated_values import build_rows, current_season_week, reconcile  # noqa: E402
from nfl_week import current_nfl_week  # noqa: E402

FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"


class ConsolidatedCurrent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detail = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_week_is_the_builds_content_week_not_value_weeks(self):
        detail = copy.deepcopy(self.detail)
        detail["built_at"] = "2026-10-08T21:01:19+00:00"   # Thursday of content week 5
        detail["value_weeks"] = {"espn": 4, "ecr": 4}       # the stale block
        self.assertEqual(current_season_week(detail), (2026, 5))
        detail["built_at"] = "2026-10-13T12:00:00+00:00"   # Tuesday: week 6 starts
        self.assertEqual(current_season_week(detail), (2026, 6))

    def test_current_fixture_week(self):
        from datetime import datetime
        built = datetime.fromisoformat(self.detail["built_at"].replace("Z", "+00:00"))
        rows, _ = build_rows(self.detail)
        self.assertEqual({r["week"] for r in rows}, {current_nfl_week(built.date())})

    def test_leg_priced_sources_are_written(self):
        rows, diag = build_rows(self.detail)
        by_source = {}
        for r in rows:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        for source in ("cbsros", "razzball", "espn", "cbs", "fantasycalc", "fantasypros", "usatoday"):
            self.assertGreater(by_source.get(source, 0), 100, source)
        self.assertEqual(reconcile(rows, self.detail, diag.get("review_no_player_key", ())), [])
        razz = next(r for r in rows if r["source"] == "razzball")
        self.assertIn(".values[", razz["detail_locator"])

    def test_reconcile_still_catches_a_wrong_value_in_a_values_cell(self):
        rows, diag = build_rows(self.detail)
        i = next(i for i, r in enumerate(rows) if r["source"] == "cbsros")
        rows[i] = dict(rows[i], value=rows[i]["value"] + 1)
        self.assertTrue(reconcile(rows, self.detail, diag.get("review_no_player_key", ())))


if __name__ == "__main__":
    unittest.main()
