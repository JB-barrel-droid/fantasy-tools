"""Your league, rendered (JEG-1021): the team list on Find a trade.

Loads the built page headless at 1366x768 and checks, against the frozen fixture leagues:

  * no team yet: the empty state, and the summary and opportunities cards stay out of the way;
  * teams are a real list; each folds and opens (aria-expanded); with three or more only the last edited is open;
  * a name is renamed inline (Enter saves, Escape cancels) and the star moves "my team" (aria-pressed);
  * Up and Down reorder; Remove asks first and Undo brings the team back; Add team opens a new team with its name ready;
  * a pasted list of names fills the team, a player already on another team is left out and named;
  * the league is saved as you type ("Saved"), is back after a reload, and a corrupt saved value is reported and not trusted;
  * Download gives a valid JSON file and Load reads it back; the shared my-roster store follows the star.

Discrimination: test_guard_fails_on_broken_builds serves a build with each rule broken (star does nothing, reorder the wrong way,
nothing saved, no confirm on Remove, ...) and requires the checks to fail.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._league_render import RESOLVE, browser_on_build, fixture, open_page, seed, source

TEAMS = "#v2LgTeams > li.v2-lg-team"


def setUpModule():
    _render_env.ensure_built()


def names(page):
    return page.evaluate("() => [...document.querySelectorAll('#v2LgTeams > li .v2-lg-name')].map(b => b.textContent)")


def pressed(page):
    return page.evaluate("() => [...document.querySelectorAll('#v2LgTeams > li .v2-lg-star')].map(b => b.getAttribute('aria-pressed'))")


def check_empty(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[empty] ")
    if page.locator(TEAMS).count() != 0:
        errors.append("[empty] teams listed before any was added")
    if not page.is_visible("#v2LgEmpty") or "No teams yet" not in page.inner_text("#v2LgEmpty"):
        errors.append("[empty] no empty state")
    for card in ("#v2LgSummary", "#v2LgOpps"):
        if page.is_visible(card):
            errors.append(f"[empty] {card} shows with no team")
    unresolved = page.evaluate(RESOLVE, fixture("20team"))
    if unresolved:
        errors.append(f"[empty] fixture players the engine does not have: {unresolved[:5]}")
    # Add the first team: the name is ready to type.
    page.click("#v2LgAdd")
    page.wait_for_selector(f"{TEAMS} .v2-lg-name-input")
    if page.evaluate("() => document.activeElement.className") != "v2-lg-name-input":
        errors.append("[empty] the new team's name box is not focused")
    page.keyboard.type("Alpha")
    page.keyboard.press("Enter")
    if names(page) != ["Alpha"]:
        errors.append(f"[empty] rename on Enter: {names(page)}")
    # Escape cancels a rename.
    page.click(f"{TEAMS} .v2-lg-name")
    page.keyboard.type("Zzz")
    page.keyboard.press("Escape")
    if names(page) != ["Alpha"]:
        errors.append(f"[empty] Escape did not cancel the rename: {names(page)}")
    if page.inner_text("#v2LgCount") != "Teams (1)":
        errors.append(f"[empty] count text {page.inner_text('#v2LgCount')!r}")
    page.context.close()


def check_list(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[list] ")
    fx = fixture("4team")
    counts = seed(page, "4team")
    if page.locator(TEAMS).count() != 4:
        errors.append(f"[list] {page.locator(TEAMS).count()} teams for a 4-team fixture")
    if names(page) != [t["name"] for t in fx["teams"]]:
        errors.append(f"[list] names {names(page)}")
    shown = page.evaluate("() => [...document.querySelectorAll('#v2LgTeams > li .v2-lg-count')].map(s => s.textContent)")
    if shown != [f"({n} players)" for n in counts]:
        errors.append(f"[list] player counts {shown} vs {counts} (K and DEF are counted)")
    if not page.evaluate("() => document.querySelector('#v2LgTeams').tagName === 'UL'"):
        errors.append("[list] the team list is not a <ul>")
    if pressed(page) != ["true", "false", "false", "false"]:
        errors.append(f"[list] star state {pressed(page)}")
    open_now = page.evaluate("() => [...document.querySelectorAll('#v2LgTeams > li .v2-lg-toggle')].map(b => b.getAttribute('aria-expanded'))")
    if open_now.count("true") != 1:
        errors.append(f"[list] with 4 teams exactly one should be open: {open_now}")
    # Fold and open.
    first = page.locator(f"{TEAMS} >> nth=1")
    toggle = first.locator(".v2-lg-toggle")
    body_id = toggle.get_attribute("aria-controls")
    toggle.click()
    if toggle.get_attribute("aria-expanded") != "true" or not page.is_visible(f"#{body_id}"):
        errors.append("[list] expand did not open the team")
    toggle.click()
    if toggle.get_attribute("aria-expanded") != "false" or page.is_visible(f"#{body_id}"):
        errors.append("[list] collapse did not fold the team")
    # The star moves.
    page.locator(f"{TEAMS} >> nth=2").locator(".v2-lg-star").click()
    if pressed(page) != ["false", "false", "true", "false"]:
        errors.append(f"[list] star did not move: {pressed(page)}")
    if page.evaluate("() => window.TradeValueWorkspace.store.getMyTeam().name") != fx["teams"][2]["name"]:
        errors.append("[list] the shared my-roster store did not follow the star")
    if len(page.evaluate("() => window.TradeValueWorkspace.store.getMyRoster()")) != counts[2]:
        errors.append("[list] getMyRoster does not return the marked team's roster")
    # Rename inline.
    page.locator(f"{TEAMS} >> nth=1").locator(".v2-lg-name").click()
    page.keyboard.type("Renamed team")
    page.keyboard.press("Enter")
    if names(page)[1] != "Renamed team" or page.evaluate("() => window.TradeValueWorkspace.store.get().teams[1].name") != "Renamed team":
        errors.append(f"[list] rename not shown or not stored: {names(page)}")
    # Reorder.
    order = names(page)
    page.locator(f"{TEAMS} >> nth=0").locator(".v2-lg-down").click()
    if names(page) != [order[1], order[0], order[2], order[3]]:
        errors.append(f"[list] Down: {names(page)} from {order}")
    if page.evaluate("() => window.TradeValueWorkspace.store.get().teams.map(t => t.name)") != names(page):
        errors.append("[list] the stored order is not the shown order")
    if not page.locator(f"{TEAMS} >> nth=0").locator(".v2-lg-up").is_disabled():
        errors.append("[list] Up is enabled on the first team")
    page.locator(f"{TEAMS} >> nth=1").locator(".v2-lg-up").click()
    if names(page) != order:
        errors.append(f"[list] Up: {names(page)}")
    # Remove asks first; Cancel keeps; Remove then Undo brings it back.
    victim = names(page)[3]
    page.locator(f"{TEAMS} >> nth=3").locator(".v2-lg-remove").click()
    if page.locator(TEAMS).count() != 4 or not page.is_visible(f"{TEAMS} >> nth=3 >> .v2-lg-confirm"):
        errors.append("[list] Remove did not ask first")
    page.locator(f"{TEAMS} >> nth=3").locator(".v2-lg-remove-no").click()
    if page.locator(TEAMS).count() != 4:
        errors.append("[list] Cancel removed the team")
    page.locator(f"{TEAMS} >> nth=3").locator(".v2-lg-remove").click()
    page.locator(f"{TEAMS} >> nth=3").locator(".v2-lg-remove-yes").click()
    if page.locator(TEAMS).count() != 3 or victim in names(page):
        errors.append("[list] Remove did not remove")
    if "Team removed" not in page.inner_text("#v2LgLive"):
        errors.append("[list] removal not announced")
    page.click("#v2LgUndo")
    if page.locator(TEAMS).count() != 4 or victim not in names(page):
        errors.append("[list] Undo did not bring the team back")
    # Clear.
    page.locator(f"{TEAMS} >> nth=3").locator(".v2-lg-clear").click()
    if page.evaluate("() => window.TradeValueWorkspace.store.get().teams[3].entries.length") != 0:
        errors.append("[list] Clear left players")
    page.click("#v2LgUndo")
    # Add a team and paste a list of names into it; a player on another team is left out and named.
    page.click("#v2LgAdd")
    page.wait_for_selector(f"{TEAMS} .v2-lg-name-input")
    page.keyboard.press("Enter")
    if page.locator(TEAMS).count() != 5:
        errors.append("[list] Add team did not add")
    if names(page)[4] != "Team 5":
        errors.append(f"[list] default name {names(page)[4]!r}")
    pick = page.evaluate("""() => { const used = new Set(window.TradeValueWorkspace.store.get().teams.flatMap(t => t.entries.map(e => e.key)));
      const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name && !used.has(String(r.player_key)))
        .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
      const names = new Map(); window.TradeValueCurveControls.getAllRows().forEach(r => names.set(r.name, (names.get(r.name) || 0) + 1));
      return rows.filter(r => names.get(r.name) === 1).slice(0, 6).map(r => r.name); }""")
    taken = fixture("4team")["teams"][0]["players"][0]["name"]
    box = page.locator(f"{TEAMS} >> nth=4").locator("textarea")
    box.fill("\n".join(pick + [taken]))
    page.wait_for_function("() => window.TradeValueWorkspace.store.get().teams[4].entries.length >= 6", timeout=10000)
    got = page.evaluate("() => window.TradeValueWorkspace.store.get().teams[4].entries.map(e => e.name)")
    if sorted(got) != sorted(pick):
        errors.append(f"[list] pasted names {got} vs {pick}")
    if taken in got:
        errors.append("[list] a player already on another team was added")
    if taken not in page.inner_text(f"{TEAMS} >> nth=4 >> .v2-find-paste-result"):
        errors.append("[list] the player left out was not named")
    page.context.close()


def check_saved(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[saved] ")
    seed(page, "2team")
    page.wait_for_function("() => document.getElementById('v2LgSaved').textContent === 'Saved'", timeout=5000)
    stored = page.evaluate("() => localStorage.getItem('ddf.v2.workspaces')")
    parsed = json.loads(stored) if stored else {}
    if parsed.get("v") != 1 or len(parsed.get("workspaces", [{}])[0].get("teams", [])) != 2:
        errors.append(f"[saved] nothing saved after Saved: {str(stored)[:120]}")
    page.locator(f"{TEAMS} >> nth=1").locator(".v2-lg-name").click()
    page.keyboard.type("Persisted name")
    page.keyboard.press("Enter")
    if page.inner_text("#v2LgSaved") not in ("Saving…", "Saved"):
        errors.append(f"[saved] indicator {page.inner_text('#v2LgSaved')!r} right after a change")
    page.wait_for_function("() => document.getElementById('v2LgSaved').textContent === 'Saved'", timeout=5000)
    page.reload(wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=30000)
    if names(page) != [fixture("2team")["teams"][0]["name"], "Persisted name"]:
        errors.append(f"[saved] after a reload: {names(page)}")
    if pressed(page) != ["true", "false"]:
        errors.append(f"[saved] my team not kept: {pressed(page)}")
    page.context.close()
    # A corrupt value is reported, not trusted, and replaced only when something is saved.
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[corrupt] ", init_script="try { if (!sessionStorage.getItem('seeded')) { localStorage.setItem('ddf.v2.workspaces', '{'); sessionStorage.setItem('seeded', '1'); } } catch (e) {}")
    if page.locator(TEAMS).count() != 0 or "could not be read" not in page.inner_text("#v2LgNotice"):
        errors.append(f"[corrupt] corrupt value: {page.locator(TEAMS).count()} teams, notice {page.inner_text('#v2LgNotice')!r}")
    if page.evaluate("() => localStorage.getItem('ddf.v2.workspaces')") != "{":
        errors.append("[corrupt] the corrupt value was overwritten before any change")
    page.click("#v2LgAdd")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.getElementById('v2LgSaved').textContent === 'Saved'", timeout=5000)
    try:
        replaced = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.workspaces')")).get("workspaces")
    except ValueError:
        replaced = None
    if not replaced:
        errors.append("[corrupt] the first change was not saved over the corrupt value")
    page.context.close()


def check_files(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[files] ")
    seed(page, "4team")
    # JEG-1213 moves transfer actions into the Import / export menu.
    page.locator("#v2LgTransfer > summary").click()
    with page.expect_download() as info:
        page.click("#v2LgDownload")
    download = info.value
    if not download.suggested_filename.endswith(".json"):
        errors.append(f"[files] download name {download.suggested_filename!r}")
    path = download.path()
    data = json.loads(open(path, encoding="utf-8").read())
    if len(data.get("teams", [])) != 4 or not data.get("id") or data["teams"][0]["entries"][0].get("key") is None:
        errors.append("[files] the downloaded file is not a league")
    # Load it back into a page with a different league: it asks, then replaces.
    page.evaluate("() => { const W = window.TradeValueWorkspace; W.store.replace(W.ops.addTeam(W.newWorkspace(), 'Other'), 'replace'); }")
    if page.locator(TEAMS).count() != 1:
        errors.append("[files] could not set up the replace case")
    page.set_input_files("#v2LgFile", path)
    page.wait_for_selector("#v2LgLoadYes")
    if page.locator(TEAMS).count() != 1:
        errors.append("[files] Load replaced the league without asking")
    page.click("#v2LgLoadYes")
    if page.locator(TEAMS).count() != 4:
        errors.append(f"[files] Load gave {page.locator(TEAMS).count()} teams")
    # A file that is not a league is refused with a sentence.
    bad = str(download.path()) + ".bad"
    open(bad, "w", encoding="utf-8").write('{"hello": 1}')
    page.set_input_files("#v2LgFile", bad)
    page.wait_for_function("() => document.getElementById('v2LgNotice').textContent.includes('not a saved league')", timeout=5000)
    page.context.close()


CHECKS = {"empty": check_empty, "list": check_list, "saved": check_saved, "files": check_files}


def run_checks(overrides=None, only=None) -> list[str]:
    errors: list[str] = []
    with browser_on_build() as (browser, base):
        for name, check in CHECKS.items():
            if only and name not in only:
                continue
            check(browser, base, overrides, errors)
    return errors


def caught(overrides, only):
    """The checks' verdict on a broken build: their errors, or the crash a missing control causes (a click that finds nothing)."""
    from playwright.sync_api import Error as PlaywrightError
    try:
        return run_checks(overrides, only)
    except PlaywrightError as exc:
        return [f"checks could not finish: {str(exc).splitlines()[0]}"]


