"""JEG-1214: Compare edits a trade from saved rosters without editing those rosters."""
from __future__ import annotations

import functools
import sys
import unittest
from pathlib import Path

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


CARRY_SETUP = """(rows) => {
    const C = window.TradeValueCurveControls, TC = window.TradeValueTradeContext, W = window.TradeValueWorkspace;
    let ws = W.newWorkspace({id: 'sender'});
    ws = W.ops.addTeam(ws, 'Alpha', {id: 'tA', entries: rows.slice(0, 4), mine: true});
    ws = W.ops.addTeam(ws, 'Bravo', {id: 'tB', entries: rows.slice(4, 8)});
    const common = TC.commonFromPage({leagueQuery: window.TradeValueV2.leagueQuery(), valueContext: window.DDFOverrides.snapshotContext(),
        sources: TC.sourcesFromEngine(C.getSourceInfo())});
    const deal = {give: [rows[0].key], get: [rows[4].key]};
    const keys = TC.pricingKeys({mine: rows.slice(0, 4), theirs: rows.slice(4, 8), deal});
    const ctx = TC.fromLeague({common, deal, pricing: TC.modeledPricing(C, keys)}, ws);
    return `#compare-trade?give=${deal.give[0]}&get=${deal.get[0]}&${window.TradeValueV2.leagueQuery()}&tc=${TC.encodeTransfer(TC.toTransfer(ctx))}`;
}"""
CARRY_STATE = """() => {
    const card = document.getElementById('v2CConstruction');
    const keys = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => li.dataset.playerKey);
    return {mine: document.getElementById('v2CMyTeam')?.value ?? null, theirs: document.getElementById('v2CTheirTeam')?.value ?? null,
        ready: card.dataset.ready, carried: card.dataset.carried || null, level: card.dataset.benchLevel || null,
        status: document.getElementById('v2CRosterStatus')?.textContent || '', give: keys('v2GivePlayers'), get: keys('v2GetPlayers'),
        tc: /[?&]tc=/.test(location.hash), saved: JSON.stringify(window.TradeValueWorkspace.store.get().teams)};
}"""
CARRY_READOUT = """() => {
    const $ = id => document.getElementById(id);
    const strip = t => ['Alpha', 'Bravo', 'Me', 'Them', 'Your team (from the link)', 'Their team (from the link)'].reduce((x, n) => x.split(n).join('#'), t || '');
    const v = window.TradeValueV2.compare();
    return {giveValues: [...document.querySelectorAll('#v2GivePlayers .v2-trade-value')].map(x => x.textContent),
        getValues: [...document.querySelectorAll('#v2GetPlayers .v2-trade-value')].map(x => x.textContent),
        totals: [$('v2GiveTotal').hidden ? null : $('v2GiveTotal').textContent, $('v2GetTotal').hidden ? null : $('v2GetTotal').textContent],
        verdict: $('v2CVerdictTitle').textContent, table: $('v2CTable').hidden ? null : $('v2CTable').textContent,
        vorp: $('v2CVorpCard').hidden ? null : $('v2CVorpTable').textContent, deal: $('v2CDeal').hidden ? null : $('v2CDeal').textContent,
        story: $('v2CStory').hidden ? null : $('v2CStory').textContent,
        construction: $('v2CConstruction').dataset.ready === 'true' ? strip($('v2CConstructionBody').textContent) : null,
        view: {points: v.points.length, vorp: v.vorp.length, verdict: v.verdict.kind, totals: Boolean(v.totals), deal: Boolean(v.deal)}};
}"""
CARRY_REPLACE = """([rows, id, teams]) => {
    const W = window.TradeValueWorkspace;
    let ws = W.newWorkspace({id});
    teams.forEach(([name, tid, from, to, mine]) => { ws = W.ops.addTeam(ws, name, {id: tid, entries: rows.slice(from, to), mine}); });
    W.store.replace(ws, 'test');
}"""


V2_JS = Path(__file__).resolve().parents[1] / "app" / "v2" / "v2.js"


def _serve(body, ctype, route, *_):
    route.fulfill(status=200, content_type=ctype, body=body)


