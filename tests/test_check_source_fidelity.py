#!/usr/bin/env python3
"""Tests for pipelines/check_source_fidelity.py (JEG-77 live puller).

Coverage:
    - parse_usatoday_tables: pure parser, no I/O.
    - live_extract_native: extracts {slug: value} for a fixture combo.
    - check_live_freshness: the concrete JEG-77 stale case from
      Jeremy's 2026-10-02 directive:
        * live Puka 62 vs fixture native 60.0 -> staleness failure
        * live JSN 73 vs native 73.0 -> pass
    - run_live_usatoday_check + main(): integration with mocked urllib
      (no network in tests -- the reviewer runs --live on real network).
    - ArgumentParser: --live, --live-combo, --live-tolerance wiring.
    - extract_page_title: pure title/H1/H2 extractor for week evidence.
    - page_week_evidence: fail-closed URL+title week-evidence gate
      (match / missing / conflict / mismatch).
    - run_live_usatoday_check integration with the week-evidence gate:
      a wrong-week page must NOT reach check_live_freshness.

All tests use synthetic HTML and a fake fetch_fn. No urllib, no browser,
no selenium/playwright. Hermetic.
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
import unittest.mock
from contextlib import redirect_stdout
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import check_source_fidelity as csf  # noqa: E402

# --- Synthetic USA Today article HTML ----------------------------------------
# Mirrors the real markup: <h2>...</h2> then <table class=gnt_ar_b_tbl>...
# Row layout: cells = [rank, name, ...values]. First value column aligns
# with headers[0].
SYNTHETIC_USATODAY_HTML = """\
<html><head><title>fantasy trade value chart week 4</title></head><body>
<h2>Week 4 fantasy trade charts</h2>
<table class=gnt_ar_b_tbl>
  <tr><th>1QB</th><th>6-TD</th><th>SFLEX</th></tr>
  <tr><td>1</td><td>Josh Allen</td><td>40</td><td>65</td><td>90</td></tr>
  <tr><td>2</td><td>Lamar Jackson</td><td>29</td><td>55</td><td>80</td></tr>
</table>
<h2>Week 4 running back trade value</h2>
<table class=gnt_ar_b_tbl>
  <tr><th>STD</th><th>HALF</th><th>PPR</th></tr>
  <tr><td>1</td><td>Jahmyr Gibbs</td><td>71</td><td>74</td><td>77</td></tr>
  <tr><td>2</td><td>Bijan Robinson</td><td>68</td><td>71</td><td>74</td></tr>
</table>
<h2>Week 4 wide receiver trade value</h2>
<table class=gnt_ar_b_tbl>
  <tr><th>STD</th><th>HALF</th><th>PPR</th></tr>
  <tr><td>1</td><td>Jaxon Smith-Njigba</td><td>70</td><td>73</td><td>76</td></tr>
  <tr><td>2</td><td>Puka Nacua</td><td>58</td><td>62</td><td>65</td></tr>
  <tr><td>3</td><td>Ja'Marr Chase</td><td>67</td><td>70</td><td>73</td></tr>
</table>
<h2>Week 4 tight end trade value</h2>
<table class=gnt_ar_b_tbl>
  <tr><th>STD</th><th>HALF</th><th>PPR</th></tr>
  <tr><td>1</td><td>Brock Bowers</td><td>32</td><td>36</td><td>40</td></tr>
  <tr><td>2</td><td>Trey McBride</td><td>40</td><td>46</td><td>52</td></tr>
</table>
</body></html>
"""

SYNTHETIC_SITEMAP = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.usatoday.com/story/sports/fantasy/2026/09/22/other-article/1/</loc></url>
  <url><loc>https://www.usatoday.com/story/sports/fantasy/2026/10/01/fantasy-trade-value-chart-week-4-ros-rankings/777/</loc></url>
</urlset>
"""


def make_fixture(half_12_native):
    """Build a minimal fixture-shaped dict with only the usatoday block.

    The check_live_freshness helper only reads sources.<source>.combos.<combo>.native
    so this minimal shape is enough for the staleness check.
    """
    return {
        "sources": {
            "usatoday": {
                "combos": {
                    "standard_12": {"native": {}},
                    "half_12": {"native": dict(half_12_native)},
                    "full_12": {"native": {}},
                }
            }
        }
    }


class FakeFetch:
    """Fake urllib-backed fetch function for tests (no network, ever)."""

    def __init__(self, mapping):
        # mapping: URL -> (status, body)
        self.mapping = dict(mapping)
        self.calls = []

    def __call__(self, url, *args, **kwargs):
        self.calls.append(url)
        if url not in self.mapping:
            return 404, ""
        return self.mapping[url]


