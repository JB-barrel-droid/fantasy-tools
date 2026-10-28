"""v2 "Explain our names" (JEG-490, contract GL-26, HV-02), rendered.

DDF Value and Trade chart average are defined once and shown wherever the names appear:

  * the header row reads "On the chart:" (not "Showing:") with an info button; opening it shows the three definitions
    and the edge in plain words (Esc closes it);
  * the same info button sits beside Risers & fallers' Movement picker, on the "Where DDF Value and the projections
    disagree" heading, on the DDF Value group in Customize, and the Compare deal-read nets open a definition that
    starts with the shared one;
  * How values work leads with the three numbers and "Where the edge comes from", with no numbers in that copy, and
    no longer says "Data Driven Adjustments" or "DDA";
  * no page errors; no sideways scroll at 390 px on Player values and How values work.

Discrimination: test_guard_fails_on_broken_builds serves v2.js / shell.html with the old "Showing:" label, a changed
definition, the Customize info button dropped and the How section removed, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import re
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
V2_JS = ROOT / "app" / "v2" / "v2.js"

from tests import _render_env  # noqa: E402
from tests._holds import pin_holds_in_dist  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

DEFS = [
    ("DDF Value", "Our estimate of what a player is worth: the trade charts FantasyCalc, USA Today, FantasyPros and CBS, adjusted to your league and averaged."),
    ("Trade chart average", "What the market will pay: the rescaled trade charts, averaged."),
]
# JEG-1073: the deal read's third net is the projections alternate; it defines itself with its own wording (not one of
# the two shared names the popovers list).
NET_ONLY_DEFS = [
    ("DDF Value (projections)", "The alternate: ESPN, CBS rest of season and Razzball projections, equal weight, averaged for your league."),
]
EDGE = "The edge: buy below DDF Value and sell above it. It is best when DDF Value says you win and the market says you lose."

POPOVER = """() => { const pop = document.getElementById('v2Popover'); return {open: !pop.hidden, title: pop.querySelector('h2')?.textContent || '',
  paragraphs: [...pop.querySelectorAll('.v2-info-text p')].map(p => p.textContent.trim().replace(/\\s+/g, ' '))}; }"""


@contextlib.contextmanager
def _served(shell_patch=None):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)
        # Held-proof fixture (JEG-718): the fidelity pulse holds different sources on different days.
        pin_holds_in_dist(dist)
        if shell_patch:
            old, new = shell_patch
            page = dist / "v2" / "index.html"
            text = page.read_text(encoding="utf-8")
            assert old in text, f"shell patch anchor missing: {old!r}"
            page.write_text(text.replace(old, new, 1), encoding="utf-8")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(Quiet, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def check_popover(pop, tag) -> list[str]:
    errors = []
    if not pop["open"] or pop["title"] != "Our names":
        errors.append(f"{tag}popover {pop['open']} {pop['title']!r}")
    want = [f"{name} {text}" for name, text in DEFS] + [EDGE]
    if pop["paragraphs"] != want:
        errors.append(f"{tag}definitions {pop['paragraphs']}, want {want}")
    return errors


def run_checks(js_patch=None, shell_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if js_patch:
        old, new = js_patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served(shell_patch) as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        page_errors: list[str] = []

        def open_page(hash_, width=1440, height=1000):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.add_init_script(_render_env.pin_data_week_script())   # JEG-1152: the data's week, not the wall clock
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(base + hash_, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
            page.wait_for_timeout(400)
            return page

        try:
            page = open_page("#player-values")
            label = page.text_content(".v2-ctx-basis b").strip()
            if label != "On the chart:":
                errors.append(f"[values] the row reads {label!r}, want 'On the chart:'")
            if "Showing:" in page.inner_text("#v2Main"):
                errors.append("[values] 'Showing:' is still on the page")
            btn = page.query_selector(".v2-ctx-basis button[data-info=names]")
            if not btn:
                errors.append("[values] no info button beside 'On the chart:'")
            else:
                btn.click()
                page.wait_for_timeout(300)
                errors += check_popover(page.evaluate(POPOVER), "[values] ")
                page.keyboard.press("Escape")
                if page.evaluate("() => !document.getElementById('v2Popover').hidden"):
                    errors.append("[values] Esc did not close the definitions")
            # Customize: the DDF Value group.
            page.click("#v2EditSources")
            page.wait_for_timeout(500)
            if not page.query_selector('#v2Popover .v2-cgroup[data-group="ddf"] button[data-info=names]'):
                errors.append("[customize] no info button on the DDF Value group")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            # Risers & fallers.
            page.evaluate("() => { location.hash = '#risers-fallers'; }")
            page.wait_for_timeout(1500)
            for sel, where in (("#v2Risers .v2-filters button[data-info=names]", "Movement"), ("#v2Risers #v2RDisagree h2 + button[data-info=names]", "disagreement heading")):
                b = page.query_selector(sel)
                if not b:
                    errors.append(f"[risers] no info button at {where}")
                    continue
                b.click()
                page.wait_for_timeout(300)
                errors += check_popover(page.evaluate(POPOVER), f"[risers {where}] ")
                page.keyboard.press("Escape")
            # Compare: the deal-read nets define themselves with the shared wording.
            page.evaluate("() => { location.hash = '#compare-trade'; }")
            page.wait_for_timeout(1200)
            # JEG-1190: Compare opens empty; the sample loads on Try a sample trade.
            if page.is_visible("#v2CTryExample"):
                page.click("#v2CTryExample")
                page.wait_for_timeout(400)
            nets = page.evaluate("""() => [...document.querySelectorAll('#v2CDealNets li')].map(li => [li.querySelector('.v2-deal-name').textContent, li.querySelector('.v2-deal-def').textContent])""")
            for name, definition in nets:
                want = next((text for n, text in DEFS + NET_ONLY_DEFS if n == name), None)
                if want is None or not definition.startswith(want):
                    errors.append(f"[compare] {name} defines itself as {definition!r}, want it to start with {want!r}")
            if len(nets) != 3:
                errors.append(f"[compare] {len(nets)} nets in the deal read")
            # How values work.
            page.evaluate("() => { location.hash = '#how-values'; }")
            page.wait_for_timeout(800)
            how = page.evaluate("""() => { const n = document.getElementById('v2HowNames'); return {has: Boolean(n), text: n ? n.innerText : '',
              primaries: n ? [...n.querySelectorAll('[data-primary]')].map(li => li.textContent.trim().replace(/\\s+/g, ' ')) : [],
              all: document.getElementById('v2How').innerText}; }""")
            if not how["has"]:
                errors.append("[how] the three-numbers section is missing")
            else:
                want = [f"{n} " for n, _ in DEFS]
                if [p[:len(w)] for p, w in zip(how["primaries"], want)] != want or len(how["primaries"]) != len(DEFS):
                    errors.append(f"[how] primaries {how['primaries']}")
                if "Where the edge comes from" not in how["text"]:
                    errors.append("[how] no 'Where the edge comes from'")
                if re.search(r"\d", how["text"]):
                    errors.append(f"[how] numbers in the new copy: {how['text']!r}")
            if "Data Driven Adjustments" in how["all"] or re.search(r"\bDDA\b", how["all"]):
                errors.append("[how] 'Data Driven Adjustments' / 'DDA' is still on the page")
            page.close()
            # 390 px.
            for hash_ in ("#player-values", "#how-values"):
                phone = open_page(hash_, 390, 844)
                over = phone.evaluate("() => document.documentElement.scrollWidth - innerWidth")
                if over > 0:
                    errors.append(f"[390px {hash_}] sideways scroll by {over}px")
                phone.close()
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


JS_PATCHES = {
    # The page rewrites NAME_DEFS[0] from the basis on load (syncBasisLabels), so the mutation targets that line.
    "definition changed": ("      : `Our estimate of what a player is worth: ${OURS_DEFAULT}.`;", "      : `A number.`;"),
    "customize info dropped": ('          if (g.id === "ddf") head.appendChild(namesInfoButton("Customize"));', ""),
}
SHELL_PATCHES = {
    "old Showing label": ("<b>On the chart:</b>", "<b>Showing:</b>"),
    "How section removed": ('id="v2HowNames"', 'id="v2HowNamesGone"'),
}


class NamesRenderTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        cases = [(name, {"js_patch": p}) for name, p in JS_PATCHES.items()] + [(name, {"shell_patch": p}) for name, p in SHELL_PATCHES.items()]
        for name, kwargs in cases:
            with self.subTest(patch=name):
                try:
                    errors = run_checks(**kwargs)
                except Exception as exc:
                    if "unavailable" in type(exc).__name__.lower() or type(exc).__name__ == "SkipTest":
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
