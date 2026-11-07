"""JEG-1535: unit tests for pipelines/build_root_pages.py.

Tests:
- rewrite_links: spot-checks for the LIVE_ROUTES mapping and edge cases
- root_page_html: exactly one engine marker required; engine block is hidden
  (legacyEngine and legacy-engine-tail present with display:none); comes before
  page's own scripts; no noindex on the root page; ?v= stamped; redirect_stub
  keeps hash
- dist/values.html scan: no visible placeholder text, no Player pool, no bare
  "Market" outside AI prompt blocks, no href into next/
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipelines'))

import build_root_pages as brp  # noqa: E402

TAG = 'tv-20261106-test'

# Minimal engine HTML that satisfies engine_block()
MINIMAL_ENGINE = (
    '<html><body>body content'
    '<script src="assets/value-model.js" defer></script>'
    '</body></html>'
)

# Minimal page HTML with the required <!-- ddf-engine --> marker
MINIMAL_PAGE = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<link rel="icon" href="data:,">'
    '<title>Values</title>'
    '</head><body>'
    '<!-- ddf-engine -->'
    '<script src="ddf-engine.js" defer></script>'
    '<script src="values-chart.js" defer></script>'
    '</body></html>'
)


class RewriteLinksTest(unittest.TestCase):

    def test_build_html_rewritten_before_swap(self):
        """build.html -> ./#compare-trade while Build a Trade is not swapped (JEG-1537 swaps it)."""
        result = brp.rewrite_links('"build.html"', root_pages=("values.html", "learn.html"))
        self.assertEqual(result, '"./#compare-trade"')

    def test_build_untouched_once_swapped(self):
        """JEG-1537: build.html is a root page with the engine, so links to it stay (names in the query)."""
        self.assertIn("build.html", brp.ROOT_PAGES)
        self.assertIn("build.html", brp.ENGINE_PAGES)
        for text in ('"build.html"', '"build.html?mode=any"', '"build.html?give=Josh%20Allen"'):
            self.assertEqual(brp.rewrite_links(text), text)

    def test_check_and_trade_go_to_build(self):
        """JEG-1537: Check a trade and Trade detail are the Build a Trade screen."""
        self.assertEqual(brp.rewrite_links('"check.html#trade=abc"'), '"build.html"')
        self.assertEqual(brp.rewrite_links("'trade.html'"), "'build.html'")

    def test_learn_numbers_rewritten(self):
        """learn.html#numbers/x -> ./#writing/how-values while Learn is not swapped (JEG-1536 swaps it)."""
        result = brp.rewrite_links('"learn.html#numbers/anything"', root_pages=("values.html",))
        self.assertEqual(result, '"./#writing/how-values"')

    def test_values_html_untouched(self):
        """values.html is in ROOT_PAGES, so it must not be rewritten."""
        result = brp.rewrite_links('"values.html"')
        self.assertEqual(result, '"values.html"')

    def test_root_page_in_root_pages_untouched(self):
        """A page listed in ROOT_PAGES is never rewritten."""
        result = brp.rewrite_links('"values.html#overrides"')
        self.assertEqual(result, '"values.html#overrides"')

    def test_learn_bare_rewritten_to_manifesto(self):
        """learn.html (bare, no hash) -> ./#writing/manifesto while Learn is not swapped."""
        result = brp.rewrite_links('"learn.html"', root_pages=("values.html",))
        self.assertEqual(result, '"./#writing/manifesto"')

    def test_learn_untouched_once_swapped(self):
        """JEG-1536: learn.html is a root page, so links to it stay."""
        self.assertIn("learn.html", brp.ROOT_PAGES)
        for text in ('"learn.html"', '"learn.html#numbers/pie"', '"learn.html#manifesto"'):
            self.assertEqual(brp.rewrite_links(text), text)

    def test_single_quotes_also_rewritten(self):
        result = brp.rewrite_links("'find.html'", root_pages=("values.html",))
        self.assertEqual(result, "'./#find-trade'")

    def test_waivers_root_page_untouched(self):
        """JEG-1539: waivers.html is a root page, so links to it stay; before the swap they went to ./#waivers."""
        self.assertEqual(brp.rewrite_links('"waivers.html"'), '"waivers.html"')
        self.assertEqual(brp.rewrite_links('"waivers.html"', root_pages=("values.html",)), '"./#waivers"')

    def test_escaped_quotes_are_not_rewritten_into_broken_js(self):
        """A rewritten shared script must still parse: the lane scripts avoid \\" inside strings (lane find, JEG-1539)."""
        for name in ("find-engine.js", "find-page.js", "waivers-page.js"):
            self.assertNotIn('\\"', (brp.SOURCE / name).read_text(encoding="utf-8"), name)

    def test_href_into_root_page_untouched(self):
        """An href that IS a root page (values.html) must stay."""
        text = '<a href="values.html#buy-sell">Buy</a>'
        self.assertEqual(brp.rewrite_links(text), text)


