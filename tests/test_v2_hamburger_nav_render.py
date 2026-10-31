"""Phone hamburger navigation guard (JEG-953; Jeremy, 2026-10-23, decision C2).

JEG-1106 (Jeremy, 2026-10-25): desktop uses the same button and menu, now grouped (Trade, Players, Auditing, Our approach,
Settings) with 14 entries. This file keeps the phone checks (the menu opens in the bar, full width) and checks the wider
screens only for what they share: the button shows, the menu starts closed and the page does not scroll sideways. The
desktop panel, keys and deep links are in test_v2_desktop_menu_render.py. The text below is the original JEG-953 note.

Below the phone breakpoint (under 768 px wide, or a landscape phone up to 932 x 500) the top nav collapses to a
44 x 44 button; the menu lists all ten tabs (the finder split in two, JEG-1094) (Waivers added 2026-10-24, JEG-1022; Overrides, JEG-1035), marks the active one, and closes on selection, Escape (focus returns
to the button) and a tap outside. 768 px and wider keep the tab row, unchanged.

Discrimination (test_guard_fails_on_broken_builds): each break below must make the check fail:
  * the hamburger CSS block removed (button never shows on a phone);
  * the toggle's default display:none removed (button leaks onto desktop);
  * the menu given a 600 px basis (menu widens the page at 320);
  * JS without the Escape handler, without outside-tap, and without close-on-selection.
"""
from __future__ import annotations

import re
import unittest
import sys
from pathlib import Path

from tests import _render_env
from tests.test_v2_phone_weight_render import _served

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
JS = ROOT / "app" / "v2" / "v2.js"
PHONES = ((320, 568), (360, 740), (390, 844), (844, 390))
WIDE = ((768, 1024), (1366, 768))
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

# JEG-1371: the Research entry is in the menu only once a post is published.
RESEARCH = ["Research"] if build_v2_page.load_posts() else []
LABELS = ["Value chart", "Compare a trade", "Find a trade: your team", "Find a trade: league-wide", "Risers and fallers", "Waivers", "Trade targets", "Value pie", "Source build-up", "Methodology", *RESEARCH, "Manifesto", "Customize", "Overrides"]


def setUpModule():
    _render_env.ensure_built()


STATE = """() => {
  const vw = document.documentElement.clientWidth;
  const t = document.getElementById('v2NavToggle');
  const tr = t.getBoundingClientRect();
  const shown = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const tabs = [...document.querySelectorAll('.v2-tabs .v2-tab')];
  return {
    over: document.documentElement.scrollWidth - vw,
    toggleShown: shown(t), toggleW: tr.width, toggleH: tr.height,
    expanded: t.getAttribute('aria-expanded'), controls: t.getAttribute('aria-controls'),
    controlsOk: document.getElementById(t.getAttribute('aria-controls')) === document.querySelector('.v2-tabs'),
    tabsShown: tabs.filter(shown).length,
    labels: tabs.map(a => a.textContent.trim()),
    offscreen: tabs.filter(a => { const r = a.getBoundingClientRect(); return r.left < -0.5 || r.right > vw + 0.5; }).length,
    short: tabs.filter(a => a.getBoundingClientRect().height < 43.5).length,
    current: tabs.filter(a => a.getAttribute('aria-current') === 'page').map(a => a.dataset.view),
    hash: location.hash,
    focus: document.activeElement && (document.activeElement.id || document.activeElement.className),
  };
}"""


