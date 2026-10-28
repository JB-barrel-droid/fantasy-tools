"""JEG-1214: Compare edits a trade from saved rosters without editing those rosters."""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_v2_deal_read_render import _served


def setUpModule():
    _render_env.ensure_built()


def check_roster_editing():
    from playwright.sync_api import sync_playwright

    with _served() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                             executable_path=_render_env.chromium_executable(playwright))
        try:
            page = browser.new_page(viewport={"width": 1000, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_selector("#v2CRosters", state="attached")
            if not page.locator("#v2CRosters").is_hidden():
                errors.append("roster controls visible with no loaded teams")
            if page.locator("#v2CConstruction").get_attribute("data-ready") != "false":
                errors.append("missing rosters produced a guessed lineup")
            rows = page.evaluate("""() => window.TradeValueCurveControls.getAllRows()
                .filter(r => Number.isFinite(r.values.ddf_value) && ['RB','WR','TE'].includes(r.pos))
                .sort((a,b) => b.values.ddf_value - a.values.ddf_value).slice(0, 6)
                .map(r => ({key: String(r.player_key), name: r.name, pos: r.pos}))""")
            if len(rows) < 6:
                raise AssertionError("fixture needs six priced RB/WR/TE players")
            page.evaluate("""(key) => {
                const params = new URLSearchParams();
                params.set('basis', 'fantasycalc');
                params.set('ov', `${key}:42.5`);
                window.DDFOverrides.applyLink(params);
            }""", rows[0]["key"])
            override_before = page.evaluate("""() => JSON.stringify({basis: window.DDFOverrides.basis(),
                values: window.DDFOverrides.all()})""")
            page.evaluate("""(rows) => {
                const W = window.TradeValueWorkspace;
                let ws = W.ops.addTeam(W.newWorkspace(), 'Mine', {entries: rows.slice(0, 3), mine: true});
                ws = W.ops.addTeam(ws, 'Theirs', {entries: rows.slice(3, 6)});
                W.store.replace(ws, 'test');
            }""", rows)
            original = page.evaluate("() => JSON.stringify(window.TradeValueWorkspace.store.get().teams)")
            original_team_ids = [page.locator("#v2CMyTeam").input_value(), page.locator("#v2CTheirTeam").input_value()]
            if page.locator("#v2CEditRosters").count() != 1:
                raise AssertionError(f"roster picker did not open: errors={errors}, status={page.locator('#v2CRosters').inner_text()!r}")
            page.locator("#v2CEditRosters").click()
            mine = page.locator("#v2CRosterLists section").nth(0)
            theirs = page.locator("#v2CRosterLists section").nth(1)
            mine.locator("button").nth(0).click()
            mine.locator("button").nth(1).click()
            mine.locator("button").nth(0).click()
            mine.locator("button").nth(0).click()
            if mine.locator("button").nth(0).get_attribute("aria-pressed") != "true":
                errors.append("repeated roster toggle lost its accessible selected state")
            theirs.locator("button").nth(0).click()
            if page.locator("#v2GivePlayers li[data-player-key]").count() != 2:
                errors.append("2-for-1 give side did not update immediately")
            if page.locator("#v2GetPlayers li[data-player-key]").count() != 1:
                errors.append("receive side did not update immediately")
            if page.locator("#v2CVerdictTitle").inner_text() == "No verdict yet":
                errors.append("verdict did not update for a complete trade")
            if page.locator("#v2CTable tbody tr[data-source='ddf_value']").count() != 1:
                errors.append("DDF Value comparison missing after roster edits")
            parity = page.evaluate("""() => {
                const rows = new Map(window.TradeValueCurveControls.getAllRows().map(r => [String(r.player_key), r]));
                const sum = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)]
                    .reduce((n, li) => n + rows.get(li.dataset.playerKey).values.ddf_value, 0);
                const tr = document.querySelector('#v2CTable tbody tr[data-source="ddf_value"]');
                return {give: sum('v2GivePlayers'), receive: sum('v2GetPlayers'),
                    shownGive: tr.querySelector('[data-col="give"]').textContent,
                    shownReceive: tr.querySelector('[data-col="receive"]').textContent};
            }""")
            if parity["shownGive"] != f"{parity['give']:.1f}" or parity["shownReceive"] != f"{parity['receive']:.1f}":
                errors.append(f"trade values diverged from engine: {parity}")
            if page.locator("#v2CConstruction").get_attribute("data-ready") != "true":
                errors.append("two loaded rosters did not render construction")
            if page.locator("#v2CConstruction .v2-lineup-comparison").count() != 2:
                errors.append("both before/after lineup tables are required")
            if "Opens 1 roster/bench spot" not in page.locator("#v2CConstruction").inner_text():
                errors.append("2-for-1 did not show the opened spot")
            if "Uses 1 roster/bench spot" not in page.locator("#v2CConstruction").inner_text():
                errors.append("2-for-1 did not show the consumed spot")
            page.locator("#v2CConstruction .v2-lineup-bench-toggle").first.click()
            if page.locator("#v2CConstruction .v2-lineup-bench-toggle").first.get_attribute("aria-expanded") != "true":
                errors.append("bench expansion did not work")
            page.locator("#v2CCancelRosterEdit").click()
            if page.locator("#v2GivePlayers li[data-player-key]").count() or page.locator("#v2GetPlayers li[data-player-key]").count():
                errors.append("Cancel did not restore the prior trade")
            page.locator("#v2CEditRosters").click()
            mine.locator("button").nth(0).click()
            theirs.locator("button").nth(0).click()
            page.locator("#v2CEditRosters").click()
            page.locator("#v2CEditRosters").click()
            if page.locator("#v2GivePlayers li[data-player-key]").count() != 1:
                errors.append("Back and edit lost the trade")
            before_swap = page.evaluate("""() => ({give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(x => x.dataset.playerKey),
                get: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(x => x.dataset.playerKey)})""")
            page.locator("#v2CSwap").click()
            if page.locator("#v2CMyTeam").input_value() == page.locator("#v2CTheirTeam").input_value():
                errors.append("Swap did not preserve distinct teams")
            page.locator("#v2CCancelRosterEdit").click()
            restored = page.evaluate("""() => ({give: [...document.querySelectorAll('#v2GivePlayers li[data-player-key]')].map(x => x.dataset.playerKey),
                get: [...document.querySelectorAll('#v2GetPlayers li[data-player-key]')].map(x => x.dataset.playerKey)})""")
            if restored != before_swap or [page.locator("#v2CMyTeam").input_value(), page.locator("#v2CTheirTeam").input_value()] != original_team_ids:
                errors.append("Swap then Cancel did not restore trade and team IDs atomically")
            if page.locator("#v2CConstruction").get_attribute("data-ready") != "true":
                errors.append("Swap then Cancel hid valid lineup construction")
            page.locator("#v2CSwap").click()
            if page.evaluate("() => JSON.stringify(window.TradeValueWorkspace.store.get().teams)") != original:
                errors.append("Compare changed the saved league rosters")
            if page.evaluate("""() => JSON.stringify({basis: window.DDFOverrides.basis(),
                values: window.DDFOverrides.all()})""") != override_before:
                errors.append("Compare changed the custom value basis or player override")
            page.evaluate("() => { location.hash = '#values'; }")
            page.evaluate("() => { location.hash = '#compare-trade'; }")
            page.wait_for_timeout(250)
            if page.locator("#v2GivePlayers li[data-player-key]").count() != 1:
                errors.append("tab round trip lost the chosen trade")
            page.locator("#v2CEditRosters").click()
            page.evaluate("key => { location.hash = `#compare-trade?give=${key[0]}&get=${key[1]}`; }", [rows[4]["key"], rows[1]["key"]])
            page.wait_for_timeout(300)
            if page.locator("#v2CCancelRosterEdit").count() or page.locator("#v2CEditRosters").get_attribute("aria-expanded") != "false":
                errors.append("new Compare hash did not invalidate stale edit session")
            if page.locator("#v2GivePlayers li[data-player-key]").first.get_attribute("data-player-key") != rows[4]["key"]:
                errors.append("new Compare hash did not replace the trade")
            page.locator("#v2CEditRosters").click()
            page.locator("#v2CRosterLists section").first.locator("button").nth(0).click()
            page.locator("#v2CCancelRosterEdit").click()
            if page.locator("#v2GivePlayers li[data-player-key]").first.get_attribute("data-player-key") != rows[4]["key"]:
                errors.append("Cancel after a new Compare hash restored an older trade")
            page.locator("#v2CEditRosters").click()
            page.evaluate("""keys => window.DDFAssist.applyLink(`give=${keys[0]}&get=${keys[1]}`)""",
                          [rows[5]["key"], rows[2]["key"]])
            if page.locator("#v2CCancelRosterEdit").count():
                errors.append("assist setTrade did not invalidate stale edit session")
            if page.locator("#v2GivePlayers li[data-player-key]").first.get_attribute("data-player-key") != rows[5]["key"]:
                errors.append("assist setTrade did not replace the trade")
            page.locator("#v2CEditRosters").click()
            page.locator("#v2CRosterLists section").first.locator("button").nth(0).click()
            page.locator("#v2CCancelRosterEdit").click()
            if page.locator("#v2GivePlayers li[data-player-key]").first.get_attribute("data-player-key") != rows[5]["key"]:
                errors.append("Cancel after assist setTrade restored an older trade")
            page.evaluate("""() => {
                const W = window.TradeValueWorkspace;
                W.store.update(ws => W.ops.removeTeam(ws, ws.teams.find(t => t.id !== ws.myTeamId).id), 'test-remove');
            }""")
            if page.locator("#v2CConstruction").get_attribute("data-ready") != "false":
                errors.append("removing a roster left guessed construction visible")
            return errors
        finally:
            browser.close()


class CompareRosterRenderTest(unittest.TestCase):
    def test_roster_editing(self):
        self.assertEqual(check_roster_editing(), [])
