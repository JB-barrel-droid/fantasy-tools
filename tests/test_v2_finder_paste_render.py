"""v2 Find a trade, JEG-853 phase 2: a whole ESPN or Yahoo page pasted in is the default roster input, rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads Find a trade headless. Each of the four real scrubbed
fixtures (tests/fixtures/roster_paste/) goes through the page's own paste box; what the page shows is checked
against roster-paste.js run directly on the engine's rows (the parser has its own node tests), plus floors so a
broken player index is caught. Checks:

  * the paste box is the first input on each side, says the text stays on this device, and the old import methods sit
    behind a closed "Other ways" link; the textarea and every button are at least 44 px tall at 375 px;
  * a team page: "Matched N of M players", the sure matches on the roster with the page's slot (Starter / Bench / IR),
    unmatched lines listed with a one-tap "Search to add" that fills and opens the side's name search, the textarea
    cleared; a player already on the other roster is left there and named;
  * a lesser match (initial form "A. Rodgers", into Your roster) is not added until "Yes, add" is tapped;
  * a matchup page: both teams shown with their names and counts, nothing placed until one "... is mine" tap, then your
    roster is that team and theirs the other, "Found N starters, 2 injured, 2 on bye", the bench-not-on-this-page notice,
    Swap teams exchanges them and Undo is offered;
  * negatives: empty, garbage, a non-ESPN/Yahoo page and a league-wide player list add nothing and say so; too few
    matches (1 of 4) adds nothing until "Add these 1 anyway";
  * no page errors; no sideways scroll at 375; at 320 px in a wide fallback face +3 px the Package size select no
    longer pushes the page sideways (the tap-target sweep found 84 px).

Discrimination: test_guard_fails_on_broken_builds serves finder.js with each of six defects (lesser matches added
silently, the team pick ignored, the bench notice dropped, unmatched lines hidden, the too-few guard off, the count
wrong) and requires each to fail; test_guard_fails_without_the_320_rule serves v2.css without the JEG-853 rule and
requires the sideways scroll back.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_modules_render import _built_dist, _serve

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
CSS = ROOT / "app" / "v2" / "v2.css"
FIXTURES = ROOT / "tests" / "fixtures" / "roster_paste"
FLOORS = {"yahoo-team.txt": 12, "espn-team.txt": 12, "espn-matchup.txt": 16, "yahoo-matchup.txt": 14}
RULE_320 = "#v2Find .v2-ctoolbar label.v2-field { flex-wrap: wrap; max-width: 100%; min-width: 0; }\n#v2Find .v2-ctoolbar select { min-width: 0; max-width: 100%; }\n"


def setUpModule():
    _render_env.ensure_built()


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# The parser's own reading of a page against the engine's rows: what the page must show.
EXPECT = """(text) => {
  const r = window.DDFRosterPaste.parse(text, window.TradeValueCurveControls.getAllRows());
  const sure = ps => ps.filter(p => p.confidence >= 1).map(p => p.name);
  return {matched: r.matched, total: r.total, mode: r.mode, bench: r.benchIncluded, sure: sure(r.players),
    unsure: r.players.filter(p => p.confidence < 1).map(p => p.name), unmatched: r.unmatched.filter(u => u.pos !== 'K' && u.pos !== 'DEF').map(u => u.line), slots: r.players.map(p => p.slot),
    players: r.players.map(p => ({name: p.name, slot: p.slot, sure: p.confidence >= 1})),
    teams: (r.teams || []).map(t => ({name: t.teamName, sure: sure(t.players), unmatched: t.unmatched.length}))};
}"""
NAMES = "(id) => [...document.querySelectorAll(`#${id} li`)].filter(li => !li.textContent.includes('Not evaluated')).map(li => li.querySelector('b').textContent)"
CHIPS = "(id) => [...document.querySelectorAll(`#${id} .v2-find-slot`)].map(c => c.textContent)"
OVER = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
SHORT = """(sel) => [...document.querySelectorAll(sel)].filter(e => !e.closest('[hidden]') && e.getBoundingClientRect().width > 0)
  .filter(e => e.getBoundingClientRect().height < 43.5).map(e => (e.id || e.className) + ' ' + Math.round(e.getBoundingClientRect().height))"""
PLUS = "(n) => { for (const e of document.querySelectorAll('body *')) { const fs = parseFloat(getComputedStyle(e).fontSize); e.style.fontSize = (fs + n) + 'px'; } }"
FAMILIES = ("DejaVu Sans", "Verdana")
HAS_FACE = """(family) => { const c = document.createElement('canvas').getContext('2d'); const t = 'Wide fallback face WMwmi 0123';
  c.font = "40px monospace"; const a = c.measureText(t).width; c.font = `40px '${family}', monospace`; return c.measureText(t).width !== a; }"""


PASTE_EVENT = """([id, text]) => { const dt = new DataTransfer(); dt.setData('text', text);
  document.getElementById(id).dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }"""


def paste(page, side, text, via_event=False):
    """Text into the side's one box (JEG-988): by a real paste event, or typed in whole (the input event)."""
    if via_event:
        page.evaluate(PASTE_EVENT, [f"v2Find{side}Search", text])
    else:
        page.fill(f"#v2Find{side}Search", text)
    page.wait_for_timeout(300)
    return page.text_content(f"#v2Find{side}PasteResult")


