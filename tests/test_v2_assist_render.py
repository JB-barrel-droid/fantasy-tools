"""JEG-1026: the site side of the LLM <-> site round trip, in headless Chromium against the built dist/.

  * Copy link (JEG-1101) puts the current view's plain site link on the clipboard, nothing else (no prompt, no ddf-state
    block); opening that link in a fresh page (another league) reproduces the league and the trade on the right tab;
    a link an assistant wrote by hand (names only, one that matches nobody, a sources list) puts both Find a trade rosters
    in, lists the unmatched name and the advisory field under "Ignored";
  * deep links open the right tab with the rosters / the target / the team count: #find-trade?mine=..&theirs=..,
    #trade-targets?target=.., names written n:<twice-encoded>, and a `view` that names another route;
  * the footer line "Using ChatGPT or Claude? Connect the tool" is in the served HTML (no JavaScript) and on every tab;
  * the ChatGPT/Claude Copy / Paste buttons and the paste box are gone (Jeremy, 2026-10-26), and Copy link has its line;
  * no page errors and no horizontal overflow at 390px, with a report showing.

Discrimination: test_guard_fails_on_broken_builds serves ddf-assist.js / v2.js with a part removed and requires the checks to fail.
"""
from __future__ import annotations

import functools
import json
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_share_render import _built_dist, _serve  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
ASSIST_JS = ROOT / "app" / "v2" / "ddf-assist.js"
TABS = ["#trade-targets", "#player-values", "#risers-fallers", "#compare-trade", "#find-trade", "#waivers", "#value-overrides",
        "#values-auditing/health-check", "#writing/manifesto", "#writing/research"]
LINE = "Using ChatGPT or Claude?"
KEYS = """(names) => { const rows = window.TradeValueCurveControls.getAllRows();
  return names.map(n => String((rows.find(r => r.name === n) || {}).player_key)); }"""
STATE = """() => ({hash: location.hash,
  teams: window.TradeValueCurveControls.getState().teams, scoring: window.TradeValueCurveControls.getState().scoring,
  give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(li => li.dataset.playerKey),
  get: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(li => li.dataset.playerKey),
  mine: window.TradeValueFinder.ui.getMine().map(p => p.key), theirs: window.TradeValueFinder.ui.getTheirs().map(p => p.key),
  search: document.getElementById('v2TSearch').value,
  visible: ['v2Targets', 'v2Compare', 'v2FindTrade'].filter(id => !document.getElementById(id).hidden),
  note: document.getElementById('v2AssistNote').hidden ? '' : document.getElementById('v2AssistNote').textContent})"""