class TestParseUsatodayTables(unittest.TestCase):
    """Pure parser tests -- no I/O."""

    def test_parses_all_four_position_tables(self):
        tables = csf.parse_usatoday_tables(SYNTHETIC_USATODAY_HTML)
        positions = [t["position"] for t in tables]
        self.assertEqual(positions, ["QB", "RB", "WR", "TE"])

    def test_qb_inferred_from_header_when_h2_is_section_heading(self):
        tables = csf.parse_usatoday_tables(SYNTHETIC_USATODAY_HTML)
        qb = next(t for t in tables if t["position"] == "QB")
        # Section heading "Week 4 fantasy trade charts" should be promoted
        # to "Quarterback Trade Value Chart" because headers carry 1QB.
        self.assertIn("Quarterback", qb["title"])
        self.assertEqual(qb["headers"], ["1QB", "6-TD", "SFLEX"])
        self.assertEqual(len(qb["rows"]), 2)

    def test_wr_rows_have_rank_name_value_shape(self):
        tables = csf.parse_usatoday_tables(SYNTHETIC_USATODAY_HTML)
        wr = next(t for t in tables if t["position"] == "WR")
        self.assertEqual(wr["headers"], ["STD", "HALF", "PPR"])
        # First row: rank=1, name="Jaxon Smith-Njigba", STD=70, HALF=73, PPR=76
        self.assertEqual(wr["rows"][0][0], "1")
        self.assertEqual(wr["rows"][0][1], "Jaxon Smith-Njigba")
        self.assertEqual(wr["rows"][0][2], "70")
        self.assertEqual(wr["rows"][0][3], "73")
        self.assertEqual(wr["rows"][0][4], "76")

    def test_returns_empty_when_table_mark_missing(self):
        self.assertEqual(csf.parse_usatoday_tables("<html>no tables</html>"), [])

    def test_skips_rows_without_digit_rank(self):
        html = (
            "<h2>Week 4 wide receiver trade value</h2>"
            "<table class=gnt_ar_b_tbl>"
            "<tr><th>HALF</th></tr>"
            "<tr><td>1</td><td>Real Player</td><td>50</td></tr>"
            "<tr><td>HEADER ROW</td><td>name</td><td>99</td></tr>"
            "</table>"
        )
        tables = csf.parse_usatoday_tables(html)
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0]["rows"]), 1)


class TestLiveExtractNative(unittest.TestCase):
    """Extract {slug: value} for one fixture combo."""

    def setUp(self):
        self.tables = csf.parse_usatoday_tables(SYNTHETIC_USATODAY_HTML)

    def test_half_combo_uses_half_column_for_non_qb(self):
        out = csf.live_extract_native(self.tables, "half_12")
        # Puka @52, JSN @55 from the synthetic HTML (not 60/73)
        self.assertEqual(out["puka nacua"], 62.0)  # JEG-77 stale case fixture=60, live=62
        self.assertEqual(out["jaxon smithnjigba"], 73.0)
        self.assertEqual(out["jamarr chase"], 70.0)

    def test_full_combo_uses_ppr_column(self):
        out = csf.live_extract_native(self.tables, "full_12")
        self.assertEqual(out["puka nacua"], 65.0)
        self.assertEqual(out["jaxon smithnjigba"], 76.0)

    def test_standard_combo_uses_std_column(self):
        out = csf.live_extract_native(self.tables, "standard_12")
        self.assertEqual(out["puka nacua"], 58.0)
        self.assertEqual(out["jahmyr gibbs"], 71.0)

    def test_qb_uses_1qb_for_all_combos(self):
        # save_usatoday_references IMPLIED rule: QB is reused for std/half/full.
        for combo in ("standard_12", "half_12", "full_12"):
            out = csf.live_extract_native(self.tables, combo)
            self.assertEqual(out["josh allen"], 40.0,
                             "QB 1QB value should be constant across combos for %s" % combo)
            self.assertEqual(out["lamar jackson"], 29.0)

    def test_unknown_combo_raises(self):
        with self.assertRaises(ValueError):
            csf.live_extract_native(self.tables, "ten_teams_standard")

    def test_slugs_match_fixture_native_keys(self):
        # The fixture stores keys like "jaxon smithnjigba" and "puka nacua"
        # (player_norm). The live extractor must produce exactly those keys,
        # otherwise check_live_freshness cannot match them.
        out = csf.live_extract_native(self.tables, "half_12")
        self.assertIn("jaxon smithnjigba", out)
        self.assertIn("puka nacua", out)

    def test_position_uninferable_tables_are_skipped(self):
        # Markup with a title that matches no LIVE_POS_BY_TITLE key and no
        # 1QB header to promote to QB. parse_usatoday_tables gives position=None.
        html = (
            "<h2>Week 4 something unfamiliar</h2>"
            "<table class=gnt_ar_b_tbl>"
            "<tr><th>HALF</th></tr>"
            "<tr><td>1</td><td>Lonely Player</td><td>10</td></tr>"
            "</table>"
        )
        tables = csf.parse_usatoday_tables(html)
        self.assertEqual(tables[0]["position"], None)
        self.assertEqual(csf.live_extract_native(tables, "half_12"), {})


