#!/usr/bin/env python3
"""Negative tests for the source-pull watchdog (ops/watchdog/).

Each test simulates the historical miss the check must catch:
a failed pull, a stale snapshot, a changed article URL, a missing CBS
source, a poisoned artifact. Stdlib unittest; hermetic (tmp dirs, mocked
fetch) — no network, no dependency on live pull outputs.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "ops", "watchdog"))
import pull_watchdog as wd
import pull_usatoday as usat
import pull_cbs as cbs
from _common import REPO, classify_run_line, todays_run_lines

DAY = date(2026, 9, 22)  # a Tuesday; nfl_week == 2


def _write(path, text, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _ts(days_ago=0, hour=6, minute=10):
    base = datetime(2026, 9, 22, hour, minute, tzinfo=timezone.utc)
    return (base - timedelta(days=days_ago)).timestamp()


def _age_ts(days_ago=0, hour=6, minute=10):
    """An mtime `days_ago` old RIGHT NOW, for fixtures whose freshness the
    check measures with age_days().

    The checks take an explicit `day` but measure age against the real clock,
    so a fixture stamped relative to the frozen scenario day drifts further
    from it every day the suite is not run. That is what broke
    test_non_wednesday_allows_weekly_cadence on 2026-09-25: a snapshot written
    as "5 days old" was really 8 days old, crossed the 7-day non-Wednesday
    limit, and took `make validate` -- and the Pages deploy behind it -- down
    on an unrelated commit.

    The weekday still comes from the frozen DAY, the age from here. They are
    independent inputs to the check, so the scenario keeps its meaning.
    """
    base = datetime.now(timezone.utc).replace(hour=hour, minute=minute,
                                              second=0, microsecond=0)
    return (base - timedelta(days=days_ago)).timestamp()


def _daily_cfg(tmp, log_text, csv_rows=500, csv_age_days=0,
               vintage="2026-09-21", n_priced=500, log_age_days=0):
    csv_p = os.path.join(tmp, "s.csv")
    _write(csv_p, "a,b\n" + "1,2\n" * csv_rows, mtime=_ts(csv_age_days))
    meta_p = os.path.join(tmp, "meta.json")
    _write(meta_p, json.dumps({"vintage": vintage, "n_priced": n_priced}))
    log_p = os.path.join(tmp, "runs.log")
    _write(log_p, log_text, mtime=_ts(log_age_days, 7, 0))
    return {"label": "T", "expected": "daily 06:00 CT", "csv": csv_p,
            "meta": meta_p, "log": log_p, "min_rows": 400}


class TestRunLogClassification(unittest.TestCase):
    def test_watchdog_repo_path_is_this_checkout(self):
        self.assertEqual(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            os.path.abspath(REPO),
        )

    def test_failed_token_detected(self):
        self.assertEqual(classify_run_line(
            "2026-09-22 06:20 CDT | FAILED | source=razzball; pull failed"), "failed")

    def test_player_name_cannot_trip_failed(self):
        # 'failed' inside a player-name-ish token must not classify as failed.
        self.assertNotEqual(classify_run_line(
            "2026-09-22 06:10 CDT | SUCCESS: notes=unfailed-check ok"), "failed")

    def test_no_update_is_healthy(self):
        self.assertEqual(classify_run_line(
            "2026-09-22 06:10 CDT | SUCCESS: no update, snapshot current"), "unchanged")

    def test_failed_then_recovered_same_day_is_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "runs.log")
            _write(p, "2026-09-22 06:20 CDT | FAILED | boom\n"
                      "2026-09-22 06:21 CDT | OK | recovered\n")
            state, _ = todays_run_lines(p, DAY)
            self.assertEqual(state, "ok")

    def test_failed_with_no_recovery_is_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "runs.log")
            _write(p, "2026-09-22 06:20 CDT | FAILED | boom\n")
            state, _ = todays_run_lines(p, DAY)
            self.assertEqual(state, "failed")


class TestDailyChecks(unittest.TestCase):
    def test_failed_pull_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _daily_cfg(tmp, "2026-09-22 06:10 CDT | pull | FAILED | 403\n",
                             csv_age_days=1)
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "failed")
            self.assertIn("FAILED", v["detail"])

    def test_unchanged_source_is_healthy_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _daily_cfg(tmp, "2026-09-22 06:10 CDT | pull | SUCCESS: no update, snapshot current\n")
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "unchanged")

    def test_did_not_run_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _daily_cfg(tmp, "2026-09-21 06:10 CDT | pull | SUCCESS\n",
                             csv_age_days=1)
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "stale")

    def test_zero_rows_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _daily_cfg(tmp, "2026-09-22 06:10 CDT | pull | SUCCESS\n",
                             csv_rows=0)
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "failed")

    def test_zero_priced_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _daily_cfg(tmp, "2026-09-22 06:10 CDT | pull | SUCCESS\n",
                             n_priced=0)
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "failed")
            self.assertIn("n_priced", v["detail"])

    def test_fail_closed_holds_when_artifact_older_than_failure(self):
        # Failed run at 06:10 today; artifact last written yesterday ->
        # the failed pull did NOT poison downstream.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _daily_cfg(tmp, "2026-09-22 06:10 CDT | pull | FAILED | boom\n",
                             csv_age_days=1)
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "failed")
            self.assertTrue(v["fail_closed"])

    def test_poisoned_artifact_is_critical(self):
        # Failed run at 06:10 today but the artifact was rewritten at 06:15
        # -> the failure poisoned downstream; must be flagged CRITICAL.
        with tempfile.TemporaryDirectory() as tmp:
            csv_p = os.path.join(tmp, "s.csv")
            _write(csv_p, "a,b\n" + "1,2\n" * 10,
                   mtime=_ts(0, 11, 15))  # rewritten AFTER the failure (log stamps are CT)
            meta_p = os.path.join(tmp, "meta.json")
            _write(meta_p, json.dumps({"vintage": "2026-09-22", "n_priced": 10}))
            log_p = os.path.join(tmp, "runs.log")
            _write(log_p, "2026-09-22 06:10 CDT | pull | FAILED | boom\n")
            cfg = {"label": "T", "expected": "daily", "csv": csv_p,
                   "meta": meta_p, "log": log_p, "min_rows": 5}
            v = wd.check_daily(cfg, DAY)
            self.assertEqual(v["status"], "failed")
            self.assertFalse(v["fail_closed"])
            self.assertIn("CRITICAL", v["detail"])


class TestWeeklyArticleChecks(unittest.TestCase):
    def _cache(self, tmp, week, age_days, tables=4, rows_per=40):
        p = os.path.join(tmp, "u.json")
        payload = {
            "fetched_at": "2026-09-21T14:00:00Z",
            "url": ("https://x/y/fantasy-football-trade-value-chart-week-%d-"
                    "ros-rankings/123/" % week),
            "tables": [{"title": "QB", "headers": [], "rows": [["1"] * 3] * rows_per}
                       for _ in range(tables)],
        }
        _write(p, json.dumps(payload), mtime=_age_ts(age_days))
        return p

    def test_current_week_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly",
                   "cache": self._cache(tmp, 2, 1)}
            v = wd.check_weekly_article(cfg, DAY, 2)
            self.assertEqual(v["status"], "ok")

    def test_last_week_not_yet_published_is_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly",
                   "cache": self._cache(tmp, 1, 1)}
            v = wd.check_weekly_article(cfg, DAY, 2)
            self.assertEqual(v["status"], "unchanged")

    def test_stale_article_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly",
                   "cache": self._cache(tmp, 1, 10)}
            v = wd.check_weekly_article(cfg, DAY, 3)
            self.assertEqual(v["status"], "stale")

    def test_missing_cache_is_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly",
                   "cache": os.path.join(tmp, "nope.json")}
            v = wd.check_weekly_article(cfg, DAY, 2)
            self.assertEqual(v["status"], "failed")

    def test_thin_tables_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly",
                   "cache": self._cache(tmp, 2, 1, tables=1, rows_per=5)}
            v = wd.check_weekly_article(cfg, DAY, 2)
            self.assertEqual(v["status"], "failed")


class TestFantasyCalcWednesday(unittest.TestCase):
    def _fc(self, tmp, combo_age_days, n_rows=210):
        snap = {"week": "Week 2",
                "combos": ["half_12_qb1", "half_12_qb2"]}
        _write(os.path.join(tmp, "fantasycalc_snapshot.json"),
               json.dumps(snap), mtime=_age_ts(combo_age_days))
        for c in snap["combos"]:
            _write(os.path.join(tmp, "fantasycalc_%s.json" % c),
                   json.dumps({"fetched_at": "2026-09-16T14:00:48Z",
                               "rows": [{"name": "P%d" % i, "pos": "RB",
                                         "value": 100.0} for i in range(n_rows)]}),
                   mtime=_age_ts(combo_age_days))
        old = wd.CACHE
        wd.CACHE = tmp
        return old

    def test_wednesday_requires_this_weeks_snapshot(self):
        wednesday = date(2026, 9, 23)
        with tempfile.TemporaryDirectory() as tmp:
            old = self._fc(tmp, 5)  # 5 days old
            try:
                v = wd.check_fantasycalc(wednesday, 3)
            finally:
                wd.CACHE = old
            self.assertEqual(v["status"], "stale")

    def test_non_wednesday_allows_weekly_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = self._fc(tmp, 5)
            try:
                v = wd.check_fantasycalc(DAY, 2)  # Tuesday
            finally:
                wd.CACHE = old
            self.assertEqual(v["status"], "ok")

    def test_legacy_dead_file_is_never_checked(self):
        # 2026-09-22 live miss: the check read the dead legacy
        # fantasycalc_half_12.json (frozen since 2026-09-16 cache split)
        # while the real per-combo files were fresh. A fresh legacy file
        # must not mask missing real artifacts, and a stale legacy file
        # must not stale a fresh real snapshot.
        with tempfile.TemporaryDirectory() as tmp:
            old = self._fc(tmp, 1)
            try:
                _write(os.path.join(tmp, "fantasycalc_half_12.json"),
                       json.dumps([{"x": 1}] * 10), mtime=_age_ts(0))
                self.assertEqual(wd.check_fantasycalc(DAY, 2)["status"], "ok")
                os.remove(os.path.join(tmp, "fantasycalc_half_12_qb1.json"))
                self.assertEqual(wd.check_fantasycalc(DAY, 2)["status"],
                                 "failed")
            finally:
                wd.CACHE = old

    def test_zero_rows_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = self._fc(tmp, 1, n_rows=0)
            try:
                v = wd.check_fantasycalc(DAY, 2)
            finally:
                wd.CACHE = old
            self.assertEqual(v["status"], "failed")

    def test_missing_combo_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = self._fc(tmp, 1)
            try:
                os.remove(os.path.join(tmp, "fantasycalc_half_12_qb2.json"))
                v = wd.check_fantasycalc(DAY, 2)
            finally:
                wd.CACHE = old
            self.assertEqual(v["status"], "failed")


class TestSupabaseLanded(unittest.TestCase):
    def _health_file(self, tmp, sources):
        p = os.path.join(tmp, "source-import-health.json")
        _write(p, json.dumps({"schema": "trade-value-import-health-v1",
                              "sources": sources}))
        return p

    def test_missing_file_is_pending_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = wd.IMPORT_HEALTH
            wd.IMPORT_HEALTH = os.path.join(tmp, "nope.json")
            try:
                landed, *_ = wd.supabase_landed("usatoday")
            finally:
                wd.IMPORT_HEALTH = old
            self.assertEqual(landed, "pending")

    def test_ok_source_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._health_file(tmp, {"usatoday": {
                "status": "ok", "content_vintage": "2026-09-15",
                "last_successful_import": "2026-09-22T02:00:00Z",
                "failure_reason": None}})
            old = wd.IMPORT_HEALTH
            wd.IMPORT_HEALTH = p
            try:
                landed, status, vintage, imported, failure = wd.supabase_landed("usatoday")
            finally:
                wd.IMPORT_HEALTH = old
            self.assertTrue(landed)
            self.assertEqual(status, "ok")
            self.assertEqual(vintage, "2026-09-15")
            self.assertIsNone(failure)

    def test_stale_vintage_still_counts_as_landed(self):
        # Staleness is about the source's vintage, not the import: a stale
        # source still verified its bytes, so it landed.
        with tempfile.TemporaryDirectory() as tmp:
            p = self._health_file(tmp, {"cbs": {
                "status": "stale", "content_vintage": "Week 2",
                "last_successful_import": "2026-09-22T02:00:00Z",
                "failure_reason": "STALE_VINTAGE: ..."}})
            old = wd.IMPORT_HEALTH
            wd.IMPORT_HEALTH = p
            try:
                landed, status, vintage, imported, failure = wd.supabase_landed("cbs")
            finally:
                wd.IMPORT_HEALTH = old
            self.assertTrue(landed)
            self.assertEqual(status, "stale")
            self.assertIsNotNone(failure)

    def test_failed_source_not_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._health_file(tmp, {"espn": {
                "status": "failed", "content_vintage": None,
                "last_successful_import": None,
                "failure_reason": "ZERO_ROWS: ..."}})
            old = wd.IMPORT_HEALTH
            wd.IMPORT_HEALTH = p
            try:
                landed, status, vintage, imported, failure = wd.supabase_landed("espn")
            finally:
                wd.IMPORT_HEALTH = old
            self.assertFalse(landed)


# --- USA Today discovery (mocked fetch) -------------------------------------

def _sitemap_fetch(url):
    """Serve the article from whichever monthly sitemap discovery asks for.

    discover_url builds the sitemap URL from the CURRENT month, so pinning the
    mock to "web-sitemap-2026-09" made the test pass only during September:
    from 2026-10-01 it 404s and discovery fails closed on a fixture that was
    meant to succeed. Matching the shape instead of the month keeps the test
    about discovery, not about what month it is run in.
    """
    if re.search(r"web-sitemap-\d{4}-\d{2}", url):
        return (200, "<urlset><url><loc>https://www.usatoday.com/story/sports/fantasy/football/"
                     "2026/09/22/fantasy-football-trade-value-chart-week-3-"
                     "ros-rankings/999/</loc></url></urlset>")
    return (404, "")


class TestUsatodayDiscovery(unittest.TestCase):
    def test_discovers_new_article_url(self):
        url = usat.discover_url(3, fetch_fn=_sitemap_fetch)
        self.assertIn("week-3-ros-rankings", url)
        self.assertIn("999/", url)

    def test_discovery_fails_closed_when_nothing_found(self):
        with self.assertRaises(usat.DiscoveryFailed):
            usat.discover_url(3, fetch_fn=lambda u: (404, ""))

    def test_pull_rejects_markup_mismatch(self):
        with self.assertRaises(RuntimeError):
            usat.pull("https://example.com/x",
                      fetch_fn=lambda u: (200, "<html>no tables here</html>"))

    def test_pull_parses_tables(self):
        html = "".join(
            '<h2 class=gnt_ar_b_h2>Quarterback Trade Value Chart</h2>'
            '<table class=gnt_ar_b_tbl><tr><th>Rank</th><th>Player</th><th>1QB</th></tr>'
            '<tr><td>1</td><td>Josh Allen</td><td>33.2</td></tr></table>'
            for _ in range(4))
        tables = usat.pull("https://example.com/x",
                           fetch_fn=lambda u: (200, html))
        self.assertEqual(len(tables), 4)
        self.assertEqual(tables[0]["rows"][0][1], "Josh Allen")

    def test_pull_inferrs_qb_from_week3_generic_heading(self):
        html = (
            '<h2 class=gnt_ar_b_h2>Week 3 fantasy trade charts</h2>'
            '<table class=gnt_ar_b_tbl><tr><th>RK</th><th>Player</th><th>1QB</th><th>6/TD</th><th>SFLEX</th></tr>'
            '<tr><td>1</td><td>Josh Allen</td><td>33.2</td><td>38.0</td><td>66.0</td></tr></table>'
            '<h2 class=gnt_ar_b_h2>Running back trade value chart</h2>'
            '<table class=gnt_ar_b_tbl><tr><th>RK</th><th>Player</th><th>STD</th></tr>'
            '<tr><td>1</td><td>Bijan Robinson</td><td>77</td></tr></table>'
            '<h2 class=gnt_ar_b_h2>Wide receiver trade value chart</h2>'
            '<table class=gnt_ar_b_tbl><tr><th>RK</th><th>Player</th><th>STD</th></tr>'
            '<tr><td>1</td><td>JaMarr Chase</td><td>75</td></tr></table>'
            '<h2 class=gnt_ar_b_h2>Tight end trade value chart</h2>'
            '<table class=gnt_ar_b_tbl><tr><th>RK</th><th>Player</th><th>STD</th></tr>'
            '<tr><td>1</td><td>Brock Bowers</td><td>30</td></tr></table>'
        )
        tables = usat.pull("https://example.com/x",
                           fetch_fn=lambda u: (200, html))
        self.assertIn("Quarterback", tables[0]["title"])

    def test_pull_rejects_thin_page(self):
        html = ('<h2 class=gnt_ar_b_h2>QB</h2><table class=gnt_ar_b_tbl>'
                '<tr><td>1</td><td>X</td></tr></table>')
        with self.assertRaises(RuntimeError):
            usat.pull("https://example.com/x",
                      fetch_fn=lambda u: (200, html))


# --- CBS discovery (mocked fetch) --------------------------------------------

def _cbs_fetch(url):
    if "week-3-trade-chart" in url:
        return (404, "")
    if "week-2-trade-chart" in url:
        return (200, '<h2>Quarterbacks</h2><table class="TableBuilder">'
                     '<tr><th>Rank</th></tr><tr><td>1</td></tr></table>' * 4)
    return (404, "")


class TestCbsDiscovery(unittest.TestCase):
    def test_falls_back_to_latest_live_week(self):
        url = cbs.discover_url(3, fetch_fn=_cbs_fetch)
        self.assertIn("week-2-trade-chart", url)

    def test_discovery_fails_closed_when_none_resolve(self):
        with self.assertRaises(cbs.DiscoveryFailed):
            cbs.discover_url(3, fetch_fn=lambda u: (404, ""))

    def test_pull_rejects_markup_mismatch(self):
        with self.assertRaises(RuntimeError):
            cbs.pull("https://example.com/x",
                     fetch_fn=lambda u: (200, "<html>no tables</html>"))


if __name__ == "__main__":
    unittest.main()
