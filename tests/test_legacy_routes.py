"""JEG-1539: tests for app/next/legacy-routes.js.

legacy-routes.js runs first in <head> of dist/index.html (the redesigned front door) and
dist/v2/index.html (the redirect stub). It maps every old v2 hash route to the redesigned
page that does that job now, forwarding the query intact.

Checks (one browser, many navigations for speed):
  - Every key in DDFLegacyRoutes.ROUTES resolves via resolve()
  - Aliases (#manifesto, #how-values, #research/*, #values-auditing/value-pie)
  - Query forwarding (#player-values?valuecontext=1&basis=..&ov=.. -> values.html?..query..)
  - #find-trade?workspace= -> find.html (re-routed to #find-league by resolve())
  - #find-trade (no workspace) -> find.html
  - #s=<token> -> connect.html#s=<token>
  - Unknown hash: atRoot=true -> null (stay on front door); atRoot=false -> root URL
  - Empty hash stays on front door (null at root)
  - Browser navigation: / and /v2/ prefix routes land on the right pages
  - /v2/ bare redirects to root
  - Query forwarded end-to-end in a real browser navigation
  - MCP site_url shapes from supabase/functions/mcp/state.ts ROUTES (each with a query)

The lead adds DDFAssist state translation in legacy-routes.js separately; that part is
tested in another file - do not test it here.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import serve

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def setUpModule():
    _render_env.ensure_built()


# ---------------------------------------------------------------------------
# Static resolve() tests: load legacy-routes.js once, call resolve() many times
# ---------------------------------------------------------------------------

class LegacyRoutesResolveTest(unittest.TestCase):
    """Call DDFLegacyRoutes.resolve() in the browser and verify the returned URL.

    Uses one browser + one page (class-level). The page loads dist/index.html with
    data-legacy-routes-off so the auto-redirect is disabled while DDFLegacyRoutes
    remains available for direct testing.
    """

    _serve_cm = None
    _pw_cm = None
    base_url: str = ""
    browser = None
    page = None

    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist not built (run make sync)")
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        cls._serve_cm = serve()
        cls.base_url = cls._serve_cm.__enter__()
        cls._pw_cm = sync_playwright()
        pw = cls._pw_cm.__enter__()
        exe = _render_env.chromium_executable(pw)
        if not exe:
            cls._cleanup()
            raise _render_env.unavailable("Chromium not available")
        try:
            cls.browser = pw.chromium.launch(
                args=_render_env.HERMETIC_ARGS,
                executable_path=exe,
            )
        except Exception as exc:
            cls._cleanup()
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        cls.page = cls.browser.new_page(viewport={"width": 1440, "height": 900})
        cls.page.route(
            lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")),
            lambda route: route.abort(),
        )
        # Prevent auto-redirect so DDFLegacyRoutes.resolve() is callable without navigation.
        cls.page.add_init_script(
            "document.documentElement.setAttribute('data-legacy-routes-off', '1');"
        )
        cls.page.goto(f"{cls.base_url}/index.html", wait_until="networkidle", timeout=30000)

    @classmethod
    def _cleanup(cls):
        for attr, fn in [
            ("browser", lambda b: b.close()),
            ("_pw_cm", lambda c: c.__exit__(None, None, None)),
            ("_serve_cm", lambda c: c.__exit__(None, None, None)),
        ]:
            obj = getattr(cls, attr, None)
            if obj is not None:
                try:
                    fn(obj)
                except Exception:
                    pass

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()

    def _resolve(self, hash_val, at_root=True):
        return self.page.evaluate(
            "([h, r]) => window.DDFLegacyRoutes.resolve(h, {atRoot: r})",
            [hash_val, at_root],
        )

    def assertTarget(self, hash_val, expected_suffix, at_root=True, msg=None):
        result = self._resolve(hash_val, at_root)
        self.assertIsNotNone(result, f"resolve({hash_val!r}, atRoot={at_root}) returned null")
        self.assertTrue(
            result.endswith(expected_suffix),
            msg or f"resolve({hash_val!r}) = {result!r}; expected suffix {expected_suffix!r}",
        )

    # --- Every key in ROUTES ---
    def test_player_values(self):
        self.assertTarget("#player-values", "/values.html")

    def test_value_overrides(self):
        self.assertTarget("#value-overrides", "/values.html#overrides")

    def test_risers_fallers(self):
        self.assertTarget("#risers-fallers", "/values.html")

    def test_trade_targets(self):
        self.assertTarget("#trade-targets", "/values.html#buy-sell")

    def test_compare_trade(self):
        self.assertTarget("#compare-trade", "/build.html")

    def test_find_trade(self):
        self.assertTarget("#find-trade", "/find.html")

    def test_find_league(self):
        self.assertTarget("#find-league", "/find.html")

    def test_waivers(self):
        self.assertTarget("#waivers", "/waivers.html")

    def test_simplified_site_stays_on_front_door(self):
        # The retired Simplified site -> the front door itself, without the old hash.
        result = self._resolve("#simplified-site", at_root=True)
        self.assertTrue(result and result.endswith("/") and "#" not in result, f"#simplified-site -> front door, got {result!r}")

    def test_writing_manifesto(self):
        self.assertTarget("#writing/manifesto", "/learn.html#manifesto")

    def test_writing_how_values(self):
        self.assertTarget("#writing/how-values", "/learn.html#numbers/logic")

    def test_writing_wildcard(self):
        self.assertTarget("#writing/anything-else", "/learn.html")

    def test_values_auditing_health_check(self):
        self.assertTarget("#values-auditing/health-check", "/learn.html#numbers/pie")

    def test_values_auditing_single_source(self):
        self.assertTarget("#values-auditing/single-source", "/learn.html#numbers/build-up")

    def test_values_auditing_wildcard(self):
        self.assertTarget("#values-auditing/other", "/learn.html#numbers/pie")

    # --- Aliases ---
    def test_alias_manifesto(self):
        self.assertTarget("#manifesto", "/learn.html#manifesto")

    def test_alias_how_values(self):
        self.assertTarget("#how-values", "/learn.html#numbers/logic")

    def test_alias_research_prefix(self):
        self.assertTarget("#research/some-post", "/learn.html")

    def test_alias_value_pie(self):
        self.assertTarget("#values-auditing/value-pie", "/learn.html#numbers/pie")

    # --- Query forwarding ---
    def test_query_forwarding_player_values(self):
        """#player-values?valuecontext=1&basis=fantasycalc&ov=2227:58.0 -> values.html?..."""
        result = self._resolve("#player-values?valuecontext=1&basis=fantasycalc&ov=2227:58.0")
        self.assertIsNotNone(result)
        self.assertIn("values.html", result)
        self.assertIn("valuecontext=1", result)
        self.assertIn("ov=2227:58.0", result)
        self.assertIn("basis=fantasycalc", result)

    def test_query_forwarding_value_overrides(self):
        """#value-overrides?valuecontext=1&ov=2227:58.0 -> values.html#overrides?..."""
        result = self._resolve("#value-overrides?valuecontext=1&ov=2227:58.0")
        self.assertIsNotNone(result)
        self.assertIn("values.html", result)
        self.assertIn("overrides", result)
        self.assertIn("valuecontext=1", result)
        self.assertIn("ov=2227:58.0", result)

    def test_query_forwarding_compare_trade(self):
        """#compare-trade?give=1001&get=2227 -> build.html?give=..&get=.."""
        result = self._resolve("#compare-trade?give=1001&get=2227")
        self.assertIsNotNone(result)
        self.assertIn("build.html", result)
        self.assertIn("give=1001", result)
        self.assertIn("get=2227", result)

    # --- find-trade?workspace= special case ---
    def test_find_trade_workspace_redirects_to_find(self):
        """#find-trade?workspace=abc -> find.html (re-routed to #find-league)."""
        result = self._resolve("#find-trade?workspace=abc123")
        self.assertIsNotNone(result)
        self.assertIn("find.html", result)
        self.assertIn("workspace=abc123", result)

    # --- #s= token -> connect.html ---
    def test_s_token_redirects_to_connect(self):
        """#s=<token> -> connect.html#s=<token> (JEG-1538 entry page)."""
        result = self._resolve("#s=abc123xyz")
        self.assertIsNotNone(result)
        self.assertIn("connect.html", result)
        self.assertIn("#s=abc123xyz", result)

    # --- Unknown hash ---
    def test_unknown_hash_at_root_is_null(self):
        result = self._resolve("#totally-unknown-route", at_root=True)
        self.assertIsNone(result, f"Unknown hash at root should return null, got {result!r}")

    def test_unknown_hash_at_stub_redirects_to_root(self):
        result = self._resolve("#totally-unknown-route", at_root=False)
        self.assertIsNotNone(result, "Unknown hash at /v2/ stub should redirect to root")
        self.assertRegex(result, r"/$", f"Expected root URL, got {result!r}")

    def test_empty_hash_at_root_is_null(self):
        result = self._resolve("", at_root=True)
        self.assertIsNone(result, f"Empty hash at root should return null, got {result!r}")

    def test_bare_home_hash_at_root_is_null(self):
        result = self._resolve("#home", at_root=True)
        self.assertIsNone(result, f"#home at root should return null, got {result!r}")

    # --- MCP site_url shapes from supabase/functions/mcp/state.ts ROUTES ---
    # state.ts: compare->#compare-trade, targets->#trade-targets, finder->#find-trade,
    # league->#find-league?workspace=, risers->#risers-fallers, audit->#values-auditing
    def test_mcp_compare(self):
        self.assertTarget("#compare-trade", "/build.html")

    def test_mcp_targets(self):
        self.assertTarget("#trade-targets", "/values.html#buy-sell")

    def test_mcp_finder_with_query(self):
        result = self._resolve("#find-trade?give=1001&scoring=ppr")
        self.assertIn("find.html", result)
        self.assertIn("give=1001", result)
        self.assertIn("scoring=ppr", result)

    def test_mcp_league_with_workspace_query(self):
        result = self._resolve("#find-league?workspace=abc&wm=0&scoring=half_ppr")
        self.assertIn("find.html", result)
        self.assertIn("workspace=abc", result)
        self.assertIn("wm=0", result)

    def test_mcp_risers(self):
        self.assertTarget("#risers-fallers", "/values.html")

    def test_mcp_audit(self):
        self.assertTarget("#values-auditing", "/learn.html#numbers/pie")

    def test_mcp_audit_with_query(self):
        result = self._resolve("#values-auditing?scoring=ppr&teams=12")
        self.assertIn("learn.html", result)
        self.assertIn("numbers/pie", result)
        self.assertIn("scoring=ppr", result)

    def test_routes_object_is_exposed(self):
        """window.DDFLegacyRoutes.ROUTES is an object with the expected keys."""
        keys = self.page.evaluate("() => Object.keys(window.DDFLegacyRoutes.ROUTES)")
        self.assertIn("#player-values", keys)
        self.assertIn("#compare-trade", keys)
        self.assertIn("#find-trade", keys)
        self.assertIn("#waivers", keys)
        self.assertIn("#writing/manifesto", keys)
        self.assertIn("#values-auditing/health-check", keys)