class TestCheckLiveFreshness(unittest.TestCase):
    """The concrete JEG-77 stale case: live Puka 62 vs fixture native 60.0.

    Live JSN 73 vs native 73.0 must PASS (no failure)."""

    LIVE_HALF_NATIVE = {
        # Built from SYNTHETIC_USATODAY_HTML half column for WR (Puka=62, JSN=73).
        "jaxon smithnjigba": 73.0,
        "puka nacua": 62.0,
        "jamarr chase": 70.0,
        "jahmyr gibbs": 74.0,
        "bijan robinson": 71.0,
        "brock bowers": 36.0,
        "josh allen": 40.0,
        "lamar jackson": 29.0,
    }

    def test_jeg77_stale_puka_drift_caught(self):
        # Fixture has Puka at 60.0 (the pre-drift snapshot). Live has 62.
        # This is the canonical JEG-77 staleness case from Jeremy's
        # 2026-10-02 directive.
        fixture = make_fixture({"puka nacua": 60.0, "jaxon smithnjigba": 73.0})
        live_native_by_combo = {"half_12": self.LIVE_HALF_NATIVE}
        failures = csf.check_live_freshness(
            "usatoday", fixture, live_native_by_combo,
            combo="half_12", tolerance=0.0,
        )
        drift = [f for f in failures if f["type"] == "staleness_drift"]
        self.assertEqual(len(drift), 1, "expected exactly one drift failure")
        self.assertEqual(drift[0]["player"], "puka nacua")
        self.assertEqual(drift[0]["fixture_native"], 60.0)
        self.assertEqual(drift[0]["live"], 62.0)
        self.assertEqual(drift[0]["delta"], 2.0)

    def test_jeg77_puka_drift_message_mentions_publisher_update(self):
        fixture = make_fixture({"puka nacua": 60.0, "jaxon smithnjigba": 73.0})
        live_native_by_combo = {"half_12": self.LIVE_HALF_NATIVE}
        failures = csf.check_live_freshness(
            "usatoday", fixture, live_native_by_combo,
            combo="half_12", tolerance=0.0,
        )
        drift = [f for f in failures if f["type"] == "staleness_drift"]
        self.assertEqual(len(drift), 1)
        self.assertIn("Publisher updated", drift[0]["message"])

    def test_jsn_match_is_pass(self):
        # JSN is unchanged: fixture 73.0 == live 73. No drift failure.
        fixture = make_fixture({"puka nacua": 60.0, "jaxon smithnjigba": 73.0})
        live_native_by_combo = {"half_12": self.LIVE_HALF_NATIVE}
        failures = csf.check_live_freshness(
            "usatoday", fixture, live_native_by_combo,
            combo="half_12", tolerance=0.0,
        )
        jsn_failures = [f for f in failures if f.get("player") == "jaxon smithnjigba"]
        self.assertEqual(jsn_failures, [],
                         "JSN is equal in fixture and live -- must not flag")

    def test_combined_jeg77_outcome_puka_fail_jsn_pass(self):
        # Combined assertion: the test reviewer needs both the FAIL and
        # the PASS visible in the same run, per acceptance criteria.
        fixture = make_fixture({"puka nacua": 60.0, "jaxon smithnjigba": 73.0})
        live_native_by_combo = {"half_12": self.LIVE_HALF_NATIVE}
        failures = csf.check_live_freshness(
            "usatoday", fixture, live_native_by_combo,
            combo="half_12", tolerance=0.0,
        )
        by_player = {f.get("player"): f for f in failures
                     if f["type"] == "staleness_drift"}
        # Puka: stale, must fail.
        self.assertIn("puka nacua", by_player,
                      "Puka drift (fixture 60.0 vs live 62) MUST be flagged")
        # JSN: equal, must NOT be flagged.
        self.assertNotIn("jaxon smithnjigba", by_player,
                         "JSN (fixture 73.0 vs live 73) MUST pass")

    def test_missing_in_live_is_staleness(self):
        # Fixture has a slug that does not exist on the live page.
        fixture = make_fixture({"puka nacua": 60.0, "dropped player": 50.0})
        live_native_by_combo = {"half_12": self.LIVE_HALF_NATIVE}
        failures = csf.check_live_freshness(
            "usatoday", fixture, live_native_by_combo,
            combo="half_12", tolerance=0.0,
        )
        missing = [f for f in failures if f["type"] == "staleness_missing_in_live"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["player"], "dropped player")

    def test_live_extra_player_is_not_a_failure(self):
        # Live has a slug not in fixture -- not a failure (informational).
        # Puka is at live parity (62.0) so the only delta is the new player.
        live = dict(self.LIVE_HALF_NATIVE)
        live["newly published player"] = 12.0
        fixture = make_fixture({"puka nacua": 62.0, "jaxon smithnjigba": 73.0})
        failures = csf.check_live_freshness(
            "usatoday", fixture, {"half_12": live},
            combo="half_12", tolerance=0.0,
        )
        self.assertEqual(failures, [])

    def test_tolerance_zero_is_strict(self):
        # Any non-zero difference must trip drift at tolerance=0.0.
        fixture = make_fixture({"puka nacua": 60.0})
        failures = csf.check_live_freshness(
            "usatoday", fixture,
            {"half_12": {"puka nacua": 60.001}},
            combo="half_12", tolerance=0.0,
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["type"], "staleness_drift")

    def test_tolerance_can_absorb_small_drift(self):
        # A larger tolerance swallows the 0.001 difference.
        fixture = make_fixture({"puka nacua": 60.0})
        failures = csf.check_live_freshness(
            "usatoday", fixture,
            {"half_12": {"puka nacua": 60.001}},
            combo="half_12", tolerance=0.01,
        )
        self.assertEqual(failures, [])

    def test_strict_equality_passes_when_values_match(self):
        # 73.0 == 73 must be a clean pass (no failure).
        fixture = make_fixture({"jaxon smithnjigba": 73.0})
        failures = csf.check_live_freshness(
            "usatoday", fixture,
            {"half_12": {"jaxon smithnjigba": 73.0}},
            combo="half_12", tolerance=0.0,
        )
        self.assertEqual(failures, [])

    def test_wrong_combo_skipped(self):
        # If fixture only has half_12 native but we ask for full_12,
        # empty fixture native means no failures (not an error).
        fixture = make_fixture({"puka nacua": 60.0})
        failures = csf.check_live_freshness(
            "usatoday", fixture,
            {"full_12": {"puka nacua": 65.0}},
            combo="full_12", tolerance=0.0,
        )
        self.assertEqual(failures, [])


