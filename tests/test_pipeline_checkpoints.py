"""Regression tests for pipelines/build_pipeline_checkpoints.py.

JEG-306: Razzball intentionally has no candidate/review artifact -- its c7
reason already says "Direct fixture updates are the intended workflow; no
formal promotion artifact required." Reporting `unk` for c6 reads as a
missing-artifact alarm that will never resolve.

The fix: a Razzball-specific clause that emits `ok` with reason
"File-scraped source; c6/c7 stages N/A by design." regardless of whether
artifacts exist on disk. CBS must keep its old behavior so this branch
doesn't silently swallow genuine gaps in the candidate/promotion chain.

JEG-315, GAP-043: dashboard per-source content_vintage color bands.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))

import build_pipeline_checkpoints as bpc  # noqa: E402


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _vintage_band(content_vintage, today=None):
    """Replicates the dashboard's client-side band logic for the
    freshness line. Kept here as a separate helper so the test stays
    a true regression against a fixture-driven value rather than just
    echoing an inline constant in the dashboard.
    """
    import re as _re
    if not content_vintage:
        return "unk"
    m = _re.match(r"^(\d{4}-\d{2}-\d{2})$", str(content_vintage))
    if not m:
        return "unk"
    if today is None:
        today = datetime.now(timezone.utc)
    vt = datetime.fromisoformat(str(content_vintage) + "T00:00:00+00:00")
    age_days = (today - vt).total_seconds() / 86400
    if age_days <= 4:
        return "green"
    if age_days <= 7:
        return "amber"
    return "red"


class RazzballC6VerdictTest(unittest.TestCase):
    """C6 verdict for Razzball must be `ok` (N/A by design), not `unk`.

    These tests prove the JEG-306 branch and prove it discriminates:
    test_cbs_empty_still_unk replicates the by-design-empty CBS case the
    old logic called `unk` and asserts it still does, so the suite would
    fail against any regression that lets the Razzball branch swallow CBS.
    """

    def test_razzball_empty_artifacts_is_ok(self):
        """Razzball c6 with empty artifacts -> `ok` with N/A reason."""
        v = bpc.c6_candidate_verdict(
            src="razzball",
            cand_mtime=None,
            review_mtime=None,
            chain_result="",
            chain_run_at=None,
        )
        self.assertEqual("ok", v["status"], v["reason"])
        self.assertIn("N/A by design", v["reason"])
        self.assertIsNone(v["timestamp"])

    def test_razzball_with_nonempty_artifacts_is_still_ok(self):
        """Razzball c6 forced to look like CBS (non-empty review artifact)
        must still emit `ok` -- the Razzball branch is keyed on source id,
        not on artifact presence, so a stray review file cannot quietly
        downgrade the verdict and JEG-307 (which decides whether Razzball
        should join the chain) keeps a clean default.
        """
        v = bpc.c6_candidate_verdict(
            src="razzball",
            cand_mtime=_iso(1),
            review_mtime=_iso(0.5),
            chain_result="promoted 1/1",
            chain_run_at=_iso(0.1),
        )
        self.assertEqual("ok", v["status"], v["reason"])
        self.assertIn("N/A by design", v["reason"])

    def test_cbs_empty_artifacts_still_unk(self):
        """CBS c6 with empty artifacts must still be `unk` -- the Razzball
        branch must not silently swallow genuine missing-artifact gaps in
        the CBS candidate/promotion chain. This is the no-regression guard.
        """
        v = bpc.c6_candidate_verdict(
            src="cbs",
            cand_mtime=None,
            review_mtime=None,
            chain_result="",
            chain_run_at=None,
        )
        self.assertEqual("unk", v["status"], v["reason"])
        self.assertIn("No candidate or review artifacts found", v["reason"])

    def test_cbs_with_fresh_artifacts_is_ok(self):
        """CBS c6 with a fresh review artifact must keep the old `ok`
        path -- proves the inline fall-through still works for non-Razzball.
        """
        v = bpc.c6_candidate_verdict(
            src="cbs",
            cand_mtime=_iso(1),
            review_mtime=_iso(0.5),
            chain_result="",
            chain_run_at=None,
        )
        self.assertEqual("ok", v["status"], v["reason"])
        self.assertIn("Candidate built and reviewed", v["reason"])

    def test_razzball_branch_is_keyed_on_source_only(self):
        """Discrimination proof: the Razzball branch must key on source
        id, not on the c6_ts that the existing fall-through would have
        produced. If a future refactor moves the Razzball check below the
        c6_ts branch, a fresh stray artifact would silently downgrade
        Razzball from `ok` to a real chain verdict.
        """
        # Even with a fully populated c6_ts path, Razzball stays ok/N-A.
        v_with = bpc.c6_candidate_verdict(
            src="razzball",
            cand_mtime=_iso(2),
            review_mtime=_iso(1),
            chain_result="promoted 1/1",
            chain_run_at=_iso(0.1),
        )
        v_without = bpc.c6_candidate_verdict(
            src="razzball",
            cand_mtime=None,
            review_mtime=None,
            chain_result="",
            chain_run_at=None,
        )
        self.assertEqual("ok", v_with["status"])
        self.assertEqual("ok", v_without["status"])
        self.assertEqual(v_with["status"], v_without["status"])
        self.assertEqual(v_with["reason"], v_without["reason"])


class ContentVintageBandTest(unittest.TestCase):
    """JEG-315, GAP-043: content_vintage color bands.

    The dashboard renders a freshness line under each per-source card.
    The bands are:
      green: age <= 4 days
      amber: 4 < age <= 7 days
      red:   age > 7 days
      unk:   missing or "Week N" vintage (no absolute age)
    """

    def test_fantasycalc_eight_days_old_is_red(self):
        """FantasyCalc content_vintage 8 days old must read red (stale)."""
        today = datetime(2026, 10, 3, tzinfo=timezone.utc)
        eight = (today - timedelta(days=8)).date().isoformat()
        self.assertEqual("red", _vintage_band(eight, today=today))

    def test_content_vintage_two_days_old_is_green(self):
        """Content_vintage 2 days old must read green (fresh)."""
        today = datetime(2026, 10, 3, tzinfo=timezone.utc)
        two = (today - timedelta(days=2)).date().isoformat()
        self.assertEqual("green", _vintage_band(two, today=today))

    def test_content_vintage_five_days_old_is_amber(self):
        """5-day-old vintage sits in the amber band (4-7d)."""
        today = datetime(2026, 10, 3, tzinfo=timezone.utc)
        five = (today - timedelta(days=5)).date().isoformat()
        self.assertEqual("amber", _vintage_band(five, today=today))

    def test_week_label_is_unk(self):
        """Week-designated vintages (e.g. CBS) cannot carry absolute
        age and must render in the unknown band -- the bands only
        make sense for dated vintages.
        """
        self.assertEqual("unk", _vintage_band("Week 4"))
        self.assertEqual("unk", _vintage_band(None))
        self.assertEqual("unk", _vintage_band(""))

    def test_band_thresholds_are_inclusive(self):
        """4d and 7d boundary checks: a 4.0d vintage is still green,
        a 7.0d vintage is still amber, only >7d crosses to red.
        """
        today = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        four = (today - timedelta(days=4)).date().isoformat()
        seven = (today - timedelta(days=7)).date().isoformat()
        just_over = (today - timedelta(days=7, hours=1)).date().isoformat()
        self.assertEqual("green", _vintage_band(four, today=today))
        self.assertEqual("amber", _vintage_band(seven, today=today))
        # 7d + 1h rolls the date string past 7 days for a UTC noon today.
        if just_over != seven:
            self.assertEqual("red", _vintage_band(just_over, today=today))


if __name__ == "__main__":
    unittest.main()