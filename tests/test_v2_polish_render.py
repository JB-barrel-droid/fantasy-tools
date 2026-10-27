"""Live-sweep polish (JEG-909 to JEG-913), rendered against the built dist/v2.

  * JEG-909: a 200-character search echoed in the Player values empty state wraps; no horizontal
    page scroll at 1280 or 375.
  * JEG-910: the Trade targets "Show all N …" control reveals all N (it reads "Show more (5 of N)"
    when a page of 25 would not); once everything is shown the control is hidden, never a dead
    "(N of N)" button.
  * JEG-911: a search that matches no name on Trade targets and Risers says "No player matches
    “<q>”" with a Clear search action, never the lists' own "no player…" copy.
  * JEG-912: the Value pie formatters never print a signed zero ("-0.00", "-0.0", "-0.0%").
  * JEG-913: an unknown hash (#nonsense-route) lands on the default route with the address
    rewritten in place (Back still works); known routes (#find-trade included, JEG-852) and
    their query strings are untouched.

Discrimination: test_guard_fails_on_broken_builds reverts each fix and requires its check to fail.
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
from tests._holds import pin_holds_in_dist  # noqa: E402

V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
PIE_JS = ROOT / "app" / "v2" / "audit-pie.js"
LONG_QUERY = "x" * 200
NO_MATCH = "zzzz no such player"
TARGET_SIDES = ("sell", "buy")
PIE_HARNESS = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>pie fmt</title></head>
<body><script src="/app/v2/audit-pie.js"></script></body></html>"""


def setUpModule():
    _render_env.ensure_built()


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


@contextlib.contextmanager
def _pie_harness():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(PIE_HARNESS.encode())
                return
            super().do_GET()
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT))) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


OVERFLOW = """() => ({empty: !document.getElementById('v2Empty').hidden,
  text: document.getElementById('v2EmptyText').textContent,
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  textRight: document.getElementById('v2EmptyText').getBoundingClientRect().right - window.innerWidth})"""

TARGET_FOOT = """(side) => { const ids = side === 'sell' ? {table: 'v2TTable', cards: 'v2TCards', more: 'v2TSellMore', less: 'v2TSellLess'}
    : {table: 'v2TBuyTable', cards: 'v2TBuyCards', more: 'v2TBuyMore', less: 'v2TBuyLess'};
  const table = document.getElementById(ids.table);
  const tableOn = getComputedStyle(table.closest('.v2-table-wrap')).display !== 'none';
  const shown = tableOn ? document.querySelectorAll(`#${ids.table} tbody tr[data-player-key]`).length
    : document.querySelectorAll(`#${ids.cards} li`).length;
  const more = document.getElementById(ids.more), less = document.getElementById(ids.less);
  return {count: window.TradeValueV2.targets()[side].length, shown,
    more: more.hidden || getComputedStyle(more).display === 'none' ? null : more.textContent.trim(),
    less: !(less.hidden || getComputedStyle(less).display === 'none')}; }"""

EMPTIES = """(ids) => Object.fromEntries(ids.map(id => { const n = document.getElementById(id);
  return [id, {shown: !n.hidden, text: n.textContent.trim(), clear: Boolean(n.querySelector('button'))}]; }))"""

ROUTE = """() => ({hash: location.hash,
  tab: [...document.querySelectorAll('.v2-tab')].filter(t => t.getAttribute('aria-current') === 'page').map(t => t.dataset.view)})"""