def check_carried_trade(v2_js=None):
    """JEG-1259 / JEG-1285: a trade carried to Compare (tc=) keeps its rosters, deal and numbers on another device, after a reload
    and under Swap; a mismatch holds it with the reasons and no number priced here; choosing a team ends it, and Cancel
    brings it back. Saved rosters are never written. v2_js: serve this page script instead (the guard's mutations)."""
    from playwright.sync_api import sync_playwright

    with _served() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                             executable_path=_render_env.chromium_executable(playwright))
        try:
            page = browser.new_page(viewport={"width": 1000, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "application/javascript"))
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_selector("#v2CRosters", state="attached")
            rows = page.evaluate("""() => window.TradeValueCurveControls.getAllRows()
                .filter(r => Number.isFinite(r.values.ddf_value) && ['RB','WR','TE'].includes(r.pos))
                .sort((a,b) => b.values.ddf_value - a.values.ddf_value).slice(0, 12)
                .map(r => ({key: String(r.player_key), name: r.name, pos: r.pos}))""")
            if len(rows) < 12:
                raise AssertionError("fixture needs twelve priced RB/WR/TE players")
            give, get = [rows[0]["key"]], [rows[4]["key"]]

            def go(hash_):
                page.evaluate("() => { location.hash = '#values'; }")
                page.wait_for_timeout(250)
                page.evaluate("h => { location.hash = h; }", hash_)
                page.wait_for_timeout(400)
                return page.evaluate(CARRY_STATE)

            def suppressed(label):
                r = page.evaluate(CARRY_READOUT)
                if r["giveValues"] != ["held"] or r["getValues"] != ["held"] or r["totals"] != [None, None]:
                    errors.append(f"{label}: values or totals shown on a held trade: {r['giveValues']} {r['getValues']} {r['totals']}")
                if "held" not in r["verdict"] or any(r[k] is not None for k in ("table", "vorp", "deal", "story", "construction")):
                    errors.append(f"{label}: a verdict or result shown on a held trade: {r['verdict']!r}")
                if r["view"] != {"points": 0, "vorp": 0, "verdict": None, "totals": False, "deal": False}:
                    errors.append(f"{label}: the compare view is still priced: {r['view']}")

            # The sender's own Compare readout on its saved teams, with no carried context: the numbers to keep.
            page.evaluate(CARRY_REPLACE, [rows, "sender", [["Alpha", "tA", 0, 4, True], ["Bravo", "tB", 4, 8, False]]])
            plain = page.evaluate("keys => `#compare-trade?give=${keys[0]}&get=${keys[1]}&${window.TradeValueV2.leagueQuery()}`", [give[0], get[0]])
            go(plain)
            expected = page.evaluate(CARRY_READOUT)
            if not (expected["totals"][0] and expected["table"] and expected["construction"]):
                raise AssertionError(f"sender readout incomplete: {expected}")
            link = page.evaluate(CARRY_SETUP, rows)
            league_link = page.evaluate("""(rows) => {
                const C = window.TradeValueCurveControls, TC = window.TradeValueTradeContext, ws = window.TradeValueWorkspace.store.get();
                const deal = {give: [rows[0].key], get: [rows[4].key]};
                const keys = TC.pricingKeys({mine: rows.slice(0, 4), theirs: rows.slice(4, 8), deal});
                const all = C.getAllRows();
                const pricing = {mode: 'league', levels: {ddf: TC.levelIdentity('ddf', {rows: all, keys}), market: TC.levelIdentity('market', {rows: all, keys})}, rostered: keys, reserve: []};
                const common = TC.commonFromPage({leagueQuery: window.TradeValueV2.leagueQuery(), valueContext: window.DDFOverrides.snapshotContext(),
                    sources: TC.sourcesFromEngine(C.getSourceInfo())});
                return `#compare-trade?give=${deal.give[0]}&get=${deal.get[0]}&${window.TradeValueV2.leagueQuery()}&tc=${TC.encodeTransfer(TC.toTransfer(TC.fromLeague({common, deal, pricing}, ws)))}`;
            }""", rows)

            # Another device: the same saved IDs hold other players (today's link prices those instead).
            page.evaluate(CARRY_REPLACE, [rows, "reader", [["Alpha", "tA", 8, 12, True], ["Bravo", "tB", 2, 6, False]]])
            saved = page.evaluate(CARRY_STATE)["saved"]
            s = go(link)
            if [s["mine"], s["theirs"], s["ready"], s["carried"], s["level"]] != ["carried-mine", "carried-theirs", "true", "ok", "modeled"]:
                errors.append(f"foreign device did not price the carried rosters: {s}")
            if page.evaluate(CARRY_READOUT) != expected:
                errors.append("foreign device shows other numbers than the sender for the same trade")
            if [s["give"], s["get"]] != [give, get] or not s["tc"] or s["saved"] != saved:
                errors.append(f"foreign device lost the deal or context, or wrote the saved rosters: {s}")
            go(page.evaluate("() => location.hash"))
            if page.evaluate(CARRY_READOUT) != expected:
                errors.append("reload changed the carried trade's numbers")
            # Holds: a changed override, and a trade priced at the league levels. No number or claim, players and reasons kept.
            before = page.evaluate("() => window.DDFOverrides.snapshotContext()")
            page.evaluate("key => window.DDFOverrides.applyLink(new URLSearchParams(`ov=${key}:42.5`))", rows[0]["key"])
            s = go(link)
            suppressed("override hold")
            if [s["mine"], s["theirs"], s["carried"], s["ready"]] != ["", "", "hold", "false"] or "overrides" not in s["status"] or not s["tc"]:
                errors.append(f"a changed override was not held with its reason: {s}")
            # Share while held: the address still carries the trade exactly as it arrived, so the next reader holds too.
            if page.evaluate("() => new URLSearchParams(location.hash.split('?')[1]).get('tc')") != link.split("tc=", 1)[1]:
                errors.append("sharing a held trade changed the carried context in the address")
            page.evaluate("snap => window.DDFOverrides.restoreContext(snap)", before)
            page.evaluate("() => window.DDFOverrides.applyLink(new URLSearchParams('basis=fantasycalc'))")
            s = go(link)
            suppressed("basis hold")
            if s["carried"] != "hold" or "basis" not in s["status"]:
                errors.append(f"a changed value basis was not held with its reason: {s}")
            page.evaluate("snap => window.DDFOverrides.restoreContext(snap)", before)
            s = go(league_link)
            suppressed("league-level hold")
            if s["carried"] != "hold" or "level" not in s["status"]:
                errors.append(f"a league-level trade was not held on the modeled bench: {s}")
            # Edit players, choose another saved team, Cancel: the carried trade comes back, through reload and Back.
            page.evaluate(CARRY_REPLACE, [rows, "reader3", [["Me", "r1", 0, 4, True], ["Them", "r2", 4, 8, False], ["Other", "r3", 8, 12, False]]])
            s = go(link)
            if [s["mine"], s["theirs"], s["carried"]] != ["r1", "r2", "ok"]:
                errors.append(f"exact roster match not shown as the reader's teams: {s}")
            page.locator("#v2CEditRosters").click()
            page.select_option("#v2CTheirTeam", "r3")
            s = page.evaluate(CARRY_STATE)
            if s["carried"] != "none" or s["tc"]:
                errors.append(f"choosing a team did not end the carried trade: {s}")
            page.locator("#v2CCancelRosterEdit").click()
            s = page.evaluate(CARRY_STATE)
            if [s["mine"], s["theirs"], s["carried"], s["give"], s["get"]] != ["r1", "r2", "ok", give, get] or not s["tc"]:
                errors.append(f"Cancel did not restore the carried trade: {s}")
            if page.evaluate(CARRY_READOUT) != expected:
                errors.append("Cancel restored other numbers")
            go(page.evaluate("() => location.hash"))
            if page.evaluate(CARRY_STATE)["carried"] != "ok":
                errors.append("reload after Cancel lost the carried trade")
            page.locator("#v2CSwap").click()
            s = page.evaluate(CARRY_STATE)
            if [s["mine"], s["theirs"], s["ready"], s["give"]] != ["r2", "r1", "true", get]:
                errors.append(f"Swap did not exchange the carried rosters with the trade: {s}")
            page.locator("#v2CSwap").click()
            # Swap inside an edit, then Cancel: the carried rosters and the deal come back the way round they were.
            page.locator("#v2CEditRosters").click()
            page.locator("#v2CSwap").click()
            page.locator("#v2CCancelRosterEdit").click()
            s = page.evaluate(CARRY_STATE)
            if [s["mine"], s["theirs"], s["carried"], s["give"], s["get"]] != ["r1", "r2", "ok", give, get]:
                errors.append(f"Swap then Cancel in an edit did not restore the carried trade: {s}")
            page.evaluate("() => { location.hash = '#values'; }")
            page.wait_for_timeout(250)
            page.go_back()
            page.wait_for_timeout(400)
            if page.evaluate(CARRY_STATE)["carried"] != "ok" or page.evaluate(CARRY_READOUT) != expected:
                errors.append("Back did not return to the carried trade")
            return errors
        finally:
            browser.close()


