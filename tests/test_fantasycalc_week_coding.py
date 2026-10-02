#!/usr/bin/env python3
"""JEG-87 tests: FantasyCalc puller week-coding with fail-closed validation.

The 2026-10-02 USA Today incident (pulled Week 3 article, dashboard labeled
Week 4) made week-coding a hard rule (docs/week-coding-rules.md).

Honest scope for FantasyCalc (reviewer correction 2026-10-02):
FantasyCalc's API (/values/current) carries no week in the URL and has no
week-labeled page title, so there is no page content to extract a week
from. The first implementation generated a page title from the request
and appended &week=N to the recorded URL -- synthetic evidence that made
the validator agree with itself. This module pins the honest behavior:
the week is asserted from --week-label (fail-closed if unparseable),
the recorded URL is byte-identical to the URL actually fetched, and the
evidence dict carries week_url=None / week_titles=[] so downstream
consumers can see the evidence is request-asserted.

All tests are negative-tested against the named defects:
1. The validator must fail closed when URL week != title week !=
   requested week, and must not silently fall back to the request alone.
2. main() must not record synthetic page evidence (no generated title,
   no &week= param on a URL the API ignores).
3. main() must write caches keyed exactly like the real bsd contract
   (string keys "scoring_teams_qbN"); tuple-unpacking the string keys
   crashed the write loop in the first implementation.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

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


# Mirror the REAL build_sources_dashboard contract (values verified
# against ~/workspace/goals/football-signal-database-and-app/lottery/bin/
# build_sources_dashboard.py): SCORINGS uses "half"/"full" (not
# "half_ppr"/"ppr"), pull keys are "%s_%d_qb%d" strings, and the fetched
# URL is .../values/current?isDynasty=false&numQbs=N&numTeams=M&ppr=P
# with ppr in {"standard": 0, "half": 0.5, "full": 1}.
class _FakeBSD:
    SCORINGS = ["standard", "half", "full"]
    TEAM_COUNTS = [8, 10, 12, 14]
    QB_COUNTS = [1, 2]

    def __init__(self):
        self.pull_calls = []
        self.saved_calls = []

    def pull_fantasycalc(self, scoring, teams, qbs):
        self.pull_calls.append((scoring, teams, qbs))
        return [{"player_key": i, "value": 100 - i} for i in range(150)]

    def save_cache(self, name, payload):
        self.saved_calls.append((name, payload))


sys.modules["build_sources_dashboard"] = _FakeBSD()
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
        # The real FantasyCalc API URL has no week param -- the extractor
        # must say so (None), not invent one.
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


# ---------------------------------------------------------------------------
# 2. Title week parsing
# ---------------------------------------------------------------------------


class ExtractWeekFromTitleTest(unittest.TestCase):
    def test_week_at_start(self):
        self.assertEqual(
            refresh.extract_week_from_title("Week 4 Trade Value Chart"), 4)

    def test_week_in_middle(self):
        self.assertEqual(
            refresh.extract_week_from_title("FantasyCalc Week 7 Trade Values"), 7)

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


# ---------------------------------------------------------------------------
# 3. Validator: agreement + fail-closed
# ---------------------------------------------------------------------------


class ValidateWeekConsistencyTest(unittest.TestCase):
    def test_url_title_request_all_agree(self):
        url = ("https://api.fantasycalc.com/values/current"
               "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5&week=4")
        title = "FantasyCalc Week 4 Trade Values"
        ev = refresh.validate_week_consistency(url, title, 4)
        self.assertEqual(ev["week"], 4)
        self.assertEqual(ev["week_url"], 4)
        self.assertEqual(ev["week_titles"], [4])
        self.assertEqual(ev["week_requested"], 4)

    def test_request_only_path_is_honest(self):
        """The FantasyCalc production path: real API URL (no week param),
        no page title (API pull, not a page scrape), request asserts the
        week. The evidence dict must show week_url=None / week_titles=[]
        so consumers know no page corroboration exists."""
        url = ("https://api.fantasycalc.com/values/current"
               "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")
        ev = refresh.validate_week_consistency(url, None, 4)
        self.assertEqual(ev["week"], 4)
        self.assertIsNone(ev["week_url"])
        self.assertEqual(ev["week_titles"], [])
        self.assertEqual(ev["week_requested"], 4)

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
            "have raised to fail closed." % (ev,))


# ---------------------------------------------------------------------------
# 4. fantasycalc_url mirrors the real fetch URL
# ---------------------------------------------------------------------------


class FantasycalcUrlTest(unittest.TestCase):
    def test_url_matches_real_api_shape(self):
        url = refresh.fantasycalc_url("standard", 8, 1)
        self.assertEqual(
            url,
            "https://api.fantasycalc.com/values/current"
            "?isDynasty=false&numQbs=1&numTeams=8&ppr=0")

    def test_ppr_mapping_mirrors_bsd(self):
        """Pin the ppr mapping against bsd.pull_fantasycalc's own
        {"standard": 0, "half": 0.5, "full": 1}. The first implementation
        used half_ppr/ppr keys and recorded ppr=0.5 for "full" while the
        real fetch used ppr=1."""
        self.assertIn("ppr=0.5", refresh.fantasycalc_url("half", 12, 1))
        self.assertIn("ppr=1", refresh.fantasycalc_url("full", 12, 1))
        self.assertIn("ppr=0", refresh.fantasycalc_url("standard", 12, 1))

    def test_no_week_param_recorded(self):
        """The API ignores unknown params; recording a &week=N URL would
        be evidence for a request that was never made."""
        url = refresh.fantasycalc_url("half", 12, 1)
        self.assertNotIn("week=", url)


# ---------------------------------------------------------------------------
# 5. End-to-end: main() writes honest week evidence
# ---------------------------------------------------------------------------


class MainWeekCodingTest(unittest.TestCase):
    """Drive main() with a FakeBSD mirroring the real bsd contract."""

    def setUp(self):
        self._fake = _FakeBSD()
        self._orig_bsd = refresh.bsd
        refresh.bsd = self._fake

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

    def test_payloads_include_honest_week_evidence(self):
        self.assertIsNone(self._run_main(["--week-label", "Week 4"]))
        # 24 combo caches + 1 snapshot manifest.
        self.assertEqual(len(self._fake.saved_calls), 25)
        for name, payload in self._fake.saved_calls:
            self.assertIn("week_evidence", payload,
                          "cache %s missing 'week_evidence'" % name)
            ev = payload["week_evidence"]
            self.assertEqual(ev["week"], 4)
            # Honest request-asserted evidence: no page corroboration.
            self.assertIsNone(ev["week_url"])
            self.assertEqual(ev["week_titles"], [])
            self.assertEqual(ev["week_requested"], 4)
            # No synthetic page evidence anywhere in the payload.
            self.assertNotIn("page_title", payload,
                             "cache %s must not carry a generated title" % name)
            self.assertNotIn("week=", payload.get("url", ""),
                             "cache %s records a URL that was never fetched" % name)
            if name == "fantasycalc_snapshot":
                # The manifest keeps the human label string: pull_watchdog
                # formats snap["week"] into its content_vintage line.
                self.assertEqual(payload["week"], "Week 4")
            else:
                self.assertIn("week", payload,
                              "cache %s missing 'week'" % name)
                self.assertEqual(payload["week"], 4)

    def test_cache_names_match_real_key_shape(self):
        """Discrimination for the first implementation's crash: it
        tuple-unpacked the string cache keys ("half_12_qb1") in the write
        loop, so main() died before writing anything. These names only
        exist if the loop handles the real bsd key shape."""
        self.assertIsNone(self._run_main(["--week-label", "Week 4"]))
        names = [n for n, _ in self._fake.saved_calls]
        self.assertIn("fantasycalc_half_12_qb1", names)
        self.assertIn("fantasycalc_full_14_qb2", names)
        self.assertIn("fantasycalc_standard_8_qb1", names)
        self.assertIn("fantasycalc_snapshot", names)

    def test_recorded_url_is_the_fetched_url(self):
        self.assertIsNone(self._run_main(["--week-label", "Week 7"]))
        payload = dict(self._fake.saved_calls)["fantasycalc_half_12_qb1"]
        self.assertEqual(
            payload["url"],
            "https://api.fantasycalc.com/values/current"
            "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")

    def test_unparseable_label_refuses_to_pull(self):
        """A request that does not parse as 'Week N' must fail closed
        before any API call is made -- no pulls, no writes."""
        rc = self._run_main(["--week-label", "Sometime soon"])
        self.assertEqual(rc, 1, "main() must sys.exit(1) on unparseable "
                                "week-label")
        self.assertEqual(self._fake.pull_calls, [])
        self.assertEqual(self._fake.saved_calls, [])


if __name__ == "__main__":
    unittest.main()
