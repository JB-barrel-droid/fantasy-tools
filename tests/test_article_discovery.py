"""Trade-chart article discovery (GAP-CBS-DISCOVERY-SLUG, 2026-10-08).

CBS published Dave Richard's Week 5 chart on 2026-10-06 at
/fantasy/football/news/dave-richards-2026-week-5-trade-chart/. Discovery on
origin/main guessed one slug template ("dave-richards-week-%d-trade-chart-
and-rest-of-season-...") for weeks 5, 4, 3, found the Week 4 article, and the
ingest skipped it as "not published yet" -- every day. The same class of miss
hit USA Today a day earlier ("chart" -> "charts").

Fixtures under tests/fixtures/discovery/ are the live pages of 2026-10-08,
trimmed to what discovery reads (links + titles; og:title + tables).

Proof against origin/main (run 2026-10-08, see docs/claude-log/2026-10-08-
cbs-discovery.md): CbsDiscoveryTest's path tests fail there because the
old discover_url returns the week-4 URL (or raises when only www is served);
OverdueTest fails because a miss is always a quiet skip; FantasyPros and
USA Today listing tests fail because the old discovery falls back to week 4.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / "ops" / "watchdog"
FIX = ROOT / "tests" / "fixtures" / "discovery"
sys.path.insert(0, str(WATCHDOG))
sys.path.insert(0, str(ROOT / "pipelines"))

import article_discovery as ad  # noqa: E402
import ingest_common as ic  # noqa: E402
import pull_cbs  # noqa: E402
import pull_fantasypros as fp  # noqa: E402
import pull_usatoday as usat  # noqa: E402

CBS_W5 = "https://www.cbssports.com/fantasy/football/news/dave-richards-2026-week-5-trade-chart/"
CBS_W4 = ("https://www.cbssports.com/fantasy/football/news/dave-richards-week-4-trade-chart-"
          "and-rest-of-season-fantasy-football-rankings-help-you-win-now/")
# Pinned here (not read from pull_cbs) so the file also runs against
# origin/main's pull_cbs for the regression proof.
AUTHOR = "https://www.cbssports.com/writers/dave-richard/"
HUB = "https://www.cbssports.com/fantasy/football/"
SITEMAP = "https://www.cbssports.com/news-fantasy-sitemap.xml"


def url_key(url):
    return re.sub(r"^https?://[^/]+", "", url).split("?")[0].rstrip("/").lower()


def discover(mod, week, fetch, llm=None):
    """mod.discover_url, passing llm_fn only where the signature has it."""
    import inspect
    if llm is not None and "llm_fn" in inspect.signature(mod.discover_url).parameters:
        return mod.discover_url(week, fetch_fn=fetch, llm_fn=llm)
    return mod.discover_url(week, fetch_fn=fetch)


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def cbs_site(listings=("author", "hub", "sitemap"), w5=True, extra=None):
    """Fake fetch serving the saved pages. Host-insensitive (www or the
    sportsfly mirror), like the real site; anything else is a 404."""
    pages = {}
    if "author" in listings:
        pages[AUTHOR] = read("cbs-author-dave-richard-2026-10-08.html")
    if "hub" in listings:
        pages[HUB] = read("cbs-fantasy-football-hub-2026-10-08.html")
    if "sitemap" in listings:
        pages[SITEMAP] = read("cbs-news-fantasy-sitemap-2026-10-08.xml")
    if w5:
        pages[CBS_W5] = read("cbs-week-5-article-2026-10-08.html")
    pages[CBS_W4] = read("cbs-week-4-article-2026-10-08.html")
    pages.update(extra or {})
    by_key = {url_key(u): body for u, body in pages.items()}
    calls = []

    def fetch(url):
        calls.append(url)
        body = by_key.get(url_key(url))
        return (200, body) if body is not None else (404, "<html>not found</html>")

    fetch.calls = calls
    return fetch


def no_llm(week, links):
    raise AssertionError("LLM fallback consulted although a deterministic path found the article")


class CbsDiscoveryTest(unittest.TestCase):
    def test_each_listing_path_alone_finds_week_5(self):
        for path in ("author", "hub", "sitemap"):
            with self.subTest(path=path):
                url = discover(pull_cbs, 5, cbs_site(listings=(path,)), llm=no_llm)
                self.assertEqual(url, CBS_W5)

    def test_all_listings(self):
        self.assertEqual(discover(pull_cbs, 5, cbs_site(), llm=no_llm), CBS_W5)

    def test_week_4_still_found_for_week_4(self):
        self.assertEqual(discover(pull_cbs, 4, cbs_site(), llm=no_llm), CBS_W4)

    def test_never_falls_back_to_an_older_week(self):
        """Week 5 not served: no week-4 URL comes back, a quiet miss naming
        the newest older week the listings advertise."""
        with self.assertRaises(pull_cbs.DiscoveryFailed) as ctx:
            discover(pull_cbs, 5, cbs_site(w5=False), llm=lambda w, ls: None)
        self.assertTrue(ctx.exception.quiet)
        self.assertEqual(ctx.exception.newest_week, 4)

    def test_no_readable_listing_is_loud(self):
        with self.assertRaises(pull_cbs.DiscoveryFailed) as ctx:
            pull_cbs.discover_url(5, fetch_fn=cbs_site(listings=(), w5=False),
                                  llm_fn=lambda w, ls: None)
        self.assertFalse(ctx.exception.quiet)

    def test_headline_week_decides_not_the_slug(self):
        """A week-5 slug whose page headline says Week 4 is rejected."""
        fake = CBS_W5.replace("2026-week-5", "week-5-extra")
        site = cbs_site(w5=False, extra={
            fake: read("cbs-week-4-article-2026-10-08.html"),
            HUB: '<a href="%s">Week 5 trade chart</a>' % fake})
        self.assertIsNotNone(pull_cbs.check_article(fake, 5, site))
        with self.assertRaises(pull_cbs.DiscoveryFailed):
            pull_cbs.discover_url(5, fetch_fn=site, llm_fn=lambda w, ls: None)

    def test_slugless_url_week_comes_from_the_headline(self):
        slugless = "https://www.cbssports.com/fantasy/football/news/jsn-takes-over-no-1-wr/"
        site = cbs_site(extra={slugless: read("cbs-week-5-article-2026-10-08.html")})
        self.assertIsNone(pull_cbs.extract_week_from_url(slugless))
        self.assertEqual(pull_cbs.page_week(slugless, site), 5)
        self.assertEqual(pull_cbs.extract_week_from_url(CBS_W5), 5)

    def test_week_5_tables_parse(self):
        tables, headline = pull_cbs.pull(CBS_W5, fetch_fn=cbs_site())
        self.assertIn("Week 5", headline)
        self.assertEqual([len(t["rows"]) for t in tables], [35, 44, 45, 15])
        self.assertEqual(tables[0]["headers"], ["Player", "tm", "1QB-4", "1QB-6", "2QB"])


class CbsLlmFallbackTest(unittest.TestCase):
    """The LLM only nominates a listing link; the page checks decide."""

    SLUGLESS = "https://www.cbssports.com/fantasy/football/news/jsn-takes-over-no-1-wr-spot/"

    def site(self, article):
        # A listing whose only route to the chart is a link with no
        # "trade chart" wording: the deterministic paths cannot see it.
        hub = '<a href="%s">Jaxon Smith-Njigba takes over No. 1 WR spot</a>' % self.SLUGLESS
        return cbs_site(listings=(), w5=False, extra={HUB: hub, self.SLUGLESS: article})

    def test_consulted_only_when_deterministic_paths_fail_and_pick_validated(self):
        seen = []

        def llm(week, links):
            seen.append((week, [u for u, _t in links]))
            return self.SLUGLESS

        url = pull_cbs.discover_url(5, fetch_fn=self.site(read("cbs-week-5-article-2026-10-08.html")),
                                    llm_fn=llm)
        self.assertEqual(url, self.SLUGLESS)
        self.assertEqual(seen[0][0], 5)
        self.assertIn(self.SLUGLESS, seen[0][1])

    def test_wrong_week_pick_rejected(self):
        with self.assertRaises(pull_cbs.DiscoveryFailed):
            pull_cbs.discover_url(5, fetch_fn=self.site(read("cbs-week-4-article-2026-10-08.html")),
                                  llm_fn=lambda w, ls: self.SLUGLESS)

    def test_llm_pick_only_returns_listed_urls(self):
        links = [("https://a.example/1", "one"), ("https://a.example/2", "two")]
        self.assertEqual(ad.llm_pick("X", 5, links, complete=lambda p: '{"index": 2}'),
                         "https://a.example/2")
        for reply in ('{"index": 3}', '{"index": 0}', '{"index": null}', "https://evil.example/",
                      '{"index": true}', "no json"):
            self.assertIsNone(ad.llm_pick("X", 5, links, complete=lambda p, r=reply: r), reply)

    def test_llm_failure_or_missing_key_is_a_no_op(self):
        def boom(prompt):
            raise RuntimeError("api down")
        self.assertIsNone(ad.llm_pick("X", 5, [("https://a/1", "t")], complete=boom))
        with mock.patch.dict(os.environ, {ad.LLM_KEY_ENV: ""}):
            self.assertIsNone(ad.llm_pick("X", 5, [("https://a/1", "t")]))

    def test_prompt_names_publisher_week_and_links(self):
        got = []
        ad.llm_pick("CBS Sports (Dave Richard)", 5, [("https://a/1", "Week 5 chart")],
                    complete=lambda p: got.append(p) or "{}")
        self.assertIn("Week 5", got[0])
        self.assertIn("1. https://a/1 | Week 5 chart", got[0])


class OverdueTest(unittest.TestCase):
    """A miss is a quiet "not published yet" only while the week is young."""

    TUE, THU = date(2026, 10, 6), date(2026, 10, 8)  # week 5 turns over Tue Oct 6

    def run_cbs(self, today, discover_fn):
        import ingest_cbs
        cfg = dict(ingest_cbs.CFG, today_fn=lambda: today)
        with tempfile.TemporaryDirectory() as td:
            return ic.run_ingest(cfg, week=5, discover_fn=discover_fn,
                                 pull_fn=lambda u: self.fail("must not pull"),
                                 db=object(), state_dir=td, pulls_dir=td)

    def miss(self, week):
        import ingest_cbs
        # The class the ingest catches (other test modules may re-load pull_cbs).
        raise ingest_cbs.CFG["discovery_failed_cls"]("nothing", quiet=True, newest_week=4)

    def test_young_week_miss_is_quiet(self):
        res = self.run_cbs(self.TUE, self.miss)
        self.assertEqual(res["status"], "not_published")
        self.assertEqual(res["newest_week"], 4)

    def test_overdue_miss_is_loud(self):
        with self.assertRaises(ic.IngestError) as ctx:
            self.run_cbs(self.THU, self.miss)
        self.assertIn("DISCOVERY_OVERDUE", str(ctx.exception))

    def test_overdue_older_week_fallback_is_loud(self):
        """The USA Today shape: discovery returns last week's URL."""
        with self.assertRaises(ic.IngestError) as ctx:
            self.run_cbs(self.THU, lambda w: CBS_W4)
        self.assertIn("DISCOVERY_OVERDUE", str(ctx.exception))
        self.assertEqual(self.run_cbs(self.TUE, lambda w: CBS_W4)["status"], "not_published")

    def test_backfill_of_an_old_week_stays_quiet(self):
        cfg = {"name": "x", "week_fn": __import__("_common").content_week, "overdue_after_days": 2}
        self.assertFalse(ic.overdue(cfg, 3, today=self.THU))
        self.assertTrue(ic.overdue(cfg, 5, today=self.THU))
        self.assertFalse(ic.overdue(cfg, 5, today=date(2026, 10, 7)))

    def test_every_source_has_the_guard(self):
        import ingest_cbs
        import ingest_usatoday
        for cfg in (ingest_cbs.CFG, ingest_usatoday.CFG):
            self.assertEqual(cfg["overdue_after_days"], 2, cfg["name"])
        self.assertEqual(ingest_cbs.CFG["discovery_failed_cls"].__name__, "DiscoveryFailed")
        self.assertEqual(ingest_cbs.CFG["discovery_failed_cls"].__module__, "pull_cbs")
        self.assertEqual(fp.OVERDUE_AFTER_DAYS, 2)

    def test_fantasypros_overdue_exit(self):
        with mock.patch.object(fp, "today_ct", return_value=self.THU):
            self.assertEqual(fp._not_published(5, "x", save=True), 1)
            self.assertEqual(fp._not_published(5, "x", save=False), 0)
        with mock.patch.object(fp, "today_ct", return_value=self.TUE):
            self.assertEqual(fp._not_published(5, "x", save=True), 0)


