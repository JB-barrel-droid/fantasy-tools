"""v2 shareable trade links and page metadata.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless:

  * build a trade on Compare a trade through the search boxes; the address
    becomes #compare-trade?give=<keys>&get=<keys>&scoring=<s>&roster=<shape>
    (Jeremy, 2026-10-08: links carry the sender's scoring and roster, not teams);
  * a link with another scoring and roster opens with exactly those settings
    in the engine (getState / getRosterShape), the reader's team count kept,
    and says so;
  * opening that address in a fresh page shows the same players on the same
    sides and the same per-source rows (same give / get / net text);
  * a link with an unknown or repeated key does not crash: the unknown player is
    listed, every row it touches shows —, and a repeated key appears once;
  * the built page declares color-scheme "light dark" (v2 has a dark theme;
    v1's "light" left form controls light inside it).

Discrimination: test_guard_fails_on_broken_builds serves v2.js without
reading the hash and without writing it, and requires the checks to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"

READ = """() => ({hash: location.hash,
  give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey),
  get: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(li => li.dataset.playerKey),
  rows: [...document.querySelectorAll('#v2CTable tbody tr')].map(tr => tr.dataset.source + ' ' + tr.textContent),
  scheme: document.querySelector('meta[name=color-scheme]')?.content})"""


def _serve(body, route, *_):
    route.fulfill(status=200, content_type="text/javascript", body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def run_checks(v2_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc

        def open_page(url):
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.errors = []
            page.on("pageerror", lambda e: page.errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=30000)
            page.wait_for_timeout(200)
            return page

        try:
            page = open_page(base + "#compare-trade")
            for field, results, query in (("#v2GiveSearch", "#v2GiveResults", "Gibbs"), ("#v2GiveSearch", "#v2GiveResults", "Nacua"),
                                          ("#v2GetSearch", "#v2GetResults", "Chase")):
                page.fill(field, query)
                page.click(f"{results} button >> nth=0")
            first = page.evaluate(READ)
            if first["scheme"] != "light dark":
                errors.append(f"color-scheme meta is {first['scheme']!r}, expected 'light dark'")
            league = page.evaluate("""() => { const C = window.TradeValueCurveControls; const r = C.getRosterShape();
              return `scoring=${C.getState().scoring}&roster=QB${r.QB}.RB${r.RB}.WR${r.WR}.TE${r.TE}.FLEX${r.FLEX}.SF${r.SUPERFLEX || 0}.BN${r.BENCH}`
                + `&bench=${C.getBenchShare().toFixed(3)}`; }""")
            want = f"#compare-trade?give={','.join(first['give'])}&get={','.join(first['get'])}&{league}"
            if first["hash"] != want:
                errors.append(f"address {first['hash']!r} != {want!r}")
            shared = open_page(base + want)
            second = shared.evaluate(READ)
            if (second["give"], second["get"]) != (first["give"], first["get"]):
                errors.append(f"shared link opened {second['give']} / {second['get']}, built {first['give']} / {first['get']}")
            if not first["rows"] or second["rows"] != first["rows"]:
                errors.append("shared link rows differ from the built trade's rows")
            # The sender's scoring and roster travel with the link; the team count stays the reader's.
            teams = page.evaluate("() => window.TradeValueCurveControls.getState().teams")
            other = open_page(base + f"#compare-trade?give={first['give'][0]}&get={first['get'][0]}"
                              "&scoring=half_ppr&roster=QB1.RB2.WR2.TE1.FLEX2.SF1.BN5&bench=0.200"
                              "&shares=QB0.100_RB0.400_WR0.400_TE0.100")
            got = other.evaluate("""() => { const C = window.TradeValueCurveControls; return {scoring: C.getState().scoring,
              teams: C.getState().teams, roster: C.getRosterShape(), bench: C.getBenchShare(), shares: C.getPositionWeights(),
              toast: document.getElementById('v2Status').textContent}; }""")
            if any(abs(got["shares"][p] - v) > 0.002 for p, v in (("QB", 0.1), ("RB", 0.4), ("WR", 0.4), ("TE", 0.1))):
                errors.append(f"link position shares not applied: {got['shares']}")
            # A sender with custom shares writes them into the link.
            other.evaluate("() => { location.hash = '#compare-trade'; }")
            other.wait_for_timeout(300)
            if "&shares=QB0.100_RB0.400_WR0.400_TE0.100" not in other.evaluate("() => location.hash"):
                errors.append(f"custom shares not written to the link: {other.evaluate('() => location.hash')!r}")
            if abs(got["bench"] - 0.2) > 0.006:
                errors.append(f"link bench share not applied: {got['bench']}")
            r = got["roster"]
            if got["scoring"] != "half_ppr" or (r["QB"], r["RB"], r["WR"], r["TE"], r["FLEX"], r.get("SUPERFLEX"), r["BENCH"]) != (1, 2, 2, 1, 2, 1, 5):
                errors.append(f"link league not applied: {got['scoring']} {r}")
            if got["teams"] != teams:
                errors.append(f"team count changed by the link: {got['teams']} (was {teams})")
            if "link's league settings" not in got["toast"]:
                errors.append(f"no notice that the link's settings were applied: {got['toast']!r}")
            other.close()
            odd = open_page(base + f"#compare-trade?give={first['give'][0]},{first['give'][0]},999999999&get={first['get'][0]}")
            third = odd.evaluate(READ)
            if third["give"] != [first["give"][0], "999999999"]:
                errors.append(f"repeated / unknown keys: give side {third['give']}")
            if not third["rows"] or any("—" not in r for r in third["rows"]):
                errors.append("an unknown player must turn every row into —")
            for p in (page, shared, odd):
                if p.errors:
                    errors.append(f"page errors {p.errors}")
                p.close()
        finally:
            browser.close()
    return errors


class ShareRenderTest(unittest.TestCase):
    def test_shared_trade_link(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        broken = {
            "hash not read": js.replace("    readTradeHash();   // may set a status", "    // readTradeHash();", 1),
            "link league ignored": js.replace("    TR.receive = read(\"get\");\n    applyLinkLeague(params);", "    TR.receive = read(\"get\");", 1),
            "link shares ignored": js.replace("    if (sharesGiven) { C.setPositionWeights(shares, false); refresh(); }", "", 1),
            "link bench ignored": js.replace("    if (benchChange) { C.setBenchShareFraction(bench); refresh(); }", "", 1),
            "hash not written": js.replace("    if (location.hash !== want) history.replaceState(null, \"\", want);", "", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