def names(page, side):
    """The evaluated players on a side (a kept defense or kicker, marked "Not evaluated" since JEG-988, is not listed)."""
    return page.evaluate(NAMES, f"v2Find{side}Players")


def check(page, tag, width) -> list[str]:
    errors = []
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.wait_for_timeout(300)
    say = lambda what: errors.append(tag + what)
    overflow = lambda step: (width <= 390 and page.evaluate(OVER) > 0 and say(f"horizontal overflow after {step}"))

    # 1. JEG-988: one box per side (no separate paste box); the old methods sit behind a closed link.
    for side in ("Mine", "Theirs"):
        boxes = page.evaluate("(s) => [...document.querySelectorAll(`#v2Find${s} textarea, #v2Find${s} input[type=search], #v2Find${s} input[type=text]`)].filter(e => !e.closest('details')).map(e => e.id)", side)
        if boxes != [f"v2Find{side}Search"]:
            say(f"{side}: want exactly one add-players box, found {boxes}")
        # JEG-1130 (approved PMM launch copy, Jeremy 2026-10-26): storage copy says "on this device", never "in this browser".
        if "stays on this device" not in (page.text_content(f"#v2Find{side}PasteHelp") or ""):
            say(f"{side}: the paste box does not say the text stays on this device")
        if page.evaluate("(s) => document.querySelector(`#v2Find${s} .v2-find-import`).open", side):
            say(f"{side}: the other import methods are open by default")
        if "Other ways" not in page.text_content(f"#v2Find{side} .v2-find-import summary"):
            say(f"{side}: no 'Other ways' link to the old methods")
    short = page.evaluate(SHORT, "#v2Find .v2-find-search-wrap textarea, #v2Find .v2-find-clear")
    if short:
        say(f"paste controls under 44px: {short}")

    # 2. Negatives on Their roster: nothing added, said plainly.
    #    JEG-1010: extraction now finds real player names in any text, so negatives must contain NO real names.
    for label, text in (("garbage", "asdf qwerty\n1234\n!!!\n"),
                        ("nav-only page", "Sleeper\nMy Team\nHome\nSettings\nLeague\nStandings\nPlayers\n"),
                        ("abbreviations only", "Players\nBuf - QB\nBal - QB\nAtl - RB\nCin - WR\nNot A Player\nAnother Fake\n")):
        status = paste(page, "Theirs", text)
        if names(page, "Theirs"):
            say(f"{label}: players were added: {names(page, 'Theirs')}")
        if "No players recognised" not in status or "Nothing was added" not in status:
            say(f"{label}: result reads {status!r}, want 'No players recognised' and 'Nothing was added'")
    # 2b. JEG-1010: a Sleeper-like page with real player names IS now matched (extraction), not rejected.
    sleeper_text = "Sleeper\nMy Team\nQB Josh Allen BUF\nRB Bijan Robinson ATL\nSettings\nLeague\n"
    status = paste(page, "Theirs", sleeper_text)
    if not names(page, "Theirs"):
        say("JEG-1010 extraction: a Sleeper-like page with real names should find players")
    if "Found" not in status or "player" not in status:
        say(f"JEG-1010 extraction: result reads {status[:120]!r}, want 'Found N players'")
    # Clear Theirs before the next step
    clear_btn = page.locator("#v2FindTheirsClear")
    if clear_btn.count() and clear_btn.is_visible():
        clear_btn.click()
        page.wait_for_timeout(200)
    # Too few: one real player among four slots adds nothing until asked.
    # A QB the fixtures never mention, so later steps are not confused by him.
    qb = page.evaluate("(texts) => { const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.pos === 'QB' && r.team); const n = new Map(); rows.forEach(r => n.set(r.name, (n.get(r.name) || 0) + 1)); const r = rows.find(r => n.get(r.name) === 1 && !texts.some(t => t.includes(r.name))); return {name: r.name, team: r.team}; }",
                       [fixture(n) for n in FLOORS])
    team = qb["team"][0] + qb["team"][1:].lower()
    few = f"Yahoo Sports Fantasy Football\nQB\n{qb['name']}Player Note\n{team} - QB\nRB\nNot A Player\n{team} - RB\nWR\nAnother Fake\n{team} - WR\nTE\nFake Three\n{team} - TE\n"
    status = paste(page, "Theirs", few)
    if names(page, "Theirs"):
        say(f"too few (1 of 4): players were added without asking: {names(page, 'Theirs')}")
    if "Matched 1 of 4" not in status or "too few" not in status:
        say(f"too few: result reads {status!r}")
    if page.locator("#v2FindTheirsPasteAnyway").count() != 1:
        say("too few: no 'Add these 1 anyway' button")
    else:
        page.click("#v2FindTheirsPasteAnyway")
        page.wait_for_timeout(200)
        if names(page, "Theirs") != [qb["name"]]:
            say(f"'Add anyway' put {names(page, 'Theirs')} on their roster, want [{qb['name']}]")
    overflow("negatives")

    # 3. A lesser match waits for a tap: Yahoo team page with Rodgers in initial form, into Your roster (replaces it).
    lesser = fixture("yahoo-team.txt").replace("Aaron RodgersPlayer Note\nPit - QB", "A. RodgersPlayer Note\nPit - QB")
    want = page.evaluate(EXPECT, lesser)
    if want["unsure"] != ["Aaron Rodgers"]:
        say(f"the lesser-match fixture does not parse as expected: unsure {want['unsure']}")
    status = paste(page, "Mine", lesser)
    if "Aaron Rodgers" in names(page, "Mine"):
        say("a lesser match (A. Rodgers) was added without a tap")
    if sorted(names(page, "Mine")) != sorted(want["sure"]):
        say(f"lesser-match paste put {sorted(names(page, 'Mine'))} on your roster, want the sure matches {sorted(want['sure'])}")
    if "Check 1 match" not in status or "not added until you say so" not in status:
        say(f"the lesser match is not called out: {status!r}")
    unsure = page.locator("#v2FindMinePasteResult .v2-find-unsure")
    if unsure.count() != 1 or "Aaron Rodgers" not in unsure.first.text_content():
        say("no confirm row for Aaron Rodgers")
    else:
        unsure.first.locator(".v2-find-confirm").click()
        page.wait_for_timeout(200)
        if "Aaron Rodgers" not in names(page, "Mine"):
            say("'Yes, add' did not add Aaron Rodgers")
    if page.input_value("#v2FindMineSearch"):
        say("the box was not cleared after a used paste")

    # 4. Team pages through the paste event: counts, slots, unmatched with search-to-add, the player on the other roster.
    for name, side, via_event in (("yahoo-team.txt", "Mine", True), ("espn-team.txt", "Theirs", False)):
        text = fixture(name)
        if name == "yahoo-team.txt":   # one player no list has, so the unmatched rows are still exercised (the fixture's own unmatched are a kicker and a defense, kept since JEG-988)
            text = text.replace("BN\nJosh AllenVideo", "BN\nZed NotaplayerPlayer Note\nChi - WR\nBN\nJosh AllenVideo", 1)
        want = page.evaluate(EXPECT, text)
        if name == "yahoo-team.txt" and not want["unmatched"]:
            say("the yahoo fixture with an invented player has no unmatched line")
        if want["matched"] < FLOORS[name]:
            say(f"{name}: parser matched only {want['matched']} against the engine's rows (floor {FLOORS[name]})")
        before_other = set(names(page, "Theirs" if side == "Mine" else "Mine"))
        status = paste(page, side, text, via_event)
        if f"Matched {want['matched']} of {want['total']} players" not in status:
            say(f"{name}: result reads {status[:80]!r}, want 'Matched {want['matched']} of {want['total']} players'")
        expect_on = sorted(n for n in want["sure"] if n not in before_other)
        if sorted(names(page, side)) != expect_on:
            say(f"{name}: {side} roster is {sorted(names(page, side))}, want {expect_on}")
        left_out = [n for n in want["sure"] if n in before_other]
        for n in left_out:
            if n not in status or "other roster" not in status:
                say(f"{name}: {n} is on the other roster but the result does not say so")
        chips = page.evaluate(CHIPS, f"v2Find{side}PasteResult")
        shown = [p["slot"] for p in want["players"] if p["sure"] and p["name"] not in before_other]   # rows the panel lists
        want_bench = sum(1 for s in shown if s in ("BN", "Bench"))
        if chips.count("Bench") != want_bench or chips.count("IR") != shown.count("IR"):
            say(f"{name}: slot chips {chips} do not show {want_bench} bench and {shown.count('IR')} IR")
        if not chips or chips.count("Starter") < 5:
            say(f"{name}: starters are not marked: {chips}")
        items = page.locator(f"#v2Find{side}PasteResult .v2-find-unmatched li")
        if items.count() != len(want["unmatched"]):
            say(f"{name}: {items.count()} unmatched rows shown, parser found {len(want['unmatched'])}")
        if want["unmatched"] and f"Not matched ({len(want['unmatched'])})" not in status:
            say(f"{name}: the unmatched count is not stated")
        if want["unmatched"] and items.count():
            items.first.locator(".v2-find-search-add").click()
            page.wait_for_timeout(300)
            query = page.input_value(f"#v2Find{side}Search")
            if not query or query not in want["unmatched"][0].replace("Player Note", "").replace("D/ST", "").strip():
                say(f"{name}: search-to-add filled {query!r} from {want['unmatched'][0]!r}")
            if page.evaluate("(id) => document.getElementById(id).hidden", f"v2Find{side}Results"):
                say(f"{name}: search-to-add did not open the name search")
            if page.evaluate("() => document.activeElement && document.activeElement.id") != f"v2Find{side}Search":
                say(f"{name}: search-to-add did not focus the name search")
            page.fill(f"#v2Find{side}Search", "")
        overflow(name)
    short = page.evaluate(SHORT, "#v2Find .v2-find-paste-result button")
    if short:
        say(f"result buttons under 44px: {short}")

    # 4b. JEG-1010: an unknown-site paste uses extraction, shows "Found N players", and populates the roster.
    fantrax_text = (ROOT / "tests" / "fixtures" / "noisy_paste" / "fantrax-team.txt").read_text(encoding="utf-8")
    # Clear Mine by pasting garbage first, then paste Fantrax
    paste(page, "Mine", "clear\nclear")
    page.wait_for_timeout(200)
    status = paste(page, "Mine", fantrax_text)
    if "Found" not in status or "player" not in status:
        say(f"extraction: result reads {status[:120]!r}, want 'Found N players'")
    mine_after = names(page, "Mine")
    if not mine_after or len(mine_after) < 5:
        say(f"extraction: only {len(mine_after)} players on the roster after Fantrax paste, want at least 5")
    if "ignored" in status:
        # The ignored-lines disclosure should exist
        ignored_details = page.locator("#v2FindMinePasteResult .v2-find-ignored")
        if ignored_details.count() < 1:
            say("extraction: 'ignored' mentioned in status but no ignored-lines disclosure")
        elif not ignored_details.first.locator("summary").count():
            say("extraction: ignored-lines disclosure has no summary")
    overflow("fantrax extraction")

    # 5. A matchup page fills both rosters after one tap; the page's bench notice; Swap teams fixes a wrong pick.
    text = fixture("espn-matchup.txt")
    want = page.evaluate(EXPECT, text)
    if want["mode"] != "matchup" or want["matched"] < FLOORS["espn-matchup.txt"]:
        say(f"espn-matchup: parser gives mode {want['mode']} with {want['matched']} matched")
    mine_before, theirs_before = names(page, "Mine"), names(page, "Theirs")
    status = paste(page, "Mine", text)
    if names(page, "Mine") != mine_before or names(page, "Theirs") != theirs_before:
        say("a matchup paste changed the rosters before a team was picked")
    if "matchup page with two teams" not in status or "Which team is yours?" not in status:
        say(f"matchup: result reads {status[:120]!r}")
    for i, t in enumerate(want["teams"]):
        button = page.locator(f"#v2FindMinePickTeam{i + 1}")
        if button.count() != 1 or button.text_content() != f"{t['name']} is mine":
            say(f"matchup: no '{t['name']} is mine' button")
    if "2 injured, 2 on bye" not in status:
        say(f"matchup: what ESPN listed (injured, bye) is not said: {status[:300]!r}")
    if page.locator("#v2FindMinePasteResult .v2-find-bench-note").count() != 1 or "Bench players are not on this page" not in status or "Show Bench" not in status:
        say("matchup: the bench-not-on-this-page notice is missing")
    page.click("#v2FindMinePickTeam2")
    page.wait_for_timeout(300)
    status = page.text_content("#v2FindMinePasteResult")
    if sorted(names(page, "Mine")) != sorted(want["teams"][1]["sure"]) or sorted(names(page, "Theirs")) != sorted(want["teams"][0]["sure"]):
        say(f"after picking team 2: mine {names(page, 'Mine')}, theirs {names(page, 'Theirs')}; want mine {want['teams'][1]['sure']}")
    if f"Your roster: {want['teams'][1]['name']}" not in status or "Swap teams" not in status:
        say(f"after the pick the result does not say which team is which: {status[:200]!r}")
    chips = page.evaluate(CHIPS, "v2FindMinePasteResult")
    if chips.count("Injured") != want["slots"].count("Injured") or chips.count("Bye") != want["slots"].count("Bye"):
        say(f"matchup chips {chips} do not show {want['slots'].count('Injured')} injured and {want['slots'].count('Bye')} bye")
    if page.locator("#v2FindMinePasteResult .v2-find-bench-note").count() != 1:
        say("after the pick the bench notice is gone")
    if page.evaluate("() => document.getElementById('v2FindUndo').disabled"):
        say("Undo is not offered after a matchup fill")
    page.click("#v2FindSwap")
    page.wait_for_timeout(200)
    if sorted(names(page, "Mine")) != sorted(want["teams"][0]["sure"]):
        say("Swap teams after a matchup fill did not exchange the rosters")
    overflow("espn matchup")
    text = fixture("yahoo-matchup.txt")
    want = page.evaluate(EXPECT, text)
    if want["mode"] != "matchup" or want["matched"] < FLOORS["yahoo-matchup.txt"]:
        say(f"yahoo-matchup: parser gives mode {want['mode']} with {want['matched']} matched")
    status = paste(page, "Theirs", text)
    for i, t in enumerate(want["teams"]):
        if page.locator(f"#v2FindTheirsPickTeam{i + 1}").count() != 1 or t["name"] not in status:
            say(f"yahoo-matchup: team {t['name']} is not offered")
    if "Bench players are not on this page" not in status:
        say("yahoo-matchup: the bench notice is missing")
    page.click("#v2FindTheirsPickTeam1")
    page.wait_for_timeout(300)
    if sorted(names(page, "Mine")) != sorted(want["teams"][0]["sure"]) or sorted(names(page, "Theirs")) != sorted(want["teams"][1]["sure"]):
        say(f"yahoo-matchup pick 1: mine {names(page, 'Mine')}, theirs {names(page, 'Theirs')}")
    overflow("yahoo matchup")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (375, 812))) -> list[str]:
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
            for width, height in viewports:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


