"""v2 Waivers tab: paste a whole roster page or waiver page into the one box (JEG-1104), rendered.

Pages are built in the browser from real engine rows, in the same layouts as the SYNTHETIC fixtures in
tests/fixtures/waivers_paste/ (free-agent pages) and tests/fixtures/roster_paste/ (team pages). Pasting into the one box:

  * a Yahoo and an ESPN free-agent page fill Waiver candidates and not Your roster, and say which list they were read as;
  * a Yahoo team page fills Your roster (replacing it) and not Waiver candidates;
  * a bare list of names with no cue asks which list it is, and the answer fills that list;
  * a roster page pasted into the Waiver candidates box is held back with a button to use it for the roster.

Discrimination: test_guard_fails_on_broken_builds serves roster-paste.js without the free-agent row reader and
waivers.js without the detection, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import _built_dist
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
PASTE_JS = ROOT / "app" / "v2" / "roster-paste.js"
WAIVERS_JS = ROOT / "app" / "v2" / "waivers.js"


def setUpModule():
    _render_env.ensure_built()


PAGES = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const count = new Map(); rows.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const by = pos => rows.filter(r => r.pos === pos && count.get(r.name) === 1);
  const cap = t => String(t || '').charAt(0) + String(t || '').slice(1).toLowerCase();
  const fa = [].concat(by('RB').slice(30, 33), by('WR').slice(30, 33), by('TE').slice(10, 11));
  const roster = [['QB', by('QB')[6]], ['RB', by('RB')[8]], ['RB', by('RB')[9]], ['WR', by('WR')[8]], ['WR', by('WR')[9]], ['TE', by('TE')[5]], ['BN', by('WR')[12]], ['BN', by('RB')[12]]];
  const yahooChrome = 'Yahoo Sports\\nSearch\\nFantasy Football\\nOverview\\nYahoo Sports Fantasy Football\\n';
  const espnChrome = 'ESPN\\nESPN Fantasy\\nFantasy Football Home\\nMy Team\\nPlayers\\n';
  const yahooFa = yahooChrome + 'Players\\nAvailable Players\\nPosition\\nAll Offense\\nQB\\nRB\\nWR\\nTE\\nK\\nDEF\\nFan Pts\\nProj\\n% Owned\\n'
    + fa.map(r => '+\\nAdd\\n' + r.name + 'Video ForecastPlayer Note\\n' + cap(r.team) + ' - ' + r.pos + '\\nSun 1:00 pm vs Ind\\n8.1\\n9.0\\n40%\\n').join('') + '\\nPrivacy\\n';
  const espnFa = espnChrome + 'Players\\nFree Agents\\nAvailable\\nQB\\nRB\\nWR\\nTE\\nD/ST\\nK\\nPlayer\\nAction\\nProj\\n% Own\\n'
    + fa.map(r => r.name + r.name + '\\n' + r.name + '\\n' + cap(r.team) + '\\n' + r.pos + '\\nSun 1:00 pm vs Ind\\nADD\\n6.3\\n41%\\n').join('') + '\\nFantasy Football Glossary\\n';
  const yahooTeam = yahooChrome + 'My Team\\n' + roster.map(([slot, r]) => slot + '\\n' + r.name + 'Video ForecastPlayer Note\\n' + cap(r.team) + ' - ' + r.pos + '\\nSun 1:00 pm vs Ind\\n10.0\\n').join('');
  const names = fa.map(r => r.name).join('\\n');
  return {yahooFa, espnFa, yahooTeam, names, faNames: fa.map(r => r.name), rosterNames: roster.map(([, r]) => r.name)};
}"""

LISTS = """() => {
  const txt = id => [...document.querySelectorAll('#' + id + ' .v2-wv-players li')].map(li => li.innerText);
  return {mine: txt('v2WaiversMineInput'), cands: txt('v2WaiversCandsInput'),
    any: document.getElementById('v2WaiversAnyResult').innerText.replace(/\\s+/g, ' ').trim(),
    mineResult: document.getElementById('v2WaiversMinePasteResult').innerText.replace(/\\s+/g, ' ').trim(),
    candsResult: document.getElementById('v2WaiversCandsPasteResult').innerText.replace(/\\s+/g, ' ').trim()};
}"""

PASTE = """([id, text]) => {
  const box = document.getElementById(id);
  const data = new DataTransfer();
  data.setData('text', text);
  box.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
}"""