class FantasyProsDiscoveryTest(unittest.TestCase):
    W5_OCT = "https://www.fantasypros.com/2026/10/fantasy-football-trade-value-chart-week-5-2026/"

    def site(self):
        pages = {
            fp.ARTICLES_SITEMAP: read("fantasypros-articles-sitemap-2026-10-08.xml"),
            self.W5_OCT: read("fantasypros-week-5-article-2026-10-08.html"),
            fp.SECTION_SLUG % 4: "<title>Fantasy Football Trade Value Chart: Week 4 (2026)</title>",
        }

        def fetch(url):
            return (200, pages[url]) if url in pages else (404, "")
        return fetch

    def test_sitemap_finds_week_5_when_the_slug_template_misses(self):
        with mock.patch.object(fp, "today_ct", return_value=date(2026, 10, 8)):
            url = discover(fp, 5, self.site(), llm=no_llm)
        self.assertEqual(url, self.W5_OCT)


class UsaTodayDiscoveryTest(unittest.TestCase):
    W4 = ("https://www.usatoday.com/story/sports/fantasy/football/2026/09/29/"
          "fantasy-football-trade-value-chart-week-4-ros-rankings/1/")
    W5_REWORDED = ("https://www.usatoday.com/story/sports/fantasy/football/2026/10/06/"
                   "week-5-fantasy-football-trade-chart-rest-of-season/2/")

    def fetch(self, urls):
        body = "<urlset>%s</urlset>" % "".join("<url><loc>%s</loc></url>" % u for u in urls)
        return lambda url: (200, body)

    def test_reworded_week_5_slug_beats_week_4_fallback(self):
        with mock.patch.object(usat, "today_ct", return_value=date(2026, 10, 8)):
            url = discover(usat, 5, self.fetch([self.W4, self.W5_REWORDED]), llm=no_llm)
        self.assertEqual(url, self.W5_REWORDED)

    def test_llm_pick_must_carry_the_week(self):
        odd = ("https://www.usatoday.com/story/sports/fantasy/football/2026/10/06/"
               "ros-player-values-jsn-tops-receivers/3/")
        with mock.patch.object(usat, "today_ct", return_value=date(2026, 10, 8)):
            url = usat.discover_url(5, fetch_fn=self.fetch([self.W4, odd]),
                                    llm_fn=lambda w, ls: odd)
        self.assertEqual(url, self.W4)  # pick rejected (no week 5 in slug) -> old fallback


