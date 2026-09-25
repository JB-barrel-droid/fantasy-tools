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
            self.json_path, dry_run=False, week=2, bake_id="pullwk2_2026-09-22",
            reindex=False,  # grain/identity scope: tiny pull can't meet the
                            # reindex's >=10 anchor-pair floor (tested below)
        )
        self.assertFalse(result["dry_run"])
        # Josh Allen: 3 scorings (1QB reused). Gibbs: 3 scorings.
        # Jordan Davis: ambiguous -> review, not written.
        self.assertEqual(result["written"], 6)
        self.assertEqual(result["review_count"], 3)
        table, rows, conflict = self.writes[0]
        self.assertEqual(table, "source_trade_values")
        # The live grain is (source, player_norm, scoring, league_teams,
        # qb_slots, season, week, variant): conflict must use player_norm,
        # NOT player_key, or the upsert 400s (no unique constraint matches).
        self.assertIn("player_norm", conflict)
        self.assertNotIn("player_key", conflict)
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
            self.json_path, dry_run=False, week=2, bake_id="pullwk2_2026-09-22",
            reindex=False,  # grain/identity scope: tiny pull can't meet the
                            # reindex's >=10 anchor-pair floor (tested below)
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
            self.json_path, dry_run=True, week=2, bake_id="pullwk2_2026-09-22",
            reindex=False,  # grain/identity scope (see above)
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(self.writes, [])


# ---------------------------------------------------------------------------
# 3b. USA Today write-time isotonic reindex (defect: saver wrote raw
# published numbers into `value`, silently replacing the reindexed values
# the dashboard builder reads).
# ---------------------------------------------------------------------------