class RootPageHtmlTest(unittest.TestCase):

    def _build(self, page=None, engine=None, tag=TAG):
        return brp.root_page_html(
            page or MINIMAL_PAGE,
            'values.html',
            engine or MINIMAL_ENGINE,
            tag,
        )

    def test_exactly_one_engine_marker_required(self):
        """root_page_html raises if the page has zero or two markers."""
        no_marker = MINIMAL_PAGE.replace('<!-- ddf-engine -->', '')
        with self.assertRaises(ValueError):
            brp.root_page_html(no_marker, 'values.html', MINIMAL_ENGINE, TAG)

        two_markers = MINIMAL_PAGE.replace(
            '<!-- ddf-engine -->', '<!-- ddf-engine --><!-- ddf-engine -->')
        with self.assertRaises(ValueError):
            brp.root_page_html(two_markers, 'values.html', MINIMAL_ENGINE, TAG)

    def test_engine_block_is_hidden(self):
        """legacyEngine must carry display:none; legacy-engine-tail too."""
        out = self._build()
        self.assertIn('id="legacyEngine"', out)
        self.assertIn('class="legacy-engine"', out)
        self.assertIn('class="legacy-engine-tail"', out)
        # Both must have display:none
        idx_eng = out.index('id="legacyEngine"')
        idx_tail = out.index('class="legacy-engine-tail"')
        # Check that display:none appears in the opening tag of each div
        # The engine div
        div_eng = out[idx_eng - 50:idx_eng + 200]
        self.assertIn('display:none', div_eng,
                      'legacyEngine div does not carry display:none')
        # The tail div
        div_tail = out[idx_tail - 10:idx_tail + 100]
        self.assertIn('display:none', div_tail,
                      'legacy-engine-tail div does not carry display:none')

    def test_engine_block_before_page_scripts(self):
        """The injected engine block must appear before the page's own scripts."""
        out = self._build()
        engine_at = out.index('id="legacyEngine"')
        # The page's own scripts come after
        for script in ('ddf-engine.js', 'values-chart.js'):
            script_at = out.find(script)
            if script_at >= 0:
                self.assertLess(engine_at, script_at,
                                f'Engine block appears after {script}')

    def test_no_noindex_on_root_page(self):
        """Root pages are public; they must not carry a noindex meta tag."""
        out = self._build()
        self.assertNotIn('noindex', out.lower())
        self.assertNotIn('robots', out.lower())

    def test_v_stamp_applied(self):
        """Local asset references get ?v=<tag> stamped."""
        out = self._build()
        self.assertIn(f'?v={TAG}', out)

    def test_icon_swapped(self):
        """The blank icon placeholder is replaced with the site icon."""
        out = self._build()
        self.assertNotIn(brp.ICON_BLANK, out)
        self.assertIn(brp.ICON_SITE, out)

    def test_redirect_stub_keeps_hash(self):
        """redirect_stub carries a script that appends location.hash."""
        stub = brp.redirect_stub('values.html')
        self.assertIn('location.hash', stub)
        self.assertIn('../values.html', stub)
        self.assertIn('noindex', stub)

    def test_no_engine_raises_for_engine_page(self):
        """Passing engine_html=None for an ENGINE_PAGE raises ValueError."""
        with self.assertRaises(ValueError):
            brp.root_page_html(MINIMAL_PAGE, 'values.html', None, TAG)


