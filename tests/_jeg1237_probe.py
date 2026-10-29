"""JEG-1237 scratch probe: measures every block above the finder results after Find (not a test; scratch branch only)."""
from __future__ import annotations

import json

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import PICK, _built_dist, add

MEASURE = """() => {
  const card = document.getElementById('v2Find');
  const rect = n => { const r = n.getBoundingClientRect(); const cs = getComputedStyle(n);
    return {top: Math.round(r.top), h: Math.round(r.height), bottom: Math.round(r.bottom), mt: cs.marginTop, mb: cs.marginBottom}; };
  const out = {viewport: [innerWidth, innerHeight], scrollY, host: rect(document.getElementById('v2FindTrade')), card: rect(card), blocks: []};
  let n = document.getElementById('v2FindTrade');
  out.above = [...document.body.querySelectorAll('header, nav, .v2-context, #v2Context, .v2-tabs')].filter(x => x.getBoundingClientRect().height > 0).slice(0, 8).map(x => ({tag: x.tagName, id: x.id, cls: x.className, ...rect(x)}));
  [...card.children].forEach(c => { if (c.hidden || c.getBoundingClientRect().height === 0) return;
    out.blocks.push({tag: c.tagName, id: c.id, cls: String(c.className), ...rect(c),
      kids: [...c.children].filter(k => !k.hidden && k.getBoundingClientRect().height > 0).slice(0, 12).map(k => ({tag: k.tagName, id: k.id, cls: String(k.className), ...rect(k)}))}); });
  const hostKids = [...document.getElementById('v2FindTrade').children].map(c => ({tag: c.tagName, id: c.id, cls: String(c.className), hidden: c.hidden, ...rect(c)}));
  out.hostKids = hostKids;
  return out;
}"""


def main():
    _render_env.ensure_built()
    from playwright.sync_api import sync_playwright
    with _built_dist() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        for width, height in ((1366, 768), (1440, 900), (390, 844), (320, 640)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(base + "#find-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
            pick = page.evaluate(PICK)
            for name in pick["mine"]:
                add(page, "Mine", name)
            for name in pick["theirs"]:
                add(page, "Theirs", name)
            page.select_option("#v2FindSize", "3")
            page.evaluate("() => window.scrollTo(0, 0)")
            print(f"JEG1237 BEFORE {width}x{height} " + json.dumps(page.evaluate(MEASURE)))
            page.focus("#v2FindGo")
            page.wait_for_timeout(900)
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            print(f"JEG1237 AFTER {width}x{height} " + json.dumps(page.evaluate(MEASURE)))
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
