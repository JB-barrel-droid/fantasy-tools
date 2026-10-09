"""v2 bench share, rendered: the share shown is the share the engine priced with.

Below the league's feasible window (PPR, 12 teams: about 4.4% for RB / WR /
TE and 7.5% for QB) the engine prices each position at a higher feasible share
and records it as bench_share_used on its calibration. v2 must show that share,
not the requested one.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 1440 x 900:

  * Weights & bench: dragging the slider to 2% shows the engine's used shares
    (lowest to highest across positions) in the readout and the Starters /
    Bench split, plus one note naming the requested 2%; Apply keeps it;
  * the engine accessor getBenchShareUsed() agrees with the calibration the
    engine actually priced with (TradeValueTwoTierLive.calibration);
  * How values work shows the same used share and note;
  * at 15% (inside the window) the shares shown are 15% and there is no note;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js showing the
requested share instead of the used one, and requires the checks to fail.
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


USED = """share => { const cal = window.TradeValueTwoTierLive.calibration(share);
  const out = {}; for (const pos of ['QB', 'RB', 'WR', 'TE']) { const c = cal && cal[pos];
    out[pos] = c && !c.invalid && Number.isFinite(c.bench_share_used) ? c.bench_share_used : null; }
  return out; }"""



def _numbers(text: str) -> list[float]:
    return [float(x) / 100 for x in re.findall(r"(\d+(?:\.\d+)?)", text or "")]


def _bench_numbers(text: str) -> list[float]:
    """The numbers after 'Bench' in 'Starters a% / Bench b–c%'."""
    tail = text.split("Bench", 1)[1] if "Bench" in (text or "") else ""
    return _numbers(tail.split("·")[0])


def _check_shown(tag, numbers, used) -> list[str]:
    """numbers shown (one value, or low and high) must equal the engine's used shares."""
    finite = [v for v in used.values() if v is not None]
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
        note: note && !note.hidden ? note.textContent : ''}; }""")


def _set_slider(page, share):
    page.evaluate("v => { const s = document.getElementById('v2BenchSlider'); s.value = String(v); s.dispatchEvent(new Event('input')); }", share)


def check_bench(page) -> list[str]:
    errors = []
    bounds = page.evaluate("() => window.TradeValueCurveControls.getBenchBounds()")
    if not bounds or bounds[0] > 0.02:
        return [f"bench: feasible slider bounds {bounds} do not reach 2%"]
    low = page.evaluate(USED, 0.02)
    if not any(v is not None and v > 0.02 + 1e-6 for v in low.values()):
        return [f"bench: the engine priced 2% at {low}; the fixture no longer exercises the floor"]
    accessor = page.evaluate("() => window.TradeValueCurveControls.getBenchShareUsed ? window.TradeValueCurveControls.getBenchShareUsed(0.02) : null")
    if accessor != low:
        errors.append(f"bench: getBenchShareUsed(0.02) {accessor} != engine calibration {low}")

    # Below the floor, in the draft (before Apply).
    page.click("#v2Weights")
    _set_slider(page, 0.02)
    shown = _panel(page)
    errors += _check_shown("bench draft readout", _numbers(shown["readout"]), low)
    errors += _check_shown("bench draft split", _bench_numbers(shown["split"]), low)
    if "2.0% requested" not in shown["note"] or "lowest the league supports" not in shown["note"]:
        errors.append(f"bench: no requested-vs-used note at 2%: {shown['note']!r}")
    page.click('#v2Popover [data-apply="weights"]')
    if abs(page.evaluate("() => window.TradeValueCurveControls.getBenchShare()") - 0.02) > 1e-6:
        errors.append("bench: Apply did not request 2%")
    applied = page.evaluate("() => window.TradeValueCurveControls.getBenchShareUsed ? window.TradeValueCurveControls.getBenchShareUsed() : null")
    if applied != low:
        errors.append(f"bench: getBenchShareUsed() after Apply {applied} != {low}")
    page.click("#v2Weights")
    shown = _panel(page)
    errors += _check_shown("bench applied readout", _numbers(shown["readout"]), low)
    errors += _check_shown("bench applied split", _bench_numbers(shown["split"]), low)
    if "2.0% requested" not in shown["note"]:
        errors.append(f"bench: no note after Apply at 2%: {shown['note']!r}")
    page.keyboard.press("Escape")

    # How values work names the same used share.
    page.evaluate("() => { location.hash = '#how-values'; }")
    page.wait_for_function("() => !document.getElementById('v2How').hidden")
    how = page.evaluate("""() => ({bench: document.getElementById('v2HowBench').textContent,
      note: [...document.querySelectorAll('#v2How [data-bench-note]')].filter(n => !n.hidden).map(n => n.textContent).join(' ')})""")
    errors += _check_shown("bench How values", _numbers(how["bench"]), low)
    if "2.0% requested" not in how["note"]:
        errors.append(f"bench: How values has no requested-vs-used note: {how['note']!r}")
    page.evaluate("() => { location.hash = '#player-values'; }")
    page.wait_for_function("() => !document.getElementById('v2Main').hidden")

    # Inside the window: shown as requested, no note.
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
    page.evaluate("() => { location.hash = '#how-values'; }")
    page.wait_for_function("() => !document.getElementById('v2How').hidden")
    note = page.evaluate("() => [...document.querySelectorAll('#v2How [data-bench-note]')].filter(n => !n.hidden).map(n => n.textContent).join('')")
    if note:
        errors.append(f"bench: How values has a note at 15%: {note!r}")
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
                "    const used = null;", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, v2, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(v2_js=body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