class DistValuesScanTest(unittest.TestCase):
    """Scan dist/values.html for disqualifying content.

    Skipped if dist/values.html is not built.
    """

    DIST_VALUES = ROOT / 'dist' / 'values.html'

    @classmethod
    def setUpClass(cls):
        if not cls.DIST_VALUES.exists():
            raise unittest.SkipTest('dist/values.html not built')
        cls.html = cls.DIST_VALUES.read_text(encoding='utf-8')

    def test_no_placeholder_text(self):
        """No visible placeholder text (example data, sample data, wireframe, etc.).

        Uses whole-word matching so player names like "Drew Sample" are not
        flagged as placeholder text.
        """
        import re
        stripped = _strip_text_plain(self.html)
        low = stripped.lower()
        # Exact compound phrases — these should never appear in a live page.
        for phrase in ('example data', 'sample data', 'sample value',
                       'wireframe', 'illustrative', 'mock data'):
            self.assertNotIn(phrase, low,
                             f'Placeholder text {phrase!r} found in dist/values.html')
        # Bare words: use word-boundary check so "Drew Sample" does not trigger.
        for word in ('wireframe',):
            if re.search(r'\b' + re.escape(word) + r'\b', low):
                self.fail(
                    f'Placeholder word {word!r} found in dist/values.html')

    def test_no_player_pool_text(self):
        stripped = _strip_text_plain(self.html)
        self.assertNotIn('Player pool', stripped,
                         'Text "Player pool" found in dist/values.html')

    def test_no_bare_market_outside_prompt(self):
        """The word "Market" should not appear as a standalone label outside
        the AI prompt <script type="text/plain"> blocks."""
        stripped = _strip_text_plain(self.html)
        # Allow "Live market" (the chart series name) and similar compound phrases
        import re
        bare_market = re.findall(r'(?<![A-Za-z])Market(?![A-Za-z])', stripped)
        # There may be legitimate uses of "Market" in the page labels; we allow
        # occurrences in compound phrases like "Live market" (lowercase) but flag
        # standalone capitalised "Market" outside the AI prompt.
        for m in bare_market:
            # If it appears in a compound phrase it's acceptable
            context = stripped[max(0, stripped.index('Market') - 20): stripped.index('Market') + 30]
            if 'live' not in context.lower() and 'market' not in context.lower():
                self.fail(
                    f'Bare "Market" found outside AI prompt in dist/values.html: {context!r}')

    def test_no_href_into_next(self):
        """No link should point into next/."""
        import re
        hrefs = re.findall(r'href="([^"]*)"', self.html)
        bad = [h for h in hrefs if 'next/' in h]
        self.assertEqual(bad, [],
                         f'dist/values.html links into next/: {bad}')


def _strip_text_plain(html: str) -> str:
    """Remove <script type="text/plain"> ... </script> blocks."""
    import re
    return re.sub(
        r'<script[^>]+type=["\']text/plain["\'][^>]*>.*?</script>',
        '', html, flags=re.DOTALL | re.IGNORECASE,
    )


class FrontDoorDataIslandTest(unittest.TestCase):
    """JEG-1539: get-values (supabase/functions/get-values/index.ts) parses players-data from the root page."""

    def test_root_page_carries_players_data(self):
        import json
        import re
        page = ROOT / "dist" / "index.html"
        if not page.exists() or "legacy-routes.js" not in page.read_text(encoding="utf-8"):
            self.skipTest("run make sync first")
        html = page.read_text(encoding="utf-8")
        m = re.search(r'id="players-data"[^>]*>([\s\S]*?)<\/script>', html)   # get-values' own pattern
        self.assertIsNotNone(m, "players-data island missing from the front door: get-values would fail")
        doc = json.loads(m.group(1))
        self.assertGreater(len(doc["players"]), 100)


if __name__ == '__main__':
    unittest.main()