class LeagueRenderTest(unittest.TestCase):
    def test_team_list(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        league = source("league.js")
        workspace = source("workspace.js")
        broken = {
            "the star does nothing": ({"league.js": league.replace('update(w => W.ops.setMyTeam(w, w.myTeamId === t.id ? null : t.id), "mine");', 'void 0;', 1)}, {"list"}),
            "Down moves the team up": ({"league.js": league.replace('W.ops.moveTeam(w, team.id, 1)', 'W.ops.moveTeam(w, team.id, -1)', 1)}, {"list"}),
            "Remove does not ask": ({"league.js": league.replace('confirmBox.hidden = false;', 'confirmBox.hidden = true; update(w => W.ops.removeTeam(w, team.id), "remove"); return;', 1)}, {"list"}),
            "nothing is saved": ({"workspace.js": workspace.replace('storage.setItem(STORAGE_KEY, serialize(ws));', 'void 0;', 1)}, {"saved"}),
            "a pasted player already on another team is added": ({"league.js": league.replace('if (holder) { onOther.push(`${row.name} (${holder.name})`); return; }', '', 1)}, {"list"}),
            "download carries no teams": ({"workspace.js": workspace.replace('const exportJson = ws => JSON.stringify(ws, null, 2);', 'const exportJson = ws => JSON.stringify({...ws, teams: []}, null, 2);', 1)}, {"files"}),
            "Load replaces without asking": ({"league.js": league.replace('if (!ws.teams.length) { applyImported(workspace, source); return; }', 'applyImported(workspace, source); return;', 1)}, {"files"}),
            "a corrupt value is overwritten at load": ({"workspace.js": workspace.replace("        if (loadStatus === \"unavailable\") setState(\"unavailable\");", "        if (loadStatus === \"corrupt\") storage.setItem(STORAGE_KEY, serialize(ws));\n        if (loadStatus === \"unavailable\") setState(\"unavailable\");", 1)}, {"saved"}),
            "no empty state": ({"league.js": league.replace('$("v2LgEmpty").hidden = ws.teams.length > 0;', '$("v2LgEmpty").hidden = true;', 1)}, {"empty"}),
        }
        for name, (overrides, only) in broken.items():
            with self.subTest(mutation=name):
                key = next(iter(overrides))
                self.assertNotEqual(overrides[key], source(key), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(caught(overrides, only), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
