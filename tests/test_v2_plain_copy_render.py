"""v2 public copy, rendered: plain names, no abbreviations (JEG-812, owner rules).

Owner rules (Jeremy): no title abbreviations, no Vegas, no vanity stats. Live QA (2026-10-22) found "USAT",
"FP" and "Wk 6" on Trade targets and Player values, a "VORP vs waivers" panel title, and a Research page
that only said "No posts are published yet."

Loads the built page headless at 1440 and 390 px, visits every tab (opening a few Trade targets rows), and
requires: none of USAT / FP / FC / CBS ROS / Wk / Vegas / "median" in the visible text, both value-over-waiver panel
titles in plain words, and a Research page that says what is there instead of promising dates.

JEG-861 (2026-10-22): every value page title carries the same "NFL Week N · as of Mon D" line Player values
shows (read from the data week and the fixture's built_at, never hard-coded), the Trade targets market column
says "middle of N charts" instead of "median of N", and the Deal read sentences do not overclaim what the other
manager will do ("easy for them to accept", "will likely accept", "and is not").
JEG-888 (2026-10-22): the Trade targets intro counts the charts the view compares ("We check 3 trade charts", read
from window.TradeValueV2.targets().used), and the Compare verdict card has no headline lines. (JEG-1112, 2026-10-26, Jeremy's option D: the
"Should you propose or accept?" / "Will they accept?" lines were removed from it, so the JEG-888 / JEG-895 / JEG-863 copy
checks that read them went too; the Deal read overclaim check stays.)
Discrimination: test_guard_fails_on_broken_builds serves v2.js with the old USAT label, with "Wk" back, with
"median of" back, with the page stamp not rendered and with "NFL" dropped from it, trade.js with the old
overclaiming sentence, and the shell with the old panel title and the old Research line, and requires failures.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_deal_read_render import _served, V2_JS

TABS = ("#trade-targets", "#player-values", "#risers-fallers", "#compare-trade", "#find-trade", "#writing/how-values", "#writing/research", "#values-auditing")
BANNED = re.compile(r"\b(USAT|FP|FC|Wk|median)\b|CBS ROS|\bvegas\b", re.I)
STAMP = re.compile(r"NFL Week \d+ · as of [A-Z][a-z]{2} \d{1,2}")
VALUE_TABS = ("#trade-targets", "#player-values", "#risers-fallers", "#compare-trade", "#find-trade", "#writing/how-values", "#values-auditing")
OVERCLAIMS = ("easy for them to accept", "will likely accept", "and is not.")
TRADE_JS = V2_JS.with_name("trade.js")
PROMISES = re.compile(r"\b(soon|coming|will be published|next week|tomorrow|\d{4}-\d{2}-\d{2})\b", re.I)
READ = "() => document.body.innerText"
TITLES = "() => ['v2VorpTitle', 'v2CVorpTitle'].map(id => document.getElementById(id).textContent.trim())"
RESEARCH = "() => document.getElementById('v2Research').innerText"
# The visible page title block: the first shown <main>'s .v2-title (Compare nests it in .v2-chead).
TITLE = "() => { const m = [...document.querySelectorAll('main.v2-main')].find(n => !n.hidden); const t = m && m.querySelector('.v2-title'); return t ? t.innerText : ''; }"
DEAL_TEXTS = "() => Object.values(window.TradeValueTrade.DEAL_READS).map(c => c.text)"
INTRO = "() => document.getElementById('v2TIntro').textContent"
USED = "() => window.TradeValueV2.targets().used"
HEADS = "() => Boolean(document.getElementById('v2CHeads') || document.querySelector('#v2CVerdict .v2-chead'))"


def bad_words(text: str) -> list[str]:
    return sorted({m.group(0) for m in BANNED.finditer(text)})


def run_checks(v2_patch=None, shell_patch=None, trade_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if v2_patch:
        assert v2_patch[0] in js, f"patch anchor missing: {v2_patch[0]!r}"
        js = js.replace(v2_patch[0], v2_patch[1])
    trade_js = TRADE_JS.read_text(encoding="utf-8")
    if trade_patch:
        assert trade_patch[0] in trade_js, f"trade patch anchor missing: {trade_patch[0]!r}"
        trade_js = trade_js.replace(trade_patch[0], trade_patch[1])
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 1000), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_patch:
                    page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
                if trade_patch:
                    page.route("**/v2/trade.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=trade_js))
                if shell_patch:
                    def serve_shell(route, *_):
                        response = route.fetch()
                        body = response.text()
                        assert shell_patch[0] in body, f"shell patch anchor missing: {shell_patch[0]!r}"
                        route.fulfill(response=response, body=body.replace(shell_patch[0], shell_patch[1]))
                    page.route("**/v2/", serve_shell)
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
                for tab in TABS:
                    page.evaluate("h => { location.hash = h; }", tab)
                    page.wait_for_timeout(500)
                    if tab == "#trade-targets":
                        for _ in range(3):
                            toggle = page.locator("[data-expand][aria-expanded=false]").first
                            if toggle.count() and toggle.is_visible():
                                toggle.click()
                    found = bad_words(page.evaluate(READ))
                    if found:
                        errors.append(f"[{width}px {tab}] banned words in visible text: {found}")
                    if tab in VALUE_TABS:
                        title = page.evaluate(TITLE)
                        if not STAMP.search(title):
                            errors.append(f"[{width}px {tab}] title lacks the 'NFL Week N · as of Mon D' line: {title!r}")
                    if tab == "#trade-targets":
                        # JEG-888: the intro counts the charts this view compares, never a hard-coded "four publishers".
                        intro, used = page.evaluate(INTRO), page.evaluate(USED)
                        if "publisher" in intro:
                            errors.append(f"[{width}px targets] intro names publishers instead of the compared count: {intro!r}")
                        want = f"We check {len(used)} trade chart{'' if len(used) == 1 else 's'} against"
                        if len(used) and not intro.startswith(want):
                            errors.append(f"[{width}px targets] intro count is not the compared set ({len(used)} charts): {intro!r}")
                    if tab == "#compare-trade":
                        # JEG-1112: the propose / accept headline lines are gone from the verdict card.
                        if page.evaluate(HEADS):
                            errors.append(f"[{width}px headline] the verdict card still has the propose / accept lines")
                        for text in page.evaluate(DEAL_TEXTS):
                            hits = [phrase for phrase in OVERCLAIMS if phrase in text]
                            if hits:
                                errors.append(f"[{width}px deal read] overclaims {hits}: {text!r}")
                    if tab == "#writing/research":
                        text = page.evaluate(RESEARCH)
                        if "No posts are published yet" in text:
                            errors.append(f"[{width}px research] still says 'No posts are published yet.'")
                        elif "Nothing is published here yet" not in text:
                            errors.append(f"[{width}px research] empty-state line missing: {text[:200]!r}")
                        if "How values work" not in text or "Manifesto" not in text:
                            errors.append(f"[{width}px research] empty state should point to How values work and the Manifesto")
                        if PROMISES.search(text):
                            errors.append(f"[{width}px research] promises a date or a time: {PROMISES.search(text).group(0)!r}")
                titles = page.evaluate(TITLES)
                if any("VORP" in title for title in titles):
                    errors.append(f"[{width}px] panel titles still say VORP: {titles}")
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "USAT label back": {"v2_patch": ('{label: "USA Today", color', '{label: "USAT", color')},
    "Wk back": {"v2_patch": ("`Week ${item.week}`", "`Wk ${item.week}`")},
    "old panel title": {"shell_patch": ('<h2 id="v2VorpTitle">Value above waivers</h2>', '<h2 id="v2VorpTitle">VORP vs waivers</h2>')},
    "old research line": {"shell_patch": ("Nothing is published here yet.", "No posts are published yet.")},
    "median back": {"v2_patch": ("`middle of ${m.count} chart${m.count === 1 ? \"\" : \"s\"}", "`median of ${m.count}")},
    "page stamp not rendered": {"v2_patch": ("    renderPageStamps();\n    const s = view.state;", "    const s = view.state;")},
    "NFL dropped from the stamp": {"v2_patch": ("`NFL Week ${view.refWeek}`", "`Week ${view.refWeek}`")},
    "deal read overclaims": {"trade_patch": ("so the other manager has little reason to refuse.", "so it is easy for them to accept.")},
    # JEG-888.
    "four publishers back": {"v2_patch": ("`We check ${introCharts} against", "`We check four publishers' trade charts against")},
    # 7 is more charts than exist, so it differs from the compared count whether the fixture holds CBS (3 charts) or not (4).
    "intro count hard-coded": {"v2_patch": ("const introCount = targetsView.used.length;", "const introCount = 7;")},
}


class PlainCopyRenderTest(unittest.TestCase):
    def test_plain_copy(self):
        _render_env.ensure_built()
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        _render_env.ensure_built()
        for name, kwargs in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(**kwargs), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