def run_checks(assist_js=None, v2_js=None) -> list[str]:
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
        pages = []
        contexts = []

        def open_page(url, width=1440):
            # JEG-1089: one browser context (own localStorage) per page, as every real visitor has. Pages sharing a context share the
            # saved "my roster" (workspace.js), and a still-open earlier page saving ~1s late sends the new page an `other-tab` event
            # that replaces the rosters its link just set (finder.js pullMine): the name-only link failed 3 runs in 4 that way.
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base.split("/v2/")[0])
            contexts.append(context)
            page = context.new_page()
            page.set_viewport_size({"width": width, "height": 1000})
            page.errors = []
            page.set_default_timeout(10000)
            page.on("pageerror", lambda e: page.errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if assist_js is not None:
                page.route("**/v2/ddf-assist.js*", functools.partial(_serve, assist_js))
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.getElementById('v2State').hidden", timeout=30000)
            page.wait_for_timeout(200)
            pages.append(page)
            return page

        try:
            # 1. The footer line is in the served HTML, so an assistant that runs no JavaScript reads it.
            raw = urllib.request.urlopen(base).read().decode("utf-8")
            if LINE not in raw or "Connect the tool" not in raw or "/connect/" not in raw:
                errors.append("footer line missing from the served page HTML")

            # 2. Copy link -> open round trip between two leagues.
            probe = open_page(base + "#compare-trade")
            give, get = probe.evaluate(KEYS, ["Jahmyr Gibbs", "Puka Nacua"]), probe.evaluate(KEYS, ["Ja'Marr Chase"])
            sender = open_page(base + f"#compare-trade?give={give[0]},{give[1]}&get={get[0]}&scoring=half_ppr&teams=10&roster=QB1.RB2.WR2.TE1.FLEX2.SF1.BN5")
            sent = sender.evaluate(STATE)
            if (sent["teams"], sent["scoring"], sent["give"], sent["get"]) != (10, "half_ppr", give, get):
                errors.append(f"sender page did not open the link: {sent}")
            sender.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
            sender.click("#v2AssistCopy")
            sender.wait_for_timeout(300)
            text = sender.evaluate("() => navigator.clipboard.readText()")
            # Jeremy, 2026-10-26: the site link is the hand-off, not a code. One line, the page's own URL, no block, no prompt.
            if "\n" in text.strip() or "```" in text or not text.startswith(sender.evaluate("() => location.href.split('#')[0]") + "#compare-trade?"):
                errors.append(f"clipboard is not just the site link: {text[:200]!r}")
            st = sender.evaluate("(t) => window.DDFState.decodeQuery(t.split('#')[1].split('?')[1])", text).get("state") or {}
            if (st.get("league") or {}).get("teams") != 10 or [p["key"] for p in (st.get("work") or {}).get("give", [])] != give:
                errors.append(f"copied link lost the league or the trade: {json.dumps(st)[:300]}")
            if "✓ Copied the link" not in sender.evaluate("() => document.getElementById('v2AssistNote').textContent"):
                errors.append("no copy confirmation shown")

            receiver = open_page(base + "#trade-targets")
            before = receiver.evaluate(STATE)
            if before["teams"] == 10 and before["scoring"] == "half_ppr":
                errors.append("receiver already in the sender's league; the round trip proves nothing")
            receiver = open_page(text)
            got = receiver.evaluate(STATE)
            if (got["teams"], got["scoring"], got["give"], got["get"]) != (10, "half_ppr", give, get):
                errors.append(f"the copied link did not reproduce the sender's league and trade: {got}")
            if not got["hash"].startswith("#compare-trade") or got["visible"] != ["v2Compare"]:
                errors.append(f"the copied link did not open Compare a trade: {got['hash']!r} {got['visible']}")

            # 3. A link written by hand by an assistant: names only, one that matches nobody, an advisory sources list.
            hand = open_page(base + "#find-trade?view=finder&mine=n:Jahmyr%2520Gibbs,n:Not%2520A%2520Real%2520Player"
                             "&theirs=n:Ja'Marr%2520Chase,n:Puka%2520Nacua&scoring=ppr&teams=12&src=fantasycalc")
            hand_got = hand.evaluate(STATE)
            mine_k, theirs_k = hand.evaluate(KEYS, ["Jahmyr Gibbs"]), hand.evaluate(KEYS, ["Ja'Marr Chase", "Puka Nacua"])
            if (hand_got["mine"], hand_got["theirs"]) != (mine_k, theirs_k) or hand_got["visible"] != ["v2FindTrade"] or hand_got["teams"] != 12:
                errors.append(f"hand-written link not applied to Find a trade: {hand_got}")
            note = hand_got["note"]
            if "Ignored." not in note or "Not A Real Player (not in the values)" not in note or "advisory" not in note:
                errors.append(f"report does not name what was ignored: {note!r}")

            # 4. Deep links.
            mine_keys = probe.evaluate(KEYS, ["Jahmyr Gibbs", "Puka Nacua"])
            link = open_page(base + f"#find-trade?mine={','.join(mine_keys)}&theirs={get[0]}&scoring=ppr&teams=14")
            link_got = link.evaluate(STATE)
            if (link_got["mine"], link_got["theirs"], link_got["teams"], link_got["visible"]) != (mine_keys, get, 14, ["v2FindTrade"]):
                errors.append(f"find-trade link: {link_got}")
            if link.evaluate("() => document.querySelectorAll('#v2FindMine .v2-find-row').length") != 2:
                errors.append("find-trade link rosters not drawn on the page")
            # Copy writes what the page reads: the copied link opens the same rosters.
            link.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
            link.click("#v2AssistCopy")
            link.wait_for_timeout(300)
            url = link.evaluate("() => navigator.clipboard.readText()").strip()
            again = open_page(url)
            again_got = again.evaluate(STATE)
            if (again_got["mine"], again_got["theirs"], again_got["teams"]) != (mine_keys, get, 14):
                errors.append(f"the link written by Copy did not reopen the rosters: {url} -> {again_got}")

            named = open_page(base + "#find-trade?mine=n:Jahmyr%2520Gibbs,n:Nobody%2520Atall&theirs=n:Puka%2520Nacua")
            named_got = named.evaluate(STATE)
            if (named_got["mine"], named_got["theirs"]) != (mine_keys[:1], mine_keys[1:]) or "Nobody Atall" not in named_got["note"]:
                errors.append(f"name-only find-trade link: {named_got}")
            target = open_page(base + f"#trade-targets?target={get[0]}&scoring=half_ppr&teams=8")
            target_got = target.evaluate(STATE)
            if target_got["search"] != "Ja'Marr Chase" or target_got["visible"] != ["v2Targets"] or target_got["teams"] != 8:
                errors.append(f"trade-targets link: {target_got}")
            rerouted = open_page(base + f"#compare-trade?view=finder&mine={mine_keys[0]}&theirs={get[0]}")
            rerouted_got = rerouted.evaluate(STATE)
            if not rerouted_got["hash"].startswith("#find-trade") or rerouted_got["visible"] != ["v2FindTrade"] or rerouted_got["mine"] != mine_keys[:1]:
                errors.append(f"view=finder link: {rerouted_got}")
            # 5. Footer on every tab, and no overflow at 390px with a report showing.
            narrow = open_page(base + "#trade-targets", width=390)
            for tab in TABS:
                narrow.evaluate("(h) => { location.hash = h; }", tab)
                narrow.wait_for_timeout(250)
                seen = narrow.evaluate("""() => { const f = document.getElementById('v2Assist'); const r = f.getBoundingClientRect();
                  return {shown: r.height > 0 && getComputedStyle(f).display !== 'none', text: f.textContent.includes('Using ChatGPT or Claude?')}; }""")
                if not (seen["shown"] and seen["text"]):
                    errors.append(f"footer not shown on {tab}: {seen}")
                # Copy link sits in the league strip (Jeremy, 2026-10-25) on every tab that has the strip: whole, on screen,
                # wrapped or stacked rather than clipped, and the page no wider than the phone. Since JEG-1119 (Jeremy's
                # scope, 2026-10-26) it sits in the strip's ⋯ menu, so the menu is opened to measure it.
                strip = narrow.evaluate("""() => { const w = document.documentElement.clientWidth;
                  const sum = document.getElementById('v2ContextSummary');   // JEG-1134: on a phone the row opens first
                  if (sum && sum.offsetParent && sum.getAttribute('aria-expanded') !== 'true') sum.click();
                  const more = document.getElementById('v2ContextMore'); if (more.offsetParent) more.click();
                  const box = id => { const e = document.getElementById(id); const r = e.getBoundingClientRect();
                    return {inStrip: Boolean(e.closest('#v2Context')), ok: r.width > 0 && r.left >= 0 && r.right <= w + 0.5 && e.scrollWidth <= e.clientWidth + 1}; };
                  return {stripShown: !document.getElementById('v2Context').hidden, copy: box('v2AssistCopy'),
                          over: document.documentElement.scrollWidth - w, footerButtons: document.querySelectorAll('#v2Assist button').length}; }""")
                narrow.keyboard.press("Escape")
                if strip["stripShown"] and not (strip["copy"]["inStrip"] and strip["copy"]["ok"]):
                    errors.append(f"Copy link not whole in the league strip at 390px on {tab}: {strip}")
                if strip["over"] > 0 or strip["footerButtons"]:
                    errors.append(f"390px {tab}: overflow {strip['over']}px, buttons left in the footer {strip['footerButtons']}")
            # 6. JEG-1101 (Jeremy, 2026-10-26): no ChatGPT/Claude buttons and no paste box; Copy link carries one line under it.
            narrow.evaluate("() => { location.hash = '#trade-targets'; }")   # the last tab above hides the league strip
            narrow.wait_for_timeout(300)
            gone = narrow.evaluate("""() => ({ids: ['v2AssistPasteToggle', 'v2AssistPaste', 'v2AssistApply', 'v2AssistPasteText']
                .filter(id => document.getElementById(id)),
              named: [...document.querySelectorAll('button')].filter(b => /ChatGPT|Claude/.test(b.textContent)).map(b => b.textContent.trim())})""")
            if gone["ids"] or gone["named"]:
                errors.append(f"the ChatGPT/Claude buttons or the paste box are still on the page: {gone}")
            line = narrow.evaluate("""() => { const more = document.getElementById('v2ContextMore');
              if (more.offsetParent && document.getElementById('v2ContextMenu').hidden) more.click();
              const p = document.getElementById('v2AssistCopyHint'), btn = document.getElementById('v2AssistCopy');
              const box = p ? p.getBoundingClientRect() : null;
              return {label: btn.textContent.trim(), text: p ? p.textContent.trim() : '', shown: Boolean(p && !p.hidden && box.height > 0),
                under: Boolean(box && box.top >= btn.getBoundingClientRect().bottom - 0.5),
                described: btn.getAttribute('aria-describedby') === 'v2AssistCopyHint', over: p ? p.scrollWidth - p.clientWidth : 0}; }""")
            if line["label"] != "Copy link" or not (line["shown"] and line["text"] and line["under"] and line["described"]) or line["over"] > 0:
                errors.append(f"Copy link or its line is not right: {line}")
            narrow.keyboard.press("Escape")
            narrow.evaluate("() => { location.hash = '#find-trade?mine=n:Nobody%2520Atall'; }")
            narrow.wait_for_timeout(400)
            wide = narrow.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if wide > 0:
                errors.append(f"horizontal overflow at 390px: {wide}px")
            for p in pages:
                if p.errors:
                    errors.append(f"page errors {p.errors}")
        finally:
            for c in contexts:
                c.close()
            browser.close()
    return errors


class AssistRenderTest(unittest.TestCase):
    def test_copy_link_round_trip_links_and_footer(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        assist = ASSIST_JS.read_text(encoding="utf-8")
        js = V2_JS.read_text(encoding="utf-8")
        broken = [
            ("a link applies no league", "assist", assist.replace("H.applyLinkLeague(new URLSearchParams(codec().encodeQuery({league: state.league})));", "", 1)),
            ("finder rosters not set", "assist", assist.replace("finder().ui.setSides(mine, theirs)", "{bothSides: []}", 1)),
            ("unmatched names not reported", "assist", assist.replace("if (unresolved.length) ignored.push", "if (false) ignored.push", 1)),
            ("copy writes no link", "assist", assist.replace("return {text: siteLink(built.state), built};", "return {text: \"\", built};", 1)),
            ("find-trade links not read", "v2", js.replace("if (window.DDFAssist) window.DDFAssist.applyLink(query);\n      return;\n    }\n    if (base ===", "return;\n    }\n    if (base ===", 1)),
            ("teams not read from a link", "v2", js.replace("if (teamsChange) C.setTeams(teams);", "", 1)),
            ("teams not written to a link", "v2", js.replace("    parts.push(`teams=${C.getState().teams}`);", "", 1)),
            ("no line under Copy link", "assist", assist.replace("if (hint) hint.hidden = false;", "", 1)),
        ]
        for name, which, body in broken:
            with self.subTest(mutation=name):
                source = assist if which == "assist" else js
                self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                try:
                    found = run_checks(assist_js=body) if which == "assist" else run_checks(v2_js=body)
                except (unittest.SkipTest, RuntimeError):
                    raise
                except Exception as exc:   # a control that never appears is a caught break too (the page timed out waiting for it)
                    found = [f"{type(exc).__name__}: {str(exc)[:80]}"]
                self.assertNotEqual(found, [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
