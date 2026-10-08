#!/usr/bin/env python3
"""Negative tests for the trade-chart pullers in ops/watchdog/ (the code
trade-chart-ingest.yml runs): run-log classification, USA Today / CBS
discovery and parsing, the same-week versioning guard, the versioned upsert
grain. Stdlib unittest; hermetic (mocked fetch) -- no network.

Split out of tests/test_pull_watchdog.py on 2026-10-08 when the Muse-era
source-pull watchdog (ops/watchdog/pull_watchdog.py, which graded files on
Muse's machine) was retired; its grader tests went with it. Monitoring of the
CI producers is monitoring.check_observations (config/monitoring_coverage.json).
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
import pull_usatoday as usat
import pull_cbs as cbs
import ingest_usatoday as ing_usat
import ingest_common as ing_common
from _common import REPO, classify_run_line, todays_run_lines

DAY = date(2026, 9, 22)  # a Tuesday; nfl_week == 2


def _write(path, text, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _ts(days_ago=0, hour=6, minute=10):
    base = datetime(2026, 9, 22, hour, minute, tzinfo=timezone.utc)
    return (base - timedelta(days=days_ago)).timestamp()






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
    def test_never_falls_back_to_an_older_week(self):
        # 2026-10-08: the old test required a Week 2 article when Week 3 was
        # asked for. 10bd086 (GAP-CBS-DISCOVERY-SLUG) made discovery never
        # return an older week -- that fallback is how CBS sat on Week 4 while
        # Week 5 was published -- so the same state must now fail closed.
        # Listing-based discovery is covered by tests/test_article_discovery.py.
        with self.assertRaises(cbs.DiscoveryFailed):
            cbs.discover_url(3, fetch_fn=_cbs_fetch)

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


if __name__ == "__main__":
    unittest.main()