class UsatodayReindexTest(unittest.TestCase):
    @staticmethod
    def _fixture_rows():
        """Synthetic clean rows on the fixture's own ESPN slugs (>= 12 per
        position per scoring, so the >= 10 anchor-pair floor is met), with
        published-scale native values simulating USA Today's ~0-75 chart."""
        import sys
        sys.path.insert(0, str(ROOT / "pipelines"))
        from match_source_snapshot import normalize_name
        from save_usatoday_references import FIXTURE_SCORING

        fx = json.loads(
            (ROOT / "data/fixtures/current/comparison-sources-data.json")
            .read_text())
        players = json.loads(
            (ROOT / "data/fixtures/current/players.json").read_text())["players"]
        slug_pos_key = {}
        for rec in players:
            slug_pos_key[normalize_name(rec["name"])] = (
                rec["pos"], rec["player_key"])
        # The fixture's ESPN slugs use a different convention than
        # normalize_name ('cj stroud' vs 'c j stroud'); resolve those via the
        # fixture's own player_keys map so they aren't silently dropped.
        key_pos = {rec["player_key"]: rec["pos"] for rec in players}
        for slug, key in fx.get("player_keys", {}).items():
            if slug not in slug_pos_key and key in key_pos:
                slug_pos_key[slug] = (key_pos[key], key)
        espn_combos = fx["sources"]["espn"]["combos"]
        clean = []
        for scoring, stem in FIXTURE_SCORING.items():
            values = espn_combos[f"{stem}_12"]["values"]
            by_pos: dict[str, list[str]] = {}
            for slug in values:
                pos_key = slug_pos_key.get(slug)
                if pos_key:
                    by_pos.setdefault(pos_key[0], []).append(slug)
            for pos, slugs in sorted(by_pos.items()):
                if pos not in ("QB", "RB", "WR", "TE"):
                    continue  # the USA Today pull has no K/DST tables
                for i, slug in enumerate(slugs[:12]):
                    _, key = slug_pos_key[slug]
                    native = 75.0 - 2.0 * i  # USA Today-like published scale
                    clean.append({
                        "source": "usatoday", "variant": "as_published",
                        "player_key": key, "player_norm": slug,
                        "scoring": scoring, "league_teams": 12, "qb_slots": 1,
                        "season": 2026, "week": 2, "position": pos,
                        "value": native, "native_value": native,
                    })
        return clean, espn_combos

    def test_reindex_moves_values_onto_anchor_scale(self):
        """Named defect: the saver used to write raw published numbers into
        `value`. After the fix, `value` must sit on the ESPN anchor's scale
        (reindexed totals track the anchor totals over the priced set) while
        `native_value` keeps the raw published number."""
        from save_usatoday_references import (
            apply_reindex, FIXTURE_SCORING)
        clean, espn_combos = self._fixture_rows()
        self.assertGreater(len(clean), 100)
        final, review = apply_reindex(clean, [], "test_bake")
        self.assertEqual(review, [])
        self.assertEqual(len(final), len(clean))
        by_row = {(r["player_key"], r["scoring"]): r for r in final}
        # native_value preserved verbatim on every row.
        for r in clean:
            self.assertEqual(
                by_row[(r["player_key"], r["scoring"])]["native_value"],
                r["native_value"])
        # The translation actually happened: most values moved off the
        # published number onto the anchor scale.
        moved = sum(
            1 for r in clean
            if by_row[(r["player_key"], r["scoring"])]["value"]
            != r["native_value"])
        self.assertGreater(moved, 0.9 * len(clean))
        # Reindexed totals track the ESPN anchor totals over the priced set
        # (fixed-pie scaling), per scoring.
        for scoring, stem in FIXTURE_SCORING.items():
            anchor = espn_combos[f"{stem}_12"]["values"]
            priced = [r for r in final if r["scoring"] == scoring]
            anchor_total = sum(anchor[r["player_norm"]] for r in priced)
            reindexed_total = sum(r["value"] for r in priced)
            self.assertAlmostEqual(
                reindexed_total, anchor_total,
                delta=0.05 * anchor_total,
                msg=f"scoring={scoring}: reindexed total diverged from anchor")

    def test_reindex_preserves_rank_order_within_position(self):
        """Isotonic property: within a position, rank order of the published
        numbers is preserved by the reindex (monotone map)."""
        from save_usatoday_references import apply_reindex
        clean, _ = self._fixture_rows()
        final, _ = apply_reindex(clean, [], "test_bake")
        by_pos_scoring: dict[tuple[str, str], list] = {}
        for r in final:
            by_pos_scoring.setdefault(
                (r["position"], r["scoring"]), []).append(r)
        for (pos, scoring), rows in by_pos_scoring.items():
            # Isotonic = monotone map: sorting by native ascending must give
            # non-decreasing reindexed values (ties from pooled segments are
            # expected and fine).
            ordered = sorted(rows, key=lambda r: r["native_value"])
            values = [r["value"] for r in ordered]
            for a, b in zip(values, values[1:]):
                self.assertLessEqual(
                    a, b + 1e-9, f"monotonicity broken for {pos}/{scoring}")

    def test_unmatched_anchor_identity_goes_to_review(self):
        """A row whose identity has no ESPN anchor pair is never written
        with an un-reindexed value: it moves to review."""
        from save_usatoday_references import apply_reindex
        clean, _ = self._fixture_rows()
        bogus = dict(clean[0])
        bogus["player_key"] = 999999999
        bogus["player_norm"] = "no such player"
        bogus["native_value"] = 50.0
        bogus["value"] = 50.0
        final, review = apply_reindex(clean + [bogus], [], "test_bake")
        self.assertEqual(len(final), len(clean))
        self.assertNotIn(999999999, {r["player_key"] for r in final})
        bogus_reviews = [r for r in review
                         if r.get("player_key") == 999999999]
        self.assertGreaterEqual(len(bogus_reviews), 1)
        self.assertTrue(all("reindex" in r["reason"]
                            for r in bogus_reviews))

    def test_anchor_pairs_by_player_key_not_slug(self):
        """Named defect: the candidate's slugs and the fixture's slugs come
        from different normalizers ('c j stroud' vs 'cj stroud'). Pairing
        anchors by exact slug silently dropped ~56 real players to review.
        The join must be on the canonical numeric player_key (declared by
        the fixture's own player_keys map), never on raw slug strings."""
        from save_usatoday_references import apply_reindex
        clean, _ = self._fixture_rows()
        # Simulate the saver's real slug convention: the candidate slug for
        # C.J. Stroud is 'c j stroud' while the fixture's anchor slug is
        # 'cj stroud'. The player_key is the same either way.
        template = next(r for r in clean
                        if r["position"] == "QB" and r["scoring"] == "std")
        for scoring, native in (("std", 40.0), ("half", 42.0), ("full", 44.0)):
            row = dict(template)
            row.update({"player_key": 4158, "player_norm": "c j stroud",
                        "scoring": scoring, "position": "QB",
                        "value": native, "native_value": native})
            clean.append(row)
        stroud_rows = [r for r in clean if r["player_norm"] == "c j stroud"]
        self.assertEqual(len(stroud_rows), 3)
        final, review = apply_reindex(clean, [], "test_bake")
        final_keys = {(r["player_key"], r["scoring"]) for r in final}
        for r in stroud_rows:
            self.assertIn((r["player_key"], r["scoring"]), final_keys)
        self.assertFalse(
            [r for r in review if r.get("player_norm") == "c j stroud"])

    def test_below_anchor_floor_fails_closed(self):
        """Named defect guard: fewer than 10 anchor pairs must fail loudly,
        never silently write raw values."""
        from save_usatoday_references import apply_reindex
        clean, _ = self._fixture_rows()
        tiny = [r for r in clean
                if r["scoring"] == "std" and r["position"] == "QB"][:3]
        with self.assertRaises(SystemExit):
            apply_reindex(tiny, [], "test_bake")


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