# ---------------------------------------------------------------------------
# Browser navigation tests: actual page loads and redirects
# ---------------------------------------------------------------------------

class LegacyRoutesBrowserTest(unittest.TestCase):
    """Navigate the browser to hash routes and verify the resulting URL.

    One browser, many navigations (a single test method handles all cases
    to keep the browser open and avoid repeated startup cost).
    """

    def _browser(self, pw):
        exe = _render_env.chromium_executable(pw)
        if not exe:
            raise _render_env.unavailable("Chromium not available")
        try:
            return pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        except Exception as exc:
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc

    def test_browser_route_redirects(self):
        """Key routes redirect correctly from both / and /v2/ prefixes."""
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc

        cases = [
            ("#player-values", "values.html"),
            ("#value-overrides", "values.html"),
            ("#compare-trade", "build.html"),
            ("#find-trade", "find.html"),
            ("#waivers", "waivers.html"),
            ("#writing/manifesto", "learn.html"),
            ("#values-auditing/health-check", "learn.html"),
        ]
        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route(
                lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")),
                lambda route: route.abort(),
            )
            failures = []
            for prefix in ("/", "/v2/"):
                for hash_val, expected_page in cases:
                    page.goto(base_url + prefix + hash_val,
                              wait_until="networkidle", timeout=30000)
                    try:
                        page.wait_for_url(
                            re.compile(re.escape(expected_page) + r"($|[#?])"),
                            timeout=15000,
                        )
                    except PlaywrightError:
                        failures.append(f"{prefix}{hash_val} -> {page.url!r}, expected {expected_page!r}")

            # Bare / (no hash) stays on the redesigned front door.
            page.goto(base_url + "/", wait_until="networkidle", timeout=15000)
            final = page.url
            for unexpected in ("values.html", "learn.html", "build.html", "find.html"):
                if unexpected in final:
                    failures.append(f"bare / redirected to {final!r}, should stay on front door")
                    break

            # /v2/ bare (no hash) redirects to the root.
            page.goto(base_url + "/v2/", wait_until="networkidle", timeout=15000)
            try:
                page.wait_for_url(
                    lambda u: u.split("#")[0].rstrip("/") == base_url.rstrip("/"),
                    timeout=10000,
                )
            except PlaywrightError:
                failures.append(f"/v2/ did not redirect to root; got {page.url!r}")

            browser.close()
        self.assertEqual(failures, [], "\n".join(failures))

    def test_query_forwarded_through_browser_redirect(self):
        """#player-values?valuecontext=1&ov=2227:58.0 forwards the query to values.html."""
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc

        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route(
                lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")),
                lambda route: route.abort(),
            )
            page.goto(
                f"{base_url}/#player-values?valuecontext=1&ov=2227:58.0",
                wait_until="networkidle", timeout=30000,
            )
            try:
                page.wait_for_url(re.compile(r"values\.html"), timeout=15000)
            except PlaywrightError:
                self.fail(f"Did not redirect to values.html; at {page.url!r}")
            final = page.url
            self.assertIn("valuecontext=1", final, f"Query not forwarded: {final!r}")
            self.assertIn("ov=2227:58.0", final, f"ov param not forwarded: {final!r}")
            browser.close()

    def test_s_token_redirects_to_connect_in_browser(self):
        """#s=<token> in browser redirects to connect.html#s=<token>."""
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc

        with serve() as base_url, sync_playwright() as pw:
            browser = self._browser(pw)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.route(
                lambda u: not (u.startswith("http://127.0.0.1") or u.startswith("http://localhost")),
                lambda route: route.abort(),
            )
            page.goto(f"{base_url}/index.html#s=testtoken",
                      wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            final = page.url
            self.assertIn("connect.html", final,
                          f"#s=token should go to connect.html; got {final!r}")
            self.assertIn("#s=testtoken", final,
                          f"Token not preserved in URL: {final!r}")
            browser.close()


if __name__ == "__main__":
    unittest.main()
