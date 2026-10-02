#!/usr/bin/env python3
"""Negative tests for the FantasyPros week-coding pullers (JEG-86).

Covers:
  - ops/watchdog/pull_fantasypros.py (new page puller with URL+title validation)
  - weekly_vegas/pipeline/loaders/fantasypros.py (filename-week guard for the
    CSV snapshot path; the page puller can also cache a sidecar week.json).

Each test simulates the historical miss the guard must catch: a stale URL
slug, a wrong page title, a caller's --week that disagrees with the page,
a CSV filename that disagrees with the caller's --week, a sidecar that
disagrees with the CSV. Stdlib unittest; hermetic (mocked fetch, tmp dirs)
— no network, no Supabase, no live pull outputs.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "ops", "watchdog"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "weekly_vegas", "pipeline", "loaders"))
import pull_fantasypros as fp
from fantasypros import (  # noqa: E402
    extract_week_from_filename,
    fp_week_sidecar_path,
    validate_filename_week_consistency,
)


FP_URL_W4 = ("https://www.fantasypros.com/2026/09/"
             "fantasy-football-trade-value-chart-week-4-2026/")
FP_URL_W3 = ("https://www.fantasypros.com/2026/09/"
             "fantasy-football-trade-value-chart-week-3-2026/")
FP_HTML_W3 = "<html><head><title>Week 3 fantasy football trade value chart</title></head><body></body></html>"
FP_HTML_W4 = "<html><head><title>Week 4 fantasy football trade value chart</title></head><body></body></html>"
FP_HTML_TITLE_W5_URL_W4 = ("<html><head><title>Week 5 fantasy football trade value chart"
                          "</title></head></html>")


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# --- URL slug + title extraction --------------------------------------------

class TestExtractWeekFromUrl(unittest.TestCase):
    def test_url_with_week_4(self):
        self.assertEqual(fp.extract_week_from_url(FP_URL_W4), 4)

    def test_url_with_week_3(self):
        self.assertEqual(fp.extract_week_from_url(FP_URL_W3), 3)

    def test_url_without_week_returns_none(self):
        self.assertIsNone(fp.extract_week_from_url(
            "https://www.fantasypros.com/2026/09/some-other-article/"))

    def test_url_with_malformed_slug_returns_none(self):
        # The slug must have _wk<N>_ followed by a separator; "wk4.csv"
        # at the end is not a real FantasyPros URL pattern.
        self.assertIsNone(fp.extract_week_from_url(
            "https://example.com/trade-value-chart-wk4"))


class TestExtractWeekFromTitle(unittest.TestCase):
    def test_title_with_week_4(self):
        self.assertEqual(fp.extract_week_from_title(
            "Week 4 fantasy football trade value chart"), 4)

    def test_title_with_week_15(self):
        self.assertEqual(fp.extract_week_from_title(
            "Rest-of-Season Week 15 trade value chart"), 15)

    def test_title_with_lowercase_week(self):
        # Lowercase "week 4" should still parse (we use \bweek\b case-insens).
        self.assertEqual(fp.extract_week_from_title(
            "week 4 fantasy football trade value chart"), 4)

    def test_title_without_week_returns_none(self):
        self.assertIsNone(fp.extract_week_from_title(
            "FantasyPros trade value chart"))

    def test_title_with_only_word_does_not_match(self):
        # "midweek" must not be parsed as week=anything. \bword\b only.
        self.assertIsNone(fp.extract_week_from_title(
            "midweek fantasy football trade value chart"))


class TestExtractTitleText(unittest.TestCase):
    def test_prefers_title_over_h1(self):
        html = ("<html><head><title>Week 4 fantasy football trade value chart"
                "</title></head><body><h1>Some longer H1</h1></body></html>")
        self.assertEqual(fp._extract_title_text(html),
                         "Week 4 fantasy football trade value chart")

    def test_falls_back_to_h1_when_no_title(self):
        html = ("<html><body><h1>Week 4 fantasy football trade value chart"
                "</h1></body></html>")
        self.assertEqual(fp._extract_title_text(html),
                         "Week 4 fantasy football trade value chart")

    def test_returns_none_when_neither_present(self):
        self.assertIsNone(fp._extract_title_text("<html><body></body></html>"))


# --- Page puller validate_week_consistency ----------------------------------

class TestValidateWeekConsistency(unittest.TestCase):
    def test_all_three_agree(self):
        ev = fp.validate_week_consistency(FP_URL_W4, "Week 4 trade value chart",
                                          requested_week=4)
        self.assertEqual(ev["week"], 4)
        self.assertEqual(ev["week_url"], 4)
        self.assertEqual(ev["week_titles"], [4])
        self.assertEqual(ev["week_requested"], 4)

    def test_requested_none_passes_when_url_and_title_agree(self):
        # The caller didn't specify --week; the page evidence still labels it.
        ev = fp.validate_week_consistency(FP_URL_W4, "Week 4 trade value chart",
                                          requested_week=None)
        self.assertEqual(ev["week"], 4)

    def test_url_mismatch_title_fails_closed(self):
        # URL says week-4, title says week-5: page content does not match slug.
        with self.assertRaises(RuntimeError) as cm:
            fp.validate_week_consistency(FP_URL_W4, "Week 5 trade value chart",
                                         requested_week=None)
        self.assertIn("URL week", str(cm.exception))
        self.assertIn("title week", str(cm.exception))

    def test_requested_mismatch_page_fails_closed(self):
        # 2026-10-02 USA Today class of miss: caller asked for week 4 but the
        # page is week 3. Refuse to label.
        with self.assertRaises(RuntimeError) as cm:
            fp.validate_week_consistency(FP_URL_W3,
                                         "Week 3 trade value chart",
                                         requested_week=4)
        self.assertIn("requested week", str(cm.exception))
        self.assertIn("page week", str(cm.exception))

    def test_url_without_week_fails_closed(self):
        with self.assertRaises(RuntimeError) as cm:
            fp.validate_week_consistency(
                "https://www.fantasypros.com/2026/09/some-article/",
                "Week 4 trade value chart", requested_week=4)
        self.assertIn("no week slug", str(cm.exception))

    def test_title_without_week_fails_closed(self):
        with self.assertRaises(RuntimeError) as cm:
            fp.validate_week_consistency(FP_URL_W4,
                                         "FantasyPros trade value chart",
                                         requested_week=4)
        self.assertIn("Week N", str(cm.exception))

    def test_empty_title_fails_closed(self):
        with self.assertRaises(RuntimeError):
            fp.validate_week_consistency(FP_URL_W4, "", requested_week=4)


# --- Page puller pull() ----------------------------------------------------

class TestPagePull(unittest.TestCase):
    def test_returns_extracted_title(self):
        def fetch(url):
            return (200, FP_HTML_W4)
        title = fp.pull(FP_URL_W4, fetch_fn=fetch)
        self.assertIn("Week 4", title)

    def test_fetch_failure_raises(self):
        def fetch(url):
            return (404, "")
        with self.assertRaises(RuntimeError) as cm:
            fp.pull(FP_URL_W4, fetch_fn=fetch)
        self.assertIn("404", str(cm.exception))

    def test_no_title_no_h1_raises(self):
        def fetch(url):
            return (200, "<html><body></body></html>")
        with self.assertRaises(RuntimeError):
            fp.pull(FP_URL_W4, fetch_fn=fetch)


# --- Page puller discovery (mocked fetch) ----------------------------------

class TestDiscoverUrl(unittest.TestCase):
    def test_discovers_when_url_and_title_agree(self):
        def fetch(url):
            return (200, FP_HTML_W4)
        url = fp.discover_url(4, fetch_fn=fetch)
        self.assertEqual(url, FP_URL_W4)

    def test_falls_back_to_previous_week(self):
        # Week 4 doesn't resolve (404); week 3 does.
        calls = []
        def fetch(url):
            calls.append(url)
            if "week-4-" in url:
                return (404, "")
            return (200, FP_HTML_W3)
        url = fp.discover_url(4, fetch_fn=fetch)
        self.assertEqual(url, FP_URL_W3)

    def test_rejects_page_when_title_disagrees_with_slug(self):
        # URL says week-4 but the <title> says week-5: discovery walks past
        # this page (same class of miss as 2026-10-02 USA Today incident).
        def fetch(url):
            return (200, FP_HTML_TITLE_W5_URL_W4)
        with self.assertRaises(fp.DiscoveryFailed):
            fp.discover_url(4, fetch_fn=fetch)

    def test_raises_when_no_candidate_resolves(self):
        def fetch(url):
            return (404, "")
        with self.assertRaises(fp.DiscoveryFailed):
            fp.discover_url(4, fetch_fn=fetch)


# --- CSV loader filename-week guard ----------------------------------------

class TestExtractWeekFromFilename(unittest.TestCase):
    def test_weekly_csv(self):
        self.assertEqual(extract_week_from_filename(
            "/data/fantasypros/ecr_qb_wk4.csv"), 4)

    def test_projection_csv(self):
        self.assertEqual(extract_week_from_filename(
            "/data/fantasypros/proj_wr_wk5.csv"), 5)

    def test_ros_csv(self):
        self.assertEqual(extract_week_from_filename(
            "/data/fantasypros/ecr_ros_qb_wk3.csv"), 3)

    def test_draft_csv_returns_none(self):
        # Draft / dynasty CSVs are not week-stamped; the guard must not fire.
        self.assertIsNone(extract_week_from_filename(
            "/data/fantasypros/ecr_draft_qb.csv"))

    def test_dynasty_csv_returns_none(self):
        self.assertIsNone(extract_week_from_filename(
            "/data/fantasypros/ecr_dynasty_wr.csv"))


class TestValidateFilenameWeekConsistency(unittest.TestCase):
    def test_filename_agrees_with_requested_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "proj_qb_wk4.csv")
            _write(csv_p, "Player,Team\nA,B\n")
            ev = validate_filename_week_consistency(csv_p, 4)
            self.assertEqual(ev["week"], 4)
            self.assertEqual(ev["week_filename"], 4)
            self.assertEqual(ev["week_requested"], 4)
            self.assertIsNone(ev["week_sidecar_week"])

    def test_filename_agrees_with_requested_week_when_no_request(self):
        # Caller didn't pass --week; the filename alone is enough to label.
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "proj_qb_wk4.csv")
            _write(csv_p, "Player,Team\n")
            ev = validate_filename_week_consistency(csv_p, None)
            self.assertEqual(ev["week"], 4)
            self.assertEqual(ev["week_requested"], None)

    def test_filename_disagrees_with_requested_week_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "proj_qb_wk3.csv")
            _write(csv_p, "Player,Team\n")
            with self.assertRaises(RuntimeError) as cm:
                validate_filename_week_consistency(csv_p, 4)
            self.assertIn("filename week", str(cm.exception))
            self.assertIn("requested week", str(cm.exception))

    def test_sidecar_agrees_with_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "proj_qb_wk4.csv")
            _write(csv_p, "Player,Team\n")
            _write(fp_week_sidecar_path(csv_p), json.dumps({
                "week": 4,
                "week_evidence": {"week": 4, "week_titles": [4]}}))
            ev = validate_filename_week_consistency(csv_p, 4)
            self.assertEqual(ev["week_sidecar_week"], 4)
            self.assertEqual(ev["week_titles"], [4])

    def test_sidecar_disagrees_with_filename_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "proj_qb_wk3.csv")
            _write(csv_p, "Player,Team\n")
            _write(fp_week_sidecar_path(csv_p), json.dumps({
                "week": 4,
                "week_evidence": {"week": 4, "week_titles": [4]}}))
            with self.assertRaises(RuntimeError) as cm:
                validate_filename_week_consistency(csv_p, 3)
            self.assertIn("filename week", str(cm.exception))
            self.assertIn("page puller week", str(cm.exception))

    def test_missing_sidecar_is_ok_when_filename_agrees(self):
        # The sidecar is optional: until the page puller caches it, the
        # filename is the only evidence the CSV loader has. Agreement
        # between filename and --week is sufficient; no sidecar, no fail.
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "proj_qb_wk4.csv")
            _write(csv_p, "Player,Team\n")
            ev = validate_filename_week_consistency(csv_p, 4)
            self.assertIsNone(ev["week_sidecar_week"])

    def test_draft_csv_with_zero_requested_week_is_ok(self):
        # Draft / dynasty CSVs are not week-stamped and callers pass 0.
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "ecr_draft_qb.csv")
            _write(csv_p, "Player,Team\n")
            ev = validate_filename_week_consistency(csv_p, 0)
            self.assertEqual(ev["week"], 0)
            self.assertIsNone(ev["week_filename"])

    def test_draft_csv_with_nonzero_requested_week_fails_closed(self):
        # A draft CSV with caller --week=4 is a caller/snapshot mismatch;
        # we must not silently relabel.
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "ecr_draft_qb.csv")
            _write(csv_p, "Player,Team\n")
            with self.assertRaises(RuntimeError):
                validate_filename_week_consistency(csv_p, 4)


if __name__ == "__main__":
    unittest.main()