class TestLivePullUsatoday(unittest.TestCase):
    """End-to-end with mocked fetch (no network in tests, ever)."""

    def setUp(self):
        # Sitemap index URL not used by live_pull_usatoday directly (only
        # by discover_url); patch live_discover_url indirectly via fetch.
        self.fetch = FakeFetch({
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   datetime.now(timezone.utc).month): (200, SYNTHETIC_SITEMAP),
            "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
            "fantasy-trade-value-chart-week-4-ros-rankings/777/":
            (200, SYNTHETIC_USATODAY_HTML),
        })

    def test_full_pull_extracts_native_for_all_combos(self):
        result = csf.live_pull_usatoday(week=4, fetch_fn=self.fetch)
        self.assertEqual(result["source"], "usatoday")
        self.assertIn("native_by_combo", result)
        self.assertIn("week-4-ros-rankings", result["url"])
        self.assertEqual(result["n_tables"], 4)
        # half_12 -> Puka=62 from synthetic HTML
        self.assertEqual(result["native_by_combo"]["half_12"]["puka nacua"], 62.0)
        # full_12 -> Puka=65
        self.assertEqual(result["native_by_combo"]["full_12"]["puka nacua"], 65.0)
        # standard_12 -> Puka=58
        self.assertEqual(result["native_by_combo"]["standard_12"]["puka nacua"], 58.0)

    def test_full_pull_fail_closed_on_short_table_count(self):
        # Returned page has only 2 tables -> LivePullError.
        fetch = FakeFetch({
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   datetime.now(timezone.utc).month):
                (200, SYNTHETIC_SITEMAP),
            "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
            "fantasy-trade-value-chart-week-4-ros-rankings/777/":
            (200, "<h2>Week 4 wide receiver trade value</h2>"
                  "<table class=gnt_ar_b_tbl>"
                  "<tr><th>HALF</th></tr>"
                  "<tr><td>1</td><td>Lonely</td><td>10</td></tr>"
                  "</table>"),
        })
        with self.assertRaises(csf.LivePullError):
            csf.live_pull_usatoday(week=4, fetch_fn=fetch)

    def test_discover_fail_closed_on_no_url(self):
        # Sitemap has no matching URL -> LivePullError.
        empty_sitemap = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset></urlset>'
        )
        fetch = FakeFetch({
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   datetime.now(timezone.utc).month):
                (200, empty_sitemap),
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   max(1, datetime.now(timezone.utc).month - 1)):
                (200, empty_sitemap),
        })
        with self.assertRaises(csf.LivePullError):
            csf.live_discover_url(4, fetch_fn=fetch)


class TestRunLiveUsatodayCheck(unittest.TestCase):
    """Top-level wrapper used by main()."""

    def test_jeg77_stale_returns_one_failure_for_puka(self):
        fixture = make_fixture({"puka nacua": 60.0, "jaxon smithnjigba": 73.0})
        fetch = FakeFetch({
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   datetime.now(timezone.utc).month): (200, SYNTHETIC_SITEMAP),
            "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
            "fantasy-trade-value-chart-week-4-ros-rankings/777/":
            (200, SYNTHETIC_USATODAY_HTML),
        })
        live_pull, failures = csf.run_live_usatoday_check(
            fixture, week=4, fetch_fn=fetch,
            combo="half_12", tolerance=0.0,
        )
        self.assertNotIn("error", live_pull, "live pull should succeed")
        drift = [f for f in failures if f["type"] == "staleness_drift"]
        self.assertEqual(len(drift), 1)
        self.assertEqual(drift[0]["player"], "puka nacua")
        # JSN must NOT be in failures.
        jsn_failures = [f for f in failures
                        if f.get("player") == "jaxon smithnjigba"]
        self.assertEqual(jsn_failures, [])

    def test_live_pull_failure_is_reported_not_swallowed(self):
        fixture = make_fixture({})
        fetch = FakeFetch({})  # every URL returns 404/empty
        live_pull, failures = csf.run_live_usatoday_check(
            fixture, week=4, fetch_fn=fetch, combo="half_12",
        )
        self.assertIn("error", live_pull)
        self.assertTrue(any(f["type"] == "live_unavailable" for f in failures),
                        "LivePullError must surface as a live_unavailable failure")

    def test_live_extras_reported_in_live_pull(self):
        # Fixture doesn't know about "newly added" player; live has them.
        # Puka at live parity (62.0) so extras are the only delta.
        fixture = make_fixture({"puka nacua": 62.0, "jaxon smithnjigba": 73.0})
        fetch = FakeFetch({
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   datetime.now(timezone.utc).month): (200, SYNTHETIC_SITEMAP),
            "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
            "fantasy-trade-value-chart-week-4-ros-rankings/777/":
            (200, SYNTHETIC_USATODAY_HTML),
        })
        live_pull, failures = csf.run_live_usatoday_check(
            fixture, week=4, fetch_fn=fetch,
            combo="half_12", tolerance=0.0,
        )
        # Live has more WRs than fixture lists -- not a failure.
        self.assertIn("live_extra", live_pull)
        self.assertEqual(live_pull["live_extra"]["combo"], "half_12")
        self.assertGreaterEqual(live_pull["live_extra"]["count"], 1)
        # No failures from live extras.
        self.assertEqual(failures, [])


