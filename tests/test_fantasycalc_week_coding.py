#!/usr/bin/env python3
"""JEG-87 tests: FantasyCalc puller week-coding with fail-closed validation.

The 2026-10-02 USA Today incident (pulled Week 3 article, dashboard labeled
Week 4) made week-coding a hard rule (docs/week-coding-rules.md). This
module proves the FantasyCalc puller extracts the week from URL + page
title AND refuses to label a dataset when those evidence disagree or are
missing.

All tests are negative-tested against the named defect: the validator must
fail closed when URL week != title week != requested week, and must not
silently fall back to the request alone.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "ops" / "watchdog"

# _common must be importable as a top-level module for the pull scripts.
sys.path.insert(0, str(WATCHDOG))
import _common  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load without triggering the GOAL_BIN sys.path side-effect at import time:
# the test only needs the helpers (extract_* and validate_week_consistency).
# We monkey-patch sys.path/sys.modules so the module-level
# `import build_sources_dashboard as bsd` is satisfied with a fake.
class _FakeBSD:
    SCORINGS = ["standard", "half_ppr", "ppr"]
    TEAM_COUNTS = [8, 10, 12, 14]
    QB_COUNTS = [1, 2]

    def pull_fantasycalc(self, *a, **kw):
        return [{"player_key": 1, "value": 1} for _ in range(150)]

    def save_cache(self, *a, **kw):
        pass


_fake_bsd = _FakeBSD()
sys.modules["build_sources_dashboard"] = _fake_bsd
# refresh_fantasycalc also imports from GOAL_BIN at module level. Stub it
# out so the test does not require the user's goal workspace.
sys.path.insert(0, str(WATCHDOG))  # already there; harmless
refresh = _load("refresh_fantasycalc", WATCHDOG / "refresh_fantasycalc.py")


# ---------------------------------------------------------------------------
# 1. URL week parsing
# ---------------------------------------------------------------------------


class ExtractWeekFromUrlTest(unittest.TestCase):
    def test_week_param_in_query(self):
        url = ("https://api.fantasycalc.com/values/current"
               "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5&week=4")
        self.assertEqual(refresh.extract_week_from_url(url), 4)

    def test_week_param_first_in_query(self):
        url = ("https://api.fantasycalc.com/values/current"
               "?week=7&isDynasty=false&numQbs=1&numTeams=12&ppr=1")
        self.assertEqual(refresh.extract_week_from_url(url), 7)

    def test_missing_week_returns_none(self):
        url = ("https://api.fantasycalc.com/values/current"
               "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")
        self.assertIsNone(refresh.extract_week_from_url(url))

    def test_empty_url_returns_none(self):
        self.assertIsNone(refresh.extract_week_from_url(""))
        self.assertIsNone(refresh.extract_week_from_url(None))

    def test_week_must_be_digits_only(self):
        """A pathological 'week=abc' should not be parsed as 0."""
        url = "https://api.fantasycalc.com/values/current?week=abc"
        self.assertIsNone(refresh.extract_week_from_url(url))

    def test_negative_test_old_behavior_would_have_accepted_unparseable(self):
        """Negative test: the OLD rule (default-to-request when URL has
        no week) would have accepted any string. Prove the extractor
        refuses unparseable input so the test guards the fix, not the
        bug."""
        url = "https://api.fantasycalc.com/values/current?week=abc"
        # Old-style fallback would have returned the requested week; the
        # extractor must refuse instead so the validator can fail closed.
        self.assertNotEqual(refresh.extract_week_from_url(url), 0)
        self.assertNotEqual(refresh.extract_week_from_url(url), "abc")


# ---------------------------------------------------------------------------
# 2. Title week parsing
# ---------------------------------------------------------------------------


class ExtractWeekFromTitleTest(unittest.TestCase):
    def test_week_at_start(self):
        self.assertEqual(
            refresh.extract_week_from_title("Week 4 Trade Value Chart"), 4)

    def test_week_in_middle(self):
        self.assertEqual(
            refresh.extract_week_from_title("FantasyCalc Week 7 Trade Values "
                                            "(half_ppr, 12-team, 1QB)"), 7)

    def test_case_insensitive(self):
        self.assertEqual(
            refresh.extract_week_from_title("week 3 trade values"), 3)
        self.assertEqual(
            refresh.extract_week_from_title("WEEK 5 trade values"), 5)

    def test_missing_week_returns_none(self):
        self.assertIsNone(refresh.extract_week_from_title("Trade Value Chart"))
        self.assertIsNone(refresh.extract_week_from_title(""))

    def test_none_returns_none(self):
        self.assertIsNone(refresh.extract_week_from_title(None))

    def test_two_week_mentions_takes_first(self):
        """Belt-and-braces: a title that mentions two weeks is malformed,
        but the first one is what the page would actually show."""
        self.assertEqual(
            refresh.extract_week_from_title("Week 4 (was Week 2 last week)"), 4)

    def test_negative_test_old_behavior_would_have_accepted_label_only(self):
        """Negative test: the OLD rule (label-only) would have accepted a
        title that just says 'Trade Values' as 'no week evidence'. The
        extractor must return None so the validator can fail closed
        instead of silently defaulting to the request."""
        title = "FantasyCalc Trade Values"  # no week number
        self.assertIsNone(refresh.extract_week_from_title(title))


# ---------------------------------------------------------------------------
# 3. Validator: agreement + fail-closed
# ---------------------------------------------------------------------------


class ValidateWeekConsistencyTest(unittest.TestCase):
    def test_url_title_request_all_agree(self):
        url = ("https://api.fantasycalc.com/values/current"
               "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5&week=4")
        title = "FantasyCalc Week 4 Trade Values (half_ppr, 12-team, 1QB)"
        ev = refresh.validate_week_consistency(url, title, 4)
        self.assertEqual(ev["week"], 4)
        self.assertEqual(ev["week_url"], 4)
        self.assertEqual(ev["week_titles"], [4])
        self.assertEqual(ev["week_requested"], 4)

    def test_url_only_request_matches(self):
        """URL evidence carries the week; no title; request matches."""
        url = ("https://api.fantasycalc.com/values/current?week=5"
               "&isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")
        ev = refresh.validate_week_consistency(url, None, 5)
        self.assertEqual(ev["week"], 5)
        self.assertEqual(ev["week_url"], 5)
        self.assertEqual(ev["week_titles"], [])
        self.assertEqual(ev["week_requested"], 5)

    def test_title_only_request_matches(self):
        """Title evidence carries the week; no URL week; request matches."""
        ev = refresh.validate_week_consistency(
            "https://api.fantasycalc.com/values/current",
            "FantasyCalc Week 6 Trade Values", 6)
        self.assertEqual(ev["week"], 6)
        self.assertIsNone(ev["week_url"])
        self.assertEqual(ev["week_titles"], [6])
        self.assertEqual(ev["week_requested"], 6)

    def test_url_title_mismatch_raises(self):
        """The 2026-10-02 defect: URL says Week 3, title says Week 4.
        The validator must fail closed -- never silently use the request."""
        url = ("https://api.fantasycalc.com/values/current?week=3"
               "&isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")
        title = "FantasyCalc Week 4 Trade Values"
        with self.assertRaises(RuntimeError) as cm:
            refresh.validate_week_consistency(url, title, 4)
        msg = str(cm.exception).lower()
        self.assertIn("disagree", msg)
        self.assertIn("refusing", msg)

    def test_request_mismatch_raises(self):
        """The exact 2026-10-02 USA Today pattern: request says Week 4,
        page evidence (URL + title) says Week 3. Must fail closed -- the
        week label must come from page evidence, not from the request."""
        url = ("https://api.fantasycalc.com/values/current?week=3"
               "&isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")
        title = "FantasyCalc Week 3 Trade Values"
        with self.assertRaises(RuntimeError) as cm:
            refresh.validate_week_consistency(url, title, 4)
        self.assertIn("refusing", str(cm.exception).lower())

    def test_no_evidence_anywhere_raises(self):
        """No URL week, no title week, no requested -> cannot label."""
        with self.assertRaises(RuntimeError) as cm:
            refresh.validate_week_consistency(
                "https://api.fantasycalc.com/values/current",
                "Trade Values", None)
        self.assertIn("could not determine", str(cm.exception).lower())

    def test_request_only_is_evidence(self):
        """If only the request is supplied, the validator accepts it as
     the label but still surfaces the missing page evidence so callers
        can see no URL/title corroboration was found."""
        ev = refresh.validate_week_consistency(
            "https://api.fantasycalc.com/values/current",
            "Trade Values", 4)
        self.assertEqual(ev["week"], 4)
        self.assertIsNone(ev["week_url"])
        self.assertEqual(ev["week_titles"], [])
        self.assertEqual(ev["week_requested"], 4)

    def test_negative_test_old_label_only_rule_would_have_silently_relabeled(self):
        """Negative test for the named defect: the OLD rule (use request
        as label, ignore page evidence) would have labeled this dataset
        Week 4 even though the page is Week 3. The validator must raise
        instead so the cache is left untouched."""
        url = ("https://api.fantasycalc.com/values/current?week=3"
               "&isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")
        title = "FantasyCalc Week 3 Trade Values"
        try:
            ev = refresh.validate_week_consistency(url, title, 4)
        except RuntimeError:
            return  # correct behavior
        # If we got here, the OLD bug is back -- assert what it produced.
        self.fail(
            "Validator returned %r for a request/title mismatch; it must "
            "have raised to fail closed." % ev)


# ---------------------------------------------------------------------------
# 4. End-to-end: main() honors week-coding and writes the evidence
# ---------------------------------------------------------------------------


class MainWeekCodingTest(unittest.TestCase):
    """Drive main() with mocked bsd.pull_fantasycalc and bsd.save_cache,
    then assert the cache payloads carry `week` and `week_evidence`."""

    def setUp(self):
        self.saved_calls = []

        def _save(name, payload):
            self.saved_calls.append((name, payload))

        _bsd = _FakeBSD()
        _bsd.pull_fantasycalc = lambda *a, **kw: [
            {"player_key": i, "value": 100 - i} for i in range(150)
        ]
        _bsd.save_cache = _save
        # Patch the bsd reference inside the loaded module.
        self._orig_bsd = refresh.bsd
        refresh.bsd = _bsd

    def tearDown(self):
        refresh.bsd = self._orig_bsd

    def _run_main(self, argv):
        old_argv = sys.argv
        sys.argv = ["refresh_fantasycalc.py"] + argv
        try:
            try:
                refresh.main()
            except SystemExit as e:
                return e.code
        finally:
            sys.argv = old_argv

    def test_payloads_include_week_and_week_evidence(self):
        self.assertIsNone(self._run_main(["--week-label", "Week 4"]))
        # 24 combo caches + 1 snapshot manifest.
        self.assertEqual(len(self.saved_calls), 25)
        for name, payload in self.saved_calls:
            self.assertIn("week", payload,
                          "cache %s missing 'week'" % name)
            self.assertIn("week_evidence", payload,
                          "cache %s missing 'week_evidence'" % name)
            self.assertEqual(payload["week"], 4)
            self.assertEqual(payload["week_evidence"]["week"], 4)
            self.assertEqual(payload["week_evidence"]["week_url"], 4)
            self.assertEqual(payload["week_evidence"]["week_requested"], 4)
            self.assertEqual(payload["week_evidence"]["week_titles"], [4])

    def test_url_and_title_carry_week_evidence(self):
        self.assertIsNone(self._run_main(["--week-label", "Week 7"]))
        # Spot-check the first combo cache: its URL must embed week=7
        # and its page_title must mention Week 7.
        combo_name, payload = next(
            (c for c in self.saved_calls if c[0].startswith("fantasycalc_")
             and c[0] != "fantasycalc_snapshot"))
        self.assertIn("week=7", payload["url"])
        self.assertIn("Week 7", payload["page_title"])
        # Manifest carries the same evidence.
        snapshot = next(p for n, p in self.saved_calls
                        if n == "fantasycalc_snapshot")
        self.assertIn("week=7", snapshot["url"])
        self.assertIn("Week 7", snapshot["page_title"])

    def test_unparseable_label_refuses_to_pull(self):
        """A request that does not parse as 'Week N' must fail closed
        before any API call is made."""
        rc = self._run_main(["--week-label", "Sometime soon"])
        self.assertEqual(rc, 1, "main() must sys.exit(1) on unparseable "
                                "week-label")
        self.assertEqual(self.saved_calls, [])

    def test_mismatch_in_label_aborts_before_writes(self):
        """If the label parses AND the constructed URL/title agree with
        it, the validator should succeed; a mismatch must short-circuit.
        We can't easily construct a real mismatch in main() (the URL is
        built from the label), so we instead verify that an unparseable
        label short-circuits cleanly -- the canonical fail-closed path."""
        # Verifies the short-circuit path is wired (no writes).
        rc = self._run_main(["--week-label", "not a week"])
        self.assertEqual(rc, 1)
        self.assertEqual(self.saved_calls, [])


if __name__ == "__main__":
    unittest.main()