class WorkflowUrlInputTest(unittest.TestCase):
    WF = (ROOT / ".github/workflows/trade-chart-ingest.yml").read_text(encoding="utf-8")

    def argv(self, inputs, source="cbs"):
        from tests.test_rebuild_chain_workflow import find_step, script_of
        from tests.test_trade_chart_ingest_ci import render
        ctx = {"matrix.source": source, "steps.cfg.outputs.mode": "dry"}
        for k in ("week",):
            ctx[f"github.event.inputs.{k}"] = inputs.get(k, "")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "bin").mkdir()
            fake = td / "bin" / "python3"
            fake.write_text(f'#!/bin/bash\necho "$@" > {td}/argv\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            env = {"PATH": f"{td / 'bin'}:/usr/bin:/bin", "HOME": str(td),
                   "GITHUB_OUTPUT": str(td / "out"),
                   "INPUT_URL": inputs.get("url", ""), "INPUT_SOURCE": inputs.get("source", "")}
            r = subprocess.run(["bash", "-e", "-c", render(script_of(find_step(self.WF, "Ingest")), ctx)],
                               cwd=td, env=env, capture_output=True, text=True)
            if r.returncode != 0:
                return None
            return (td / "argv").read_text(encoding="utf-8").split()

    def test_url_passed_to_the_ingest(self):
        self.assertEqual(self.argv({"url": CBS_W5, "source": "cbs", "week": "5"}),
                         ["ops/watchdog/ingest_cbs.py", "--dry-run", "--week", "5", "--url", CBS_W5])

    def test_url_with_source_both_refused(self):
        self.assertIsNone(self.argv({"url": CBS_W5, "source": "both"}))

    def test_overdue_error_code_and_optional_key(self):
        self.assertIn('grep -q "DISCOVERY_OVERDUE" /tmp/ingest.log && code=DISCOVERY_OVERDUE', self.WF)
        self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", self.WF)


if __name__ == "__main__":
    unittest.main()
