"""JEG-1479: a FantasyCalc pull on Monday evening ET is accepted on either clock.

A pull on Monday evening ET is already Tuesday in UTC, the day the content
week flips. The FantasyCalc writer has labelled such pulls on both clocks:
2026-10-27T01:05Z (Mon Oct 26 21:05 ET) as week 8, which is the UTC week, and
2026-11-03T03:05Z (Mon Nov 2 22:05 ET) as week 8, which is the New York week.
build_week_history.evidence_week checked only the UTC week, raised
"fantasycalc: week column 8 but pulled in week 9", and the chain's week
history capture failed on every run after the Week 8 -> 9 flip. Without
Week 9 history the engine and the Python reference disagreed on all seven
sources, every source was held, and the board stayed on Week 8.
"""
from __future__ import annotations

import json
import tempfile
from unittest.mock import patch
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_week_history as H  # noqa: E402


def _fc(week, pulled_at):
    return {"source": "fantasycalc", "week_evidence": {
        "rule": "week_column_pull", "week_column": week, "pulled_at": pulled_at}}


class FantasyCalcPullClockTest(unittest.TestCase):
    def test_new_york_labelled_monday_night_pull(self):
        # The production row that blocked Week 9 (bake fcwk8_2026-11-03t0305_v1),
        # in the shapes PostgREST and the snapshot files carry.
        for stamp in ("2026-11-03 03:05:25+00", "2026-11-03T03:05:25+00:00",
                      "2026-11-03T03:05:25Z"):
            with self.subTest(stamp=stamp):
                self.assertEqual(H.evidence_week(_fc(8, stamp)), 8)

    def test_utc_labelled_monday_night_pull_still_accepted(self):
        # bake fcwk8_2026-10-27t0105_v1: labelled on the UTC calendar.
        self.assertEqual(H.evidence_week(_fc(8, "2026-10-27 01:05:23+00")), 8)

    def test_ordinary_pulls_unchanged(self):
        self.assertEqual(H.evidence_week(_fc(9, "2026-11-03 10:05:34+00")), 9)
        self.assertEqual(H.evidence_week(_fc(8, "2026-11-02 13:17:28+00")), 8)

    def test_real_mislabels_still_fail_closed(self):
        for week, stamp in ((8, "2026-11-03 10:05:34+00"),   # Tuesday morning ET, labelled 8
                            (9, "2026-11-02 13:17:28+00"),   # Monday midday, labelled 9
                            (7, "2026-11-03 03:05:25+00"),   # neither clock says 7
                            (0, "2026-11-03 03:05:25+00")):
            with self.subTest(week=week, stamp=stamp), self.assertRaises(H.HistoryError):
                H.evidence_week(_fc(week, stamp))

    def test_other_rules_keep_the_utc_date(self):
        self.assertEqual(H.week_of_day("2026-11-03 03:05:25+00"), 9)
        self.assertEqual(H.week_of_day("2026-11-02"), 8)


class CaptureProvenanceTest(unittest.TestCase):
    def rows(self, week=8, stamp="2026-11-03 03:05:25+00"):
        return [{"source": "fantasycalc", "week": week, "pulled_at": stamp,
                 "bake_id": "fcwk8_2026-11-03t0305_v1", "scoring": scoring,
                 "player_key": 1, "native_value": 20} for scoring in H.SCORINGS]

    def test_capture_replays_monday_night_bake(self):
        entries = H.published_entries_from_rows(self.rows())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["week"], 8)
        self.assertEqual(entries[0]["bake_ids"], ["fcwk8_2026-11-03t0305_v1"])

    def test_candidate_construction_rejects_fractional_week_before_grouping(self):
        for week in (8.5, "8.5", True, 8.0):
            with self.subTest(week=week), self.assertRaisesRegex(
                    H.HistoryError, "week column must be an integer"):
                H.published_entries_from_rows(self.rows(week))

    def test_true_mislabel_names_bake_timestamp_calendars_and_rule(self):
        with self.assertRaises(H.HistoryError) as caught:
            H.published_entries_from_rows(self.rows(7))
        message = str(caught.exception)
        for text in ("fcwk8_2026-11-03t0305_v1", "2026-11-03 03:05:25+00",
                     "UTC", "America/New_York", "2026-11-02", "'week': 8",
                     "'week': 9", "accepted_rule=week_column_pull"):
            self.assertIn(text, message)

    def test_missing_offset_and_malformed_timestamp_rejected(self):
        for stamp in ("2026-11-03", "2026-11-03T03:05:25", "2026-11-03 invalid", None):
            with self.subTest(stamp=stamp), self.assertRaises(H.HistoryError):
                H.published_entries_from_rows(self.rows(stamp=stamp))

    def test_offset_timestamp_uses_actual_utc_calendar(self):
        # Local Tuesday date is still Monday on both accepted clocks.
        with self.assertRaises(H.HistoryError):
            H.evidence_week(_fc(9, "2026-11-03T00:05:00+02:00"))
        self.assertEqual(H.evidence_week(_fc(8, "2026-11-03T00:05:00+02:00")), 8)

    def test_failed_capture_has_status_and_does_not_write_history(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            target = Path(tmp)
            dump = target / "dump.json"
            status = target / "status.json"
            dump.write_text(json.dumps({"published": self.rows(7), "projections": []}))
            with patch.object(H, "rows_from_dump", return_value=(self.rows(7), [])):
                self.assertEqual(H.main(["--supabase-dump", str(dump), "--dir", str(target / "history"),
                                         "--status-file", str(status)]), 1)
            record = json.loads(status.read_text())
            self.assertFalse(record["success"])
            self.assertEqual(record["stage"], "history-capture")
            self.assertIn("fcwk8_2026-11-03t0305_v1", record["detail"])
            self.assertFalse((target / "history").exists())

    def test_capture_io_failure_is_first_class_and_success_clears_status(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            status = Path(tmp) / "status.json"
            with patch.object(H, "run_capture", side_effect=OSError("capture input unavailable")):
                self.assertEqual(H.main(["--status-file", str(status)]), 1)
            record = json.loads(status.read_text())
            self.assertEqual(record["error_type"], "OSError")
            self.assertEqual(record["detail"], "capture input unavailable")
            with patch.object(H, "run_capture", return_value=0):
                self.assertEqual(H.main(["--status-file", str(status)]), 0)
            self.assertTrue(json.loads(status.read_text())["success"])

    def test_workflow_stops_on_both_capture_failures(self):
        text = (ROOT / ".github/workflows/rebuild-chain.yml").read_text()
        for name in ("Capture week history", "Capture week history after promotion"):
            step = text.split("      - name: " + name + "\n", 1)[1].split("      - name:", 1)[0]
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("||", step)
            self.assertIn("--status-file output/week-history-capture-status.json", step)


if __name__ == "__main__":
    unittest.main()