# JEG-1311: each JEG-1285 fix taken back out of v2.js must fail the check above (the failing-before proof, run in CI).
CARRIED_MUTATIONS = {
    "held trade still priced": [
        ("const ready = !held && giveRows.length > 0 && receiveRows.length > 0;", "const ready = giveRows.length > 0 && receiveRows.length > 0;"),
        ("totals: TR.shown && !held ?", "totals: TR.shown ?"),
        ("    if (compareView.held) return {kind: \"none\", title: \"No verdict while this trade is held\"", "    if (false) return {kind: \"none\", title: \"No verdict while this trade is held\""),
        ("      if (compareView.held) {\n        value.textContent = \"held\";", "      if (false) {\n        value.textContent = \"held\";"),
    ],
    "Cancel forgets the carried trade": [
        ("          carriedTrade = compareTeams.snapshot.carriedTrade || null;\n", ""),
    ],
}
CARRIED_EXPECT = {"held trade still priced": "override hold:", "Cancel forgets the carried trade": "Cancel did not restore"}


def mutated_v2(edits):
    js = V2_JS.read_text(encoding="utf-8")
    for old, new in edits:
        if js.count(old) != 1:
            raise AssertionError(f"mutation anchor is stale (found {js.count(old)} times): {old[:70]!r}")
        js = js.replace(old, new)
    return js


class CompareRosterRenderTest(unittest.TestCase):
    def test_roster_editing(self):
        self.assertEqual(check_roster_editing(), [])

    def test_carried_trade(self):
        self.assertEqual(check_carried_trade(), [])

    def test_carried_guard_fails_without_the_fixes(self):
        for name, edits in CARRIED_MUTATIONS.items():
            errors = check_carried_trade(mutated_v2(edits))
            caught = any(CARRIED_EXPECT[name] in e for e in errors)
            print(f"GUARD {'CAUGHT' if caught else 'NOT CAUGHT'}: {name} ({len(errors)} errors; first: {errors[0] if errors else '-'})",
                  file=sys.stderr, flush=True)
            self.assertTrue(caught, f"{name}: {errors}")
