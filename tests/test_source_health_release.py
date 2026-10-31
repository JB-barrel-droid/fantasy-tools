"""The served-week health report and hourly alert agree after a week flip."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import check_reference_freshness as freshness  # noqa: E402
import source_lateness as lateness  # noqa: E402


class SourceHealthReleaseTest(unittest.TestCase):
    def test_late_before_stale_and_warning_only_after_cutoff(self):
        # CBS's label claims Week 8 but the published history matched its
        # inputs to Week 7. Both checks must judge the served Week 7.
        fixture = {"built_at": "2026-10-28T16:00:00Z",
                   "sources": {"cbs": {"week_designated": "Week 8"}}}
        history = {"fixture_built_at": fixture["built_at"],
                   "served": {"cbs": {"week": 7}}}
        served = lateness.served_weeks(history,
                                       {"source_weeks": {"cbs": {"served_week": 8}}})
        self.assertEqual(served["cbs"], 7)

        for now, expected in (
            (datetime(2026, 10, 28, 17, 1, tzinfo=timezone.utc), "lagging"),
            (datetime(2026, 10, 29, 17, 1, tzinfo=timezone.utc), "stale"),
        ):
            with self.subTest(expected=expected):
                row = freshness.make_source_week_item(
                    "cbs", fixture["sources"]["cbs"], None,
                    now.date(), now=now,
                    served={"served_week": served["cbs"], "basis": "history_index"})
                state = {"last_ok": True, "last_fp": "same", "acked_fp": "same",
                         "last_probe_at": (now - timedelta(hours=1)).isoformat(),
                         "acked_at": (now - timedelta(hours=2)).isoformat(),
                         "last_signals": {"week": 7}}
                alert = lateness.judge("cbs", state, served["cbs"], now)
                self.assertEqual(row["week_state"], expected)
                self.assertEqual(row["served_week"], 7)
                self.assertTrue(row["freshness_ok"])
                self.assertFalse(row["enforced"])
                self.assertTrue(alert["late"])
                self.assertIn("has not published its week 8 chart", alert["reasons"][0])


if __name__ == "__main__":
    unittest.main()