# ---------------------------------------------------------------------------
# 5. Ingest wrappers (defect class: stale fallback / silent write / count
#    mismatch). Every verifier is negative-tested against its named defect.
# ---------------------------------------------------------------------------

ingest_common = load("ingest_common", WATCHDOG / "ingest_common.py")
ingest_cbs = load("ingest_cbs", WATCHDOG / "ingest_cbs.py")
ingest_usat = load("ingest_usatoday", WATCHDOG / "ingest_usatoday.py")


def _fake_tables():
    def t(title, n):
        return {"title": title, "headers": ["Player"],
                "rows": [["P%d" % i] for i in range(n)]}
    return [t("Quarterbacks", 3), t("Running Backs", 4),
            t("Wide Receivers", 5), t("Tight Ends", 2)]


CBS_URL_W2 = ("https://sportsfly.cbsistatic.com/fantasy/football/news/"
              "dave-richards-week-2-trade-chart-and-rest-of-season/")
USAT_URL_W2 = ("https://www.usatoday.com/story/sports/fantasy/football/"
               "2026/09/15/fantasy-football-trade-value-chart-week-2-ros-rankings/"
               "91770884007/")


class FakeDb:
    """In-memory (source, variant, scoring, season, week, bake_id) counts,
    plus an optional native-value map for the same-week guard."""

    def __init__(self):
        self.store = {}
        self.reads = []
        self.native = {}  # (source, variant, season, week) -> {(key, scoring): value}

    def key(self, source, variant, scoring, season, week, bake_id):
        return (source, variant, scoring, season, week, bake_id)

    def set(self, source, variant, scoring, season, week, n, bake_id=None):
        self.store[self.key(source, variant, scoring, season, week,
                            bake_id)] = n

    def set_native(self, source, variant, season, week, mapping):
        self.native[(source, variant, season, week)] = dict(mapping)

    def count_fn(self, table, params):
        self.reads.append((table, params))
        q = params.lstrip("?")
        got = {}
        for part in q.split("&"):
            k, _, v = part.partition("=")
            got[k] = v[3:] if v.startswith("eq.") else v
        return self.store.get(self.key(got.get("source"), got.get("variant"),
                                       got.get("scoring"),
                                       int(got.get("season", 0)),
                                       int(got.get("week", 0)),
                                       got.get("bake_id")), 0)

    def rows_fn(self, table, params):
        self.reads.append((table, params))
        q = params.lstrip("?")
        got = {}
        for part in q.split("&"):
            k, _, v = part.partition("=")
            got[k] = v[3:] if v.startswith("eq.") else v
        mapping = self.native.get(
            (got.get("source"), got.get("variant"),
             int(got.get("season", 0)), int(got.get("week", 0))), {})
        return [{"player_key": k, "scoring": s, "native_value": v}
                for (k, s), v in mapping.items()]

    def db(self):
        return ingest_common.Db(count_fn=self.count_fn, rows_fn=self.rows_fn)


def _fake_build(scorings, per_scoring=(2, 2, 2)):
    clean = []
    for s, n in zip(scorings, per_scoring):
        clean += [{"player_key": 1000 + len(clean) + i, "scoring": s,
                   "native_value": 10.0 + i}
                  for i in range(n)]
    return lambda path, week, bake_id: (clean, [], "2026-09-22", "url")