def _check_909(page, width) -> list[str]:
    errors = []
    page.goto(page.url.split("#")[0] + "#player-values", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
    page.fill("#v2Search", LONG_QUERY)
    page.wait_for_timeout(400)
    snap = page.evaluate(OVERFLOW)
    if not snap["empty"] or LONG_QUERY not in snap["text"]:
        errors.append(f"[909 {width}px] the long search did not reach the empty state: {snap['text'][:60]!r}")
    if snap["overflow"] > 0 or snap["textRight"] > 0:
        errors.append(f"[909 {width}px] the echoed query widens the page: overflow {snap['overflow']}px, text past the viewport by {snap['textRight']:.0f}px")
    page.fill("#v2Search", "")
    page.wait_for_timeout(300)
    return errors


def _open_targets(page):
    page.evaluate("() => { location.hash = '#trade-targets'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets() && window.TradeValueV2.targets().used", timeout=40000)
    page.wait_for_timeout(200)


def _check_910(page, width) -> list[str]:
    """Each side: the control's label matches what a click reveals, and it is hidden once all rows show."""
    errors = []
    _open_targets(page)
    small = None   # (position, side) with 6..25 targets: "Show all N" must reveal N and then hide
    large = None   # (position, side) with more than 25: the label counts, never "Show all"
    for position in ("ALL", "QB", "RB", "WR", "TE", "FLEX"):
        page.select_option("#v2TPosition", position)
        page.wait_for_timeout(250)
        for side in TARGET_SIDES:
            count = page.evaluate(TARGET_FOOT, side)["count"]
            if small is None and 5 < count <= 25:
                small = (position, side)
            if large is None and count > 25:
                large = (position, side)
    if small is None:
        errors.append("[910] no list of 6 to 25 targets in the fixture: the show-all-then-hide rule is untested")
    for case, (position, side) in (("small", small), ("large", large)):
        if position is None:
            continue
        page.select_option("#v2TPosition", position)
        page.wait_for_timeout(250)
        before = page.evaluate(TARGET_FOOT, side)
        n = before["count"]
        want = f"Show all {n} {side} targets ▾" if n <= 25 else f"Show more (5 of {n}) ▾"
        if before["more"] != want or before["shown"] != 5:
            errors.append(f"[910 {width}px {case}] {side} ({position}, {n}) opens with {before['more']!r} over {before['shown']} rows, want {want!r} over 5")
        page.click(f"#v2T{side.capitalize()}More")
        page.wait_for_timeout(250)
        after = page.evaluate(TARGET_FOOT, side)
        if after["shown"] != min(25, n):
            errors.append(f"[910 {width}px {case}] {side}: the control revealed {after['shown']} of {n}, want {min(25, n)}")
        if n <= 25 and after["more"] is not None:
            errors.append(f"[910 {width}px {case}] {side}: all {n} shown but the control still reads {after['more']!r}")
        if n > 25 and after["more"] != f"Show more (25 of {n}) ▾":
            errors.append(f"[910 {width}px {case}] {side}: after the first page the control reads {after['more']!r}")
        if not after["less"]:
            errors.append(f"[910 {width}px {case}] {side}: no Show top 5 after opening")
        page.click(f"#v2T{side.capitalize()}Less")
        page.wait_for_timeout(250)
    page.select_option("#v2TPosition", "ALL")
    page.wait_for_timeout(250)
    return errors


def _no_match_errors(tag, empties, query) -> list[str]:
    errors = []
    for id_, e in empties.items():
        if not e["shown"]:
            errors.append(f"{tag} {id_} is hidden for a search with no match")
            continue
        if not e["text"].startswith(f"No player matches “{query}”") or not e["clear"]:
            errors.append(f"{tag} {id_} reads {e['text'][:90]!r} (want 'No player matches “{query}”' with Clear search)")
    return errors


def _check_911(page, width) -> list[str]:
    errors = []
    _open_targets(page)
    page.fill("#v2TSearch", NO_MATCH)
    page.wait_for_timeout(400)
    ids = ["v2TSellEmpty", "v2TBuyEmpty"]
    errors += _no_match_errors(f"[911 targets {width}px]", page.evaluate(EMPTIES, ids), NO_MATCH)
    if not errors:
        page.click("#v2TSellEmpty button")
        page.wait_for_timeout(400)
        after = page.evaluate("() => ({value: document.getElementById('v2TSearch').value, sell: window.TradeValueV2.targets().sell.length,"
                              " empty: !document.getElementById('v2TSellEmpty').hidden})")
        if after["value"] != "" or not after["sell"] or after["empty"]:
            errors.append(f"[911 targets {width}px] Clear search did not bring the lists back: {after}")
    page.fill("#v2TSearch", "")
    page.wait_for_timeout(300)
    # Risers: the two mover lists and the two disagreement lists.
    page.evaluate("() => { location.hash = '#risers-fallers'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.risers() && window.TradeValueV2.risers().available", timeout=40000)
    page.wait_for_function("() => !/Recomputing|Reading/.test(document.getElementById('v2RMeta').textContent)", timeout=30000)
    page.fill("#v2RSearch", NO_MATCH)
    page.wait_for_timeout(400)
    ids = ["v2RRiseEmpty", "v2RFallEmpty", "v2RMktEmpty", "v2RProjEmpty"]
    errors += _no_match_errors(f"[911 risers {width}px]", page.evaluate(EMPTIES, ids), NO_MATCH)
    if not any(e.startswith("[911 risers") for e in errors):
        page.click("#v2RRiseEmpty button")
        page.wait_for_timeout(400)
        after = page.evaluate("() => ({value: document.getElementById('v2RSearch').value,"
                              " rows: document.querySelectorAll('#v2RRise li, #v2RFall li').length, empty: !document.getElementById('v2RRiseEmpty').hidden})")
        if after["value"] != "" or not after["rows"] or after["empty"]:
            errors.append(f"[911 risers {width}px] Clear search did not bring the lists back: {after}")
    page.fill("#v2RSearch", "")
    page.wait_for_timeout(300)
    return errors


def _check_913(page, base) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#player-values'; }")
    page.wait_for_timeout(200)
    page.evaluate("() => { location.hash = '#nonsense-route?x=1'; }")
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if snap["hash"] != "#player-values" or snap["tab"] != ["values"]:   # JEG-1106: the landing page is the value chart
        errors.append(f"[913] #nonsense-route?x=1 left the address at {snap['hash']!r} / tab {snap['tab']}, want #player-values")
    page.go_back()
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if snap["hash"] != "#player-values":
        errors.append(f"[913] Back after an unknown route landed at {snap['hash']!r}, want #player-values")
    # A known route keeps its deep-link query, and a legacy route still canonicalizes (JEG-855 untouched).
    page.evaluate("() => { location.hash = '#compare-trade?give=1,2&get=3'; }")
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    # (Compare appends the league settings to its own link; the give/get query must survive untouched.)
    if not snap["hash"].startswith("#compare-trade?give=1,2&get=3") or snap["tab"] != ["compare"]:
        errors.append(f"[913] the compare deep link was rewritten: {snap}")
    page.evaluate("() => { location.hash = '#how-values'; }")
    page.wait_for_timeout(300)
    if page.evaluate(ROUTE)["hash"] != "#writing/how-values":
        errors.append("[913] the legacy #how-values redirect broke")
    # #find-trade is a known route (JEG-852, #809): its own tab, the address and a deep-link query kept.
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if snap["hash"] != "#find-trade" or snap["tab"] != ["find"]:
        errors.append(f"[913] #find-trade did not land on the Find a trade tab with its address kept: {snap}")
    page.evaluate("() => { location.hash = '#find-trade?x=1'; }")
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if not snap["hash"].startswith("#find-trade?x=1") or snap["tab"] != ["find"]:
        errors.append(f"[913] the #find-trade deep link was rewritten: {snap}")
    # JEG-1094: the league-wide screen is its own route and tab; an old league share link moves to it.
    page.evaluate("() => { location.hash = '#find-league'; }")
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if snap["hash"] != "#find-league" or snap["tab"] != ["league"]:
        errors.append(f"[1094] #find-league did not land on its own tab: {snap}")
    page.evaluate("() => { location.hash = '#find-trade?workspace=zzz'; }")
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if not snap["hash"].startswith("#find-league") or snap["tab"] != ["league"]:
        errors.append(f"[1094] an old #find-trade?workspace= league link did not move to the league-wide screen: {snap}")
    # Landing on an unknown hash.
    page.goto(base + "#nonsense-route", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2", timeout=40000)
    page.wait_for_timeout(300)
    snap = page.evaluate(ROUTE)
    if snap["hash"] != "#player-values" or snap["tab"] != ["values"]:
        errors.append(f"[913 landing] #nonsense-route left the address at {snap['hash']!r} / tab {snap['tab']}")
    return errors


def check_pie_formatters(pie_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with _pie_harness() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page()
            if pie_js is not None:
                page.route("**/audit-pie.js*", functools.partial(_serve, pie_js, "text/javascript"))
            page.goto(base, wait_until="networkidle")
            page.wait_for_function("() => window.AuditPie && window.AuditPie._fmt", timeout=20000)
            got = page.evaluate("""() => { const P = window.AuditPie; return {
              delta2: P._fmt(-0.001, 2), delta1: P._fmt(-0.04), zero2: P._fmt(0, 2), neg2: P._fmt(-0.006, 2), pos2: P._fmt(0.004, 2),
              pct: P._fmtPct(-0.00001), pctNeg: P._fmtPct(-0.012), pctPos: P._fmtPct(0.012), real: P._fmt(-1.234, 2)}; }""")
        finally:
            browser.close()
    want = {"delta2": "0.00", "delta1": "0.0", "zero2": "0.00", "neg2": "\u22120.01", "pos2": "0.00",
            "pct": "0.0%", "pctNeg": "\u22121.2%", "pctPos": "+1.2%", "real": "\u22121.23"}
    return [f"[912] {key}: got {got[key]!r}, want {value!r}" for key, value in want.items() if got.get(key) != value]


def run_checks(v2_js=None, v2_css=None, only=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    only = set(only or ("909", "910", "911", "913"))
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            widths = (1280, 375) if "909" in only else (1280,)
            for width in widths:
                page = browser.new_page(viewport={"width": width, "height": 800})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
                if v2_css is not None:
                    page.route("**/v2/v2.css*", functools.partial(_serve, v2_css, "text/css"))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
                if "909" in only:
                    errors += _check_909(page, width)
                if width == 1280:
                    if "910" in only:
                        errors += _check_910(page, width)
                    if "911" in only:
                        errors += _check_911(page, width)
                    if "913" in only:
                        errors += _check_913(page, base)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class PolishRenderTest(unittest.TestCase):
    def test_polish_fixes_hold(self):
        self.assertEqual(run_checks(), [])

    def test_pie_formatters_never_print_negative_zero(self):
        self.assertEqual(check_pie_formatters(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        pie = PIE_JS.read_text(encoding="utf-8")
        broken = {
            "909 echoed query not wrapped": dict(
                v2_css=css.replace("#v2EmptyText, .v2-t-empty { overflow-wrap: anywhere; max-width: 100%; }", "", 1), only=("909",)),
            "910 Show all label lies about a page of 25": dict(v2_js=js.replace(
                "label(list.length <= TARGETS_PAGE ? `Show all ${list.length} ${side} targets` : `Show more (${shown} of ${list.length})`)",
                "label(`Show all ${list.length} ${side} targets`)", 1), only=("910",)),
            "910 dead control after everything is shown": dict(v2_js=js.replace(
                "    more.hidden = list.length <= shown;\n", "    more.hidden = false;\n", 1), only=("910",)),
            "911 targets keep their own empty copy on a no-match search": dict(v2_js=js.replace(
                "searchMiss: Boolean(needle) && !searched.length,", "searchMiss: false,", 1), only=("911",)),
            "911 risers keep their own empty copy on a no-match search": dict(v2_js=js.replace(
                "risersView.searchMiss = Boolean(needle) && !rows.length;", "risersView.searchMiss = false;", 1), only=("911",)),
            "913 unknown hash kept in the address": dict(v2_js=js.replace(
                'const unknown = base !== "" && viewFor(legacy) === null;', "const unknown = false;", 1), only=("913",)),
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = kwargs.get("v2_js") or kwargs.get("v2_css")
                self.assertNotIn(body, (js, css), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(**kwargs), [], f"render checks did not catch: {name}")
        with self.subTest(mutation="912 signed zero printed"):
            broken_pie = pie.replace("return /^-0(\\.0+)?$/.test(text) ? text.slice(1) : text;", "return text;", 1)
            self.assertNotEqual(broken_pie, pie, "mutation anchor for the pie formatter is stale")
            self.assertNotEqual(check_pie_formatters(pie_js=broken_pie), [], "the pie formatter check did not catch a signed zero")


if __name__ == "__main__":
    unittest.main()
