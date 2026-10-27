"""Unit tests for scripts/check_weekly_freshness.py (JEG-1163).

Tests only: the script under test is loaded from disk and never modified.
`sbclient` is stubbed in sys.modules before the module is loaded (the script
imports it at module level), and the clock is frozen by patching the loaded
module's `dt` with a stub whose `datetime.now()` returns a fixed aware
datetime. No test reads the real clock.
"""

import contextlib
import datetime as dt
import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_weekly_freshness.py"

# A Thursday inside game week 6 (season 2026). Fixed dates only.
TODAY = dt.date(2026, 10, 15)
MONDAY = dt.date(2026, 10, 12)
TUESDAY = dt.date(2026, 10, 13)
SEASON = 2026
WEEK = 6


class _Clock:
    """Holder for the frozen 'now' handed to the script under test."""

    now = None


class _StubDatetime(dt.datetime):
    """datetime whose now() is frozen; fromisoformat() still works."""

    @classmethod
    def now(cls, tz=None):  # noqa: ARG003 - tz accepted for signature parity
        if _Clock.now is None:
            raise AssertionError("clock not frozen for this test")
        return _Clock.now


class _StubDt:
    """Stand-in for the script's `datetime as dt` module."""

    datetime = _StubDatetime
    date = dt.date
    timezone = dt.timezone


