import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scorecard", ROOT / "scripts/efficiency_scorecard.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        self.f = json.loads((ROOT / "tests/efficiency_scorecard_fixture.json").read_text())

    def receipt(self, f=None):
        f = f or self.f
        return s.milestones(f["pr"], f["timeline"], f["reviews"], f["checks"], [], f["tickets"])

    def test_exact_head_ci_and_approval_not_old_head(self):
        r = self.receipt()
        self.assertEqual(r["wait_h"]["open_to_ci_green"], 8)
        self.assertEqual(r["wait_h"]["open_to_merge_ready_proxy"], 9)
        self.assertEqual(r["wait_h"]["merge_ready_proxy_to_merge"], 3)
        self.assertEqual(r["wait_h"]["started_to_open"], 2)
        self.assertEqual(r["tickets"], ["JEG-100", "JEG-101"])

    def test_missing_current_head_approval_is_unknown(self):
        self.f["reviews"] = self.f["reviews"][:1]
        self.assertIsNone(self.receipt()["wait_h"]["open_to_merge_ready_proxy"])

    def test_missing_ci_is_unknown_not_zero(self):
        self.f["checks"] = []
        self.assertIsNone(self.receipt()["wait_h"]["open_to_ci_green"])

    def test_all_ci_contexts_must_be_green(self):
        self.f["checks"][-1]["conclusion"] = "failure"
        self.assertIsNone(self.receipt()["wait_h"]["open_to_ci_green"])

    def test_missing_linear_history_is_unknown(self):
        self.f["tickets"] = {}
        self.assertIsNone(self.receipt()["wait_h"]["started_to_open"])

    def test_percentiles_nearest_rank(self):
        result = s.stats(range(1, 11))
        self.assertEqual(result["p90_h"], 9)
        self.assertEqual(result["median_h"], 5.5)
        self.assertIsNone(s.stats([])["median_h"])

    def test_central_dates_and_dst(self):
        a, b = s.bounds(date(2026, 11, 1))
        self.assertEqual((b - a).total_seconds(), 25 * 3600)
        self.assertEqual(s.approval_window(s.stamp("2026-10-30T11:59:59Z")), "06")
        self.assertEqual(s.approval_window(s.stamp("2026-10-30T12:00:00Z")), "outside")
        self.assertEqual(s.approval_window(s.stamp("2026-11-02T22:30:00Z")), "16")

    def test_rest_pagination_is_not_truncated(self):
        api = s.GitHub()
        with patch.object(api, "get", side_effect=[list(range(100)), [100]]) as get:
            self.assertEqual(len(api.pages("repos/example/repo/pulls")), 101)
            self.assertEqual(get.call_args.kwargs["page"], 2)

    def test_disk_floor_before_any_write_or_api(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "absent"
            with patch.object(s, "disk", return_value={"free_kib": 3669999, "mount": "/fixture"}), patch.object(s.GitHub, "get") as api:
                self.assertEqual(s.main(["run", "--out", str(out)]), 3)
                self.assertFalse(out.exists())
                api.assert_not_called()
        with patch.object(s, "disk", return_value={"free_kib": s.FLOOR_KIB, "mount": "/fixture"}):
            self.assertEqual(s.guard()["free_kib"], s.FLOOR_KIB)

    def test_journal_dedup_and_no_text_leaks(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "job-journal.json"
            path.write_text(json.dumps({"events": [{"event_id": "one", "run_id": "r", "created_at": "2026-10-30T12:00:00Z", "status": "finished", "summary": "PRIVATE", "structured_result": {"question": "PRIVATE"}}]}))
            events, _ = s.journal_data([("claude", path), ("claude", path)])
            self.assertEqual(len(events), 1)
            self.assertNotIn("PRIVATE", json.dumps(events))

    def test_no_extrapolation_of_behind_main(self):
        rows = [{"repo": "example/repo", "pr": "42", "at": "2026-10-30T12:00:00Z", "behind_by": "2"},
                {"repo": "example/repo", "pr": "42", "at": "2026-10-30T12:05:00Z", "behind_by": "0"}]
        self.assertAlmostEqual(s.behind_hours(rows, "example/repo", 42, date(2026, 10, 30)), .0833)
        self.assertIsNone(s.behind_hours(rows, "example/repo", 42, date(2026, 10, 29)))
        rows[1]["at"] = "2026-10-31T12:05:00Z"
        self.assertIsNone(s.behind_hours(rows, "example/repo", 42, date(2026, 10, 30)))

    def test_repeated_ticket_refs_do_not_duplicate_pr_count(self):
        report = s.daily(date(2026, 10, 30), [self.f["pr"]], [self.receipt()], [], [], [], [], [], datetime(2026, 11, 1, tzinfo=timezone.utc))
        self.assertEqual(report["merged"], 1)
        self.assertEqual(report["waits"]["open_to_merge"]["n"], 1)
        self.assertIsNone(report["usage"]["muse"]["observed_run_ids"])
        self.assertIsNone(report["open_conflicts"])
        self.assertEqual(report["ticket_waits"]["JEG-100"]["waits"]["open_to_merge"]["n"], 1)

    def test_search_uses_merged_at_not_closed_at_and_exclusive_end(self):
        api = s.GitHub()
        row = {"number": 1, "title": "JEG-1", "created_at": "2026-10-29T00:00:00Z",
               "closed_at": "2026-10-31T00:00:00Z", "pull_request": {"merged_at": "2026-10-31T05:00:00Z"}}
        with patch.object(api, "get", return_value={"items": [row], "total_count": 1, "incomplete_results": False}):
            self.assertEqual(api.merged_search("example/repo", date(2026, 10, 30), date(2026, 10, 30)), [])
        row["pull_request"]["merged_at"] = "2026-10-30T05:00:00Z"
        with patch.object(api, "get", return_value={"items": [row], "total_count": 1, "incomplete_results": False}):
            self.assertEqual(len(api.merged_search("example/repo", date(2026, 10, 30), date(2026, 10, 30))), 1)

    def test_search_refuses_incomplete_results(self):
        api = s.GitHub()
        with patch.object(api, "get", return_value={"items": [], "total_count": 1, "incomplete_results": True}):
            with self.assertRaises(RuntimeError):
                api.merged_search("example/repo", date(2026, 10, 30), date(2026, 10, 30))

    def test_stale_activity_not_misrepresented_as_current(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root)
            activity = out / 'activity.json'
            activity.write_text(json.dumps({"at": "2026-10-01T00:00:00Z", "claude": {"running": 9}}))
            with patch.object(s, "resources", return_value={"at": "2026-10-31T00:00:00Z"}), patch.object(s, "guard"):
                s.take_sample(out, [], activity)
            self.assertIsNone(s.read_csv(out / 'bridge-load.csv')[0].get('running') or None)

    def test_append_daily_report_is_idempotent_on_fixture_run(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root)
            with patch.object(s, "guard", return_value={"free_kib": s.FLOOR_KIB}), patch.object(s.GitHub, "merged_search", return_value=[self.f['pr']]), patch.object(s, "saved_usage", return_value=[]), patch.object(s, "take_sample"):
                args = ['run', '--summary-only', '--start', '2026-10-30', '--end', '2026-10-30', '--out', str(out)]
                self.assertEqual(s.main(args), 0)
                self.assertEqual(s.main(args), 0)
            self.assertEqual(len(s.read_csv(out / 'daily.csv')), 1)

    def test_full_rest_flow_writes_exact_head_stage_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / 'out'
            linear = Path(root) / 'linear.json'
            linear.write_text(json.dumps(self.f['tickets']))
            def pages(endpoint, **kwargs):
                if endpoint.endswith('/timeline'):
                    return self.f['timeline']
                if endpoint.endswith('/reviews'):
                    return self.f['reviews']
                if endpoint.endswith('/check-runs'):
                    self.assertIn('/merged-head/', endpoint)
                    return self.f['checks']
                return []
            with patch.object(s, 'guard', return_value={'free_kib': s.FLOOR_KIB}), patch.object(s.GitHub, 'pulls', return_value=[self.f['pr']]), patch.object(s.GitHub, 'get', return_value=self.f['pr']), patch.object(s.GitHub, 'pages', side_effect=pages), patch.object(s, 'saved_usage', return_value=[]), patch.object(s, 'take_sample'):
                self.assertEqual(s.main(['run', '--start', '2026-10-30', '--out', str(out), '--linear', str(linear)]), 0)
            report = json.loads((out / '2026-10-30.json').read_text())
            self.assertEqual(report['waits']['started_to_open']['median_h'], 2)
            self.assertEqual(report['waits']['open_to_ci_green']['median_h'], 8)
            self.assertEqual(report['waits']['merge_ready_proxy_to_merge']['worst_h'], 3)


if __name__ == "__main__":
    unittest.main()