class WrapperHarness:
    """Shared fakes for wrapper run() tests; save_fn writes into FakeDb."""

    def __init__(self, test, mod, url, scorings, source, variant):
        self.test = test
        self.mod = mod
        self.url = url
        self.scorings = scorings
        self.source = source
        self.variant = variant
        self.fakedb = FakeDb()
        self.saved = []
        self.pulled = []
        self.discovered = []

        def save_fn(path, dry_run, week, bake_id):
            clean, _, _, _ = _fake_build(scorings)(path, week, bake_id)
            if dry_run:
                return {"written": 0, "review_count": 0,
                        "bake_id": bake_id}
            self.saved.append((path, week, bake_id))
            per = {}
            for row in clean:
                per[row["scoring"]] = per.get(row["scoring"], 0) + 1
            for s, n in per.items():
                self.fakedb.set(source, variant, s, 2026, week, n)
                if bake_id:
                    self.fakedb.set(source, variant, s, 2026, week, n,
                                    bake_id=bake_id)
            return {"written": len(clean), "review_count": 0,
                    "bake_id": bake_id}

        self.save_fn = save_fn

    def run(self, week=2, **kw):
        kw.setdefault("discover_fn", lambda w: self.discovered.append(w) or self.url)
        kw.setdefault("pull_fn", lambda u: self.pulled.append(u) or _fake_tables())
        kw.setdefault("build_fn", _fake_build(self.scorings))
        kw.setdefault("save_fn", self.save_fn)
        # The guard compares published content; in tests it sees the same
        # fake pre-reindex rows the build produces.
        kw.setdefault("guard_build_fn", _fake_build(self.scorings))
        kw.setdefault("db", self.fakedb.db())
        tmp = kw.pop("tmp")
        kw.setdefault("state_dir", str(tmp / "state"))
        kw.setdefault("pulls_dir", str(tmp / "pulls"))
        return self.mod.run(week=week, **kw)


class WrapperWeekGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp())

    def test_stale_fallback_rejected(self):
        """Defect: discovery tries requested and preceding weeks; the
        wrapper must reject a stale week-2 fallback when week 3 is
        requested. Requested week deterministically beats stale fallback."""
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=3, tmp=self.tmp)
        self.assertIn("stale", str(ctx.exception))

    def test_partial_sitemap_old_week_cannot_select(self):
        """A sitemap containing only an older week cannot feed the ingest:
        even if discovery returns the old-week URL, the wrapper fails."""
        h = WrapperHarness(self, ingest_usat, USAT_URL_W2,
                           ("std", "half", "full"), "usatoday", "as_published")
        with self.assertRaises(ingest_common.IngestError):
            h.run(week=3, tmp=self.tmp)

    def test_url_without_week_slug_rejected(self):
        h = WrapperHarness(self, ingest_cbs,
                           "https://example.com/trade-chart/", 
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        with self.assertRaises(ingest_common.IngestError):
            h.run(week=2, tmp=self.tmp)


class WrapperTableValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp())

    def _run_with_tables(self, tables):
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        return h.run(week=2, tmp=self.tmp,
                     pull_fn=lambda u: tables)

    def test_zero_tables_fails(self):
        with self.assertRaises(ingest_common.IngestError):
            self._run_with_tables([])

    def test_missing_position_fails(self):
        tables = [t for t in _fake_tables()
                  if "Tight" not in t["title"]]
        with self.assertRaises(ingest_common.IngestError) as ctx:
            self._run_with_tables(tables)
        self.assertIn("TE", str(ctx.exception))

    def test_empty_table_fails(self):
        tables = _fake_tables()
        tables[0]["rows"] = []
        with self.assertRaises(ingest_common.IngestError):
            self._run_with_tables(tables)


class WrapperHappyPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp())

    def test_cbs_happy_path(self):
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        res = h.run(week=2, tmp=self.tmp)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["written"], 6)
        self.assertEqual(res["per_scoring"],
                         {"standard": 2, "half_ppr": 2, "ppr": 2})
        # pull JSON persisted, state recorded
        pulls = list((self.tmp / "pulls").glob("cbs-*.json"))
        self.assertEqual(len(pulls), 1)
        state = json.loads((self.tmp / "state" / "last_ingest_cbs.json")
                           .read_text())
        self.assertEqual(state["week"], 2)
        self.assertEqual(state["written"], 6)

    def test_usatoday_happy_path_with_bake_id(self):
        h = WrapperHarness(self, ingest_usat, USAT_URL_W2,
                           ("std", "half", "full"), "usatoday", "as_published")
        res = h.run(week=2, tmp=self.tmp)
        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["bake_id"].startswith("usatwk2_"))

    def test_unchanged_content_skips(self):
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        first = h.run(week=2, tmp=self.tmp)
        self.assertEqual(first["status"], "ok")
        second = h.run(week=2, tmp=self.tmp)
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(len(h.saved), 1)

    def test_force_reingests(self):
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        h.run(week=2, tmp=self.tmp)
        res = h.run(week=2, tmp=self.tmp, force=True)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(h.saved), 2)

    def test_discovery_failed_is_quiet_skip(self):
        def boom(week):
            raise pull_usatoday.DiscoveryFailed("no sitemap")
        h = WrapperHarness(self, ingest_usat, USAT_URL_W2,
                           ("std", "half", "full"), "usatoday", "as_published")
        res = h.run(week=2, tmp=self.tmp, discover_fn=boom)
        self.assertEqual(res["status"], "not_published")
        self.assertEqual(h.pulled, [])
        self.assertEqual(h.saved, [])

    def test_dry_run_writes_nothing(self):
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        res = h.run(week=2, tmp=self.tmp, dry_run=True)
        self.assertEqual(res["status"], "dry_run")
        self.assertEqual(h.saved, [])
        self.assertFalse((self.tmp / "state").exists())


class WrapperVerificationTest(unittest.TestCase):
    """Verify-the-verifier: each named post-write defect must trip."""

    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp())

    def test_broken_per_scoring_count_caught(self):
        """Named defect: short write on one scoring. The db reports 1
        instead of 2 for ppr; the verifier must catch it."""
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")

        real_set = h.fakedb.set

        def corrupting_save(path, dry_run, week, bake_id):
            res = h.save_fn(path, dry_run, week, bake_id)
            if not dry_run:
                h.fakedb.set("cbs", "as_published", "ppr", 2026, week, 1)
            return res

        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=2, tmp=self.tmp, save_fn=corrupting_save)
        self.assertIn("ppr", str(ctx.exception))

    def test_prior_week_clobber_caught(self):
        """Named defect: the write clobbers the prior week's rows. The db
        reports a changed week-1 count after the write."""
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")
        h.fakedb.set("cbs", "as_published", "standard", 2026, 1, 10)
        reads = {"n": 0}
        orig = h.fakedb.count_fn

        def shifting(table, params):
            n = orig(table, params)
            if "week=eq.1" in params:
                reads["n"] += 1
                if reads["n"] > 1:
                    return n - 1  # clobbered after snapshot
            return n

        h.fakedb.count_fn = shifting
        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=2, tmp=self.tmp)
        self.assertIn("week 1", str(ctx.exception))

    def test_written_vs_clean_mismatch_caught(self):
        """Named defect: saver reports a different written count than the
        clean rows the wrapper built."""
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")

        def lying_save(path, dry_run, week, bake_id):
            return {"written": 999, "review_count": 0, "bake_id": bake_id}

        with self.assertRaises(ingest_common.IngestError):
            h.run(week=2, tmp=self.tmp, save_fn=lying_save)

    def test_missing_scoring_in_clean_rows_fails(self):
        """Clean rows missing a whole scoring must fail before any write."""
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")

        def bad_build(path, week, bake_id):
            clean = [{"player_key": 1, "scoring": "standard"}]
            return (clean, [], "2026-09-22", "url")

        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=2, tmp=self.tmp, build_fn=bad_build)
        self.assertEqual(h.saved, [])
        self.assertIn("half_ppr", str(ctx.exception))

    def test_write_failure_propagates(self):
        """A saver failure (SystemExit) is a cron-visible failure, not a
        silent skip."""
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2,
                           ("standard", "half_ppr", "ppr"), "cbs",
                           "as_published")

        def failing_save(path, dry_run, week, bake_id):
            raise SystemExit("boom")

        with self.assertRaises(SystemExit):
            h.run(week=2, tmp=self.tmp, save_fn=failing_save)


class UsatodaySameWeekGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__import__("tempfile").mkdtemp())

    def _harness(self):
        return WrapperHarness(self, ingest_usat, USAT_URL_W2,
                              ("std", "half", "full"), "usatoday",
                              "as_published")

    def _fake_native(self):
        # Mirrors _fake_build(("std","half","full")): keys 1000..1005,
        # native 10.0/11.0 per scoring.
        return {(1000, "std"): 10.0, (1001, "std"): 11.0,
                (1002, "half"): 10.0, (1003, "half"): 11.0,
                (1004, "full"): 10.0, (1005, "full"): 11.0}

    def test_same_week_unchanged_content_skips_quietly(self):
        """Defect: the old guard failed closed on ANY same-week rows, even
        when the article's numbers were already in the DB. Identical native
        values must skip quietly with no write (the reindex is deterministic,
        so identical natives imply identical reindexed values)."""
        h = self._harness()
        h.fakedb.set_native("usatoday", "as_published", 2026, 2,
                            self._fake_native())
        res = h.run(week=2, tmp=self.tmp)
        self.assertEqual(res["status"], "same_week_unchanged")
        self.assertEqual(h.saved, [])

    def test_same_week_changed_values_fail_closed(self):
        """Unresolved fork: same-week rows exist but the published numbers
        changed under the existing bake. The wrapper must refuse to replace
        them, not silently re-bake (bias_adjusted consistency unresolved)."""
        h = self._harness()
        native = self._fake_native()
        native[(1000, "std")] = 99.0  # article republished with new numbers
        h.fakedb.set_native("usatoday", "as_published", 2026, 2, native)
        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=2, tmp=self.tmp)
        self.assertIn("changed", str(ctx.exception))
        self.assertEqual(h.saved, [])

    def test_same_week_key_set_difference_fails_closed(self):
        """Named defect: the DB holds a different player/scoring key set than
        the new pull (players added/dropped). Key-set drift is not an
        unchanged re-pull; the wrapper must fail closed, never silently
        merge."""
        h = self._harness()
        native = self._fake_native()
        del native[(1005, "full")]
        h.fakedb.set_native("usatoday", "as_published", 2026, 2, native)
        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=2, tmp=self.tmp)
        self.assertIn("key set", str(ctx.exception))
        self.assertEqual(h.saved, [])

    def test_no_existing_rows_writes(self):
        """No same-week rows in the DB: the guard passes and the write
        proceeds (regression: the guard must not block a first ingest)."""
        h = self._harness()
        res = h.run(week=2, tmp=self.tmp)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(h.saved), 1)

    def test_guard_sees_pre_reindex_rows(self):
        """Named defect: the guard compared post-reindex rows, so the 2
        players the reindex legitimately excludes (no ESPN anchor pair)
        tripped the key-set check and failed closed on an unchanged article.
        The guard must compare PUBLISHED (native) content: build_fn returns
        the post-reindex subset, guard_build_fn the full pre-reindex set,
        and identical natives must skip quietly."""
        h = self._harness()
        full = _fake_build(("std", "half", "full"))
        # Post-reindex subset: drop one key per scoring (reindex exclusion).
        def post_reindex(path, week, bake_id):
            clean, review, pa, pu = full(path, week, bake_id)
            return [r for r in clean
                    if (r["player_key"], r["scoring"]) not in
                    {(1001, "std"), (1003, "half"), (1005, "full")}], \
                review, pa, pu
        h.fakedb.set_native("usatoday", "as_published", 2026, 2,
                            self._fake_native())
        res = h.run(week=2, tmp=self.tmp, build_fn=post_reindex,
                    guard_build_fn=full)
        self.assertEqual(res["status"], "same_week_unchanged")
        self.assertEqual(h.saved, [])

    def test_bake_id_count_mismatch_caught(self):
        """Named defect: rows land without the new bake_id (bake id
        mis-stamped); the verifier must catch it."""
        h = WrapperHarness(self, ingest_usat, USAT_URL_W2,
                           ("std", "half", "full"), "usatoday", "as_published")

        def no_bake_save(path, dry_run, week, bake_id):
            clean, _, _, _ = _fake_build(("std", "half", "full"))(
                path, week, bake_id)
            if not dry_run:
                self_saved = h.saved
                self_saved.append((path, week, bake_id))
                for s in ("std", "half", "full"):
                    # grain rows written, but bake_id column left NULL
                    h.fakedb.set("usatoday", "as_published", s, 2026, week, 2)
            return {"written": len(clean), "review_count": 0,
                    "bake_id": bake_id}

        with self.assertRaises(ingest_common.IngestError) as ctx:
            h.run(week=2, tmp=self.tmp, save_fn=no_bake_save)
        self.assertIn("bake_id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# 5. save_fantasycalc_references (Week 3 refresh; no saver existed before --
#    the Week 2 load was ad-hoc, so the contract itself is the guard)
# ---------------------------------------------------------------------------

save_fc = load("save_fantasycalc_references", PIPELINES / "save_fantasycalc_references.py")

FC_CACHE = {
    "fantasycalc_standard_12_qb1": [
        {"name": "Jahmyr Gibbs", "pos": "RB", "value": 10656.0},
        {"name": "Mystery Player", "pos": "WR", "value": 100.0},
    ],
    "fantasycalc_half_12_qb1": [
        {"name": "Jahmyr Gibbs", "pos": "RB", "value": 10589.0},
    ],
    "fantasycalc_full_12_qb1": [
        {"name": "Jahmyr Gibbs", "pos": "RB", "value": 10595.0},
    ],
}


class SaveFantasycalcTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        for stem, rows in FC_CACHE.items():
            (self.tmp / f"{stem}.json").write_text(json.dumps(
                {"fetched_at": "2026-09-23T12:09:59Z", "rows": rows, "snapshot": {}}))
        self._cache_dir = save_fc.CACHE_DIR
        self._fetch = save_fc.fetch_players
        self._upsert = save_fc.upsert_rows
        self._count = save_fc.count_rows
        save_fc.CACHE_DIR = self.tmp
        self.writes = []
        save_fc.fetch_players = lambda: PLAYERS
        save_fc.upsert_rows = lambda table, rows, conflict: self.writes.append(
            (table, rows, conflict)
        )
        save_fc.count_rows = lambda table, params: sum(
            len(rows) for t, rows, _ in self.writes if t == table
        )

    def tearDown(self):
        save_fc.CACHE_DIR = self._cache_dir
        save_fc.fetch_players = self._fetch
        save_fc.upsert_rows = self._upsert
        save_fc.count_rows = self._count

    def test_rows_land_with_correct_grain(self):
        result = save_fc.save_fantasycalc(
            dry_run=False, week=3, bake_id="fcwk3_2026-09-25_v1",
            reindex=False,  # grain/identity scope; reindex is shared code
        )
        self.assertFalse(result["dry_run"])
        # Gibbs: 3 scorings. Mystery Player: no identity -> review.
        self.assertEqual(result["written"], 3)
        self.assertEqual(result["review_count"], 1)
        table, rows, conflict = self.writes[0]
        self.assertEqual(table, "source_trade_values")
        # Same live grain as the other savers: player_norm, NOT player_key.
        self.assertIn("player_norm", conflict)
        self.assertNotIn("player_key", conflict)
        gibbs = [r for r in rows if r["player_key"] == 2227]
        self.assertEqual(len(gibbs), 3)
        self.assertEqual({r["scoring"] for r in gibbs}, {"std", "half", "full"})
        self.assertTrue(all(r["source"] == "fantasycalc" for r in rows))
        self.assertTrue(all(r["variant"] == "as_published" for r in rows))
        self.assertTrue(all(r["week"] == 3 for r in rows))
        self.assertTrue(all(r["league_teams"] == 12 and r["qb_slots"] == 1 for r in rows))
        # as_published only: the bias_adjusted fit bake is never written here.
        self.assertTrue(all(r["bake_id"] == "fcwk3_2026-09-25_v1" for r in rows))
        self.assertFalse(any("fitwk" in r["bake_id"] for r in rows))
        # Raw published preserved as native; value==native pre-reindex.
        by_scoring = {r["scoring"]: r for r in gibbs}
        self.assertEqual(by_scoring["half"]["native_value"], 10589.0)
        self.assertEqual(by_scoring["half"]["value"], 10589.0)
        # Weekly snapshot: no article date.
        self.assertTrue(all(r["source_content_date"] is None for r in rows))

    def test_missing_cache_file_fails_closed(self):
        (self.tmp / "fantasycalc_half_12_qb1.json").unlink()
        with self.assertRaises(SystemExit):
            save_fc.save_fantasycalc(dry_run=True, week=3, reindex=False)
        self.assertEqual(self.writes, [])

    def test_zero_clean_rows_fails_closed(self):
        for stem in FC_CACHE:
            (self.tmp / f"{stem}.json").write_text(json.dumps(
                {"fetched_at": "2026-09-23T12:09:59Z", "rows": [], "snapshot": {}}))
        with self.assertRaises(SystemExit):
            save_fc.save_fantasycalc(dry_run=True, week=3, reindex=False)

    def test_dry_run_writes_nothing(self):
        result = save_fc.save_fantasycalc(dry_run=True, week=3, reindex=False)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["written"], 0)
        self.assertEqual(self.writes, [])