class TestExtractPageTitle(unittest.TestCase):
    """extract_page_title: pure HTML title/H1/H2 extractor.

    The week-evidence gate needs ONE strong title-shaped string to feed
    to page_week_evidence(). These tests pin the cascade: <title> wins,
    else <h1>, else first <h2>, else "".
    """

    def test_prefers_title_element(self):
        html = (
            "<html><head><title>Fantasy trade value chart week 4</title></head>"
            "<body><h1>Different h1</h1></body></html>"
        )
        self.assertEqual(
            csf.extract_page_title(html), "Fantasy trade value chart week 4")

    def test_falls_back_to_h1_when_no_title(self):
        html = (
            "<html><body><h1>Week 4 fantasy trade charts</h1>"
            "<h2>Week 4 wide receiver</h2></body></html>"
        )
        self.assertEqual(
            csf.extract_page_title(html), "Week 4 fantasy trade charts")

    def test_falls_back_to_first_h2(self):
        html = (
            "<html><body>"
            "<h2>Week 4 running back trade value</h2>"
            "<h2>Week 4 wide receiver trade value</h2>"
            "</body></html>"
        )
        self.assertEqual(
            csf.extract_page_title(html),
            "Week 4 running back trade value")

    def test_strips_inner_tags_in_title(self):
        html = (
            "<html><head><title>Week <b>4</b> fantasy trade charts</title>"
            "</head><body></body></html>"
        )
        self.assertEqual(
            csf.extract_page_title(html), "Week 4 fantasy trade charts")

    def test_empty_html_returns_empty_string(self):
        self.assertEqual(csf.extract_page_title(""), "")

    def test_html_with_no_title_or_headings_returns_empty_string(self):
        self.assertEqual(csf.extract_page_title("<html><body></body></html>"), "")


