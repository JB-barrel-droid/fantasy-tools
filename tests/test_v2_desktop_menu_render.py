"""Desktop navigation menu guard (JEG-1106; Jeremy, 2026-10-25, option A).

The top bar keeps the menu button, the site name, the name of the page on show and the freshness button. The button
opens a grouped menu (Trade, Players, Auditing, Our approach, Settings). This file checks, at 1366x768 and 1000x700:
  * the bar is one row, the page does not scroll sideways, the menu fits on screen;
  * keyboard: Enter / Space open, the page on show is focused, arrows / Home / End move, Escape closes and returns focus;
  * pointer: a click opens, an entry navigates and closes, a tap outside closes;
  * aria: aria-expanded follows the state, exactly one entry is aria-current, groups are labelled;
  * every old and new deep link resolves to the right page and names it beside the button; the landing page is the
    value chart; Customize opens the sources dialog.

Discrimination (test_guard_fails_on_broken_builds): arrows, Escape, aria-expanded, aria-current, the page name, the
landing route, Customize, and a menu wider than the screen must each make the check fail.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_v2_phone_weight_render import _served

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
JS = ROOT / "app" / "v2" / "v2.js"
SIZES = ((1366, 768), (1000, 700))
GROUPS = ["Trade", "Players", "Auditing", "Our approach", "Settings"]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

# JEG-1371: the Research entry is in the menu only once a post is published. Without one, its routes still open the
# (empty) Research page, and no menu entry is current.
HAS_RESEARCH = bool(build_v2_page.load_posts())
ENTRIES = 14 if HAS_RESEARCH else 13
RESEARCH_LINK = ("writing/research", "Research") if HAS_RESEARCH else (None, "")
# hash -> (entry that is current, name shown beside the button)
DEEP_LINKS = {
    "": ("values", "Value chart"),
    "#nonsense-route": ("values", "Value chart"),
    "#player-values": ("values", "Value chart"),
    "#compare-trade": ("compare", "Compare a trade"),
    "#find-trade": ("find", "Find a trade: your team"),
    "#find-league": ("league", "Find a trade: league-wide"),
    "#risers-fallers": ("risers", "Risers and fallers"),
    "#waivers": ("waivers", "Waivers"),
    "#trade-targets": ("targets", "Trade targets"),
    "#values-auditing": ("audit/health-check", "Value pie"),
    "#values-auditing/health-check": ("audit/health-check", "Value pie"),
    "#values-auditing/value-pie": ("audit/health-check", "Value pie"),
    "#values-auditing/single-source": ("audit/single-source", "Source build-up"),
    "#writing": ("writing/manifesto", "Manifesto"),
    "#writing/manifesto": ("writing/manifesto", "Manifesto"),
    "#writing/how-values": ("writing/how-values", "Methodology"),
    "#writing/research": RESEARCH_LINK,
    "#writing/research/anything": RESEARCH_LINK,
    "#manifesto": ("writing/manifesto", "Manifesto"),
    "#how-values": ("writing/how-values", "Methodology"),
    "#research": RESEARCH_LINK,
    "#value-overrides": ("overrides", "Overrides"),
}

STATE = """() => {
  const vw = document.documentElement.clientWidth, vh = innerHeight;
  const t = document.getElementById('v2NavToggle');
  const menu = document.getElementById('v2Tabs');
  const shown = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const items = [...menu.querySelectorAll('.v2-tab')];
  const mr = menu.getBoundingClientRect();
  const cur = document.getElementById('v2NavCurrent');
  return {
    over: document.documentElement.scrollWidth - vw,
    barH: document.querySelector('.v2-nav-inner').getBoundingClientRect().height,
    expanded: t.getAttribute('aria-expanded'), toggleShown: shown(t),
    menuShown: shown(menu), menuFits: mr.left >= -0.5 && mr.right <= vw + 0.5 && mr.bottom <= vh + 0.5,
    items: items.length, shownItems: items.filter(shown).length,
    labels: items.map(a => a.textContent.trim()),
    heads: [...menu.querySelectorAll('.v2-nav-grouphead')].map(h => h.textContent.trim()),
    groupsLabelled: [...menu.querySelectorAll('[role=group]')].every(g => document.getElementById(g.getAttribute('aria-labelledby'))),
    current: items.filter(a => a.getAttribute('aria-current') === 'page').map(a => a.dataset.key),
    name: cur.textContent.trim(), nameShown: shown(cur),
    brandShown: shown(document.querySelector('.v2-brand')), freshShown: shown(document.getElementById('v2Freshness')),
    focusKey: document.activeElement && (document.activeElement.dataset.key || document.activeElement.dataset.action || document.activeElement.id),
    hash: location.hash,
    dialog: !document.getElementById('v2Popover').hidden,
  };
}"""


def setUpModule():
    _render_env.ensure_built()


def run_checks(css=None, js=None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    errors: list[str] = []

    def open_page(browser, base, size, hash_):
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        page.add_init_script(_render_env.pin_data_week_script())
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        if js is not None:
            page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=js))
        page.goto(base + hash_, wait_until="networkidle")
        page.wait_for_function("() => window.TradeValueV2", timeout=40000)
        page.wait_for_timeout(250)
        return page

    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        try:
            for size in SIZES:
                tag = f"{size[0]}x{size[1]}"
                page = open_page(browser, base, size, "#compare-trade")
                s = page.evaluate(STATE)
                if not (s["toggleShown"] and s["brandShown"] and s["nameShown"] and s["freshShown"]):
                    errors.append(f"{tag}: top bar must show button, site name, page name and freshness: {s}")
                if s["barH"] > 70 or s["over"] > 0:
                    errors.append(f"{tag}: bar is {s['barH']}px tall, page scrolls sideways by {s['over']}")
                if s["expanded"] != "false" or s["menuShown"]:
                    errors.append(f"{tag}: menu not closed at load (expanded {s['expanded']}, shown {s['menuShown']})")
                if s["name"] != "Compare a trade" or s["current"] != ["compare"]:
                    errors.append(f"{tag}: page name {s['name']!r}, current {s['current']}")
                # Keyboard: Enter opens.
                page.focus("#v2NavToggle")
                page.keyboard.press("Enter")
                s = page.evaluate(STATE)
                if s["expanded"] != "true" or s["shownItems"] != ENTRIES or s["items"] != ENTRIES:
                    errors.append(f"{tag}: Enter did not open the menu with {ENTRIES} entries ({s['expanded']}, {s['shownItems']} shown)")
                if s["focusKey"] != "compare":
                    errors.append(f"{tag}: open menu focus is on {s['focusKey']!r}, want the page on show")
                if s["heads"] != GROUPS or not s["groupsLabelled"]:
                    errors.append(f"{tag}: groups {s['heads']} labelled={s['groupsLabelled']}")
                if not s["menuFits"] or s["over"] > 0 or s["barH"] > 70:
                    errors.append(f"{tag}: open menu does not fit the screen (fits {s['menuFits']}, over {s['over']}, bar {s['barH']})")
                if len(s["current"]) != 1:
                    errors.append(f"{tag}: {len(s['current'])} entries marked current")
                page.keyboard.press("ArrowDown")
                if page.evaluate(STATE)["focusKey"] != "find":
                    errors.append(f"{tag}: ArrowDown did not move to the next entry")
                page.keyboard.press("ArrowUp")
                page.keyboard.press("ArrowUp")
                if page.evaluate(STATE)["focusKey"] != "values":
                    errors.append(f"{tag}: ArrowUp did not move back")
                page.keyboard.press("End")
                if page.evaluate(STATE)["focusKey"] != "overrides":
                    errors.append(f"{tag}: End did not reach the last entry")
                page.keyboard.press("Home")
                if page.evaluate(STATE)["focusKey"] != "values":
                    errors.append(f"{tag}: Home did not reach the first entry")
                page.keyboard.press("Escape")
                s = page.evaluate(STATE)
                if s["expanded"] != "false" or s["menuShown"] or s["focusKey"] != "v2NavToggle":
                    errors.append(f"{tag}: Escape left expanded={s['expanded']} shown={s['menuShown']} focus={s['focusKey']!r}")
                # Space opens, Enter on an entry goes there and closes.
                page.keyboard.press("Space")
                if page.evaluate(STATE)["expanded"] != "true":
                    errors.append(f"{tag}: Space did not open the menu")
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                page.wait_for_timeout(250)
                s = page.evaluate(STATE)
                if s["hash"] != "#find-trade" or s["name"] != "Find a trade: your team" or s["expanded"] != "false":
                    errors.append(f"{tag}: Enter on an entry gave hash {s['hash']!r}, name {s['name']!r}, expanded {s['expanded']}")
                # Pointer: click opens, an entry navigates, a tap outside closes.
                page.click("#v2NavToggle")
                page.click('.v2-tab[data-key="writing/how-values"]')
                page.wait_for_timeout(250)
                s = page.evaluate(STATE)
                if s["hash"] != "#writing/how-values" or s["name"] != "Methodology" or s["expanded"] != "false":
                    errors.append(f"{tag}: click on Methodology gave hash {s['hash']!r}, name {s['name']!r}, expanded {s['expanded']}")
                page.click("#v2NavToggle")
                page.mouse.click(size[0] - 8, size[1] - 8)
                if page.evaluate(STATE)["expanded"] != "false":
                    errors.append(f"{tag}: a tap outside did not close the menu")
                # Customize opens the sources dialog.
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                page.wait_for_timeout(250)
                page.click("#v2NavToggle")
                page.click('.v2-tab[data-action="customize"]')
                page.wait_for_timeout(300)
                s = page.evaluate(STATE)
                if not s["dialog"] or s["expanded"] != "false":
                    errors.append(f"{tag}: Customize did not open the dialog (dialog {s['dialog']}, expanded {s['expanded']})")
                page.close()
            # Deep links (one size: routing does not depend on width).
            page = open_page(browser, base, SIZES[0], "")
            for hash_, (key, name) in DEEP_LINKS.items():
                page.goto(base + hash_, wait_until="networkidle")
                page.reload(wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                page.wait_for_timeout(200)
                s = page.evaluate(STATE)
                if s["current"] != ([key] if key else []) or s["name"] != name:
                    errors.append(f"deep link {hash_!r}: current {s['current']} name {s['name']!r}, want [{key!r}] {name!r}")
            page.close()
        finally:
            browser.close()
    return errors


class DesktopMenuRenderTest(unittest.TestCase):
    def test_desktop_menu(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        cases = {
            "no arrow keys": (None, js.replace('["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)', "false"), "ArrowDown did not"),
            "no Escape": (None, js.replace('if (event.key === "Escape" && header.classList.contains("is-open")) setNav(false, true);', ""), "Escape left"),
            "aria-expanded never set": (None, js.replace('toggle.setAttribute("aria-expanded", open ? "true" : "false");', ""), "Enter did not open"),
            "no aria-current": (None, js.replace('if (on) { tab.setAttribute("aria-current", "page"); navLabel', 'if (on) { navLabel'), "current"),
            "page name not updated": (None, js.replace('$("v2NavCurrent").textContent = navLabel;', ""), "page name"),
            "landing is Trade targets again": (None, js.replace('const DEFAULT_ROUTE = "#player-values";', 'const DEFAULT_ROUTE = "#trade-targets";').replace('viewFor(hashBase()) || "values"', 'viewFor(hashBase()) || "targets"'), "deep link"),
            "Customize does nothing": (None, js.replace('openSources(toggle);', "void 0;"), "Customize did not"),
            "menu wider than the screen": (css.replace("width: min(720px, calc(100vw - 32px));", "width: 1500px;"), None, "does not fit"),
            "menu opens in the bar": (css.replace("position: absolute; z-index: 50; left: 48px;", "position: static; z-index: 50; left: 48px;"), None, "does not fit"),
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
