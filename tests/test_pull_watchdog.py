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
import ingest_usatoday as ing_usat
import ingest_common as ing_common
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

    def test_ok_line_with_failed_in_detail_note_is_ok(self):
        # 2026-10-01: an OK Razzball run logged "1 rows failed PPG
        # consistency" in the detail note; the standalone FAILED match
        # tripped and false-flagged the run failed + the artifact poisoned
        # (CRITICAL). The STATUS marker must win over detail-text words.
        self.assertEqual(classify_run_line(
            "2026-10-01 06:20 CDT | OK | source=razzball; snapshot updated: "
            "503 players, hash 42194295c6f35139; 1 rows failed PPG "
            "consistency (>0.5 ppg): Feleipe Franks"), "ok")

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

    def _repo_pull(self, repo, prefix, week, age):
        _write(os.path.join(repo, "%s-2026-09-22.json" % prefix),
               json.dumps({
                   "fetched_at": "2026-09-22",
                   "url": ("https://x/y/fantasy-football-trade-value-chart-"
                           "week-%d-ros-rankings/123/" % week),
                   "tables": [{"title": "QB", "headers": [],
                               "rows": [["1"] * 3] * 40} for _ in range(4)]}),
               mtime=_age_ts(age))

    def test_repo_pull_preferred_over_legacy_cache(self):
        # Legacy goal cache is stale (week-1, 10 days old) but the repo
        # pipeline pulled week-2 today -> the check reads the repo pull.
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly", "pull_prefix": "utest",
                   "cache": self._cache(tmp, 1, 10)}
            repo = os.path.join(tmp, "pulls")
            os.makedirs(repo)
            self._repo_pull(repo, "utest", 2, 0)
            old = wd.PULLS
            wd.PULLS = repo
            try:
                v = wd.check_weekly_article(cfg, DAY, 2)
            finally:
                wd.PULLS = old
            self.assertEqual(v["status"], "ok")
            self.assertIn("repo pull", v["cache_source"])

    def test_newest_repo_pull_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly", "pull_prefix": "utest",
                   "cache": self._cache(tmp, 2, 1)}
            repo = os.path.join(tmp, "pulls")
            os.makedirs(repo)
            _write(os.path.join(repo, "utest-2026-09-20.json"),
                   json.dumps({"url": "https://x/y/week-1/123/",
                               "tables": [{"title": "QB", "headers": [],
                                           "rows": [["1"] * 3] * 40}
                                          for _ in range(4)]}),
                   mtime=_age_ts(2))
            self._repo_pull(repo, "utest", 2, 0)
            old = wd.PULLS
            wd.PULLS = repo
            try:
                v = wd.check_weekly_article(cfg, DAY, 2)
            finally:
                wd.PULLS = old
            self.assertEqual(v["status"], "ok")
            self.assertIn("utest-2026-09-22.json", v["cache_source"])

    def test_falls_back_to_legacy_cache_without_repo_pull(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"label": "U", "expected": "weekly", "pull_prefix": "utest",
                   "cache": self._cache(tmp, 2, 1)}
            repo = os.path.join(tmp, "pulls")
            os.makedirs(repo)
            old = wd.PULLS
            wd.PULLS = repo
            try:
                v = wd.check_weekly_article(cfg, DAY, 2)
            finally:
                wd.PULLS = old
            self.assertEqual(v["status"], "ok")
            self.assertEqual(v["cache_source"], "legacy goal cache")


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


def _sitemap_fetch_new_slug(url):
    """Serve the week-4 article under USA Today's NEW slug pattern.

    Regression for 2026-10-02: USA Today renamed the article slug between
    week 3 and week 4 ("fantasy-football-trade-value-chart-week-N" ->
    "fantasy-trade-value-chart-week-N"). Discovery matched only the old
    pattern, so the Oct 1/2 scheduled runs failed closed on the stale week-3
    article even though the week-4 article (2026-09-29) was in the sitemap.
    """
    if re.search(r"web-sitemap-\d{4}-\d{2}", url):
        return (200, "<urlset><url><loc>https://www.usatoday.com/story/sports/fantasy/football/"
                     "2026/09/29/fantasy-trade-value-chart-week-4-"
                     "ros-rankings/92008742007/</loc></url></urlset>")
    return (404, "")


class TestUsatodayDiscoverySlugChange(unittest.TestCase):
    def test_discovers_article_under_new_slug(self):
        url = usat.discover_url(4, fetch_fn=_sitemap_fetch_new_slug)
        self.assertIn("week-4-ros-rankings", url)
        self.assertIn("92008742007/", url)

    def test_still_discovers_article_under_old_slug(self):
        url = usat.discover_url(3, fetch_fn=_sitemap_fetch)
        self.assertIn("week-3-ros-rankings", url)


class _FakeDb:
    """Minimal stand-in for ingest_common.Db.grain_native_values."""
    def __init__(self, existing):
        self._existing = existing

    def grain_native_values(self, table, source, variant, season, week):
        return dict(self._existing)


def _guard_row(player_key, scoring, native_value):
    return {"player_key": player_key, "scoring": scoring,
            "native_value": native_value}


