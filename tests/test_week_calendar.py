"""One week rule (GAP-WEEK-CALENDARS, GAP-WATCHDOG-THU-WEEK).

pipelines/nfl_week.py defines the two week concepts once:
  content week (Tuesday flip) -- every data label;
  game week (Thursday flip)   -- only where games matter.
These tests pin the calendar, prove every Python caller delegates to it (no
second anchor date anywhere), and prove the savers / watchdog default to the
content week. Each guard is negative-tested against the broken state it names
(the Thursday-flip copy that lived in ops/watchdog/_common.py until 2026-10-08).
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))

import nfl_week  # noqa: E402
import _common  # noqa: E402

# A literal season anchor (the dates a week rule is computed from).
ANCHOR = re.compile(r"date\(\s*2026\s*,\s*9\s*,\s*(?:8|10)\s*\)|Date\.UTC\(\s*2026\s*,\s*8\s*,\s*(?:8|10)\s*\)")
# The only places allowed to hold the anchor: the module itself, and the JS /
# SQL ports (which cannot import Python; each is pinned to it by its own test:
# tests/test_source_freshness.py).
ALLOWED = {"pipelines/nfl_week.py", "app/trade-value-chart/assets/product-data.js"}
SCANNED = ("pipelines", "ops", "app/trade-value-chart/assets", "producers", "scripts", "tools")

# The broken state: origin/main's ops/watchdog/_common.py before this change.
BROKEN_COMMON = '''
def nfl_week(asof=None):
    asof = asof or today_ct()
    kickoff = date(2026, 9, 10)
    wk = (asof - kickoff).days // 7 + 1
    return max(1, min(22, wk))
'''


def calendar_copies(files: dict[str, str]) -> list[str]:
    return sorted(path for path, text in files.items()
                  if path not in ALLOWED and ANCHOR.search(text))


def tracked_sources() -> dict[str, str]:
    out = subprocess.check_output(["git", "ls-files", *SCANNED], cwd=ROOT, text=True)
    files = {}
    for rel in out.split():
        if rel.endswith((".py", ".js")) and (ROOT / rel).exists():
            files[rel] = (ROOT / rel).read_text(errors="replace")
    return files


class CalendarTest(unittest.TestCase):
    def test_content_week_flips_tuesday(self):
        self.assertEqual(nfl_week.content_week(date(2026, 10, 5)), 4)   # Mon
        self.assertEqual(nfl_week.content_week(date(2026, 10, 6)), 5)   # Tue
        self.assertEqual(nfl_week.content_week(date(2026, 9, 7)), 1)    # preseason
        self.assertIsNone(nfl_week.content_week_or_none(date(2026, 9, 7)))
        self.assertEqual(nfl_week.content_week(date(2027, 1, 30)), 18)  # capped
        self.assertEqual(nfl_week.content_week_start(5), date(2026, 10, 6))

    def test_game_week_flips_thursday(self):
        self.assertEqual(nfl_week.game_week(date(2026, 10, 7)), 4)      # Wed
        self.assertEqual(nfl_week.game_week(date(2026, 10, 8)), 5)      # Thu
        # Tue/Wed: game week trails content week by one; Thu..Mon they agree.
        for day, lag in ((6, 1), (7, 1), (8, 0), (12, 0)):
            d = date(2026, 10, day)
            self.assertEqual(nfl_week.content_week(d) - nfl_week.game_week(d), lag, d)

    def test_back_compat_name_is_content_week(self):
        for day in range(1, 60):
            d = date(2026, 9, 1).fromordinal(date(2026, 9, 1).toordinal() + day)
            self.assertEqual(nfl_week.current_nfl_week(d), nfl_week.content_week(d))

    def test_watchdog_wrappers_delegate(self):
        self.assertFalse(hasattr(_common, "nfl_week"),
                         "_common.nfl_week (Thursday flip) must not come back as a data label")
        for day in range(0, 120):
            d = date.fromordinal(date(2026, 9, 1).toordinal() + day)
            self.assertEqual(_common.content_week(d), nfl_week.content_week(d))
            self.assertEqual(_common.game_week(d), nfl_week.game_week(d))


class OneRuleTest(unittest.TestCase):
    def test_no_second_calendar_in_the_code(self):
        self.assertEqual(calendar_copies(tracked_sources()), [])

    def test_guard_catches_the_old_thursday_copy(self):
        files = tracked_sources()
        files["ops/watchdog/_common.py"] += BROKEN_COMMON
        self.assertEqual(calendar_copies(files), ["ops/watchdog/_common.py"])
        files["pipelines/check_deadlines.py"] += "\nstart = date(2026, 9, 8)\n"
        self.assertIn("pipelines/check_deadlines.py", calendar_copies(files))


class DefaultWeekTest(unittest.TestCase):
    """On a Tuesday the defaults must be the NEW week (content), not the
    game week that still says last week."""
    TUESDAY = date(2026, 10, 6)  # content week 5, game week 4

    def test_savers_and_pullers_default_to_content_week(self):
        import pull_cbs
        import pull_fantasypros
        with mock.patch.object(_common, "today_ct", lambda: self.TUESDAY):
            self.assertEqual(_common.content_week(), 5)
            self.assertEqual(pull_cbs.candidate_urls()[0], pull_cbs.SLUG % 5)
            self.assertEqual(pull_fantasypros.candidate_urls()[0], pull_fantasypros.candidate_urls(5)[0])
        for rel in ("pipelines/save_espn_cbs_references.py", "pipelines/save_usatoday_references.py",
                    "pipelines/save_fantasypros_references.py", "pipelines/save_fantasycalc_references.py",
                    "ops/watchdog/pull_usatoday.py", "ops/watchdog/pull_cbs.py",
                    "ops/watchdog/refresh_fantasycalc.py", "ops/watchdog/pull_watchdog.py"):
            text = (ROOT / rel).read_text()
            self.assertNotRegex(text, r"\bnfl_week\(\)", rel)
            self.assertIn("content_week", text, rel)

    def test_watchdog_import_health_takes_the_verifier_default(self):
        import pull_watchdog
        calls = []
        with mock.patch("subprocess.run", lambda cmd, **kw: calls.append(cmd)):
            pull_watchdog.refresh_import_health()
        self.assertEqual(calls, [["make", "import-health"]])


if __name__ == "__main__":
    unittest.main()