def _load_script(sbclient_stub):
    """Load the script fresh with `sbclient_stub` bound to the sbclient import."""
    sys.modules["sbclient"] = sbclient_stub
    saved_path = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location(
            "check_weekly_freshness_under_test", SCRIPT_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
    return module


def _status_row(**overrides):
    """A healthy weekly_dashboard_status row; `overrides` replace fields."""
    row = {
        "has_current": True,
        "season": SEASON,
        "week": WEEK,
        "signal_count": 12,
        "run_created_at": TODAY.isoformat(),
        "bundle_built_at": TODAY.isoformat(),
        "current_run_count": 1,
    }
    row.update(overrides)
    return row


class CheckWeeklyFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.sbclient = mock.MagicMock()
        self.module = _load_script(self.sbclient)
        self.sbclient.get.return_value = [_status_row()]

    def _freeze(self, today):
        _Clock.now = dt.datetime.combine(today, dt.time(12, 0), tzinfo=dt.timezone.utc)

    def _run(self, today=TODAY, rows=None, environ=None):
        """Run main() with a frozen clock; return (exit_code, stdout)."""
        self._freeze(today)
        if rows is not None:
            self.sbclient.get.return_value = rows
        buf = io.StringIO()
        with mock.patch.object(self.module, "dt", _StubDt):
            if environ is None:
                with contextlib.redirect_stdout(buf):
                    code = self.module.main()
            else:
                with mock.patch.dict(os.environ, environ, clear=False):
                    with contextlib.redirect_stdout(buf):
                        code = self.module.main()
        return code, buf.getvalue()

    # --- expected_week ---------------------------------------------------

    def test_expected_week_accepts_prior_week_on_monday_and_tuesday(self):
        raw = self.module.nfl_week.game_week(MONDAY)
        self.assertEqual({raw - 1, raw}, self.module.expected_week(MONDAY))
        self.assertEqual({raw - 1, raw}, self.module.expected_week(TUESDAY))

    def test_expected_week_is_current_week_only_from_wednesday_on(self):
        for day in (
            dt.date(2026, 10, 14),  # Wed
            dt.date(2026, 10, 15),  # Thu
            dt.date(2026, 10, 16),  # Fri
            dt.date(2026, 10, 17),  # Sat
            dt.date(2026, 10, 18),  # Sun
        ):
            with self.subTest(day=day):
                raw = self.module.nfl_week.game_week(day)
                self.assertEqual({raw}, self.module.expected_week(day))
                self.assertNotIn(raw - 1, self.module.expected_week(day))

    def test_monday_published_prior_week_is_accepted(self):
        code, out = self._run(
            today=MONDAY,
            rows=[_status_row(week=self.module.nfl_week.game_week(MONDAY) - 1)],
        )
        self.assertEqual(0, code)
        self.assertIn("OK:", out)

    # --- main(): breaches -------------------------------------------------

    def test_all_clear_returns_zero_and_prints_ok(self):
        code, out = self._run()
        self.assertEqual(0, code)
        self.assertIn("OK:", out)
        self.assertIn(f"season {SEASON}", out)

    def test_missing_current_run_is_a_breach(self):
        code, out = self._run(rows=[_status_row(has_current=False)])
        self.assertEqual(1, code)
        self.assertIn("has_current=false", out)

    def test_wrong_week_is_a_breach(self):
        code, out = self._run(rows=[_status_row(week=WEEK + 1)])
        self.assertEqual(1, code)
        self.assertIn("not in expected", out)

    def test_wrong_season_is_a_breach(self):
        code, out = self._run(rows=[_status_row(season=SEASON - 1)])
        self.assertEqual(1, code)
        self.assertIn("not in expected", out)

    def test_run_created_at_older_than_eight_days_is_a_breach(self):
        code, out = self._run(
            rows=[_status_row(run_created_at=(TODAY - dt.timedelta(days=9)).isoformat())]
        )
        self.assertEqual(1, code)
        self.assertIn("9d old", out)

    def test_unparseable_run_created_at_is_a_breach(self):
        code, out = self._run(rows=[_status_row(run_created_at="not-a-timestamp")])
        self.assertEqual(1, code)
        self.assertIn("run_created_at missing/unparseable", out)

    def test_multiple_current_runs_is_a_breach(self):
        code, out = self._run(rows=[_status_row(current_run_count=2)])
        self.assertEqual(1, code)
        self.assertIn("current_run_count=2", out)

    # --- main(): warnings -------------------------------------------------

    def test_zero_signal_count_is_a_warning(self):
        code, out = self._run(rows=[_status_row(signal_count=0)])
        self.assertEqual(1, code)
        self.assertIn("0 signals", out)

    def test_stale_bundle_is_a_warning(self):
        code, out = self._run(
            rows=[_status_row(bundle_built_at=(TODAY - dt.timedelta(days=9)).isoformat())]
        )
        self.assertEqual(1, code)
        self.assertIn("stale bundle", out)

    # --- main(): transport and row-count failures -------------------------

    def test_sbclient_error_returns_one(self):
        self.sbclient.get.side_effect = RuntimeError("boom")
        code, out = self._run()
        self.assertEqual(1, code)
        self.assertIn("could not read api.weekly_dashboard_status", out)

    def test_zero_rows_returns_one(self):
        code, out = self._run(rows=[])
        self.assertEqual(1, code)
        self.assertIn("returned 0 rows", out)

    def test_two_rows_returns_one(self):
        code, out = self._run(rows=[_status_row(), _status_row()])
        self.assertEqual(1, code)
        self.assertIn("returned 2 rows", out)

    # --- GitHub Actions annotations ---------------------------------------

    def test_github_actions_annotation_is_printed_on_breach(self):
        code, out = self._run(
            rows=[_status_row(has_current=False)],
            environ={"GITHUB_ACTIONS": "true"},
        )
        self.assertEqual(1, code)
        self.assertIn("::error::", out)

    def test_github_actions_annotation_is_printed_on_warning(self):
        code, out = self._run(
            rows=[_status_row(signal_count=0)],
            environ={"GITHUB_ACTIONS": "true"},
        )
        self.assertEqual(1, code)
        self.assertIn("::warning::", out)

    def test_no_annotation_outside_github_actions(self):
        code, out = self._run(rows=[_status_row(has_current=False)])
        self.assertEqual(1, code)
        self.assertNotIn("::error::", out)


if __name__ == "__main__":
    unittest.main()