class TestUsatodaySameWeekVersioning(unittest.TestCase):
    """Week-versioning guard (Jeremy 2026-10-02): changed same-week content
    writes a NEW version; only degenerate pulls fail closed."""

    def test_no_existing_rows_proceeds(self):
        clean = [_guard_row(1, "std", 40.0)]
        self.assertIsNone(
            ing_usat.pre_write_guard(_FakeDb({}), 4, {"std": 1}, clean))

    def test_identical_content_skips_quietly(self):
        existing = {(1, "std"): 40.0}
        clean = [_guard_row(1, "std", 40.0)]
        self.assertEqual(
            ing_usat.pre_write_guard(_FakeDb(existing), 4, {"std": 1}, clean),
            "unchanged")

    def test_changed_values_and_new_keys_version_instead_of_refusing(self):
        # Mirrors the real 2026-10-02 case: Sep-29 bake vs Oct-2 pull
        # (+12 keys, 9 bumped values, 0 removed) must NOT fail closed.
        existing = {(1, "std"): 40.0, (2, "std"): 58.0}
        clean = [_guard_row(1, "std", 40.0),   # unchanged
                 _guard_row(2, "std", 60.0),   # bumped
                 _guard_row(3, "std", 2.0)]    # new key
        self.assertIsNone(
            ing_usat.pre_write_guard(_FakeDb(existing), 4, {"std": 3}, clean))

    def test_degenerate_pull_fails_closed(self):
        # >5% of existing keys vanished: probable truncated pull.
        existing = {(k, "std"): 10.0 for k in range(100)}
        clean = [_guard_row(k, "std", 10.0) for k in range(90)]  # 10% gone
        with self.assertRaises(ing_common.IngestError):
            ing_usat.pre_write_guard(_FakeDb(existing), 4, {"std": 90}, clean)

    def test_small_attrition_does_not_trip(self):
        # 3% key attrition is legitimate chart churn, not a broken pull.
        existing = {(k, "std"): 10.0 for k in range(100)}
        clean = [_guard_row(k, "std", 10.0) for k in range(97)]
        self.assertIsNone(
            ing_usat.pre_write_guard(_FakeDb(existing), 4, {"std": 97}, clean))

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


# --- Versioned upsert grain: all source_trade_values writers -----------------

class TestVersionedUpsertGrain(unittest.TestCase):
    """Every writer to source_trade_values must arbitrate the 9-column
    versioned grain (bake_id included). The retired 8-column grain allowed
    only one row per week and rejected second versions with 23505."""

    VERSIONED = ("source,variant,scoring,league_teams,qb_slots,season,week,"
                 "player_key,bake_id")

    def test_versioned_constant_is_9col_with_bake(self):
        from pipelines.save_usatoday_references import USAT_UPSERT_CONFLICT_VERSIONED
        self.assertEqual(USAT_UPSERT_CONFLICT_VERSIONED, self.VERSIONED)

    def test_legacy_8col_constant_is_gone(self):
        import pipelines.save_usatoday_references as usat
        self.assertFalse(hasattr(usat, "USAT_UPSERT_CONFLICT"),
                         "legacy 8-col USAT_UPSERT_CONFLICT must be removed")

    def test_fantasypros_upserts_on_versioned_grain(self):
        import pipelines.save_fantasypros_references as fp
        import inspect
        tree = inspect.getsource(fp.save_fantasypros)
        self.assertIn("USAT_UPSERT_CONFLICT_VERSIONED", tree)

    def test_fantasycalc_upserts_on_versioned_grain(self):
        import pipelines.save_fantasycalc_references as fc
        import inspect
        tree = inspect.getsource(fc.save_fantasycalc)
        self.assertIn("USAT_UPSERT_CONFLICT_VERSIONED", tree)

    def test_usat_saver_upserts_on_versioned_grain(self):
        import pipelines.save_usatoday_references as usat
        import inspect
        tree = inspect.getsource(usat.save_usatoday)
        self.assertIn("USAT_UPSERT_CONFLICT_VERSIONED", tree)


class TestImportHealthWeek(unittest.TestCase):
    """GAP-WATCHDOG-THU-WEEK: the watchdog's nfl_week() flips Thursday, the
    content week flips Tuesday. On a Tuesday/Wednesday passing the former to
    `make import-health` checks one week behind and hides a one-week lag."""

    def _argv(self):
        from unittest import mock
        with mock.patch("subprocess.run") as run:
            wd.refresh_import_health()
        return run.call_args[0][0]

    def test_no_nfl_week_override_passed(self):
        argv = self._argv()
        self.assertEqual(argv, ["make", "import-health"])
        self.assertFalse(any(a.startswith("NFL_WEEK") for a in argv), argv)

    def test_thursday_flip_week_differs_from_content_week(self):
        # Premise of the fix: on Tue 2026-10-06 the two calendars disagree.
        sys.path.insert(0, os.path.join(REPO, "pipelines"))
        from nfl_week import current_nfl_week
        from _common import nfl_week
        d = date(2026, 10, 6)
        self.assertEqual(current_nfl_week(d), 5)
        self.assertEqual(nfl_week(d), 4)


if __name__ == "__main__":
    unittest.main()
