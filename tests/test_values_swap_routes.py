"""JEG-1535 / JEG-1539: legacy-routes.js swap routes and storage bridge for values.html.

JEG-1539 step 5: dist/index.html is the redesigned front door; the v2 shell is build-only at
build/v2/index.html and served at /v2-app.html. legacy-routes.js (loaded first in <head> of index.html
and of the /v2/ redirect stub) forwards old hash routes to their new page; ?swapped=1 and the
navigator.webdriver escape are gone (they were in v2.js which no longer has SWAPPED_ROUTES).

Checks:
1. dist/index.html#player-values -> values.html (Chart tab selected, via legacy-routes.js)
2. dist/index.html#value-overrides -> values.html#overrides (Overrides tab)
3. dist/v2/index.html#value-overrides?valuecontext=1&ov=2227:58.0 ->
   values.html#overrides, override for player 2227 applied (DDF.engine.overrides.get('2227')===58),
   not written to localStorage ddf-v2-value-overrides
4. dist/index.html (empty hash) stays on the redesigned front door
5. dist/next/values.html redirects to ../values.html keeping the hash
Storage bridge:
6. A record written in the live override format to localStorage before load shows as an override
7. An override set via DDF.engine.overrides.set is in localStorage in the live format
8. ddf.v2.league-settings {v:1, scoring:'half_ppr', teams:10, roster:{...}} saved before load
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
        """index.html#player-values navigates to values.html with Chart tab active (via legacy-routes.js)."""
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
        """index.html#value-overrides navigates to values.html#overrides with Overrides tab (via legacy-routes.js)."""
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
                page.goto(f'{base_url}/index.html#value-overrides',
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
        """v2/index.html#value-overrides?valuecontext=1&ov=2227:58.0 -> values.html#overrides,
        override applied for the visit (DDF.engine.overrides.get('2227') === 58),
        not persisted to localStorage ddf-v2-value-overrides.
        JEG-1539: legacy-routes.js on the /v2/ stub forwards the hash+query; no ?swapped=1 needed."""
        sync_playwright, PlaywrightError = _pw()
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                # Simple clear: legacy-routes.js does a synchronous location.replace, no sessionStorage bridge.
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                # The /v2/ redirect stub at dist/v2/index.html forwards the hash+query via legacy-routes.js.
                url = (f'{base_url}/v2/index.html'
                       f'#value-overrides?valuecontext=1&ov=2227:58.0')
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

                # Must NOT be persisted to localStorage (session-only visit)
                import json
                stored_raw = page.evaluate(
                    "() => { try { return localStorage.getItem('ddf-v2-value-overrides'); } catch(_){return null;} }"
                )
                if stored_raw is not None:
                    try:
                        data = json.loads(stored_raw)
                        saved_vals = data.get('values', {})
                        self.assertNotIn('2227', saved_vals,
                                         'Override for 2227 was written to localStorage (should be session-only)')
                    except (ValueError, KeyError):
                        pass  # unparseable: nothing stored for this player
            finally:
                browser.close()

    def test_link_then_edit_saves_both(self):
        """Open values.html with link context, add a second override via the engine API.
        After save(): localStorage has both overrides, sessionStorage LINK_KEY is gone,
        and the hash no longer carries valuecontext/ov.  A fresh page load shows both."""
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
                # Load with a live-format link context (ov=2227:40 seeds one override)
                page.goto(
                    f'{base_url}/values.html#overrides?valuecontext=1&ov=2227:40',
                    wait_until='networkidle', timeout=60000,
                )
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                # Confirm we are in session mode (link context applied)
                in_session = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.session() : null; }"
                )
                self.assertTrue(in_session, 'Engine not in session mode after link-context load')

                # Add a second override for a different player - this calls save() which
                # transitions out of session mode, writes both overrides to localStorage,
                # removes LINK_KEY, and strips valuecontext/ov from the hash.
                ok = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.set('1001', 70) : false; }"
                )
                self.assertTrue(ok, 'overrides.set returned false')
                page.wait_for_timeout(300)

                # 1. Both keys in localStorage
                stored_raw = page.evaluate(
                    "() => { try { return localStorage.getItem('ddf-v2-value-overrides'); } catch(_){return null;} }"
                )
                self.assertIsNotNone(stored_raw, 'Nothing written to ddf-v2-value-overrides after edit')
                stored = json.loads(stored_raw)
                saved_vals = stored.get('values', {})
                self.assertIn('2227', saved_vals,
                              f'Link-context override 2227 missing from localStorage: {saved_vals!r}')
                self.assertIn('1001', saved_vals,
                              f'Newly-set override 1001 missing from localStorage: {saved_vals!r}')

                # 2. LINK_KEY must be gone from sessionStorage
                link_key = page.evaluate(
                    "() => { try { return sessionStorage.getItem('ddf-v2-link-state'); } catch(_){return 'err';} }"
                )
                self.assertIsNone(link_key,
                                  f'sessionStorage LINK_KEY not cleared after save(); got {link_key!r}')

                # 3. Hash must not contain valuecontext or ov=
                current_hash = page.evaluate("() => location.hash")
                self.assertNotIn('valuecontext', current_hash,
                                 f'valuecontext still in hash after save(): {current_hash!r}')
                self.assertNotIn('ov=', current_hash,
                                 f'ov= still in hash after save(): {current_hash!r}')

                # 4. Navigate the same page to a clean URL (no link params) and verify
                #    both overrides load from localStorage only (no session context).
                #    Note: browser.new_page() creates a NEW isolated context (separate
                #    localStorage), so we reuse the existing page which shares storage.
                page.goto(f'{base_url}/values.html#overrides',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'Clean reload never became live: {exc}')

                # Must NOT be in session mode on a clean reload
                in_session_after = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.session() : null; }"
                )
                self.assertFalse(in_session_after,
                                 'Engine still in session mode after clean reload (should be localStorage)')

                ov_2227 = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.get('2227') : null; }"
                )
                ov_1001 = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.get('1001') : null; }"
                )
                self.assertIsNotNone(ov_2227,
                                     'Override 2227 missing from clean reload after link-then-edit')
                self.assertIsNotNone(ov_1001,
                                     'Override 1001 missing from clean reload after link-then-edit')
            finally:
                browser.close()

    def test_removed_on_live_side_stays_removed(self):
        """An override saved to localStorage, then removed by clearing OV_KEY,
        does not return after a page reload even if sessionStorage has content."""
        sync_playwright, PlaywrightError = _pw()
        import json
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw, PlaywrightError)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                # Seed an override in localStorage on the FIRST load only.
                # add_init_script runs before every load (including reload), so guard with
                # a sessionStorage flag to avoid re-seeding after the user clears OV_KEY.
                override_data = json.dumps({
                    'v': 2,
                    'basis': None,
                    'values': {'2227': 65.0},
                    'names': {'2227': 'Test Player'},
                })
                _seed = json.dumps(override_data)
                page.add_init_script(
                    f'(function(){{'
                    f'try{{'
                    f'if(!sessionStorage.getItem("__sw_init__")){{'
                    f'localStorage.clear();sessionStorage.clear();'
                    f'sessionStorage.setItem("__sw_init__","1");'
                    f'localStorage.setItem("ddf-v2-value-overrides",{_seed});'
                    f'}}'
                    f'}}catch(_){{}}}})()'
                )
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                page.goto(f'{base_url}/values.html#overrides',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                # Confirm the override is there before we remove it
                ov_before = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.get('2227') : null; }"
                )
                self.assertEqual(ov_before, 65.0,
                                 f'Seeded override not present before removal: {ov_before!r}')

                # Simulate the live side clearing the override: remove OV_KEY from localStorage,
                # but deliberately leave sessionStorage untouched
                page.evaluate(
                    "() => { try { localStorage.removeItem('ddf-v2-value-overrides'); } catch(_){} }"
                )

                # Reload the page (no init_script on reload - sessionStorage survives)
                page.reload(wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live after reload: {exc}')

                # Override must NOT return after the localStorage clear
                ov_after = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.get('2227') : null; }"
                )
                self.assertIsNone(ov_after,
                                  f'Override for 2227 returned after localStorage clear: {ov_after!r}')
            finally:
                browser.close()

    def test_session_only_link_no_localStorage(self):
        """Navigating to values.html with a link context but without editing:
        engine is in session mode, nothing is written to localStorage OV_KEY."""
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
                page.goto(
                    f'{base_url}/values.html#overrides?valuecontext=1&ov=2227:58.0',
                    wait_until='networkidle', timeout=60000,
                )
                try:
                    page.wait_for_function(OVERRIDES_READY, timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'values.html never became live: {exc}')

                # Must be in session mode
                in_session = page.evaluate(
                    "() => { const e=window.DDF&&window.DDF.engine; "
                    "return e ? e.overrides.session() : null; }"
                )
                self.assertTrue(in_session,
                                'Engine not in session mode after link-context-only navigation')

                # OV_KEY must NOT be in localStorage (no edit was made)
                stored_raw = page.evaluate(
                    "() => { try { return localStorage.getItem('ddf-v2-value-overrides'); } catch(_){return null;} }"
                )
                self.assertIsNone(stored_raw,
                                  f'OV_KEY was written to localStorage without any edit: {stored_raw!r}')
            finally:
                browser.close()

    def test_redesign_token_on_v2_route(self):
        """dist/index.html#s=abc redirects to connect.html keeping #s=abc.
        JEG-1539: legacy-routes.js routes #s=<token> to connect.html#s=<token> (JEG-1538 entry page)."""
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
                page.goto(f'{base_url}/index.html#s=abc',
                          wait_until='networkidle', timeout=60000)
                try:
                    page.wait_for_function("() => document.body.classList.contains('connect')", timeout=20000)
                except PlaywrightError as exc:
                    self.fail(f'connect.html never loaded after #s= redirect: {exc}')

                final_url = page.url
                self.assertIn('connect.html', final_url,
                              f'Did not land on connect.html; got {final_url!r}')
                self.assertIn('#s=abc', final_url,
                              f'Hash #s=abc not preserved; got {final_url!r}')
            finally:
                browser.close()

    def test_empty_hash_stays_on_v2_landing(self):
        """dist/index.html with empty hash stays on the redesigned front door."""
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
                # Should still be index.html (redesigned front door)
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