def _open_page(browser, base, size, css, js):
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    if css is not None:
        page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
    if js is not None:
        page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=js))
    page.goto(base + "#trade-targets", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2", timeout=40000)
    page.wait_for_timeout(300)
    return page


def run_checks(css=None, js=None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    errors: list[str] = []
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        try:
            for size in PHONES:
                tag = f"{size[0]}x{size[1]}"
                page = _open_page(browser, base, size, css, js)
                s = page.evaluate(STATE)
                if not s["toggleShown"] or abs(s["toggleW"] - 44) > 0.5 or abs(s["toggleH"] - 44) > 0.5:
                    errors.append(f"{tag}: hamburger not shown at 44x44 ({s['toggleW']}x{s['toggleH']}, shown={s['toggleShown']})")
                    page.close()
                    continue
                if s["tabsShown"] or s["expanded"] != "false":
                    errors.append(f"{tag}: menu not collapsed at load (tabs shown {s['tabsShown']}, expanded {s['expanded']})")
                if s["over"] > 0:
                    errors.append(f"{tag}: page scrolls sideways by {s['over']} (collapsed)")
                if not s["controlsOk"]:
                    errors.append(f"{tag}: aria-controls {s['controls']!r} does not point at the tab nav")
                # Open.
                page.click("#v2NavToggle")
                s = page.evaluate(STATE)
                if s["expanded"] != "true" or s["tabsShown"] != len(LABELS):
                    errors.append(f"{tag}: open menu shows {s['tabsShown']} tabs, expanded {s['expanded']}; want {len(LABELS)} and true")
                if s["labels"] != LABELS:
                    errors.append(f"{tag}: menu labels {s['labels']}")
                if s["over"] > 0 or s["offscreen"]:
                    errors.append(f"{tag}: open menu overflows (page +{s['over']}, {s['offscreen']} tabs off screen)")
                if s["short"]:
                    errors.append(f"{tag}: {s['short']} menu items under 44 px tall")
                if s["current"] != ["targets"]:
                    errors.append(f"{tag}: active tab marked {s['current']}, want ['targets']")   # the page opens on #trade-targets
                # Select.
                page.click('.v2-tab[data-view="values"]')
                page.wait_for_timeout(200)
                s = page.evaluate(STATE)
                if s["hash"] != "#player-values" or s["current"] != ["values"]:
                    errors.append(f"{tag}: selecting Value chart gave hash {s['hash']!r}, current {s['current']}")
                if s["expanded"] != "false" or s["tabsShown"]:
                    errors.append(f"{tag}: menu stayed open after selection")
                # Escape returns focus to the button.
                page.click("#v2NavToggle")
                page.keyboard.press("Escape")
                s = page.evaluate(STATE)
                if s["expanded"] != "false" or s["tabsShown"]:
                    errors.append(f"{tag}: Escape did not close the menu")
                if s["focus"] != "v2NavToggle":
                    errors.append(f"{tag}: after Escape focus is on {s['focus']!r}, want the button")
                # Outside tap (the page brand row's right of the button is inside the header, so tap the main area).
                page.click("#v2NavToggle")
                page.mouse.click(size[0] - 6, size[1] - 6)
                s = page.evaluate(STATE)
                if s["expanded"] != "false" or s["tabsShown"]:
                    errors.append(f"{tag}: outside tap did not close the menu")
                page.close()
            for size in WIDE:
                tag = f"{size[0]}x{size[1]}"
                page = _open_page(browser, base, size, css, js)
                s = page.evaluate(STATE)
                if not s["toggleShown"]:
                    errors.append(f"{tag}: hamburger missing on a wide screen")
                if s["tabsShown"] or s["labels"] != LABELS:
                    errors.append(f"{tag}: wide-screen menu should start closed with {len(LABELS)} entries; shows {s['tabsShown']}, labels {s['labels']}")
                if s["over"] > 0:
                    errors.append(f"{tag}: page scrolls sideways by {s['over']}")
                page.close()
        finally:
            browser.close()
    return errors


class HamburgerNavRenderTest(unittest.TestCase):
    def test_hamburger_menu_and_unchanged_desktop(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        block = re.search(r"/\* ===== JEG-953 hamburger.*?end JEG-953 =+ \*/\n", css, re.S)
        self.assertTrue(block, "stale mutation anchor (css block)")
        cases = {
            "no hamburger block": (css.replace(block.group(0), ""), None, "hamburger not shown"),
            "menu leaks open on desktop": (css.replace("  .v2-nav .v2-tabs { display: none; position: absolute;", "  .v2-nav .v2-tabs { display: grid; position: absolute;"), None, "should start closed"),
            "menu widens the page": (css.replace("flex: 1 0 100%; display: none;", "flex: 1 0 600px; display: none;"), None, "overflows"),
            "no Escape": (None, js.replace('if (event.key === "Escape" && header.classList.contains("is-open")) setNav(false, true);', ""), "Escape did not close"),
            "no outside tap": (None, js.replace('if (header.classList.contains("is-open") && !header.contains(event.target)) setNav(false, false);', ""), "outside tap did not close"),
            "no close on selection": (None, js.replace('if (item && header.classList.contains("is-open")) setNav(false, false);', "").replace('window.addEventListener("hashchange", () => { if (header.classList.contains("is-open")) setNav(false, false); });', ""), "stayed open after selection"),
        }
        for name, (c, j, want) in cases.items():
            if c is not None:
                self.assertNotEqual(c, css, f"{name}: mutation did not apply")
            if j is not None:
                self.assertNotEqual(j, js, f"{name}: mutation did not apply")
            with self.subTest(name):
                errors = run_checks(css=c, js=j)
                self.assertTrue(any(want in e for e in errors), f"{name} not caught: {errors}")


if __name__ == "__main__":
    unittest.main()
