"""JEG-1535: v2 swap routes and storage bridge for values.html.

Checks:
1. dist/index.html#player-values?swapped=1 -> values.html (Chart tab selected)
2. dist/index.html#value-overrides?swapped=1 -> values.html#overrides (Overrides tab)
3. dist/v2/index.html#value-overrides?valuecontext=1&ov=2227:58.0?swapped=1 ->
   values.html#overrides, override for player 2227 applied (DDF.engine.overrides.get('2227')===58),
   not written to localStorage ddf-v2-value-overrides
4. Without ?swapped=1 under navigator.webdriver the v2 view stays (Playwright automation escape)
5. dist/index.html (empty hash) stays on the v2 landing page
6. dist/next/values.html redirects to ../values.html keeping the hash
Storage bridge:
7. A record written in the live override format to localStorage before load shows as an override
8. An override set via DDF.engine.overrides.set is in localStorage in the live format
9. ddf.v2.league-settings {v:1, scoring:'half_ppr', teams:10, roster:{...}} saved before load
   is what the page applies
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'

READY_EXPR = (
    "() => document.body.classList.contains('values-live')"
    " && document.querySelector('#rows tr') !== null"
)
OVERRIDES_READY = (
    "() => document.body.classList.contains('values-live')"
)


def setUpModule():
    _render_env.ensure_built()


def _pw():
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except Exception as exc:
        raise _render_env.unavailable(f'Playwright not available: {exc}') from exc
    return sync_playwright, PlaywrightError


class ValuesSwapRoutesTest(unittest.TestCase):

    def _browser(self, pw, PlaywrightError):
        try:
            return pw.chromium.launch(
                args=_render_env.HERMETIC_ARGS,
                executable_path=_render_env.chromium_executable(),
            )
        except PlaywrightError as exc:
            raise _render_env.unavailable(f'Chromium not available: {exc}') from exc

    def test_player_values_swapped_lands_on_chart_tab(self):
        """#player-values?swapped=1 navigates to values.html with Chart tab active."""
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/index.html?swapped=1#player-values',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(READY_EXPR, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                final_url = page.url
                self.assertIn('values.html', final_url,
                              f'Did not land on values.html; got {final_url!r}')
                # Chart tab should be selected
                tab_selected = page.evaluate(
                    "() => document.getElementById('tab-chart')?.getAttribute('aria-selected')"
                )
                self.assertEqual(tab_selected, 'true',
                                 'Chart tab not selected after #player-values redirect')
            finally:
                browser.close()

    def test_value_overrides_swapped_lands_on_overrides_tab(self):
        """#value-overrides?swapped=1 navigates to values.html#overrides with Overrides tab."""
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/index.html?swapped=1#value-overrides',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                final_url = page.url
                self.assertIn('values.html', final_url,
                              f'Did not land on values.html; got {final_url!r}')
                # Overrides tab should be selected
                tab_selected = page.evaluate(
                    "() => document.getElementById('tab-ov')?.getAttribute('aria-selected')"
                )
                self.assertEqual(tab_selected, 'true',
                                 'Overrides tab not selected after #value-overrides redirect')
            finally:
                browser.close()

    def test_v2_value_overrides_link_applies_override_for_visit(self):
        """v2#value-overrides?valuecontext=1&ov=2227:58.0?swapped=1 -> values.html#overrides,
        override applied for the visit (DDF.engine.overrides.get('2227') === 58),
        not persisted to localStorage ddf-v2-value-overrides."""
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                # The v2 page is at dist/v2/index.html, served at /v2/index.html
                # The hash passes the override context
                url = (f'{base_url}/v2/index.html'
                       f'?swapped=1#value-overrides?valuecontext=1&ov=2227:58.0')
                page.goto(url, wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=25000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live after v2 redirect: {exc}')

                final_url = page.url
                self.assertIn('values.html', final_url,
                              f'Did not reach values.html; got {final_url!r}')
                self.assertIn('overrides', final_url,
                              f'Override hash missing; got {final_url!r}')

                # Override for player 2227 should be applied
                ov_val = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.get('2227') : undefined; }"
                )
                self.assertEqual(ov_val, 58,
                                 f'Override for 2227 not applied; got {ov_val!r}')

                # Must NOT be persisted to localStorage
                stored = page.evaluate(
                    "() => { try { return localStorage.getItem('ddf-v2-value-overrides'); } catch(_){return null;} }"
                )
                if stored:
                    import json
                    try:
                        data = json.loads(stored)
                        saved_vals = data.get('values', {})
                        self.assertNotIn('2227', saved_vals,
                                         'Override for 2227 was written to localStorage (should be session-only)')
                    except (ValueError, KeyError):
                        pass  # unparseable means nothing was stored for this player
            finally:
                browser.close()

    def test_automation_escape_without_swapped_flag(self):
        """Without ?swapped=1, navigator.webdriver=true means v2 stays on its view.

        Playwright sets navigator.webdriver=true; without ?swapped=1 the v2 route
        redirect is skipped, so the page stays on v2/index.html (not values.html).
        """
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/index.html#player-values',
                          wait_until='networkidle', timeout=60000)
                # Wait briefly; if no redirect, page stays on index.html
                try:
                    page.wait_for_timeout(3000)
                except PlaywrightError:
                    pass

                final_url = page.url
                self.assertNotIn('values.html', final_url,
                                 f'Should NOT redirect without ?swapped=1; got {final_url!r}')
            finally:
                browser.close()

    def test_empty_hash_stays_on_v2_landing(self):
        """dist/index.html with empty hash stays on the v2 landing page."""
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/index.html', wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_timeout(2000)
                except PlaywrightError:
                    pass

                final_url = page.url
                self.assertNotIn('values.html', final_url,
                                 f'Empty hash should not redirect; got {final_url!r}')
                # Should still be index.html (v2 page)
                self.assertIn('index.html', final_url,
                              f'Should remain on index.html; got {final_url!r}')
            finally:
                browser.close()

    def test_next_values_html_redirects_keeping_hash(self):
        """dist/next/values.html redirects to ../values.html and preserves the hash."""
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/next/values.html#overrides',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'redirect from next/values.html did not land on values.html: {exc}')

                final_url = page.url
                # Must land on the root values.html, not next/
                self.assertNotIn('/next/', final_url,
                                 f'Should not stay in next/; got {final_url!r}')
                self.assertIn('values.html', final_url,
                              f'Should reach values.html; got {final_url!r}')
                # Hash should be preserved
                self.assertIn('overrides', final_url,
                              f'Hash #overrides should be kept; got {final_url!r}')
            finally:
                browser.close()

    def test_storage_bridge_override_read(self):
        """An override written to localStorage in the live format before load
        shows up in the values.html Overrides tab."""
        sync_playwright, PlaywrightError = _pw()
        import json
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                # Seed localStorage with a live-format override before navigation
                override_data = json.dumps({
                    'v': 2,
                    'basis': None,
                    'values': {'2227': 42.5},
                    'names': {'2227': 'Test Player'},
                })
                _seed = json.dumps(override_data)
                page.add_init_script(
                    f'(function(){{'
                    f'try{{localStorage.clear();sessionStorage.clear();'
                    f'localStorage.setItem("ddf-v2-value-overrides",{_seed});'
                    f'}}catch(_){{}}}})()'
                )
                page.goto(f'{base_url}/values.html#overrides',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                # DDF.engine.overrides.get('2227') should be 42.5
                ov_val = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.get('2227') : undefined; }"
                )
                self.assertEqual(ov_val, 42.5,
                                 f'Seeded override not applied; got {ov_val!r}')
            finally:
                browser.close()

    def test_storage_bridge_override_write(self):
        """An override set via DDF.engine.overrides.set is persisted to
        localStorage in the live format (ddf-v2-value-overrides)."""
        sync_playwright, PlaywrightError = _pw()
        import json
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/values.html', wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(READY_EXPR, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                # Set an override via DDF.engine.overrides.set
                page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "if(e) e.overrides.set('2227', 55.0); }"
                )
                try:
                    page.wait_for_timeout(300)
                except PlaywrightError:
                    pass

                # Read it back from localStorage
                stored_raw = page.evaluate(
                    "() => { try { return localStorage.getItem('ddf-v2-value-overrides'); } "
                    "catch(_){return null;} }"
                )
                self.assertIsNotNone(stored_raw, 'Nothing written to ddf-v2-value-overrides')
                stored = json.loads(stored_raw)
                self.assertIn('values', stored, 'No values key in stored override')
                self.assertIn('2227', stored['values'],
                              f'Player 2227 not in stored overrides: {stored!r}')
                self.assertEqual(stored['values']['2227'], 55.0,
                                 f'Wrong stored value: {stored["values"]["2227"]!r}')
            finally:
                browser.close()

    def test_league_settings_bridge_applied(self):
        """ddf.v2.league-settings saved to localStorage before load is applied by values.html."""
        sync_playwright, PlaywrightError = _pw()
        import json
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                league_settings = json.dumps({
                    'v': 1,
                    'scoring': 'half_ppr',
                    'teams': 10,
                    'roster': {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 1, 'FLEX': 1,
                               'SUPERFLEX': 0, 'BENCH': 6, 'K': 0, 'DST': 0},
                })
                _seed = json.dumps(league_settings)
                page.add_init_script(
                    f'(function(){{'
                    f'try{{localStorage.clear();sessionStorage.clear();'
                    f'localStorage.setItem("ddf.v2.league-settings",{_seed});'
                    f'}}catch(_){{}}}})()'
                )
                page.goto(f'{base_url}/values.html', wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(READY_EXPR, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                settings = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.settings() : null; }"
                )
                self.assertIsNotNone(settings, 'DDF.engine.settings() returned null')
                self.assertEqual(settings.get('scoring'), 'half_ppr',
                                 f'Scoring not applied: {settings!r}')
                self.assertEqual(settings.get('teams'), 10,
                                 f'Teams not applied: {settings!r}')
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
