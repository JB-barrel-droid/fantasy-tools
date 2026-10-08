"""Regression: C10 rendered-output checks must use the pipeline's canonical NFL
content week, never a naive days-since-kickoff count.

On 2026-09-30 the checkpoint builder computed
((now - 2026-09-03).days // 7) + 1 = Week 5 at 01:43 UTC, while the pipeline's
canonical content week (pipelines/nfl_week.py, Tuesday turnover) and the live
data were Week 4. Every source's C10 checkpoint false-redded on
week_designated/value_weeks.monday "expected 5". The builder now delegates to
nfl_week.current_nfl_week; these tests prove the guard against the broken state.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))

import build_pipeline_checkpoints as bpc  # noqa: E402
from nfl_week import current_nfl_week  # noqa: E402


class ExpectedContentWeekTest(unittest.TestCase):
    def test_boundary_date_matches_canonical_week(self):
        # 2026-10-01 is the exact date that exposed the defect: the naive
        # kickoff count produced 5 here; canonical content week is 4.
        self.assertEqual(4, bpc.expected_content_week(date(2026, 10, 1)))

    def test_always_matches_canonical_function(self):
        for d in (date(2026, 9, 8), date(2026, 9, 29), date(2026, 9, 30),
                  date(2026, 10, 1), date(2026, 10, 6), date(2026, 10, 7)):
            self.assertEqual(
                current_nfl_week(d), bpc.expected_content_week(d),
                f"mismatch on {d}",
            )

    def test_no_naive_kickoff_math_in_builder(self):
        # Broken-state guard: the old inline formula anchored a datetime to
        # the 2026-09-03 kickoff and counted days // 7. That exact code shape
        # must not reappear in the checkpoint builder.
        src = (PIPELINES / "build_pipeline_checkpoints.py").read_text(encoding="utf-8")
        self.assertNotIn("datetime(2026, 9, 3", src)
        self.assertNotIn("2026, 9, 3", src)


if __name__ == "__main__":
    unittest.main()
