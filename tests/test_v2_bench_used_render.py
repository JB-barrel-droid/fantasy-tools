"""v2 bench share, rendered: the share shown is the share the engine priced with.

JEG-541 (after JEG-508): the two-tier calibration and its per-position feasible
windows are retired (VP-10). getBenchShareUsed(share) now returns one share for
every position: the share itself, 0 when no source has bench players above
waivers, 1 when none has starters above waivers, and null before the values are
built. getBenchBounds() is the fixed slider range. v2 must show the used share,
never the request, and "—" with a reason when there is none.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 1440 x 900:

  * Weights & bench: the slider range is getBenchBounds(), named as a range,
    not a league-feasible window;
  * at 2% the readout and the Starters / Bench split show the engine's used
    share with no note; Apply keeps it and getBenchShareUsed() agrees; How
    values work shows the same;
  * hermetic edge: with getBenchShareUsed wrapped to return 0 for every
    position (what the engine returns when no source has bench players above
    waivers), the panel and How values show 0.0% and name the requested share;
  * hermetic null: with getBenchShareUsed returning null, the panel and How
    values show "—" with a reason, never the requested share;
  * at 15% the shares shown are 15% and there is no note;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js showing the
requested share instead of the used one, and with the retired "Feasible ...
for this league" copy, and requires the checks to fail on each.
"""
from __future__ import annotations

import functools
import re
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_panels_render import V2_JS, _built_dist, _serve  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


USED = """share => window.TradeValueCurveControls.getBenchShareUsed(share)"""

# Wrap the engine's accessor: `mode` "zero" returns 0 for every position, "null" returns null,
# anything else restores the engine's own.
FORCE_USED = """mode => { const C = window.TradeValueCurveControls;
  if (!C.__usedOriginal) C.__usedOriginal = C.getBenchShareUsed;
  C.getBenchShareUsed = mode === 'zero' ? (() => ({QB: 0, RB: 0, WR: 0, TE: 0}))
    : mode === 'null' ? (() => null) : C.__usedOriginal; }"""


def _numbers(text: str) -> list[float]:
    return [float(x) / 100 for x in re.findall(r"(\d+(?:\.\d+)?)", text or "")]


def _bench_numbers(text: str) -> list[float]:
    """The numbers after 'Bench' in 'Starters a% / Bench b–c%'."""
    tail = text.split("Bench", 1)[1] if "Bench" in (text or "") else ""
    return _numbers(tail.split("·")[0])


def _check_shown(tag, numbers, used) -> list[str]:
    """numbers shown (one value, or low and high) must equal the engine's used shares."""
    finite = [v for v in (used or {}).values() if v is not None]
    if not finite:
        return [f"{tag}: engine priced no position"]
    lo, hi = min(finite), max(finite)
    want = [lo] if round(lo * 1000) == round(hi * 1000) else [lo, hi]
    if len(numbers) != len(want) or any(abs(a - b) > 0.0006 for a, b in zip(numbers, want)):
        return [f"{tag}: shows {[round(n * 100, 1) for n in numbers]}%, engine used {[round(w * 100, 2) for w in want]}%"]
    return []


def _panel(page) -> dict:
    return page.evaluate("""() => { const pop = document.getElementById('v2Popover');
      const note = pop.querySelector('[data-bench-note]');
      return {readout: pop.querySelector('output.v2-pbig')?.textContent || '',
        split: pop.querySelector('.v2-psplit b')?.textContent || '',
        text: pop.textContent,
        note: note && !note.hidden ? note.textContent : ''}; }""")


def _set_slider(page, share):
    page.evaluate("v => { const s = document.getElementById('v2BenchSlider'); s.value = String(v); s.dispatchEvent(new Event('input')); }", share)


def _how(page) -> dict:
    page.evaluate("() => { location.hash = '#how-values'; }")
    page.wait_for_function("() => !document.getElementById('v2How').hidden")
    how = page.evaluate("""() => ({bench: document.getElementById('v2HowBench').textContent,
      note: [...document.querySelectorAll('#v2How [data-bench-note]')].filter(n => !n.hidden).map(n => n.textContent).join(' ')})""")
    page.evaluate("() => { location.hash = '#player-values'; }")
    page.wait_for_function("() => !document.getElementById('v2Main').hidden")
    return how