class TestPageWeekEvidence(unittest.TestCase):
    """page_week_evidence: fail-closed URL+title week-evidence gate.

    Four acceptance cases per the JEG-77 brief:
        1. match       -> returns int week
        2. missing     -> WeekEvidenceError (URL or title empty / no match)
        3. conflict    -> WeekEvidenceError (URL says week 4, title says 5)
        (mismatch with expected week is checked by the caller -- the
         function itself just compares URL and title.)
    """

    GOOD_URL = (
        "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
        "fantasy-trade-value-chart-week-4-ros-rankings/777/")
    GOOD_TITLE = "Week 4 fantasy trade charts"

    # --- case 1: match ---------------------------------------------------------
    def test_match_returns_int_week(self):
        self.assertEqual(
            csf.page_week_evidence(self.GOOD_URL, self.GOOD_TITLE), 4)

    def test_match_accepts_uppercase_url_slug(self):
        url = ("https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
               "fantasy-trade-value-chart-WEEK-5-ros-rankings/777/")
        title = "Week 5 wide receiver trade value"
        self.assertEqual(csf.page_week_evidence(url, title), 5)

    def test_match_accepts_alternate_title_phrasing(self):
        # "fantasy trade value chart week N" phrasing.
        title = "Fantasy trade value chart week 7 - ROS rankings"
        url = ("https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
               "fantasy-trade-value-chart-week-7-ros-rankings/777/")
        self.assertEqual(csf.page_week_evidence(url, title), 7)

    def test_returns_int_not_str(self):
        result = csf.page_week_evidence(self.GOOD_URL, self.GOOD_TITLE)
        self.assertIsInstance(result, int)

    def test_week_evidence_error_is_a_live_pull_error(self):
        # WeekEvidenceError must subclass LivePullError so existing
        # callers that catch LivePullError handle it the same way.
        err = csf.WeekEvidenceError("boom")
        self.assertIsInstance(err, csf.LivePullError)

    # --- case 2: missing -------------------------------------------------------
    def test_missing_url_raises(self):
        with self.assertRaises(csf.WeekEvidenceError) as ctx:
            csf.page_week_evidence("", self.GOOD_TITLE)
        self.assertIn("missing URL", str(ctx.exception))

    def test_none_url_raises(self):
        with self.assertRaises(csf.WeekEvidenceError):
            csf.page_week_evidence(None, self.GOOD_TITLE)

    def test_url_without_slug_raises(self):
        # URL is real-looking but lacks the trade-value-chart-week-N-ros-rankings slug.
        bad_url = ("https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
                   "random-article/777/")
        with self.assertRaises(csf.WeekEvidenceError) as ctx:
            csf.page_week_evidence(bad_url, self.GOOD_TITLE)
        self.assertIn("missing URL week evidence", str(ctx.exception))

    def test_missing_title_raises(self):
        with self.assertRaises(csf.WeekEvidenceError) as ctx:
            csf.page_week_evidence(self.GOOD_URL, "")
        self.assertIn("missing page title", str(ctx.exception))

    def test_none_title_raises(self):
        with self.assertRaises(csf.WeekEvidenceError):
            csf.page_week_evidence(self.GOOD_URL, None)

    def test_title_without_week_phrasing_raises(self):
        # Title has no "week N" phrasing at all.
        title = "Fantasy football trade value chart - ROS rankings"
        with self.assertRaises(csf.WeekEvidenceError) as ctx:
            csf.page_week_evidence(self.GOOD_URL, title)
        self.assertIn("missing title week evidence", str(ctx.exception))

    # --- case 3: conflict ------------------------------------------------------
    def test_conflict_url_4_title_5_raises(self):
        # URL says week 4 but title says week 5 -- the exact scenario from
        # the JEG-77 brief.
        with self.assertRaises(csf.WeekEvidenceError) as ctx:
            csf.page_week_evidence(self.GOOD_URL, "Week 5 fantasy trade charts")
        msg = str(ctx.exception)
        self.assertIn("conflicting", msg)
        self.assertIn("week 4", msg)
        self.assertIn("week 5", msg)

    def test_conflict_url_5_title_4_raises(self):
        url_w5 = ("https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
                  "fantasy-trade-value-chart-week-5-ros-rankings/777/")
        with self.assertRaises(csf.WeekEvidenceError):
            csf.page_week_evidence(url_w5, self.GOOD_TITLE)


