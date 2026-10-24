"""JEG-1034: config/lineup_parameters.json's content_week follows the data.

content_week there is the last week with completed games (the bench-share
window starts the week after, derive_lineup_parameters.objective_window). A
"Week N" chart is posted after week N-1's games, so the newest served
content week N means content_week N-1. Nothing advanced it: it was set to 6
on 2026-10-16 and would have stayed at 6 once Week 8 charts were served.
make sync now advances it (never back) from data/history/index.json.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

import derive_lineup_parameters as dl  # noqa: E402

CONFIG = REPO / "config" / "lineup_parameters.json"
INDEX = REPO / "data" / "history" / "index.json"


def index_doc(*weeks):
    return {"content_week": max(weeks), "served": {f"s{i}": {"week": w} for i, w in enumerate(weeks)}}


class AdvanceContentWeek(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.config = self.dir / "lineup_parameters.json"
        shutil.copy2(CONFIG, self.config)
        self.index = self.dir / "index.json"

    def run_with(self, config_week, *served):
        text = self.config.read_text(encoding="utf-8")
        cfg = json.loads(text)
        self.config.write_text(text.replace(f'"content_week": {cfg["content_week"]}',
                                            f'"content_week": {config_week}'), encoding="utf-8")
        self.index.write_text(json.dumps(index_doc(*served)), encoding="utf-8")
        before = self.config.read_text(encoding="utf-8")
        week = dl.advance_content_week(self.index, self.config)
        return week, before, self.config.read_text(encoding="utf-8")

    def test_week_8_charts_move_the_window_to_week_8(self):
        week, before, after = self.run_with(6, 8, 7, 8)
        self.assertEqual(7, week)
        cfg, old = json.loads(after), json.loads(before)
        self.assertEqual(7, cfg["content_week"])
        # The stored default resolution moves with it (window starts at week 8) ...
        self.assertEqual(dl.resolve(cfg), cfg["resolved_default"])
        self.assertEqual([8, 17], cfg["resolved_default"]["window"])
        # ... and nothing else in the config changes.
        for key in set(old) - {"content_week", "resolved_default"}:
            self.assertEqual(old[key], cfg[key], key)

    def test_week_7_charts_keep_content_week_6(self):
        week, before, after = self.run_with(6, 7, 7)
        self.assertEqual(6, week)
        self.assertEqual(before, after)

    def test_never_moves_back(self):
        week, before, after = self.run_with(9, 7)
        self.assertEqual(9, week)
        self.assertEqual(before, after)

    def test_no_served_weeks_leaves_the_config(self):
        self.index.write_text(json.dumps({"served": {}}), encoding="utf-8")
        before = self.config.read_text(encoding="utf-8")
        self.assertIsNone(dl.advance_content_week(self.index, self.config))
        self.assertEqual(before, self.config.read_text(encoding="utf-8"))


class CommittedConfigIsCurrent(unittest.TestCase):
    def test_config_is_not_behind_the_served_data(self):
        served = [s["week"] for s in json.loads(INDEX.read_text(encoding="utf-8"))["served"].values()
                  if isinstance(s.get("week"), int)]
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertGreaterEqual(cfg["content_week"], max(served) - 1,
                                "config content_week is behind the served data; run make sync")


if __name__ == "__main__":
    unittest.main()