def overflow_320(css: str | None = None) -> int | None:
    """Sideways scroll on Find a trade at 320 px in a wide fallback face with every font 3 px larger; None without a face."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            probe = browser.new_page()
            family = next((f for f in FAMILIES if probe.evaluate(HAS_FACE, f)), None)
            probe.close()
            if family is None:
                return None
            page = browser.new_page(viewport={"width": 320, "height": 812})
            page.add_init_script("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                                 f"s.textContent=\"*{{font-family:'{family}',sans-serif !important}}\";document.head.appendChild(s)}})")
            if css is not None:
                page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
            page.goto(base + "#find-trade", wait_until="networkidle")
            page.wait_for_function("() => document.getElementById('v2FindSize')", timeout=60000)
            page.evaluate(PLUS, 3)
            page.wait_for_timeout(500)
            return page.evaluate(OVER)
        finally:
            browser.close()


class FinderPasteRenderTest(unittest.TestCase):
    def test_paste_is_the_default_input(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "lesser matches added silently": ("if (!(p.confidence >= 1)) { unsure.push({...p, row}); return; }", "if (false) { return; }"),
            "team pick ignored": ('const sides = [mineIdx === 0 ? "mine" : "theirs", mineIdx === 0 ? "theirs" : "mine"];', 'const sides = ["mine", "theirs"];'),
            "bench notice dropped": ("res.benchIncluded === false\n", "false\n"),
            "unmatched lines hidden": ("const unmatchedBlock = (side, unmatched) => (unmatched.length ? [", "const unmatchedBlock = (side, unmatched) => (false ? ["),
            "too-few guard off": ("if (res.matched < MIN_MATCHED || res.matched / res.total < MIN_SHARE) {", "if (false) {"),
            "count wrong": ("text: `Matched ${res.matched} of ${res.total} players${siteWord(res.site)}.`});", "text: `Matched ${res.total} of ${res.total} players${siteWord(res.site)}.`});"),
            "extraction disabled": ('if (res.mode === "extract") {', 'if (false && res.mode === "extract") {'),
        }
        for name, (old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertIn(old, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks({"finder.js": js.replace(old, new, 1)}, viewports=((1440, 900),)), [], f"not caught: {name}")

    def test_320_wide_face_no_sideways_scroll(self):
        over = overflow_320()
        if over is None:
            raise _render_env.unavailable("no wide fallback face (DejaVu Sans or Verdana) on this machine")
        self.assertEqual(over, 0, f"320 +3px find-trade scrolls sideways by {over}px")

    def test_guard_fails_without_the_320_rule(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(RULE_320, css, "stale mutation anchor")
        over = overflow_320(css.replace(RULE_320, "\n", 1))
        if over is None:
            raise _render_env.unavailable("no wide fallback face (DejaVu Sans or Verdana) on this machine")
        self.assertGreater(over, 0, "the old CSS no longer scrolls sideways, so the check proves nothing")


if __name__ == "__main__":
    unittest.main()
