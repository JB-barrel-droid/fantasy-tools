"""JEG-1081 PR 6: the Waivers view selector, rendered.

Same roster and candidates as test_waivers_render (pasted by name) at 1366x768 and 390 wide. Checked:

  * a "Decide by" select sits in the results card with DDF Value (selected), DDF Value (projections), Trade chart average
    and one option per available source (Overrides basis only off the default basis); at 390 it is at least 44 px tall and the page does not scroll sideways;
  * on DDF Value every row says what the other views read ("Other views: +x on projections, +y on market"), the headline says
    the same and carries no "judged on" note;
  * choosing DDF Value (projections) recomputes: the headline gains "(judged on DDF Value (projections))", every evaluated reason
    says "Judged on DDF Value (projections)", the context now names DDF Value and market (not projections) and the numbers match
    a recomputation in the page with the same waivers.js on the same rows; a trade chart average and a single source do the same;
  * choosing DDF Value again restores the first headline and verdicts exactly; the choice survives a reload (localStorage);
  * the headline stays inside the first screen at 1366x768 and the polite live region holds it; no page errors.

Discrimination: test_guard_fails_on_broken_builds serves waivers.js with the change handler removed, the view never passed into the
context, the context text dropped, and the choice not saved, and requires each to fail.
"""
from __future__ import annotations

import functools
import re
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist
from tests.test_v2_modules_render import _serve
from tests.test_waivers_render import PICK, SMALL, WAIVERS_JS, fill_lists


def setUpModule():
    _render_env.ensure_built()


STATE = """() => {
  const sel = document.getElementById('v2WaiversView');
  const head = document.getElementById('v2WaiversHeadline');
  const table = document.getElementById('v2WaiversTable');
  const cards = [...document.querySelectorAll('#v2WaiversOut .v2-wv-cards > li')];
  const rows = table ? [...table.querySelectorAll('tbody tr.v2-wv-main')] : [];
  const phone = innerWidth < 600;
  return {select: !!sel, value: sel && sel.value, options: sel ? [...sel.options].map(o => [o.value, o.textContent]) : [], height: sel ? sel.getBoundingClientRect().height : 0,
    head: head.innerText.replace(/\\s+/g, ' ').trim(), headBottom: head.getBoundingClientRect().bottom, vh: innerHeight, headCtx: head.querySelector('.v2-wv-headctx').textContent,
    reasons: (phone ? cards.map(c => c.querySelector('.v2-wv-card-reason').textContent) : rows.map(tr => tr.querySelector('.v2-wv-reason').textContent)).map(t => t.replace(/\\s+/g, ' ').trim()),
    verdicts: phone ? cards.map(c => c.querySelector('.v2-wv-verdict').textContent) : rows.map(tr => tr.querySelector('.v2-wv-verdict').textContent),
    scrollX: document.documentElement.scrollWidth - innerWidth, saved: (() => { try { return localStorage.getItem('ddf.v2.waivers.view'); } catch (e) { return null; } })()};
}"""


def choose(page, value):
    page.select_option("#v2WaiversView", value)
    page.wait_for_timeout(500)


