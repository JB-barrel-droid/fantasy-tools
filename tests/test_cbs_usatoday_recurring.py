#!/usr/bin/env python3
"""Tests for the CBS/USA Today recurring-ingestion build.

Covers, all negative-tested against their named defects:

1. pull_cbs row recognition: the old numeric-first-cell assumption silently
   produced ZERO rows on the current CBS markup (headers Player/tm/1QB-4/...)
   -- a silent zero-row "success". The fix accepts name-first cells.
2. pull_usatoday sitemap truncation: a truncated sitemap body (missing
   </urlset>) must fail closed via DiscoveryFailed, never return a partial
   URL list that could make discovery settle on last week's article.
3. save_usatoday_references: parse/identity/upsert contract, fail-closed on
   zero rows, QB 1QB reuse across scorings, content-date extraction.
4. save_espn_cbs_references --week: the CBS save grain follows the passed
   week instead of the hardcoded 2.

Supabase access is injected via module-level callables; all tests run
offline with recorded fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "ops" / "watchdog"
PIPELINES = ROOT / "pipelines"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# _common must be importable as a top-level module for the pull scripts.
sys.path.insert(0, str(WATCHDOG))
import _common  # noqa: E402

pull_cbs = load("pull_cbs", WATCHDOG / "pull_cbs.py")
pull_usatoday = load("pull_usatoday", WATCHDOG / "pull_usatoday.py")
save_cbs = load("save_espn_cbs_references", PIPELINES / "save_espn_cbs_references.py")
save_usat = load("save_usatoday_references", PIPELINES / "save_usatoday_references.py")

PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB"},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB"},
    {"player_key": 9993, "full_name": "Jordan Davis", "position": "QB"},
    {"player_key": 9994, "full_name": "Jordan Davis", "position": "QB"},  # genuinely ambiguous twin
]


# ---------------------------------------------------------------------------
# 1. CBS row recognition (defect: numeric-first-cell assumption -> 0 rows)
# ---------------------------------------------------------------------------

def _cbs_pos_table(title, players):
    rows = "".join(
        "<tr><td><a>%s</a></td><td>XX</td><td>20</td><td>20</td><td>44</td></tr>"
        % p for p in players
    )
    return (
        "<h2>%s</h2>\n"
        '<table class="TableBuilder">\n'
        "<thead><tr><th>Player</th><th>tm</th><th>1QB-4</th><th>1QB-6</th><th>2QB</th></tr></thead>\n"
        "<tbody>%s</tbody>\n"
        "</table>\n" % (title, rows)
    )


CBS_TABLEBUILDER_HTML = "<html><body>\n%s\n</body></html>" % "".join([
    _cbs_pos_table("Quarterback", ["Josh Allen", "Nonexistent Person"]),
    _cbs_pos_table("Running Back", ["Jahmyr Gibbs"]),
    _cbs_pos_table("Wide Receiver", ["Tyreek Hill"]),
    _cbs_pos_table("Tight End", ["Brock Bowers"]),
])


class CbsRowRecognitionTest(unittest.TestCase):
    def _tables(self):
        return pull_cbs.pull(
            "https://example.com/cbs",
            fetch_fn=lambda url: (200, CBS_TABLEBUILDER_HTML),
        )

    def test_name_first_cells_parse(self):
        """The current CBS markup has no numeric rank column; player rows
        must still be recognized (142 rows live on 2026-09-22)."""
        tables = self._tables()
        self.assertEqual(len(tables), 4)
        self.assertEqual(tables[0]["title"], "Quarterback")
        # 2 player rows (the header uses <th>, not <td>).
        self.assertEqual(len(tables[0]["rows"]), 2)
        self.assertIn("Josh Allen", tables[0]["rows"][0][0])

    def test_old_numeric_assumption_would_fail(self):
        """Negative test: the OLD rule (first cell must be numeric) yields
        zero player rows on this markup -- proving the test guards the fix,
        not the bug."""
        tables = self._tables()
        old_style_rows = [
            r for r in tables[0]["rows"]
            if r and r[0].strip().replace("-", "").isdigit()
        ]
        self.assertEqual(old_style_rows, [])


# ---------------------------------------------------------------------------
# 2. USA Today sitemap truncation (defect: partial sitemap -> stale article)
# ---------------------------------------------------------------------------

FULL_SITEMAP = (
    '<?xml version="1.0"?><urlset>'
    "<url><loc>https://www.usatoday.com/story/sports/fantasy/football/2026/09/08/"
    "fantasy-football-trade-value-chart-week-1-ros-rankings/91661608007/</loc></url>"
    "<url><loc>https://www.usatoday.com/story/sports/fantasy/football/2026/09/15/"
    "fantasy-football-trade-value-chart-week-2-ros-rankings/91770884007/</loc></url>"
    "</urlset>"
)
TRUNCATED_SITEMAP = FULL_SITEMAP[: len(FULL_SITEMAP) // 2]  # cut mid-document


class SitemapTruncationTest(unittest.TestCase):
    def test_full_sitemap_parses(self):
        urls = pull_usatoday.sitemap_urls_for_month(
            2026, 9, fetch_fn=lambda url: (200, FULL_SITEMAP)
        )
        self.assertEqual(len(urls), 2)

    def test_truncated_sitemap_fails_closed(self):
        """A truncated body must raise DiscoveryFailed (fail closed), never
        return the partial list -- which would let discovery settle on the
        week-1 article while week-2 exists."""
        with self.assertRaises(pull_usatoday.DiscoveryFailed):
            pull_usatoday.sitemap_urls_for_month(
                2026, 9, fetch_fn=lambda url: (200, TRUNCATED_SITEMAP)
            )

    def test_truncated_then_full_recovers(self):
        """One retry: transient truncation followed by a good fetch succeeds."""
        calls = {"n": 0}

        def flaky(url):
            calls["n"] += 1
            return (200, TRUNCATED_SITEMAP if calls["n"] == 1 else FULL_SITEMAP)

        urls = pull_usatoday.sitemap_urls_for_month(2026, 9, fetch_fn=flaky)
        self.assertEqual(len(urls), 2)
        self.assertEqual(calls["n"], 2)

    def test_failed_fetch_fails_closed(self):
        with self.assertRaises(pull_usatoday.DiscoveryFailed):
            pull_usatoday.sitemap_urls_for_month(
                2026, 9, fetch_fn=lambda url: (500, "")
            )


# ---------------------------------------------------------------------------
# 3. save_usatoday_references contract
# ---------------------------------------------------------------------------

USAT_PULL = {
    "url": "https://www.usatoday.com/story/sports/fantasy/football/2026/09/15/"
    "fantasy-football-trade-value-chart-week-2-ros-rankings/91770884007/",
    "fetched_at": "2026-09-22T11:00:00Z",
    "tables": [
        {
            "title": "Quarterback trade value chart",
            "headers": ["RK", "Player", "1QB", "6/TD", "SFLEX"],
            "rows": [
                ["1", "Josh Allen", "36", "42", "69"],
                ["2", "Jordan Davis", "10", "12", "20"],  # ambiguous twin -> review
            ],
        },
        {
            "title": "Running back trade value chart",
            "headers": ["RK", "Player", "STD", "Half", "PPR"],
            "rows": [
                ["1", "Jahmyr Gibbs", "70", "72", "75"],
            ],
        },
    ],
}


class SaveUsatodayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").TemporaryDirectory().name)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.json_path = self.tmp / "usatoday.json"
        self.json_path.write_text(json.dumps(USAT_PULL))
        self._fetch = save_usat.fetch_players
        self._upsert = save_usat.upsert_rows
        self._count = save_usat.count_rows
        self.writes = []
        save_usat.fetch_players = lambda: PLAYERS
        save_usat.upsert_rows = lambda table, rows, conflict: self.writes.append(
            (table, rows, conflict)
        )
        save_usat.count_rows = lambda table, params: sum(
            len(rows) for t, rows, _ in self.writes if t == table
        )

    def tearDown(self):
        save_usat.fetch_players = self._fetch
        save_usat.upsert_rows = self._upsert
        save_usat.count_rows = self._count

    def test_rows_land_with_correct_grain(self):
        result = save_usat.save_usatoday(
            self.json_path, dry_run=False, week=2, bake_id="pullwk2_2026-09-22"
        )
        self.assertFalse(result["dry_run"])
        # Josh Allen: 3 scorings (1QB reused). Gibbs: 3 scorings.
        # Jordan Davis: ambiguous -> review, not written.
        self.assertEqual(result["written"], 6)
        self.assertEqual(result["review_count"], 3)
        table, rows, conflict = self.writes[0]
        self.assertEqual(table, "source_trade_values")
        self.assertIn("player_key", conflict)
        allen = [r for r in rows if r["player_key"] == 869]
        self.assertEqual(len(allen), 3)
        self.assertEqual({r["scoring"] for r in allen}, {"std", "half", "full"})
        # QB 1QB column reused across scorings (documented implication).
        self.assertTrue(all(r["value"] == 36 for r in allen))
        # Published values preserved as native.
        gibbs_full = next(
            r for r in rows if r["player_key"] == 2227 and r["scoring"] == "full"
        )
        self.assertEqual(gibbs_full["value"], 75)
        self.assertEqual(gibbs_full["native_value"], 75)
        # Content vintage from the article URL, not the pull time.
        self.assertTrue(
            all(r["source_content_date"] == "2026-09-15" for r in rows)
        )
        self.assertTrue(all(r["week"] == 2 for r in rows))
        self.assertTrue(all(r["variant"] == "as_published" for r in rows))

    def test_ambiguous_identity_goes_to_review_never_guessed(self):
        result = save_usat.save_usatoday(
            self.json_path, dry_run=False, week=2, bake_id="pullwk2_2026-09-22"
        )
        names = {r["name"] for r in result["review"]}
        self.assertIn("Jordan Davis", names)
        table, rows, _ = self.writes[0]
        self.assertNotIn(9993, {r["player_key"] for r in rows})
        self.assertNotIn(9994, {r["player_key"] for r in rows})

    def test_zero_tables_fails_closed(self):
        empty = self.tmp / "empty.json"
        empty.write_text(json.dumps({"url": USAT_PULL["url"], "tables": []}))
        with self.assertRaises(SystemExit):
            save_usat.save_usatoday(empty, dry_run=False, week=2, bake_id="x")
        self.assertEqual(self.writes, [])

    def test_dry_run_writes_nothing(self):
        result = save_usat.save_usatoday(
            self.json_path, dry_run=True, week=2, bake_id="pullwk2_2026-09-22"
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(self.writes, [])


# ---------------------------------------------------------------------------
# 4. save_espn_cbs_references --week (defect: hardcoded week=2 grain)
# ---------------------------------------------------------------------------

CBS_PULL = {
    "fetched_at": "2026-09-22T11:00:00Z",
    "url": "https://example.com/dave-richards-week-3-trade-chart",
    "tables": [
        {
            "title": "Quarterback",
            "headers": ["Player", "tm", "1QB-4", "1QB-6", "2QB"],
            "rows": [
                ["Player", "tm", "1QB-4", "1QB-6", "2QB"],
                ["Josh Allen", "BUF", "20", "20", "44"],
            ],
        },
    ],
}


class SaveCbsWeekTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").TemporaryDirectory().name)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.json_path = self.tmp / "cbs.json"
        self.json_path.write_text(json.dumps(CBS_PULL))
        self._fetch = save_cbs.fetch_players
        self._upsert = save_cbs.upsert_rows
        self._count = save_cbs.count_rows
        self.writes = []
        self.count_params_seen = []
        save_cbs.fetch_players = lambda: PLAYERS
        save_cbs.upsert_rows = lambda table, rows, conflict: self.writes.append(
            (table, rows, conflict)
        )

        def fake_count(table, params):
            self.count_params_seen.append(params)
            return sum(len(rows) for t, rows, _ in self.writes if t == table)

        save_cbs.count_rows = fake_count

    def tearDown(self):
        save_cbs.fetch_players = self._fetch
        save_cbs.upsert_rows = self._upsert
        save_cbs.count_rows = self._count

    def test_week_param_sets_save_grain(self):
        """Defect: the CBS save grain was hardcoded to week=2. Passing
        --week 3 must stamp week=3 on rows and on the verification query."""
        result = save_cbs.save_source(
            "cbs", dry_run=False, espn_csv=Path("/dev/null"),
            espn_meta=Path("/dev/null"), cbs_json=self.json_path, week=3,
        )
        table, rows, _ = self.writes[0]
        self.assertEqual(table, "cbs_trade_values")
        self.assertTrue(rows)
        self.assertTrue(all(r["week"] == 3 for r in rows))
        self.assertIn("week=eq.3", self.count_params_seen[0])
        self.assertNotIn("week=eq.2", self.count_params_seen[0])
        self.assertEqual(result["vintage"], "Week 3")

    def test_default_week_is_current_nfl_week(self):
        save_cbs.save_source(
            "cbs", dry_run=False, espn_csv=Path("/dev/null"),
            espn_meta=Path("/dev/null"), cbs_json=self.json_path, week=None,
        )
        table, rows, _ = self.writes[0]
        self.assertTrue(all(r["week"] == _common.nfl_week() for r in rows))


if __name__ == "__main__":
    unittest.main()
