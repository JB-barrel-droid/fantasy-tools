"""v2 estimated values, rendered (VP-11, JEG-541).

After JEG-508 the engine fills in a chart value for a rosterable player the
chart doesn't list (VP-2.4) and marks it on the row: row.estimated =
{seriesKey: reason}. VP-11: the value cell, tooltip and inspector mark it
"estimated" and show the reason.

Builds dist/v2 into a temp copy of the built dist/ and loads Player values
headless at 1440 x 900. One extra estimated value is simulated on the top row
(the engine's row accessors are wrapped), so the check never depends on which
players this week's data happens to estimate. Checks:

  * every rendered table cell whose engine value is finite and estimated
    carries "≈ estimated" (symbol and word) with the engine's reason as its
    tooltip; no other cell carries it; at least one real (not simulated)
    estimated cell is rendered when the engine has any in the visible rows;
  * the player detail opened on the simulated row marks that series'
    value "≈ estimated" with the simulated reason;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js that ignores
row.estimated, and v2.js whose tag has the symbol but no word, and requires
the checks to fail on each.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_panels_render import V2_JS, _built_dist, _serve  # noqa: E402

SIM_REASON = "Simulated in test: estimated from other charts"

# Mark the top row's first shown chart value as estimated (if it is not already).
SIMULATE = """(reason) => {
  const C = window.TradeValueCurveControls;
  const shown = window.TradeValueV2.shown().filter(k => k !== 'ddf_value' && !k.startsWith('ddf_value_'));
  const top = C.getRows()[0];
  const series = shown.find(k => Number.isFinite(top.values[k]) && !(top.estimated || {})[k]);
  if (!series) return null;
  const key = String(top.player_key);
  const patch = r => (!r || String(r.player_key) !== key) ? r
    : {...r, estimated: {...(r.estimated || {}), [series]: reason}};
  for (const name of ['getAllRows', 'getRows']) {
    const original = C[name].bind(C);
    C[name] = (...args) => original(...args).map(patch);
  }
  if (C.getPlayer) { const original = C.getPlayer.bind(C); C.getPlayer = (...args) => patch(original(...args)); }
  location.hash = '#how-values'; location.hash = '#player-values';
  return {key, series};
}"""

READ = """() => {
  const C = window.TradeValueCurveControls;
  const rows = Object.fromEntries(C.getRows().map(r => [String(r.player_key), r]));
  return [...document.querySelectorAll('#v2Table tbody tr[data-player-key] td[data-source]')].map(td => {
    const row = rows[td.closest('tr').dataset.playerKey];
    const key = td.dataset.source;
    const tag = td.querySelector('[data-estimated]');
    return {player: row.name, pk: String(row.player_key), key, finite: Number.isFinite(row.values[key]),
      reason: (row.estimated || {})[key] || null,
      tag: tag ? {text: tag.textContent.trim(), title: tag.title} : null};
  });
}"""

DRAWER = """(key) => {
  document.querySelector(`#v2Table tbody tr[data-player-key="${key}"]`).click();
  const drawer = document.getElementById('v2Drawer');
  return {open: !drawer.hidden, tags: [...drawer.querySelectorAll('[data-estimated]')].map(n => ({text: n.textContent.trim(), title: n.title}))};
}"""


def check_cells(cells, simulated) -> list[str]:
    errors = []
    marked_real = 0
    for c in cells:
        where = f"{c['player']}/{c['key']}"
        if c["finite"] and c["reason"]:
            if not c["tag"] or c["tag"]["text"] != "≈ estimated" or c["tag"]["title"] != c["reason"]:
                errors.append(f"{where}: engine marks it estimated ({c['reason']!r}) but the cell shows {c['tag']}")
            elif not (c["pk"] == simulated["key"] and c["key"] == simulated["series"]):
                marked_real += 1
        elif c["tag"]:
            errors.append(f"{where}: marked {c['tag']} but the engine does not estimate it")
    if not any(c["pk"] == simulated["key"] and c["key"] == simulated["series"] for c in cells):
        errors.append(f"the simulated estimated cell {simulated} is not rendered; the check went unchecked")
    real = [c for c in cells if c["finite"] and c["reason"] and c["reason"] != SIM_REASON]
    if real and not marked_real:
        errors.append(f"{len(real)} real estimated cells rendered, none marked")
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
            simulated = page.evaluate(SIMULATE, SIM_REASON)
            if not simulated:
                return ["could not simulate an estimated value on the top row"]
            page.wait_for_function("() => !document.getElementById('v2Main').hidden")
            page.wait_for_timeout(300)
            errors += check_cells(page.evaluate(READ), simulated)
            drawer = page.evaluate(DRAWER, simulated["key"])
            if not drawer["open"]:
                errors.append("the player detail did not open")
            elif {"text": "≈ estimated", "title": SIM_REASON} not in drawer["tags"]:
                errors.append(f"player detail does not mark {simulated['series']} estimated: {drawer['tags']}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


class EstimatedRenderTest(unittest.TestCase):
    def test_estimated_values_are_marked(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        broken = {
            "row.estimated ignored": v2.replace(
                "    const reason = row && row.estimated ? row.estimated[key] : null;",
                "    const reason = null;", 1),
            "symbol without the word": v2.replace(
                '    node.append(sym, document.createTextNode(" estimated"));',
                "    node.append(sym);", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, v2, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(v2_js=body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
