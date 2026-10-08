"""Launch QA (2026-10-08): public-surface regressions found on the live site.

- The retired waiver-dashboard / weekly-signals stubs linked to "/", which on a
  GitHub Pages project site is the account root (404), not the dashboard.
- The project published no 404 page, so a bad /fantasy-tools/ URL showed
  GitHub's generic page with no way back.
- The main page's source footnote linked Week 2 articles while the chart showed
  Week 5 values, said "ESPN remains live", and the curve status called the
  ESPN series "ESPN live" although it is a daily projection pull.
- Monitor pages under modules/ are internal and must not be indexed.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
RETIRED = [ROOT / "waiver_wire" / "dashboard" / "index.html",
           ROOT / "weekly_vegas" / "dashboard" / "index.html"]
MONITORS = [ROOT / "modules" / name for name in ("status.html", "dashboard.html", "consolidation.html")]


def retired_links_ok(html: str) -> bool:
    hrefs = re.findall(r'<a\s[^>]*href="([^"]*)"', html)
    return bool(hrefs) and all(h not in ("/", "") for h in hrefs)


def has_noindex(html: str) -> bool:
    return bool(re.search(r'<meta\s+name="robots"\s+content="[^"]*noindex', html))


def stale_live_copy(index_html: str, widget_js: str) -> list:
    problems = []
    if re.search(r'href="[^"]*week-\d+[^"]*"', index_html):
        problems.append("week-specific article link in the main page")
    if "ESPN remains live" in index_html:
        problems.append("footnote says ESPN remains live")
    if re.search(r"ESPN live (plus|is shown)", widget_js):
        problems.append("curve status calls ESPN 'live'")
    return problems


class LaunchSurfaceTests(unittest.TestCase):
    def test_retired_stubs_link_back_inside_the_project(self):
        for path in RETIRED:
            html = path.read_text(encoding="utf-8")
            self.assertTrue(retired_links_ok(html), f"{path} links outside /fantasy-tools/")
            self.assertTrue(has_noindex(html), f"{path} should be noindex")
        # Negative: the pre-fix stub (href="/") is rejected.
        self.assertFalse(retired_links_ok('<p><a href="/">main dashboard</a></p>'))

    def test_project_404_page_is_published(self):
        page = (APP / "404.html").read_text(encoding="utf-8")
        self.assertIn('href="/fantasy-tools/"', page)
        sync = (ROOT / "pipelines" / "sync_dashboard_artifacts.py").read_text(encoding="utf-8")
        self.assertRegex(sync, r'for name in \([^)]*"404\.html"')

    def test_monitor_pages_are_noindex(self):
        for path in MONITORS:
            self.assertTrue(has_noindex(path.read_text(encoding="utf-8")), f"{path} lacks noindex")
        self.assertFalse(has_noindex("<head><title>Pipeline Monitor</title></head>"))

    def test_main_page_freshness_copy(self):
        index_html = (APP / "index.html").read_text(encoding="utf-8")
        widget_js = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertEqual([], stale_live_copy(index_html, widget_js))
        # Negative: the pre-fix copy is caught.
        old = ('<a href="https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-2-2026/">'
               'FantasyPros</a> ESPN remains live.')
        self.assertEqual(3, len(stale_live_copy(old, "`ESPN live plus ${liveCount}")))

    def test_main_page_has_social_meta(self):
        index_html = (APP / "index.html").read_text(encoding="utf-8")
        for prop in ("og:title", "og:description", "og:image"):
            self.assertIn(f'property="{prop}"', index_html)
        self.assertNotIn("five independent series", index_html)


if __name__ == "__main__":
    unittest.main()