def check_bench(page) -> list[str]:
    errors = []
    C = "window.TradeValueCurveControls"
    bounds = page.evaluate(f"() => {C}.getBenchBounds()")
    if not bounds or bounds[0] > 0.02:
        return [f"bench: slider bounds {bounds} do not reach 2%"]

    # The range copy is the engine's fixed range, not a league-feasible window.
    page.click("#v2Weights")
    shown = _panel(page)
    want_range = f"{bounds[0] * 100:.1f}%–{bounds[1] * 100:.1f}%"
    if want_range not in shown["text"]:
        errors.append(f"bench: range {want_range} not shown: {shown['text'][:200]!r}")
    if re.search(r"feasible", shown["text"], re.I):
        errors.append("bench: the panel still claims a league-feasible window (retired by JEG-508)")

    # 2%: priced as requested, no note, in the draft and after Apply.
    low = page.evaluate(USED, 0.02)
    _set_slider(page, 0.02)
    shown = _panel(page)
    errors += _check_shown("bench draft readout", _numbers(shown["readout"]), low)
    errors += _check_shown("bench draft split", _bench_numbers(shown["split"]), low)
    if shown["note"]:
        errors.append(f"bench: a requested-vs-used note at 2% where the engine priced 2%: {shown['note']!r}")
    page.click('#v2Popover [data-apply="weights"]')
    if abs(page.evaluate(f"() => {C}.getBenchShare()") - 0.02) > 1e-6:
        errors.append("bench: Apply did not request 2%")
    applied = page.evaluate(f"() => {C}.getBenchShareUsed()")
    if applied != low:
        errors.append(f"bench: getBenchShareUsed() after Apply {applied} != {low}")
    page.click("#v2Weights")
    shown = _panel(page)
    errors += _check_shown("bench applied readout", _numbers(shown["readout"]), applied)
    errors += _check_shown("bench applied split", _bench_numbers(shown["split"]), applied)
    page.keyboard.press("Escape")
    how = _how(page)
    errors += _check_shown("bench How values", _numbers(how["bench"]), applied)

    # Hermetic edge: the engine prices bench at 0 (no source has bench players above waivers).
    page.evaluate(FORCE_USED, "zero")
    page.click("#v2Weights")
    shown = _panel(page)
    zero = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
    errors += _check_shown("bench used-0 readout", _numbers(shown["readout"]), zero)
    if "2.0% requested" not in shown["note"] or "0.0%" not in shown["note"]:
        errors.append(f"bench: no requested-vs-used note when the engine priced 0: {shown['note']!r}")
    page.keyboard.press("Escape")
    how = _how(page)
    errors += _check_shown("bench used-0 How values", _numbers(how["bench"]), zero)
    if "2.0% requested" not in how["note"]:
        errors.append(f"bench: How values has no requested-vs-used note at used 0: {how['note']!r}")

    # Hermetic null: no used share, so "—" with a reason, never the requested 2%.
    page.evaluate(FORCE_USED, "null")
    page.click("#v2Weights")
    shown = _panel(page)
    if shown["readout"].strip() != "—" or not shown["note"]:
        errors.append(f"bench: with no used share the readout is {shown['readout']!r}, note {shown['note']!r}")
    page.keyboard.press("Escape")
    how = _how(page)
    if how["bench"].strip() != "—" or not how["note"]:
        errors.append(f"bench: with no used share How values shows {how['bench']!r}, note {how['note']!r}")
    page.evaluate(FORCE_USED, "restore")

    # 15%: shown as requested, no note.
    normal = page.evaluate(USED, 0.15)
    page.click("#v2Weights")
    _set_slider(page, 0.15)
    page.click('#v2Popover [data-apply="weights"]')
    page.click("#v2Weights")
    shown = _panel(page)
    errors += _check_shown("bench 15% readout", _numbers(shown["readout"]), normal)
    errors += _check_shown("bench 15% split", _bench_numbers(shown["split"]), normal)
    if shown["note"]:
        errors.append(f"bench: a note at 15%: {shown['note']!r}")
    page.keyboard.press("Escape")
    how = _how(page)
    if how["note"]:
        errors.append(f"bench: How values has a note at 15%: {how['note']!r}")
    return errors


def run_checks(v2_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
            page.wait_for_timeout(150)
            errors += check_bench(page)
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


class BenchUsedRenderTest(unittest.TestCase):
    def test_bench_share_shown_is_the_share_used(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "requested share shown instead of the used one": v2.replace(
                "    const used = C.getBenchShareUsed ? C.getBenchShareUsed(share) : null;",
                "    const used = {QB: share, RB: share, WR: share, TE: share};", 1),
            "retired feasible-window copy": v2.replace(
                "? `Range ${(bounds[0] * 100).toFixed(1)}%–${(bounds[1] * 100).toFixed(1)}% · Recommended 15%`",
                "? `Feasible ${(bounds[0] * 100).toFixed(1)}%–${(bounds[1] * 100).toFixed(1)}% for this league · Recommended 15%`", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, v2, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(v2_js=body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