class TestRunLiveUsatodayWeekGate(unittest.TestCase):
    """Integration: the week-evidence gate in run_live_usatoday_check.

    The gate runs BEFORE check_live_freshness. A wrong-week page must
    fail closed (live_unavailable failure, no native comparison run),
    so a stale sitemap or stale CDN cannot silently compare week-N
    values against week-M fixture natives.
    """

    BASE_URL_W4 = (
        "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
        "fantasy-trade-value-chart-week-4-ros-rankings/777/")
    BASE_URL_W5 = (
        "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
        "fantasy-trade-value-chart-week-5-ros-rankings/777/")

    def _html_with_title(self, title_text, table_title_prefix="Week 4"):
        """Synthetic USA Today article whose <title> is `title_text`."""
        return (
            "<html><head><title>%s</title></head><body>"
            "<h2>%s wide receiver trade value</h2>"
            "<table class=gnt_ar_b_tbl>"
            "<tr><th>HALF</th></tr>"
            "<tr><td>1</td><td>Player</td><td>50</td></tr>"
            "</table>"
            "</body></html>" % (title_text, table_title_prefix))

    def _fetch_for_url(self, url, html):
        return FakeFetch({
            csf.LIVE_SITEMAP_MONTH
                % (datetime.now(timezone.utc).year,
                   datetime.now(timezone.utc).month):
                (200, '<?xml version="1.0" encoding="UTF-8"?>'
                      '<urlset>'
                      '<url><loc>%s</loc></url>'
                      '</urlset>' % url),
            url: (200, html),
        })

    def test_matching_week_passes_gate_and_compares(self):
        # URL and title both say week 4; expected week 4 -> gate passes,
        # comparison runs. Puka live 60 vs fixture 60 -> no drift.
        fixture = make_fixture({"puka nacua": 60.0})
        html = self._html_with_title("Week 4 fantasy trade charts")
        live_pull, failures = csf.run_live_usatoday_check(
            fixture, week=4,
            fetch_fn=self._fetch_for_url(self.BASE_URL_W4, html),
            combo="half_12", tolerance=0.0,
        )
        week_gate_failures = [f for f in failures
                              if "week evidence gate" in f.get("message", "")]
        self.assertEqual(week_gate_failures, [])

    def test_url_title_conflict_fails_closed(self):
        # URL says week 4 but page title says week 5 -> WeekEvidenceError
        # -> live_unavailable failure, no comparison done.
        # We patch live_pull_usatoday so we can exercise the gate
        # without needing a full 4-table article.
        fixture = make_fixture({"puka nacua": 60.0})
        fake_pull = {
            "source": "usatoday",
            "url": self.BASE_URL_W4,
            "page_title": "Week 5 fantasy trade charts",
            "fetched_at": "2026-10-04T00:00:00+00:00",
            "tables": [],
            "native_by_combo": {"half_12": {"puka nacua": 60.0}},
            "n_tables": 0,
            "n_rows": 0,
        }
        original = csf.live_pull_usatoday
        csf.live_pull_usatoday = lambda **kw: fake_pull
        try:
            live_pull, failures = csf.run_live_usatoday_check(
                fixture, week=4, fetch_fn=lambda *a, **k: (200, ""),
                combo="half_12", tolerance=0.0,
            )
        finally:
            csf.live_pull_usatoday = original
        gate_failures = [f for f in failures if f["type"] == "live_unavailable"]
        self.assertEqual(len(gate_failures), 1)
        self.assertIn("week evidence gate", gate_failures[0]["message"])
        # The comparison must NOT have run.
        drift = [f for f in failures if f["type"] == "staleness_drift"]
        self.assertEqual(drift, [],
                         "comparison must not run when week evidence conflicts")

    def test_mismatch_with_expected_week_fails_closed(self):
        # URL and title both say week 5 but caller asked for week 4 ->
        # fail closed with a live_unavailable message that names both
        # observed and expected weeks.
        #
        # We patch live_pull_usatoday directly: live_discover_url(week=4)
        # would otherwise search for a week-4 URL and miss our week-5
        # URL. The gate, not the discovery layer, is what we're testing.
        fixture = make_fixture({"puka nacua": 60.0})
        html = self._html_with_title(
            "Week 5 fantasy trade charts", table_title_prefix="Week 5")
        fake_pull = {
            "source": "usatoday",
            "url": self.BASE_URL_W5,
            "page_title": "Week 5 fantasy trade charts",
            "fetched_at": "2026-10-04T00:00:00+00:00",
            "tables": csf.parse_usatoday_tables(
                self._html_with_title(
                    "Week 5 fantasy trade charts",
                    table_title_prefix="Week 5")),
            "native_by_combo": {"half_12": {"puka nacua": 60.0}},
            "n_tables": 1,
            "n_rows": 1,
        }
        original = csf.live_pull_usatoday
        csf.live_pull_usatoday = lambda **kw: fake_pull
        try:
            live_pull, failures = csf.run_live_usatoday_check(
                fixture, week=4,
                fetch_fn=lambda *a, **k: (200, html),
                combo="half_12", tolerance=0.0,
            )
        finally:
            csf.live_pull_usatoday = original
        gate_failures = [f for f in failures if f["type"] == "live_unavailable"]
        self.assertEqual(len(gate_failures), 1)
        msg = gate_failures[0]["message"]
        self.assertIn("page is week 5", msg)
        self.assertIn("expected week 4", msg)
        drift = [f for f in failures if f["type"] == "staleness_drift"]
        self.assertEqual(drift, [])

    def test_missing_url_evidence_fails_closed(self):
        # URL has no slug -> WeekEvidenceError -> live_unavailable.
        # We patch live_pull_usatoday directly because live_discover_url
        # would otherwise reject the no-slug URL before we could test
        # the gate. The gate is what we're testing, not discovery.
        fixture = make_fixture({})
        no_slug_url = ("https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
                       "random-article/777/")
        fake_pull = {
            "source": "usatoday",
            "url": no_slug_url,
            "page_title": "Week 4 fantasy trade charts",
            "fetched_at": "2026-10-04T00:00:00+00:00",
            "tables": [],
            "native_by_combo": {"half_12": {}},
            "n_tables": 0,
            "n_rows": 0,
        }
        original = csf.live_pull_usatoday
        csf.live_pull_usatoday = lambda **kw: fake_pull
        try:
            live_pull, failures = csf.run_live_usatoday_check(
                fixture, week=4, fetch_fn=lambda *a, **k: (200, ""),
                combo="half_12", tolerance=0.0,
            )
        finally:
            csf.live_pull_usatoday = original
        gate_failures = [f for f in failures if f["type"] == "live_unavailable"]
        self.assertGreaterEqual(len(gate_failures), 1)
        msg = " ".join(f["message"] for f in gate_failures)
        self.assertIn("week evidence gate failed", msg)

    def test_gate_blocks_comparison_under_negative_test(self):
        # Standing-rule negative test: if the gate were removed, this
        # fixture (page says week 5, expected week 4) would silently
        # produce staleness_drift failures on whatever values the page
        # has. With the gate wired, it produces ONE live_unavailable
        # failure and zero drift. If someone removes the gate, the
        # count of drift failures would jump from 0 to > 0.
        fixture = make_fixture({"puka nacua": 60.0})
        live = {
            "jaxon smithnjigba": 99.0,
            "puka nacua": 99.0,
        }
        fake_pull = {
            "source": "usatoday",
            "url": self.BASE_URL_W5,
            "page_title": "Week 5 fantasy trade charts",
            "fetched_at": "2026-10-04T00:00:00+00:00",
            "tables": [],
            "native_by_combo": {"half_12": live},
            "n_tables": 0,
            "n_rows": 0,
        }
        original = csf.live_pull_usatoday
        csf.live_pull_usatoday = lambda **kw: fake_pull
        try:
            live_pull, failures = csf.run_live_usatoday_check(
                fixture, week=4, fetch_fn=lambda *a, **k: (200, ""),
                combo="half_12", tolerance=0.0,
            )
        finally:
            csf.live_pull_usatoday = original
        drift = [f for f in failures if f["type"] == "staleness_drift"]
        self.assertEqual(drift, [],
                         "gate MUST prevent check_live_freshness from running")
        gate_failures = [f for f in failures if f["type"] == "live_unavailable"]
        self.assertEqual(len(gate_failures), 1)


