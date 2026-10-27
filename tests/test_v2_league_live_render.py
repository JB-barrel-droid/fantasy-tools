"""League settings apply live; Find a trade reprocesses on change (JEG-1020), rendered.

Jeremy, 2026-10-24: "Reprocess the text when league settings change. Don't require hitting accept or save when league
settings are changed." Loads dist/v2 headless (the same built copy the other render tests use) and checks:

  * Your league has no Apply and no Cancel; it has Reset defaults, Undo changes and Done; Done only closes;
  * a tap reaches the engine on its own after a short debounce, never inside the input handler; five quick taps are one
    recompute (one setRosterSpot) with the last value; Done and the close button flush a pending change;
  * an invalid intermediate state (the engine throws) keeps the last valid results, shows one inline issue and no page
    error, and the next valid change clears it;
  * a slow recompute (over 250 ms) shows "Updating" on the next change before it starts;
  * the polite live region says "Results updated for the new league settings." and focus stays on the control tapped,
    with no scroll jump;
  * Find a trade: the pasted page text is stored and re-read; the results after a settings change equal the results of
    a page that had those settings from the start (superflex, teams, scoring); the reader's ticks inside a group, open
    details, the open roster input, the ticked "move" players, hand-removed players and a cleared side all survive;
  * every tab that depends on the settings (Player values, Trade targets, Risers and fallers, Compare, Values auditing,
    How values work, Find a trade) shows the same text after a live change as a page that was set up with the
    settings first, so nothing is left stale;
  * a share link written after a live change carries the settings;
  * at 390 and 320 px the panel has no sideways scroll and every footer control is at least 44 px tall and on screen;
  * recompute time at the defaults and at extreme settings is measured and held under a generous ceiling.

Position weights (Jeremy, 2026-10-24) applies live the same way; changing Customize sources re-runs Find; a lesser-match
question ("A. Rodgers: is this Aaron Rodgers?") that was still waiting is asked again after a change, named if the player
can no longer be matched, and an answered one stays answered.

Discrimination: test_guard_fails_on_broken_builds serves a build with each of: the apply step back (Your league and Position weights), Customize leaving Find stale, the unsure question not asked again, (changes only apply
on Done), no debounce (the recompute runs in the input handler), the Find listener removed (results go stale), an
invalid intermediate that throws, no Updating state, no live-region announcement, and focus stolen on update.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_paste_render import fixture, paste
from tests.test_v2_modules_render import _built_dist, _serve

ROOT = Path(__file__).resolve().parents[1]
V2_JS = ROOT / "app" / "v2" / "v2.js"
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
LIVE_TEXT = "Results updated for the new league settings."
PERF_CEILING_MS = 1500   # generous: the point is a measured number in the log; the page shows "Updating" past ~250 ms


def setUpModule():
    _render_env.ensure_built()


PATCHES = {
    "apply step is back": ("v2_js", "        timer = setTimeout(() => setTimeout(commit, 0), LEAGUE_DEBOUNCE_MS);", "        timer = 1;"),
    "no debounce": ("v2_js", "        timer = setTimeout(() => setTimeout(commit, 0), LEAGUE_DEBOUNCE_MS);", "        commit();"),
    "find results go stale": ("finder_js", 'document.addEventListener("ddf:league-settings-changed", onLeagueSettingsChanged);', ""),
    "invalid intermediate crashes": ("v2_js", '        error = (caught && caught.message) || "Those settings could not be applied.";', "        throw caught;"),
    "no Updating state": ("v2_js", '        if (lastMs >= LEAGUE_SLOW_MS * 0.8) showMsg("Updating…");', ""),
    "no live announcement": ("v2_js", '          announceLive(["Results updated for the new league settings.", ...notes].join(" "));', ""),
    "weights apply step is back": ("v2_js", '        if (lastMs >= LEAGUE_SLOW_MS * 0.8) msg.textContent = "Updating…";\n        timer = setTimeout(() => setTimeout(commit, 0), LEAGUE_DEBOUNCE_MS);',
                                   '        timer = 1;'),
    "customize change leaves Find stale": ("v2_js", '        announceLeagueChange("sources");', ""),
    "unsure prompt not asked again": ("finder_js", "      if (unsure.length) { asks[side] = unsure;", "      if (false) { asks[side] = unsure;"),
    "focus stolen": ("v2_js", '        showMsg("");\n        if (error) {', '        showMsg(""); document.getElementById("v2EditLeague").focus();\n        if (error) {'),
}

STATE = """() => { const C = window.TradeValueCurveControls; return {shape: C.getRosterShape(), teams: C.getState().teams, scoring: C.getState().scoring,
  lineup: C.getLineupSettings()}; }"""
FIND_OUT = """() => ({out: document.getElementById('v2FindOut').innerText,
  headline: document.getElementById('v2FindFit').innerText, assess: document.getElementById('v2FindAssess').innerText,
  rosters: ['Mine', 'Theirs'].map(s => [...document.querySelectorAll('#v2Find' + s + 'Players .v2-find-row b')].map(b => b.textContent).join(',')).join('|')})"""
GROUPS = """() => [...document.querySelectorAll('#v2FindOut .v2-find-group')].map(g => ({id: g.dataset.group, edge: g.dataset.findEdge,
  open: [...g.querySelectorAll('details')].map(d => d.open),
  picks: Object.fromEntries([...g.querySelectorAll('input[data-key]')].map(i => [i.dataset.key, i.checked]))}))"""
LIVE = "() => document.getElementById('v2LeagueLive').textContent"
TAB_TEXT = ("()=>[...document.querySelectorAll('main')].filter(m=>!m.hidden&&m.offsetParent!==null).map(m=>m.innerText).join('\\n')"
            "+'\\n'+(document.getElementById('v2Context')?.innerText||'')")


def _open(browser, base, hash_, width=1440, height=900, overrides=None, errors=None, tag=""):
    page = browser.new_page(viewport={"width": width, "height": height})
    page.on("pageerror", lambda e: errors.append(f"{tag}page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    for name, body in (overrides or {}).items():
        page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
    page.goto(base + hash_, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls", timeout=60000)
    page.wait_for_timeout(500)
    return page


def _settle(page, ms=700):
    page.wait_for_timeout(ms)


def _change_settings(page):
    """The same four taps on a fresh page and a live page: superflex +1, 10 teams, half PPR, one fewer bench slot."""
    page.click("#v2EditLeague")
    page.click('#v2Popover [aria-label="More SUPERFLEX"]')
    page.click('#v2Popover [aria-label="Teams"] button[data-value="10"]')
    page.click('#v2Popover [aria-label="Scoring"] button[data-value="half_ppr"]')
    page.click('#v2Popover [aria-label="Fewer Bench slots"]')
    _settle(page, 900)
    page.click('#v2Popover [data-done="league"]')
    _settle(page, 300)


def _find_flow(page):
    paste(page, "Mine", fixture("espn-matchup.txt"), True)
    page.wait_for_selector("#v2FindMinePickTeam1")
    page.click("#v2FindMinePickTeam1")
    page.click("#v2FindGo")
    page.wait_for_selector("#v2FindOut .v2-find-group", timeout=20000)
    page.wait_for_timeout(300)


def check_panel(browser, base, overrides, errors):
    page = _open(browser, base, "#player-values", overrides=overrides, errors=errors, tag="[panel] ")
    page.evaluate("""() => { const C = window.TradeValueCurveControls; window.__calls = {rosterSpot: 0};
      const orig = C.setRosterSpot; C.setRosterSpot = (...a) => { window.__calls.rosterSpot += 1; return orig(...a); }; }""")
    start = page.evaluate(STATE)
    page.click("#v2EditLeague")
    buttons = page.evaluate("() => [...document.querySelectorAll('#v2Popover button')].map(b => b.textContent.trim())")
    if "Apply" in buttons or "Cancel" in buttons:
        errors.append(f"[panel] Apply or Cancel is still on the league panel: {buttons}")
    for want in ("Reset defaults", "Undo changes", "Done"):
        if want not in buttons:
            errors.append(f"[panel] no {want} button: {buttons}")
    # Five quick taps in one task: nothing reaches the engine inside the handler; one recompute lands the last value.
    before_log = page.evaluate("() => (window.__leagueApplyLog || []).length")
    page.evaluate("""() => { const b = document.querySelector('#v2Popover [aria-label="More WR"]');
      for (let i = 0; i < 3; i += 1) { const again = document.querySelector('#v2Popover [aria-label="More WR"]'); if (again && !again.disabled) again.click(); }
      window.__syncWR = window.TradeValueCurveControls.getRosterShape().WR; }""")
    if page.evaluate("() => window.__syncWR") != start["shape"]["WR"]:
        errors.append("[panel] a tap reached the engine inside the input handler (no debounce)")
    _settle(page, 800)
    got = page.evaluate(STATE)
    want_wr = min(5, start["shape"]["WR"] + 3)
    if got["shape"]["WR"] != want_wr:
        errors.append(f"[panel] three quick WR taps gave WR {got['shape']['WR']}, wanted {want_wr}")
    calls = page.evaluate("() => window.__calls.rosterSpot")
    if calls != 1:
        errors.append(f"[panel] three quick taps made {calls} setRosterSpot calls, wanted 1 (debounced)")
    log = page.evaluate("() => window.__leagueApplyLog || []")
    if len(log) - before_log != 1:
        errors.append(f"[panel] three quick taps made {len(log) - before_log} recomputes, wanted 1")
    if page.evaluate(LIVE) != LIVE_TEXT:
        errors.append(f"[panel] live region reads {page.evaluate(LIVE)!r}, wanted {LIVE_TEXT!r}")
    if page.evaluate("() => document.getElementById('v2LeagueLive').getAttribute('aria-live')") != "polite":
        errors.append("[panel] the live region is not polite")
    # Focus stays on the stepper that was tapped; the page did not scroll.
    page.focus('#v2Popover [aria-label="Fewer WR"]')
    scroll = page.evaluate("() => window.scrollY")
    page.click('#v2Popover [aria-label="Fewer WR"]')
    _settle(page, 600)
    focus = page.evaluate("() => document.activeElement && document.activeElement.getAttribute('aria-label')")
    if focus != "Fewer WR":
        errors.append(f"[panel] focus moved to {focus!r} after a live update, wanted the tapped stepper")
    if page.evaluate("() => window.scrollY") != scroll:
        errors.append("[panel] the page scrolled on a live update")
    # Done flushes a pending change: tap and close at once.
    page.click('#v2Popover [aria-label="More RB"]')
    page.click('#v2Popover [data-done="league"]')
    if page.evaluate(STATE)["shape"]["RB"] != start["shape"]["RB"] + 1:
        errors.append("[panel] Done did not flush a pending change")
    # Undo returns to what the panel opened with.
    page.click("#v2EditLeague")
    opened = page.evaluate(STATE)
    page.click('#v2Popover [aria-label="Teams"] button[data-value="14"]')
    _settle(page, 600)
    if page.evaluate(STATE)["teams"] != 14:
        errors.append("[panel] 14 teams did not apply live")
    page.click("#v2Popover [data-league-undo]")
    if page.evaluate(STATE)["teams"] != opened["teams"]:
        errors.append("[panel] Undo changes did not return the teams")
    page.click("#v2Popover [data-league-reset]")
    back = page.evaluate(STATE)
    if back["shape"] != start["shape"] or back["teams"] != start["teams"]:
        errors.append(f"[panel] Reset defaults gave {back['shape']} {back['teams']}, first load {start['shape']} {start['teams']}")
    # An invalid intermediate state: the engine refuses once; the results stay, one inline issue shows, no page error.
    teams_before = page.evaluate(STATE)["teams"]
    page.evaluate("""() => { const C = window.TradeValueCurveControls; window.__origTeams = C.setTeams;
      C.setTeams = () => { throw new RangeError('Teams must be 8, 10, 12 or 14'); }; }""")
    page.click('#v2Popover [aria-label="Teams"] button[data-value="8"]')
    _settle(page, 600)
    issue = page.evaluate("() => { const n = document.querySelector('#v2Popover [data-league-issue]'); return n && !n.hidden ? n.textContent : ''; }")
    if "Teams must be" not in issue:
        errors.append(f"[panel] an invalid intermediate state showed no inline issue: {issue!r}")
    if page.evaluate(STATE)["teams"] != teams_before:
        errors.append("[panel] an invalid intermediate state changed the engine")
    if not page.evaluate("() => document.getElementById('v2Popover').querySelector('.v2-panel-body') !== null && !document.getElementById('v2Popover').hidden"):
        errors.append("[panel] the panel went blank or closed on an invalid state")
    page.evaluate("() => { window.TradeValueCurveControls.setTeams = window.__origTeams; }")
    page.click('#v2Popover [aria-label="Teams"] button[data-value="10"]')
    _settle(page, 600)
    if page.evaluate("() => document.querySelector('#v2Popover [data-league-issue]').hidden") is not True:
        errors.append("[panel] the inline issue stayed after a valid change")
    if page.evaluate(STATE)["teams"] != 10:
        errors.append("[panel] the valid change after an invalid one did not apply")
    # A slow recompute shows "Updating" on the next change.
    page.evaluate("""() => { const C = window.TradeValueCurveControls; const orig = C.setTeams;
      C.setTeams = (...a) => { const t = performance.now(); while (performance.now() - t < 320) {} return orig(...a); }; window.__origTeams2 = orig; }""")
    page.click('#v2Popover [aria-label="Teams"] button[data-value="12"]')
    _settle(page, 900)
    page.evaluate("() => { window.TradeValueCurveControls.setTeams = window.__origTeams2; }")
    page.click('#v2Popover [aria-label="Teams"] button[data-value="10"]')
    msg = page.evaluate("() => document.querySelector('#v2Popover [data-league-msg]').textContent")
    if "Updating" not in msg:
        errors.append(f"[panel] after a slow recompute the next change shows {msg!r}, wanted an Updating state")
    _settle(page, 700)
    if page.evaluate("() => document.querySelector('#v2Popover [data-league-msg]').textContent").startswith("Updating"):
        errors.append("[panel] the Updating state stayed after the recompute finished")
    page.close()


def check_find(browser, base, overrides, errors):
    live = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[find live] ")
    _find_flow(live)
    first = live.evaluate(GROUPS)
    if not first:
        errors.append("[find] no groups before the change")
        live.close()
        return
    # The reader's choices: untick a give-side player where allowed, open the lineup details, open the roster input,
    # tick a player to move, remove one player by hand.
    target = live.evaluate("""() => { for (const g of document.querySelectorAll('#v2FindOut .v2-find-group')) {
      const boxes = [...g.querySelectorAll('input[data-key]')].filter(i => i.checked && !i.disabled);
      if (boxes.length > 1) return {group: g.dataset.group, key: boxes[0].dataset.key}; } return null; }""")
    if target:
        live.evaluate("([g, k]) => { const i = document.querySelector(`#v2FindOut .v2-find-group[data-group=\"${g}\"] input[data-key=\"${k}\"]`); i.click(); }",
                      [target["group"], target["key"]])
    live.evaluate("() => { document.querySelector('#v2FindOut .v2-find-group details').open = true; }")
    live.click("#v2FindEdit")
    removed_name = live.evaluate("() => document.querySelector('#v2FindMinePlayers .v2-find-row b').textContent")
    live.click("#v2FindMinePlayers .v2-find-row >> nth=0 >> .v2-find-remove")
    picked = live.evaluate("() => { const i = document.querySelectorAll('#v2FindTheirsPlayers .v2-find-pick')[0]; i.click(); return i.getAttribute('aria-label'); }")
    live.click("#v2FindGo")
    live.wait_for_selector("#v2FindOut .v2-find-group")
    live.click("#v2FindEdit")
    live.evaluate("() => { document.querySelector('#v2FindOut .v2-find-group details').open = true; }")
    if target:
        live.evaluate("([g, k]) => { const i = document.querySelector(`#v2FindOut .v2-find-group[data-group=\"${g}\"] input[data-key=\"${k}\"]`); if (i && i.checked) i.click(); }",
                      [target["group"], target["key"]])
    live.evaluate("() => { const i = document.querySelectorAll('#v2FindTheirsPlayers .v2-find-pick')[0]; if (!i.checked) i.click(); }")
    before_groups = {g["id"]: g for g in live.evaluate(GROUPS)}
    scroll = live.evaluate("() => window.scrollY")
    # The change.
    live.click("#v2EditLeague")
    live.focus('#v2Popover [aria-label="More SUPERFLEX"]')
    live.click('#v2Popover [aria-label="More SUPERFLEX"]')
    _settle(live, 900)
    focus = live.evaluate("() => document.activeElement && document.activeElement.getAttribute('aria-label')")
    if focus != "More SUPERFLEX" and focus != "Fewer SUPERFLEX":
        errors.append(f"[find] focus moved to {focus!r} on a live update")
    if live.evaluate(LIVE) != LIVE_TEXT:
        errors.append(f"[find] live region reads {live.evaluate(LIVE)!r}")
    live.click('#v2Popover [data-done="league"]')
    _settle(live, 300)
    after = live.evaluate(GROUPS)
    if not after:
        errors.append("[find] the results vanished after the change")
    if live.evaluate("() => window.scrollY") != scroll:
        errors.append("[find] the page scrolled on a live update")
    note = live.evaluate("() => document.getElementById('v2FindSettingsNote').textContent")
    if "new league settings" not in note:
        errors.append(f"[find] no inline note after the change: {note!r}")
    # Preserved choices.
    if live.evaluate("() => document.getElementById('v2FindInput').hidden"):
        errors.append("[find] the roster input folded on a settings change (the reader had it open)")
    kept_open = [g for g in after if g["id"] in before_groups and any(before_groups[g["id"]]["open"]) and not any(g["open"])]
    if kept_open:
        errors.append(f"[find] open details closed on a settings change: {[g['id'] for g in kept_open]}")
    if target:
        regrouped = [g for g in after if g["id"] == target["group"] and target["key"] in g["picks"]]
        if regrouped and regrouped[0]["picks"][target["key"]]:
            errors.append("[find] a player the reader unticked came back ticked after the change")
    if not live.evaluate("() => document.querySelectorAll('#v2FindTheirsPlayers .v2-find-pick')[0].checked"):
        errors.append("[find] the ticked 'move' player was unticked by the change")
    names = live.evaluate("() => [...document.querySelectorAll('#v2FindMinePlayers .v2-find-row b')].map(b => b.textContent)")
    if removed_name in names:
        errors.append(f"[find] {removed_name} came back after being removed by hand")
    # Cleared side stays cleared.
    live.click("#v2FindTheirsClear")
    live.click("#v2EditLeague")
    live.click('#v2Popover [aria-label="Fewer SUPERFLEX"]')
    _settle(live, 800)
    live.click('#v2Popover [data-done="league"]')
    if live.evaluate("() => document.querySelectorAll('#v2FindTheirsPlayers .v2-find-row').length") != 0:
        errors.append("[find] a cleared side was filled again by the change")
    live.close()

    # Equivalence: live results equal a page that had the settings from the start.
    a = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[find a] ")
    _find_flow(a)
    a.click("#v2EditLeague")
    a.click('#v2Popover [aria-label="More SUPERFLEX"]')
    a.click('#v2Popover [aria-label="Teams"] button[data-value="10"]')
    a.click('#v2Popover [aria-label="Scoring"] button[data-value="half_ppr"]')
    a.click('#v2Popover [aria-label="Fewer Bench slots"]')
    _settle(a, 900)
    a.click('#v2Popover [data-done="league"]')
    _settle(a, 400)
    live_out = a.evaluate(FIND_OUT)
    b = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[find b] ")
    _change_settings(b)
    _find_flow(b)
    fresh_out = b.evaluate(FIND_OUT)
    if live_out != fresh_out:
        for key in live_out:
            if live_out[key] != fresh_out[key]:
                lines = list(zip(live_out[key].split("\n"), fresh_out[key].split("\n")))
                first = next(((x, y) for x, y in lines if x != y), ("(length differs)", ""))
                errors.append(f"[find] {key} after a live change differs from a page set up with the same settings:\n live  {first[0][:300]!r}\n fresh {first[1][:300]!r}")
    a.close()
    b.close()


UNSURE_ROWS = "() => [...document.querySelectorAll('#v2FindMinePasteResult li.v2-find-unsure')].map(li => ({id: li.dataset.unsureId, name: li.dataset.unsureName, pending: Boolean(li.querySelector('button'))}))"


def check_weights_live(browser, base, overrides, errors):
    page = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[weights] ")
    _find_flow(page)
    start = page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()")
    page.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
    page.click("#v2Weights")
    buttons = page.evaluate("() => [...document.querySelectorAll('#v2Popover button')].map(b => b.textContent.trim())")
    if "Apply" in buttons or "Cancel" in buttons or not {"Reset defaults", "Undo changes", "Done"} <= set(buttons):
        errors.append(f"[weights] the Position weights footer is {buttons}, wanted Reset defaults, Undo changes, Done and no Apply or Cancel")
    page.fill("#v2ShareQB", "30")
    if abs(page.evaluate("() => window.TradeValueCurveControls.getPositionWeights().QB") - start["QB"]) > 1e-9:
        errors.append("[weights] a share reached the engine inside the input handler (no debounce)")
    _settle(page, 800)
    got = page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()")
    if abs(got["QB"] - 0.30) > 0.002:
        errors.append(f"[weights] QB 30 did not apply on its own: {got}")
    shown = page.evaluate("() => Object.fromEntries(['QB','RB','WR','TE'].map(p => [p, document.getElementById('v2Share' + p).value]))")
    if any(abs(float(shown[p]) - got[p] * 100) > 0.06 for p in shown):
        errors.append(f"[weights] the boxes {shown} do not show the rebalanced engine shares {got}")
    if page.evaluate(LIVE) != LIVE_TEXT:
        errors.append(f"[weights] live region reads {page.evaluate(LIVE)!r}")
    if "new league settings" not in page.evaluate("() => document.getElementById('v2FindSettingsNote').textContent"):
        errors.append("[weights] Find was not re-run after a share change")
    page.fill("#v2ShareWR", "150")
    _settle(page, 600)
    if page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()") != got:
        errors.append("[weights] an invalid share (150) changed the engine")
    if "between" not in (page.text_content("#v2Popover [data-share-message]") or ""):
        errors.append("[weights] an invalid share showed no inline message")
    page.click("#v2Popover [data-weights-undo]")
    if page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()") != start:
        errors.append("[weights] Undo changes did not return the opening shares")
    page.fill("#v2ShareQB", "28")
    page.click('#v2Popover [data-done="weights"]')
    if abs(page.evaluate("() => window.TradeValueCurveControls.getPositionWeights().QB") - 0.28) > 0.002:
        errors.append("[weights] Done did not flush a pending share")
    page.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
    page.click("#v2Weights")
    page.click("#v2Popover [data-weights-reset]")
    page.click('#v2Popover [data-done="weights"]')
    if page.evaluate("() => window.TradeValueCurveControls.getPositionWeights()") != start:
        errors.append("[weights] Reset defaults did not return the shares")
    page.close()
    # Find after a live share change equals a page that had the share from the start.
    a = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[weights a] ")
    _find_flow(a)
    a.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
    a.click("#v2Weights")
    a.fill("#v2ShareQB", "30")
    _settle(a, 800)
    a.click('#v2Popover [data-done="weights"]')
    _settle(a, 300)
    b = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[weights b] ")
    b.click("#v2ContextMore")  # JEG-1119: in the ⋯ menu
    b.click("#v2Weights")
    b.fill("#v2ShareQB", "30")
    _settle(b, 800)
    b.click('#v2Popover [data-done="weights"]')
    _find_flow(b)
    if a.evaluate(FIND_OUT) != b.evaluate(FIND_OUT):
        errors.append("[weights] Find results after a live share change differ from a page that had the share first")
    a.close()
    b.close()


def check_sources(browser, base, overrides, errors):
    page = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[sources] ")
    _find_flow(page)
    page.evaluate("() => { location.hash = '#player-values'; }")
    _settle(page, 600)
    page.click("#v2EditSources")
    page.wait_for_selector("#v2Popover input[data-series]")
    keys = page.evaluate("() => [...document.querySelectorAll('#v2Popover input[data-series]')].filter(i => i.checked && !i.disabled).map(i => i.dataset.series)")
    pick = next((k for k in keys if k.startswith("fantasypros") or k.startswith("cbs") or k.startswith("usatoday")), keys[-1] if keys else None)
    if pick is None:
        errors.append("[sources] no source to change in Customize")
        page.close()
        return
    page.evaluate("k => document.querySelector(`#v2Popover input[data-series=\"${k}\"]`).click()", pick)
    page.click('#v2Popover [data-apply="sources"]')
    _settle(page, 800)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    _settle(page, 600)
    note = page.evaluate("() => document.getElementById('v2FindSettingsNote').textContent")
    if "new source selection" not in note:
        errors.append(f"[sources] Find was not re-run after a Customize change: note {note!r}")
    if not page.evaluate("() => document.querySelectorAll('#v2FindOut .v2-find-group').length"):
        errors.append("[sources] the Find results vanished after a Customize change")
    if "source selection" not in page.evaluate(LIVE):
        errors.append(f"[sources] live region reads {page.evaluate(LIVE)!r}")
    page.close()


def check_unsure(browser, base, overrides, errors):
    lesser = fixture("yahoo-team.txt").replace("Aaron RodgersPlayer Note\nPit - QB", "A. RodgersPlayer Note\nPit - QB")
    page = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[unsure] ")
    paste(page, "Mine", lesser)
    page.wait_for_timeout(400)
    rows = page.evaluate(UNSURE_ROWS)
    if len(rows) != 1 or not rows[0]["pending"]:
        errors.append(f"[unsure] fixture should leave one waiting question: {rows}")
        page.close()
        return
    page.click("#v2EditLeague")
    page.focus('#v2Popover [aria-label="More SUPERFLEX"]')
    page.click('#v2Popover [aria-label="More SUPERFLEX"]')
    _settle(page, 900)
    rows = page.evaluate(UNSURE_ROWS)
    if len(rows) != 1 or not rows[0]["pending"]:
        errors.append(f"[unsure] the question was not asked again after a settings change: {rows}")
    if "check again" not in page.evaluate(LIVE):
        errors.append(f"[unsure] the live region does not say a question is back: {page.evaluate(LIVE)!r}")
    if page.evaluate("() => document.activeElement && document.activeElement.getAttribute('aria-label')") not in ("More SUPERFLEX", "Fewer SUPERFLEX"):
        errors.append("[unsure] asking again moved focus")
    page.click('#v2Popover [data-done="league"]')
    # An answered question stays answered.
    page.click("#v2FindMinePasteResult li.v2-find-unsure .v2-find-confirm")
    page.click("#v2EditLeague")
    page.click('#v2Popover [aria-label="Fewer SUPERFLEX"]')
    _settle(page, 900)
    page.click('#v2Popover [data-done="league"]')
    if any(r["pending"] for r in page.evaluate(UNSURE_ROWS)):
        errors.append("[unsure] an answered question was asked again")
    page.close()
    # A player who can no longer be matched is named.
    gone = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[unsure gone] ")
    paste(gone, "Mine", lesser)
    gone.wait_for_timeout(400)
    gone.evaluate("""() => { const C = window.TradeValueCurveControls; const all = C.getAllRows.bind(C);
      C.getAllRows = () => all().filter(r => r.name !== 'Aaron Rodgers'); }""")
    gone.click("#v2EditLeague")
    gone.click('#v2Popover [aria-label="More SUPERFLEX"]')
    _settle(gone, 900)
    if "Aaron Rodgers can no longer be matched" not in gone.evaluate("() => document.getElementById('v2FindSettingsNote').textContent"):
        errors.append("[unsure] a player who can no longer be matched was not named")
    gone.close()


def check_tabs(browser, base, overrides, errors):
    probe = _open(browser, base, "#player-values", overrides=overrides, errors=errors, tag="[probe] ")
    keys = probe.evaluate("() => window.TradeValueCurveControls.getAllRows().filter(r => r.pos === 'RB' || r.pos === 'QB').slice(0, 4).map(r => String(r.player_key))")
    probe.close()
    tabs = {"Player values": "#player-values", "Trade targets": "#trade-targets", "Risers and fallers": "#risers-fallers",
            "Compare": f"#compare-trade?give={','.join(keys[:2])}&get={','.join(keys[2:4])}", "Values auditing": "#values-auditing",
            "How values work": "#writing/how-values"}
    for name, hash_ in tabs.items():
        live = _open(browser, base, hash_, overrides=overrides, errors=errors, tag=f"[{name}] ")
        _change_settings(live)
        live_text = live.evaluate(TAB_TEXT)
        fresh = _open(browser, base, "#player-values", overrides=overrides, errors=errors, tag=f"[{name} fresh] ")
        _change_settings(fresh)
        fresh.evaluate("h => { location.hash = h; }", hash_)
        _settle(fresh, 1200)
        fresh_text = fresh.evaluate(TAB_TEXT)
        if live_text != fresh_text:
            old, new = fresh_text.split("\n"), live_text.split("\n")
            first = next(((o, n) for o, n in zip(old, new) if o != n), ("", ""))
            errors.append(f"[{name}] stale after a live settings change; first differing line: fresh {first[0][:90]!r} vs live {first[1][:90]!r}")
        live.close()
        fresh.close()
    # A share link written after a live change carries the settings.
    page = _open(browser, base, "#compare-trade", overrides=overrides, errors=errors, tag="[link] ")
    page.click("#v2EditLeague")
    page.click('#v2Popover [aria-label="More SUPERFLEX"]')
    page.click('#v2Popover [aria-label="Scoring"] button[data-value="half_ppr"]')
    _settle(page, 800)
    page.click('#v2Popover [data-done="league"]')
    page.fill("#v2GiveSearch", "Gibbs")
    page.click("#v2GiveResults button >> nth=0")
    page.fill("#v2GetSearch", "Chase")
    page.click("#v2GetResults button >> nth=0")
    _settle(page, 400)
    h = page.evaluate("() => location.hash")
    if "scoring=half_ppr" not in h or "SF1" not in h:
        errors.append(f"[link] the link after a live change does not carry the settings: {h!r}")
    page.close()


def check_phone(browser, base, overrides, errors):
    for width in (390, 320):
        page = _open(browser, base, "#find-trade", width=width, height=780, overrides=overrides, errors=errors, tag=f"[{width}px] ")
        page.click("#v2EditLeague")
        page.click('#v2Popover details.v2-padv summary')
        page.click('#v2Popover [aria-label="Teams"] button[data-value="10"]')
        _settle(page, 600)
        info = page.evaluate("""() => { const foot = document.querySelector('#v2Popover .v2-panel-foot');
          const btns = [...foot.querySelectorAll('button')].map(b => { const r = b.getBoundingClientRect(); return {t: b.textContent.trim(), h: Math.round(r.height), w: Math.round(r.width), bottom: Math.round(r.bottom), right: Math.round(r.right)}; });
          return {overflow: document.documentElement.scrollWidth - innerWidth, popOverflow: document.getElementById('v2Popover').scrollWidth - document.getElementById('v2Popover').clientWidth, btns, vh: innerHeight, vw: innerWidth}; }""")
        if info["overflow"] > 0 or info["popOverflow"] > 0:
            errors.append(f"[{width}px] sideways scroll: page {info['overflow']}px, panel {info['popOverflow']}px")
        for btn in info["btns"]:
            if btn["h"] < 44 or btn["bottom"] > info["vh"] or btn["right"] > info["vw"]:
                errors.append(f"[{width}px] footer control {btn} is under 44 px or off screen")
        page.close()


def check_perf(browser, base, overrides, errors, report):
    page = _open(browser, base, "#find-trade", overrides=overrides, errors=errors, tag="[perf] ")
    _find_flow(page)
    page.click("#v2EditLeague")
    page.click('#v2Popover [aria-label="Scoring"] button[data-value="standard"]')
    _settle(page, 900)
    default_ms = page.evaluate("() => window.__leagueApplyLog.slice(-1)[0]")
    for label in ("More SUPERFLEX", "More FLEX", "More FLEX", "More BENCH", "More Bench slots", "More Bench slots", "More Bench slots"):
        sel = f'#v2Popover [aria-label="{label}"]'
        if page.locator(sel).count() and page.locator(sel).first.is_enabled():
            page.click(sel)
    page.click('#v2Popover [aria-label="Teams"] button[data-value="14"]')
    page.click('#v2Popover details.v2-padv summary')
    page.click('#v2Popover [aria-label="Injury history"] button[data-value="all"]')
    _settle(page, 1500)
    extreme_ms = page.evaluate("() => window.__leagueApplyLog.slice(-1)[0]")
    report.append(f"recompute with Find results shown: standard/12 teams {default_ms} ms; extreme (14 teams, superflex, deep bench, flex) {extreme_ms} ms")
    if extreme_ms > PERF_CEILING_MS or default_ms > PERF_CEILING_MS:
        errors.append(f"[perf] recompute took {default_ms} ms at the defaults and {extreme_ms} ms at extreme settings (ceiling {PERF_CEILING_MS})")
    page.close()


def run_checks(patch=None, report=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    sources = {"v2_js": V2_JS.read_text(encoding="utf-8"), "finder_js": FINDER_JS.read_text(encoding="utf-8")}
    if patch:
        which, old, new = patch
        assert old in sources[which], f"patch anchor missing: {old!r}"
        sources[which] = sources[which].replace(old, new, 1)
    overrides = {"v2.js": sources["v2_js"], "finder.js": sources["finder_js"]} if patch else None
    errors: list[str] = []
    report = report if report is not None else []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            check_panel(browser, base, overrides, errors)
            check_find(browser, base, overrides, errors)
            check_weights_live(browser, base, overrides, errors)
            check_sources(browser, base, overrides, errors)
            check_unsure(browser, base, overrides, errors)
            if not patch:
                check_tabs(browser, base, overrides, errors)
                check_phone(browser, base, overrides, errors)
                check_perf(browser, base, overrides, errors, report)
        finally:
            browser.close()
    return errors


class LeagueLiveRenderTest(unittest.TestCase):
    def test_settings_apply_live_and_find_reprocesses(self):
        self.maxDiff = None
        report: list[str] = []
        errors = run_checks(report=report)
        for line in report:
            print(line)
        self.assertEqual(errors, [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(patch)
                except Exception as exc:   # a broken build that cannot finish the walk-through is caught too
                    if type(exc).__name__ == "SkipTest" or "unavailable" in type(exc).__name__.lower():
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}: {exc}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
