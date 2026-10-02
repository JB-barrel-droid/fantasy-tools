#!/usr/bin/env python3
"""JEG-85: CBS puller must codify week from page content (fail-closed).

Jeremy 2026-10-02 directive (docs/week-coding-rules.md, Rule 2): "All week
evidence must agree (fail closed). Any mismatch -> raise, do not label."

Each test simulates the historical miss the check must catch, then negative-
tests against the broken state:

  - a URL whose slug says week N paired with a page headline that says week M
  - a pull where the page headline matches but the requested week does not
  - a pull where the URL has no week AND the headline has no week
  - a happy-path pull: URL week == headline week == requested week

Stdlib unittest; hermetic (no network, mocked fetch). Mirrors the structure
of tests/test_pull_watchdog.py (which already exercises pull_cbs discovery
and markup-mismatch paths) but is dedicated to the week-coding contract.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "ops", "watchdog"))
import pull_cbs as cbs  # noqa: E402

WEEK_URL = (
    "https://sportsfly.cbsistatic.com/fantasy/football/news/"
    "dave-richards-week-%d-trade-chart-and-rest-of-season-"
    "fantasy-football-rankings-help-you-win-now/")


def _cbs_html(headline, body=""):
    """Wrap a headline and an optional body in CBS-flavored page markup."""
    return ('<html><head>'
            '<meta property="og:title" content="%s" />'
            '</head><body>%s</body></html>' % (headline, body))


def _cbs_pos_table(title, players):
    """Render one CBS TableBuilder position table (mirror pull_cbs real shape)."""
    rows = "".join('<tr><td>%s</td></tr>' % p for p in players)
    return ('<h2>%s</h2><table class="TableBuilder">'
            '<tr><th>Player</th></tr>%s</table>' % (title, rows))


def _fetch_with_headline(url, headline, n_tables=4, players_per=8):
    """Return a fetch_fn that yields a CBS page with the given headline."""
    body = "".join(_cbs_pos_table(t, ["P%d-%s" % (i, t) for i in range(players_per)])
                   for t in ("Quarterback", "Running Back",
                             "Wide Receiver", "Tight End")[:n_tables])
    html = _cbs_html(headline, body)
    return lambda u: (200, html)


class TestCbsExtractWeek(unittest.TestCase):
    """The two extractors must agree with the rule's URL/headline patterns."""

    def test_extract_week_from_url_matches_cbs_slug(self):
        self.assertEqual(cbs.extract_week_from_url(WEEK_URL % 3), 3)
        self.assertEqual(cbs.extract_week_from_url(WEEK_URL % 4), 4)
        self.assertEqual(cbs.extract_week_from_url(WEEK_URL % 17), 17)

    def test_extract_week_from_url_returns_none_when_missing(self):
        # A non-CBS URL (e.g. USA Today's slug) must not be silently matched.
        self.assertIsNone(cbs.extract_week_from_url(
            "https://www.usatoday.com/story/sports/fantasy/football/"
            "2026/09/29/fantasy-trade-value-chart-week-4-ros-rankings/123/"))
        self.assertIsNone(cbs.extract_week_from_url(
            "https://example.com/no-week-here/"))

    def test_extract_week_from_title_matches_headline_pattern(self):
        self.assertEqual(
            cbs.extract_week_from_title(
                "Fantasy Football Trade Chart: Week 4 rest-of-season rankings"),
            4)
        self.assertEqual(
            cbs.extract_week_from_title("Week 12 trade chart"), 12)
        # Case-insensitive: real CBS og:title mixes casing.
        self.assertEqual(
            cbs.extract_week_from_title("week 7 fantasy football"), 7)

    def test_extract_week_from_title_returns_none_when_missing(self):
        self.assertIsNone(cbs.extract_week_from_title(
            "Fantasy Football Trade Chart: rest-of-season rankings"))
        self.assertIsNone(cbs.extract_week_from_title(""))


class TestCbsPageHeadline(unittest.TestCase):
    """CBS H2 table titles are position-only; the week lives in the headline."""

    def test_extracts_og_title_first(self):
        html = _cbs_html("Week 4 Trade Chart",
                         "<h1>Week 99 wrong</h1>")
        self.assertEqual(cbs.extract_page_headline(html), "Week 4 Trade Chart")

    def test_falls_back_to_title_tag(self):
        html = ('<html><head><title>Week 3 fantasy football trade chart'
                '</title></head><body></body></html>')
        self.assertEqual(cbs.extract_page_headline(html),
                         "Week 3 fantasy football trade chart")

    def test_falls_back_to_first_h1(self):
        html = ('<html><body><h1>Week 5 fantasy football trade chart'
                '</h1></body></html>')
        self.assertEqual(cbs.extract_page_headline(html),
                         "Week 5 fantasy football trade chart")

    def test_returns_none_when_no_headline_present(self):
        self.assertIsNone(cbs.extract_page_headline(
            "<html><body>no headline</body></html>"))


