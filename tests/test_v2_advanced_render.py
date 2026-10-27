"""v2 bench-share readout and Advanced league settings, rendered (JEG-537, contract GL-12, GL-23, GL-24).

Replaces tests/test_v2_bench_used_render.py (the bench slider, its feasible range and the "used share" note are
retired: since JEG-536 the bench share is computed from the reader's settings). Loads the built page headless:

  * "Position weights" (renamed from "Weights & bench") shows the bench share as a readout read from the engine's
    getBenchShareReadout(): "Bench share this week: QB x%, RB y%, WR z%, TE w%, from your league settings", with
    the explanation and no slider; with the override on: "Bench share: x% (your override)" and a reset link that
    turns the override off; How values work carries the same numbers;
  * Your league has a collapsed "Advanced" section at the bottom: Injury history (Recent seasons / All seasons
    equally), Projection confidence (Less / As measured / More = 1.5 / 1 / 0.5) and the bench-share override, off
    by default, with the 1-30% slider only when on; applied as it changes, no Apply (JEG-1020; Undo changes returns
    to the settings the panel opened with); Reset defaults returns them;
  * share links write inj, conf and bso only when they differ from the defaults and never write bench=; opening
    such a link sets the engine; an old link's bench=0.150 means no override and any other bench= without bso= is
    the sender's override; bso is held to 1-30%;
  * at 390 px the Advanced section opens without sideways scroll; no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with the live change ignoring the Advanced section, the link
not writing bso, the link ignoring bso, the override on by default and the readout dropping a position.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
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
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

ENGINE = """() => { const C = window.TradeValueCurveControls; return {lineup: C.getLineupSettings(), readout: C.getBenchShareReadout(),
  overrideSetting: C.getBenchShareOverride()}; }"""

LEAGUE = """() => { const pop = document.getElementById('v2Popover');
  const adv = pop.querySelector('details.v2-padv');
  const last = [...pop.querySelectorAll('.v2-pbody > *, .v2-panel-body > *')].pop();
  const seg = label => [...(pop.querySelector(`[aria-label="${label}"]`)?.querySelectorAll('button') || [])].map(b => ({value: b.dataset.value, text: b.textContent, on: b.getAttribute('aria-pressed') === 'true'}));
  return {adv: Boolean(adv), open: adv ? adv.open : null, summary: adv?.querySelector('summary')?.textContent || '',
    injury: seg('Injury history'), conf: seg('Projection confidence'), box: pop.querySelector('#v2BenchOverride')?.checked ?? null,
    slider: Boolean(pop.querySelector('#v2BenchSlider')), sliderValue: pop.querySelector('#v2BenchSlider')?.value ?? null,
    advIsLast: adv ? [...adv.parentElement.children].pop() === adv : false, overflow: document.documentElement.scrollWidth - innerWidth}; }"""

WEIGHTS = """() => { const pop = document.getElementById('v2Popover');
  return {text: pop.querySelector('[data-bench-readout]')?.textContent || '', slider: Boolean(pop.querySelector('#v2BenchSlider')),
    reset: (() => { const b = pop.querySelector('[data-bench-override-reset]'); return b ? !b.hidden : false; })(),
    info: pop.textContent.includes('how often bench players actually reach a lineup'), title: pop.querySelector('h2')?.textContent || ''}; }"""


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)

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


def want_readout(r) -> str:
    if r["override"]:
        return f"Bench share: {r['overrideValue'] * 100:.1f}% (your override)"
    return "Bench share this week: " + ", ".join(f"{p} {r[p] * 100:.1f}%" for p in ("QB", "RB", "WR", "TE")) + ", from your league settings"


def run_checks(js_patch=None) -> list[str]:
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
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        page_errors: list[str] = []

        def open_page(url, width=1440, height=1000):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
            page.wait_for_timeout(300)
            return page

        try:
            page = open_page(base + "#player-values")
            # 1. Position weights: a readout, no slider.
            if page.text_content("#v2Weights").strip() != "Position weights":
                errors.append(f"button reads {page.text_content('#v2Weights')!r}, want 'Position weights'")
            page.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
            page.click("#v2Weights")
            w = page.evaluate(WEIGHTS)
            eng = page.evaluate(ENGINE)
            if w["title"] != "Position weights" or w["slider"] or w["reset"] or not w["info"]:
                errors.append(f"[position weights] {w}")
            if w["text"] != want_readout(eng["readout"]):
                errors.append(f"[position weights] readout {w['text']!r}, engine {want_readout(eng['readout'])!r}")
            page.keyboard.press("Escape")

            # 2. Your league: Advanced is collapsed, last, defaults, no slider while the override is off.
            page.click("#v2EditLeague")
            lg = page.evaluate(LEAGUE)
            if not lg["adv"] or lg["open"] is not False or lg["summary"] != "Advanced" or not lg["advIsLast"]:
                errors.append(f"[league] Advanced should be a collapsed section at the bottom: {lg}")
            if [(o["text"], o["on"]) for o in lg["injury"]] != [("Recent seasons", True), ("All seasons equally", False)]:
                errors.append(f"[league] injury history {lg['injury']}")
            if [(o["text"], o["value"], o["on"]) for o in lg["conf"]] != [("Less", "1.5", False), ("As measured", "1", True), ("More", "0.5", False)]:
                errors.append(f"[league] projection confidence {lg['conf']}")
            if lg["box"] is not False or lg["slider"]:
                errors.append(f"[league] the override should be off with no slider: box {lg['box']}, slider {lg['slider']}")
            # Live (JEG-1020): a change reaches the engine on its own; Undo changes returns to what the panel opened with.
            page.click("#v2Popover details.v2-padv summary")
            page.click('#v2Popover [aria-label="Injury history"] button[data-value="all"]')
            page.click('#v2Popover [aria-label="Projection confidence"] button[data-value="0.5"]')
            page.wait_for_function("() => window.TradeValueCurveControls.getLineupSettings().injuryHistory === 'all'", timeout=3000)
            page.click("#v2Popover [data-league-undo]")
            if page.evaluate(ENGINE)["lineup"]["injuryHistory"] != "recent":
                errors.append("[league] Undo changes did not return the injury history")
            if page.locator("#v2Popover button:has-text('Apply')").count() or page.locator("#v2Popover button:has-text('Cancel')").count():
                errors.append("[league] the panel still has an Apply or Cancel button")
            page.click('#v2Popover [data-done="league"]')
            # All three apply as they change.
            page.click("#v2EditLeague")
            page.click("#v2Popover details.v2-padv summary")
            page.click('#v2Popover [aria-label="Injury history"] button[data-value="all"]')
            page.click('#v2Popover [aria-label="Projection confidence"] button[data-value="0.5"]')
            page.click("#v2BenchOverride")
            lg = page.evaluate(LEAGUE)
            if not lg["slider"] or lg["open"] is not True:
                errors.append(f"[league] turning the override on should show the slider inside the open section: {lg}")
            page.evaluate("() => { const s = document.getElementById('v2BenchSlider'); s.value = '0.12'; s.dispatchEvent(new Event('input')); }")
            page.wait_for_function("() => window.TradeValueCurveControls.getLineupSettings().benchShareOverride === 0.12", timeout=3000)
            got = page.evaluate(ENGINE)
            if got["lineup"]["injuryHistory"] != "all" or got["lineup"]["projectionConfidence"] != 0.5 or abs((got["lineup"]["benchShareOverride"] or 0) - 0.12) > 1e-9:
                errors.append(f"[league] the live change gave {got['lineup']}")
            page.click('#v2Popover [data-done="league"]')
            # The panel and How values show the override; the reset link turns it off.
            page.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
            page.click("#v2Weights")
            w = page.evaluate(WEIGHTS)
            if w["text"] != "Bench share: 12.0% (your override)" or not w["reset"]:
                errors.append(f"[position weights] with the override on: {w}")
            page.click("#v2Popover [data-bench-override-reset]")
            page.wait_for_timeout(300)
            if page.evaluate(ENGINE)["lineup"]["benchShareOverride"] is not None:
                errors.append("[position weights] the reset link did not turn the override off")
            page.keyboard.press("Escape")

            # 3. Share links: settings off the defaults are written; nothing else; never bench=.
            page.evaluate("() => { location.hash = '#compare-trade'; }")
            page.fill("#v2GiveSearch", "Gibbs")
            page.click("#v2GiveResults button >> nth=0")
            page.fill("#v2GetSearch", "Chase")
            page.click("#v2GetResults button >> nth=0")
            page.wait_for_timeout(300)
            h = page.evaluate("() => location.hash")
            if "inj=all" not in h or "conf=0.5" not in h or "bso=" in h or "bench=" in h:
                errors.append(f"[link] written link {h!r}: want inj=all and conf=0.5, no bso (override off), no bench=")
            page.evaluate("() => window.TradeValueCurveControls.setLineupSettings({benchShareOverride: 0.12})")
            page.evaluate("() => { location.hash = '#player-values'; }")
            page.evaluate("() => { location.hash = '#compare-trade'; }")
            page.wait_for_timeout(300)
            h = page.evaluate("() => location.hash")
            if "bso=0.120" not in h or "bench=" in h:
                errors.append(f"[link] with the override on the link should carry bso=0.120: {h!r}")
            page.evaluate("() => window.TradeValueCurveControls.setLineupSettings({injuryHistory: 'recent', projectionConfidence: 1, benchShareOverride: null})")
            page.evaluate("() => { location.hash = '#player-values'; }")
            page.evaluate("() => { location.hash = '#compare-trade'; }")
            page.wait_for_timeout(300)
            h = page.evaluate("() => location.hash")
            if any(k in h for k in ("inj=", "conf=", "bso=", "bench=")):
                errors.append(f"[link] a default league should write none of inj, conf, bso, bench: {h!r}")
            keys = page.evaluate("() => [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey)")
            gets = page.evaluate("() => [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(li => li.dataset.playerKey)")
            page.close()
            base_link = f"#compare-trade?give={keys[0]}&get={gets[0]}&scoring=ppr&roster=QB1.RB2.WR3.TE1.FLEX1.SF0.BN6"
            for suffix, want, label in (
                ("&inj=all&conf=1.5&bso=0.120", ("all", 1.5, 0.12), "all three"),
                ("&bench=0.150", ("recent", 1, None), "old default bench"),
                ("&bench=0.200", ("recent", 1, 0.2), "old non-default bench"),
                ("&bso=0.9", ("recent", 1, 0.30), "bso held to 30%"),
                ("&bso=0.001&inj=sideways&conf=7", ("recent", 1, 0.01), "bso held to 1%, bad values ignored"),
            ):
                p2 = open_page(base + base_link + suffix)
                got = p2.evaluate(ENGINE)["lineup"]
                have = (got["injuryHistory"], got["projectionConfidence"], got["benchShareOverride"])
                if have[0] != want[0] or have[1] != want[1] or (have[2] is None) != (want[2] is None) or (want[2] is not None and abs(have[2] - want[2]) > 1e-9):
                    errors.append(f"[link {label}] opened as {have}, want {want}")
                p2.close()

            # 4. 390 px: the Advanced section opens without sideways scroll.
            phone = open_page(base + "#player-values", 390, 844)
            phone.click("#v2EditLeague")
            phone.click("#v2Popover details.v2-padv summary")
            phone.click("#v2BenchOverride")
            lg = phone.evaluate(LEAGUE)
            if lg["overflow"] > 0:
                errors.append(f"[390px] sideways scroll by {lg['overflow']}px with Advanced open")
            phone.close()
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


PATCHES = {
    "live change ignores Advanced": ("            if (!error && draft.adv) error = applyAdvanced(draft.adv);", ""),
    "link does not write bso": ("        if (adv.benchShareOverride !== null) parts.push(`bso=${Number(adv.benchShareOverride).toFixed(3)}`);", ""),
    "link ignores bso": ("      if (JSON.stringify(want) !== JSON.stringify(now)) advChange = want;", "      advChange = null;"),
    "override on by default": ("        box.checked = adv.benchShareOverride !== null;", "        box.checked = true;"),
    "readout drops a position": ('const parts = ["QB", "RB", "WR", "TE"].map(pos => `${pos} ${Number.isFinite(readout[pos]) ? pctText(readout[pos]) : "—"}`);',
                                 'const parts = ["QB", "RB", "WR"].map(pos => `${pos} ${Number.isFinite(readout[pos]) ? pctText(readout[pos]) : "—"}`);'),
}


class AdvancedRenderTest(unittest.TestCase):
    def test_readout_advanced_and_links(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(patch)
                except Exception as exc:   # a broken build that cannot finish the walk-through is caught too
                    if type(exc).__name__ == "SkipTest" or "unavailable" in type(exc).__name__.lower():
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
