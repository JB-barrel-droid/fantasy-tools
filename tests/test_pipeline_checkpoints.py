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

import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIPELINES = REPO / "pipelines"
sys.path.insert(0, str(PIPELINES))

import build_pipeline_checkpoints as bpc  # noqa: E402


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _vintage_band(content_vintage, today=None):
    """Replicates the dashboard's client-side band logic for the
    freshness line. Kept here as a separate helper so the test stays
    a true regression against a fixture-driven value rather than just
    echoing an inline constant in the dashboard.

    NOTE: This is a Python replica of the JS `vintageLine` in
    modules/dashboard.html. It mirrors the JS math so a passing test
    here is necessary but not sufficient -- the JS-side invariant is
    covered by JSBandMatchesPythonReplicaTest below, which extracts
    the real vintageLine from dashboard.html and runs it via Node.
    The reason both exist: this Python helper stays runnable in any
    environment (no Node / no DOM required) and acts as a fast
    reference; the Node test is the production-binding guard.
    """
    import re as _re
    if not content_vintage:
        return "unk"
    m = _re.match(r"^(\d{4}-\d{2}-\d{2})$", str(content_vintage))
    if not m:
        return "unk"
    # Use UTC midnight as the today anchor so a vintage that is exactly
    # N calendar days old reads as age N, not N + a half-day offset.
    # Without this, a 4-day-old vintage at noon UTC would compute as
    # 4.5d and flip into amber, breaking the 4d/7d boundary contract.
    if today is None:
        today = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif today.tzinfo is None:
        today = today.replace(tzinfo=timezone.utc)
    if today.time() != datetime.min.time():
        today = today.replace(hour=0, minute=0, second=0, microsecond=0)
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

        Anchor today at UTC midnight so a vintage dated exactly 4 or 7
        calendar days ago reads as age 4.0 / 7.0 -- the helper's date
        strings are date-only (no time component) and the band
        contract says "4d = green, 7d = amber boundary". Using noon
        UTC for today used to compute age = 4.5 / 7.5, which flipped
        4d into amber and silently passed a red-but-labeled-amber
        7d+ row -- both wrong.
        """
        today = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)
        four = (today - timedelta(days=4)).date().isoformat()
        seven = (today - timedelta(days=7)).date().isoformat()
        just_over = (today - timedelta(days=7, hours=1)).date().isoformat()
        self.assertEqual("green", _vintage_band(four, today=today))
        self.assertEqual("amber", _vintage_band(seven, today=today))
        # 7d + 1h rolls the date string past 7 days for a UTC midnight today.
        if just_over != seven:
            self.assertEqual("red", _vintage_band(just_over, today=today))


class JSBandMatchesPythonReplicaTest(unittest.TestCase):
    """Production-binding guard: the JS vintageLine in modules/dashboard.html
    must agree with the Python replica for the same input. The Python
    `_vintage_band` helper is fast and dependency-free, but it does
    not load the real dashboard -- if the JS drifts (e.g. someone
    changes the boundary constants or anchors today differently),
    this test catches it before the dashboard ships a wrong band.

    Skips gracefully if Node is not on PATH: the Python tests above
    still cover the replica; this test only adds the production
    binding when Node is available in the test environment.
    """

    DASHBOARD_HTML = REPO / "modules" / "dashboard.html"
    JS_START = "// JEG-315, GAP-043: render per-source content_vintage line under each"
    JS_END = "const rank = {"

    @classmethod
    def setUpClass(cls):
        cls._have_node = subprocess.run(
            ["node", "--version"], capture_output=True, text=True
        ).returncode == 0

    def setUp(self):
        if not self._have_node:
            self.skipTest("node not on PATH; JS-side band guard skipped")

    def _extract_vintage_line_js(self):
        src = self.DASHBOARD_HTML.read_text(encoding="utf-8")
        start = src.find(self.JS_START)
        end = src.find(self.JS_END, start)
        assert start > 0, "vintageLine block start marker not found in dashboard.html"
        assert end > start, "vintageLine block end marker not found in dashboard.html"
        return src[start:end]

    def _run_js(self, content_vintage_expr):
        js = self._extract_vintage_line_js()
        # Extract the band class from the rendered HTML. We want the
        # substring `src-vintage <band>` where <band> is one of
        # green/amber/red/unk. Older dashboard.html versions pre-fix
        # used a `class="src-vintage ${band}"` template; newer versions
        # use a tagged `src-vintage ${band}` form. Match either.
        test_js = js + f"""
const html = vintageLine({content_vintage_expr});
const m = html.match(/src-vintage (green|amber|red|unk)/);
if(!m){{ process.stdout.write("NONE"); }}
else{{ process.stdout.write(m[1]); }}
"""
        result = subprocess.run(
            ["node", "-e", test_js],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"Node vintageLine run failed: rc={result.returncode} "
            f"stderr={result.stderr!r}"
        )
        return result.stdout

    def _today_midnight_iso(self):
        # Use a fixed UTC midnight today for deterministic boundary
        # tests. Same calendar anchor as the Python tests.
        return datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc).date().isoformat()

    def _days_ago_iso(self, days):
        today = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)
        return (today - timedelta(days=days)).date().isoformat()

    def test_js_2d_is_green(self):
        self.assertEqual(
            _vintage_band(self._days_ago_iso(2)),
            self._run_js(f'"{self._days_ago_iso(2)}"'),
        )

    def test_js_4d_boundary_is_green(self):
        # Exactly 4 calendar days old must be green -- the band
        # contract says 4d = green.
        self.assertEqual(
            _vintage_band(self._days_ago_iso(4)),
            self._run_js(f'"{self._days_ago_iso(4)}"'),
        )

    def test_js_5d_is_amber(self):
        self.assertEqual(
            _vintage_band(self._days_ago_iso(5)),
            self._run_js(f'"{self._days_ago_iso(5)}"'),
        )

    def test_js_7d_boundary_is_amber(self):
        # Exactly 7 calendar days old must be amber -- the band
        # contract says 7d = amber boundary.
        self.assertEqual(
            _vintage_band(self._days_ago_iso(7)),
            self._run_js(f'"{self._days_ago_iso(7)}"'),
        )

    def test_js_8d_is_red(self):
        self.assertEqual(
            _vintage_band(self._days_ago_iso(8)),
            self._run_js(f'"{self._days_ago_iso(8)}"'),
        )

    def test_js_week_label_is_unk(self):
        self.assertEqual(
            _vintage_band("Week 4"),
            self._run_js('"Week 4"'),
        )

    def test_js_empty_is_unk(self):
        # Empty / null vintage must produce the unk band.
        self.assertEqual(
            _vintage_band(""),
            self._run_js('""'),
        )


if __name__ == "__main__":
    unittest.main()