def has_all(items, names):
    joined = " | ".join(items)
    return [n for n in names if n not in joined]


def run_checks(overrides=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            for name, (body, kind) in (overrides or {}).items():
                page.route(f"**/v2/{name}*", functools.partial(_serve, body, kind))
                context.route(f"**/v2/{name}*", functools.partial(_serve, body, kind))
            page.goto(base + "#waivers", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2WaiversAnySearch')", timeout=60000)
            pages = page.evaluate(PAGES)

            def reset():
                page.evaluate("() => { for (const id of ['v2WaiversMineClear', 'v2WaiversCandsClear']) { const b = document.getElementById(id); if (b && !b.hidden) b.click(); } }")

            for tag, key in (("Yahoo waiver page", "yahooFa"), ("ESPN waiver page", "espnFa")):
                reset()
                page.evaluate(PASTE, ["v2WaiversAnySearch", pages[key]])
                page.wait_for_timeout(300)
                s = page.evaluate(LISTS)
                missing = has_all(s["cands"], pages["faNames"])
                if missing or s["mine"]:
                    errors.append(f"{tag}: candidates missing {missing}, roster {s['mine']}")
                if "waiver options" not in s["any"] or not s["candsResult"].startswith("Found"):
                    errors.append(f"{tag}: confirmation {s['any']!r} / {s['candsResult']!r}")
            reset()
            page.evaluate(PASTE, ["v2WaiversAnySearch", pages["yahooTeam"]])
            page.wait_for_timeout(300)
            s = page.evaluate(LISTS)
            missing = has_all(s["mine"], pages["rosterNames"])
            if missing or s["cands"] or "your roster" not in s["any"] or not s["mineResult"].startswith("Found"):
                errors.append(f"Yahoo team page: roster missing {missing}, candidates {s['cands']}, {s['any']!r} / {s['mineResult']!r}")
            reset()
            page.evaluate(PASTE, ["v2WaiversAnySearch", pages["names"]])
            page.wait_for_timeout(300)
            s = page.evaluate(LISTS)
            if "which list" not in s["any"].lower() or s["mine"] or s["cands"]:
                errors.append(f"names with no cue should ask: {s}")
            else:
                page.click("text=These are waiver options")
                page.wait_for_timeout(300)
                s = page.evaluate(LISTS)
                if has_all(s["cands"], pages["faNames"]) or s["mine"]:
                    errors.append(f"answer did not fill the waiver list: {s}")
            reset()
            page.evaluate(PASTE, ["v2WaiversCandsSearch", pages["yahooTeam"]])
            page.wait_for_timeout(300)
            s = page.evaluate(LISTS)
            if s["cands"] or "roster page" not in s["candsResult"]:
                errors.append(f"roster page in the waiver box was not held back: {s['candsResult']!r}, {s['cands']}")
            else:
                page.click("#v2WaiversCandsPasteResult >> text=Use it for your roster")
                page.wait_for_timeout(300)
                s = page.evaluate(LISTS)
                if has_all(s["mine"], pages["rosterNames"]) or s["cands"]:
                    errors.append(f"redirect to roster failed: {s['mine']}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            context.close()
        finally:
            browser.close()
    return errors


class WaiversPasteRenderTests(unittest.TestCase):
    maxDiff = None

    def test_paste(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        paste = PASTE_JS.read_text(encoding="utf-8")
        js = WAIVERS_JS.read_text(encoding="utf-8")
        broken = {
            "no free-agent row reader": ("roster-paste.js", paste.replace("if (site !== \"unknown\") {\n      var listed", "if (false) {\n      var listed", 1), "text/javascript"),
            "always waivers": ("waivers.js", js.replace("const kind = P.detectListKind(text, res);\n      if (kind !== \"unknown\") { route(text, kind, res.site); return; }", "route(text, \"waivers\", res.site); return;", 1), "text/javascript"),
            "no wrong-list guard": ("waivers.js", js.replace("if (!force && res.matched && kind !== \"unknown\"", "if (false && res.matched && kind !== \"unknown\"", 1), "text/javascript"),
        }
        for name, (file, body, kind) in broken.items():
            source = {"roster-paste.js": paste, "waivers.js": js}[file]
            self.assertNotEqual(body, source, f"{name}: the replacement did not apply")
            with self.subTest(name):
                self.assertTrue(run_checks({file: (body, kind)}), f"{name} should fail the checks")


if __name__ == "__main__":
    unittest.main()