class TestLiveFetchUsesUrllib(unittest.TestCase):
    """Prove the live puller uses urllib, not browser tooling."""

    def test_live_fetch_signature_uses_urlopen(self):
        # The default opener is urllib.request.urlopen. A failure when
        # urllib can't reach the network must surface as LivePullError,
        # not a TypeError from selenium/playwright.
        import inspect
        import urllib.request

        src = inspect.getsource(csf.live_fetch)
        self.assertIn("urllib.request", src)
        self.assertIn("urlopen", src)
        # And the default opener callable, when introspected, is None
        # (keyword-only args live in __kwdefaults__, not __defaults__).
        self.assertIs(csf.live_fetch.__kwdefaults__["opener"], None)

    def test_no_browser_imports(self):
        import inspect
        import check_source_fidelity
        src = inspect.getsource(check_source_fidelity)
        # Only import statements count: the module legitimately mentions
        # selenium/playwright in comments explaining what it does NOT use.
        import_lines = [
            line for line in src.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for banned in ("selenium", "playwright", "pyppeteer", "requests_html"):
            for line in import_lines:
                self.assertNotIn(banned, line,
                                 "%s must not be imported by check_source_fidelity" % banned)


class TestMainArgparse(unittest.TestCase):
    """main() wiring: --live, --live-combo, --live-tolerance."""

    def test_argparse_accepts_live_flag(self):
        # Run main() with --live against the synthetic pull and a fixture
        # whose Puka is 60.0. Puka drifts on live -> exit 1.
        fixture = make_fixture({"puka nacua": 60.0, "jaxon smithnjigba": 73.0})
        # main() searches for the current NFL week's article; the synthetic
        # sitemap is the Week 4 chart, so pin the week (2026-10-08: this went
        # red when the real calendar reached Week 5).
        import nfl_week
        with csf._patch_fixture(fixture), \
                unittest.mock.patch.object(nfl_week, "current_nfl_week", lambda *a, **k: 4):
            fetch = FakeFetch({
                csf.LIVE_SITEMAP_MONTH
                    % (datetime.now(timezone.utc).year,
                       datetime.now(timezone.utc).month): (200, SYNTHETIC_SITEMAP),
                "https://www.usatoday.com/story/sports/fantasy/2026/10/01/"
                "fantasy-trade-value-chart-week-4-ros-rankings/777/":
                (200, SYNTHETIC_USATODAY_HTML),
            })
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = csf.main([
                    "--source", "usatoday", "--live",
                    "--live-combo", "half_12", "--live-tolerance", "0.0",
                    "--json",
                ], fetch_fn=fetch)
            self.assertEqual(rc, 1,
                             "main() must exit 1 when staleness drift is found")
            report = json.loads(buf.getvalue())
            self.assertTrue(report["live"])
            self.assertEqual(report["live_combo"], "half_12")
            self.assertGreaterEqual(report["n_failures"], 1)
            players = [f["player"] for f in report["failures"]
                       if f["type"] == "staleness_drift"]
            self.assertIn("puka nacua", players)
            self.assertNotIn("jaxon smithnjigba", players)

    def test_argparse_help_lists_live_flag(self):
        # argparse help text must document --live (this is what the
        # docstring promises but the original code didn't have).
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                csf.main(["--help"])
            except SystemExit:
                pass
        help_text = buf.getvalue()
        self.assertIn("--live", help_text)
        self.assertIn("--live-combo", help_text)
        self.assertIn("--live-tolerance", help_text)


# --- Fixture monkey-patch helper (test isolation) ----------------------------

import contextlib  # noqa: E402


class _PatchFixture:
    """Context manager that redirects FIXTURE.read_text() inside main()."""

    def __init__(self, fixture_dict):
        self.fixture_dict = fixture_dict

    @contextlib.contextmanager
    def _patch(self):
        original = csf.FIXTURE
        csf.FIXTURE = _InMemoryFixturePath(self.fixture_dict)
        try:
            yield
        finally:
            csf.FIXTURE = original


class _InMemoryFixturePath:
    """Stand-in for FIXTURE whose read_text returns JSON of fixture_dict."""

    def __init__(self, fixture_dict):
        self._text = json.dumps(fixture_dict)

    def read_text(self, *args, **kwargs):
        return self._text


# Attach the helper as an attribute on the module so tests can use it
# as a context manager.
csf._patch_fixture = lambda fixture_dict: _PatchFixture(fixture_dict)._patch()


if __name__ == "__main__":
    unittest.main()