class TestCbsValidateWeekConsistency(unittest.TestCase):
    """The fail-closed gate. Every match path must work; every mismatch
    must raise. Mirrors pull_usatoday.validate_week_consistency semantics."""

    GOOD_URL = WEEK_URL % 4
    GOOD_HEADLINE = "Fantasy Football Trade Chart: Week 4 rest-of-season"

    def test_happy_path_url_matches_headline_matches_request(self):
        ev = cbs.validate_week_consistency(self.GOOD_URL, self.GOOD_HEADLINE, 4)
        self.assertEqual(ev["week"], 4)
        self.assertEqual(ev["week_url"], 4)
        self.assertEqual(ev["week_headline"], 4)
        self.assertEqual(ev["week_requested"], 4)

    def test_happy_path_no_requested_week_still_validates(self):
        ev = cbs.validate_week_consistency(self.GOOD_URL, self.GOOD_HEADLINE, None)
        self.assertEqual(ev["week"], 4)

    def test_url_sole_evidence_when_headline_missing(self):
        # URL is authoritative when present; a page with no headline tag
        # (older markup) must not block labeling when the URL clearly says
        # the week. We refuse to label only when BOTH are missing.
        ev = cbs.validate_week_consistency(self.GOOD_URL, None, 4)
        self.assertEqual(ev["week"], 4)
        self.assertIsNone(ev["week_headline"])

    def test_url_mismatch_headline_fails_closed(self):
        """The 2026-10-02 incident pattern, on CBS: URL says week 3, headline
        says week 4 (e.g. a stale snapshot whose headline was already updated
        server-side, or vice versa). Refuse to label."""
        with self.assertRaisesRegex(RuntimeError, "URL week .3. != page headline week .4."):
            cbs.validate_week_consistency(WEEK_URL % 3, self.GOOD_HEADLINE, None)

    def test_requested_week_mismatch_fails_closed(self):
        """Requested week 3 but page is week 4: the request is wrong, refuse."""
        with self.assertRaisesRegex(RuntimeError,
                                    "requested week .3. != page week .4."):
            cbs.validate_week_consistency(self.GOOD_URL, self.GOOD_HEADLINE, 3)

    def test_url_and_headline_both_missing_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,
                                    "could not determine week"):
            cbs.validate_week_consistency(
                "https://example.com/no-week-here/", None, None)

    def test_requested_week_with_no_page_evidence_fails_closed(self):
        # A page with no week anywhere AND a request: even if the request
        # is well-formed, the page content doesn't support labeling.
        with self.assertRaisesRegex(RuntimeError, "could not determine week"):
            cbs.validate_week_consistency(
                "https://example.com/no-week-here/", None, 4)


class TestCbsPullReturnsHeadline(unittest.TestCase):
    """pull() must hand main() the headline so validate_week_consistency runs."""

    def test_pull_returns_tables_and_headline(self):
        tables, headline = cbs.pull(
            WEEK_URL % 4,
            fetch_fn=_fetch_with_headline(WEEK_URL % 4,
                                          "Week 4 fantasy trade chart"))
        self.assertEqual(len(tables), 4)
        self.assertEqual(cbs.extract_week_from_title(headline), 4)

    def test_pull_still_rejects_markup_mismatch(self):
        # Regression: the new tuple return must not break the markup check.
        with self.assertRaises(RuntimeError):
            cbs.pull("https://example.com/x",
                     fetch_fn=lambda u: (200, "<html>no tables</html>"))


class TestCbsJsonContainsWeekEvidence(unittest.TestCase):
    """The written JSON must carry week + week_evidence (Rule 3)."""

    def _run_main(self, argv, fetch_fn, swallow_errors=False):
        """Invoke pull_cbs.main() with argv + a fake fetch.

        When swallow_errors=True, RuntimeError from a fail-closed validation
        is caught (returning None) so callers can assert post-conditions like
        "no JSON file was written". When False (default), the exception
        propagates so callers can use assertRaises() around _run_main.
        """
        old_argv = sys.argv
        sys.argv = argv
        try:
            with patch("pull_cbs.fetch", fetch_fn):
                try:
                    cbs.main()
                except RuntimeError:
                    if not swallow_errors:
                        raise
        finally:
            sys.argv = old_argv

    def test_write_includes_week_and_week_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_repo = cbs.REPO
            cbs.REPO = tmp
            try:
                argv = ["pull_cbs.py", "--week", "4", "--url", WEEK_URL % 4,
                        "--write"]
                self._run_main(
                    argv,
                    _fetch_with_headline(WEEK_URL % 4,
                                         "Week 4 fantasy trade chart"))
                today = date.today().isoformat()
                outp = os.path.join(tmp, "ops", "watchdog", "pulls",
                                    "cbs-%s.json" % today)
                self.assertTrue(os.path.exists(outp),
                                "cbs pull JSON must be written")
                with open(outp) as f:
                    payload = json.load(f)
                self.assertEqual(payload["week"], 4)
                self.assertIn("week_evidence", payload)
                self.assertEqual(payload["week_evidence"]["week"], 4)
                self.assertEqual(payload["week_evidence"]["week_url"], 4)
                self.assertEqual(payload["week_evidence"]["week_headline"], 4)
                self.assertEqual(payload["week_evidence"]["week_requested"], 4)
                self.assertIn("tables", payload)
            finally:
                cbs.REPO = old_repo

    def test_write_fails_closed_on_url_headline_mismatch(self):
        # URL says week 3, headline says week 4 -> must NOT write a JSON.
        with tempfile.TemporaryDirectory() as tmp:
            old_repo = cbs.REPO
            cbs.REPO = tmp
            try:
                argv = ["pull_cbs.py", "--url", WEEK_URL % 3, "--write"]
                self._run_main(
                    argv,
                    _fetch_with_headline(WEEK_URL % 3,
                                         "Week 4 fantasy trade chart"),
                    swallow_errors=True)
                today = date.today().isoformat()
                outp = os.path.join(tmp, "ops", "watchdog", "pulls",
                                    "cbs-%s.json" % today)
                self.assertFalse(os.path.exists(outp),
                                 "mismatched week must fail closed, not write")
            finally:
                cbs.REPO = old_repo


if __name__ == "__main__":
    unittest.main()