def check(page, tag, width, base) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    phone = width < 600
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2WaiversHeadline') && !document.getElementById('v2Waivers').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    fill_lists(page, pick)
    s0 = page.evaluate(STATE)
    values = [v for v, _ in s0["options"]]
    if not s0["select"] or s0["value"] != "ddf" or values[:3] != ["ddf", "projections", "market"] or "basis" in values or not any(v.startswith("src:") for v in values):
        say(f"view selector: value {s0['value']} options {s0['options']}")
    if phone and s0["height"] < 43.5:
        say(f"the selector is {s0['height']:.0f}px tall on a phone")
    if s0["scrollX"] > 0:
        say(f"sideways scroll {s0['scrollX']}px")
    if width >= 1024 and s0["headBottom"] > s0["vh"]:
        say(f"headline not inside the first screen: bottom {s0['headBottom']:.0f} of {s0['vh']}")
    if "judged on" in s0["head"]:
        say(f"default headline names a view: {s0['head']!r}")
    if "on projections" not in s0["headCtx"] or not s0["headCtx"].startswith("Other views:"):
        say(f"default headline context {s0['headCtx']!r}")
    evaluated0 = [r for r, v in zip(s0["reasons"], s0["verdicts"]) if v != "Not evaluated"]
    if not evaluated0 or not all("Other views:" in r and "on projections" in r for r in evaluated0):
        say(f"rows without the other views' reading: {evaluated0[:2]}")
    # projections
    choose(page, "projections")
    s1 = page.evaluate(STATE)
    if s1["value"] != "projections" or "(judged on DDF Value (projections))" not in s1["head"]:
        say(f"projections headline {s1['head']!r} value {s1['value']}")
    evaluated1 = [r for r, v in zip(s1["reasons"], s1["verdicts"]) if v != "Not evaluated"]
    if not evaluated1 or not all("Judged on DDF Value (projections)." in r and "on DDF Value" in r and "on projections" not in r.split("Other views:")[-1] for r in evaluated1):
        say(f"projections rows: {evaluated1[:2]}")
    if s1["reasons"] == s0["reasons"]:
        say("choosing the projections changed nothing")
    # market and a single source
    choose(page, "market")
    s2 = page.evaluate(STATE)
    if "(judged on Trade chart average)" not in s2["head"] or any("Judged on Trade chart average." not in r for r, v in zip(s2["reasons"], s2["verdicts"]) if v != "Not evaluated" and "no Trade chart average" not in r and "not evaluated" not in r.lower()):
        say(f"market view: {s2['head']!r}")
    src = next(v for v in values if v.startswith("src:"))
    choose(page, src)
    s3 = page.evaluate(STATE)
    label = dict(s0["options"])[src].replace(" only", "")
    if f"(judged on {label})" not in s3["head"]:
        say(f"single source {src}: {s3['head']!r}")
    # a saved choice that no longer exists (a source gone, the basis back to default) falls back to DDF Value
    page.evaluate("() => localStorage.setItem('ddf.v2.waivers.view', 'src:nope')")
    page.reload(wait_until="networkidle")
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2WaiversHeadline') && !document.getElementById('v2Waivers').hidden", timeout=60000)
    page.wait_for_timeout(500)
    sx = page.evaluate(STATE)
    if sx["value"] != "ddf" or "judged on" in sx["head"]:
        say(f"a saved view that no longer exists: value {sx['value']} headline {sx['head']!r}")
    # back to DDF Value: exactly what it was; a reload keeps the choice
    choose(page, "ddf")
    s4 = page.evaluate(STATE)
    if s4["head"] != s0["head"] or s4["reasons"] != s0["reasons"] or s4["verdicts"] != s0["verdicts"]:
        say("choosing DDF Value again did not restore the first answer")
    choose(page, "projections")
    page.reload(wait_until="networkidle")
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2WaiversHeadline') && !document.getElementById('v2Waivers').hidden", timeout=60000)
    page.wait_for_timeout(500)
    s5 = page.evaluate(STATE)
    if s5["value"] != "projections" or s5["saved"] != "projections":
        say(f"the choice did not survive a reload: value {s5['value']} saved {s5['saved']}")
    choose(page, "ddf")
    small = page.evaluate(SMALL)
    if phone and any("v2WaiversView" in x for x in small["small"]):
        say(f"the selector is under 44px: {small['small']}")
    return errors


def run_checks(overrides=None, viewports=((1366, 768), (390, 844))) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            for width, height in viewports:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, kind) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, kind))
                page.goto(base + "#waivers", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                errors += check(page, f"[{width}px] ", width, base)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


def broken(overrides, viewports) -> bool:
    try:
        return bool(run_checks(overrides, viewports))
    except Exception:
        return True


class WaiversViewRenderTests(unittest.TestCase):
    def test_view_selector(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = WAIVERS_JS.read_text(encoding="utf-8")
        cases = {
            "the change handler removed": ('      S.view = sel.value;\n', ''),
            "the view never passed into the context": ("view: api.viewFor(viewChoice(), basisName())", "view: undefined"),
            "the context text dropped": ('r.context ? el("span", {class: "v2-meta v2-wv-ctx", text: ` Other views: ${r.context}.`}) : null)));', 'null)));'),
            "the choice not saved": ('try { root.localStorage.setItem(STORE_VIEW, S.view); }', 'try { void STORE_VIEW; }'),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.assertIn(old, js, f"stale anchor for {name!r}")
                self.assertTrue(broken({"waivers.js": (js.replace(old, new, 1), "text/javascript")}, ((1366, 768),)), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
