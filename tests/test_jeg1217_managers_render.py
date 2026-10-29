"""JEG-1217: the Managers card on Find a trade captures profiles and exclusions, saves them, and changes no trade numbers;
the Trade ideas card under it lists only your gains from Trade opportunities, best first, and drops won't-trade managers.

Runs on the built page (tests/_league_render.py). Desktop and phone width.
"""
from __future__ import annotations

import json
import unittest

from tests._league_render import browser_on_build, open_page, seed, wait_opps

IDEAS = """() => [...document.querySelectorAll('#v2MiList li.v2-mi-item')].map(li => ({id: li.dataset.tradeId, band: li.dataset.band, opp: li.querySelector('.v2-mi-opp').textContent}))"""
IDEAS_MODEL = """() => { const out = window.TradeValueTradeIdeas.compute(); return out && {recs: out.recommendations.map(r => ({id: r.id, gain: r.ourGain, band: r.band, opponentId: String(r.opponentId)})), stretch: out.stretch.map(r => r.band)}; }"""
OPP_ROWS = """() => (window.TradeValueLeague.ui.result ? window.TradeValueLeague.ui.result.rows : []).map(r => r.id + ':' + r.give.map(p => p.player_key).join(',') + '>' + r.receive.map(p => p.player_key).join(','))"""


class ManagersCardRenderTest(unittest.TestCase):
    def test_capture_exclusion_reload_and_no_value_change(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    context = browser.new_context(viewport={"width": width, "height": 844}, accept_downloads=True)
                    page = open_page(browser, base, width=width, height=844, errors=errors, context=context)
                    seed(page, "4team")
                    wait_opps(page, timeout=90000)
                    before = page.evaluate(OPP_ROWS)
                    card = page.locator("#v2LgManagers")
                    card.wait_for(state="visible")
                    # Sits between Team summary and Trade opportunities.
                    order = page.evaluate("() => [...document.querySelectorAll('#v2LgSummary, #v2LgManagers, #v2LgOpps')].map(n => n.id)")
                    self.assertEqual(order, ["v2LgSummary", "v2LgManagers", "v2LgOpps"])
                    ids = page.evaluate("() => { const ws = window.TradeValueWorkspace.store.get(); return {mine: ws.myTeamId, all: ws.teams.map(t => t.id)}; }")
                    listed = page.evaluate("() => [...document.querySelectorAll('#v2MgTeams li')].map(li => li.dataset.teamId)")
                    self.assertEqual(listed, [t for t in ids["all"] if t != ids["mine"]], "every team but mine, in league order")
                    first = card.locator("li.v2-mg-team").first
                    team_id = first.get_attribute("data-team-id")
                    self.assertIn("Not described yet", first.locator(".v2-mg-summary").text_content())
                    # Describe: keyboard-reachable disclosure with labelled selects.
                    first.locator("details.v2-mg-describe > summary").click()
                    first.locator("select[id^='v2MgA-draft-']").select_option("strong")
                    first.locator("select[id^='v2MgA-names-']").select_option("some")
                    first.locator("select[id^='v2MgConf-']").select_option("low")
                    # No free text, and every box starts unticked (Jeremy, 2026-10-29).
                    self.assertEqual(page.locator("#v2LgManagers textarea, #v2LgManagers input[type=text]").count(), 0)
                    self.assertEqual(page.locator("#v2LgManagers input.v2-mg-tag:checked").count(), 0)
                    self.assertEqual(first.locator("input.v2-mg-tag").count(), 6)
                    first.locator("input[id^='v2MgT-rookies-']").check()
                    summary = first.locator(".v2-mg-summary").text_content()
                    self.assertIn("Mixed", summary)
                    self.assertIn("draft capital (a lot)", summary)
                    self.assertIn("A guess", summary)
                    self.assertIn("Likes rookies", summary)
                    unlabeled = page.evaluate("() => [...document.querySelectorAll('#v2LgManagers select, #v2LgManagers textarea, #v2LgManagers input[type=checkbox]')].filter(n => !n.labels || !n.labels.length).length")
                    self.assertEqual(unlabeled, 0)
                    # Exclusion.
                    second = card.locator("li.v2-mg-team").nth(1)
                    second_id = second.get_attribute("data-team-id")
                    second.locator("input.v2-mg-excl").check()
                    self.assertIn("Won't trade", second.locator(".v2-mg-summary").text_content())
                    eligible = page.evaluate("() => { const M = window.TradeValueManagerProfiles; return M.eligibleOpponents(M.store.get(), window.TradeValueWorkspace.store.get()).map(r => r.teamId); }")
                    self.assertNotIn(second_id, eligible)
                    self.assertNotIn(ids["mine"], eligible)
                    # No trade numbers moved (stage 1 changes nothing in Trade opportunities).
                    page.wait_for_timeout(500)
                    self.assertEqual(page.evaluate(OPP_ROWS), before)
                    # Trade ideas: between Managers and Trade opportunities; only rows of Trade opportunities, your gains, best first.
                    page.wait_for_timeout(300)
                    order = page.evaluate("() => [...document.querySelectorAll('#v2LgManagers, #v2LgIdeas, #v2LgOpps')].map(n => n.id)")
                    self.assertEqual(order, ["v2LgManagers", "v2LgIdeas", "v2LgOpps"])
                    model = page.evaluate(IDEAS_MODEL)
                    self.assertIsNotNone(model)
                    opp_ids = {row.split(":")[0] for row in before}
                    recs = model["recs"]
                    self.assertTrue(all(r["id"] in opp_ids for r in recs), "every idea is a Trade opportunities row")
                    self.assertTrue(all(r["gain"] > 0 for r in recs), "every idea is a gain for you")
                    self.assertEqual([r["gain"] for r in recs], sorted((r["gain"] for r in recs), reverse=True), "best gain first")
                    self.assertTrue(all(r["band"] in ("likely", "possible") for r in recs))
                    self.assertTrue(all(b == "longShot" for b in model["stretch"]))
                    self.assertNotIn(second_id, {r["opponentId"] for r in recs}, "won't-trade managers get no ideas")
                    shown = page.evaluate(IDEAS)
                    self.assertEqual([x["id"] for x in shown], [r["id"] for r in recs][:10])
                    if not recs:
                        self.assertTrue(page.locator("#v2MiEmpty").is_visible())
                    else:
                        why = page.locator("#v2MiList li.v2-mi-item").first.locator("details.v2-mi-why")
                        why.locator("summary").click()
                        self.assertIn("DDF Value", why.text_content())
                    self.assertEqual(page.evaluate(OPP_ROWS), before, "Trade ideas change nothing in Trade opportunities")
                    # Saved and reloaded; the league itself is unchanged.
                    page.evaluate("() => { window.TradeValueManagerProfiles.store.flush(); window.TradeValueWorkspace.store.flush(); }")
                    page.reload(wait_until="networkidle")
                    page.wait_for_selector("#v2LgManagers:not([hidden])", timeout=60000)
                    stored = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.managerProfiles')"))
                    league_id = page.evaluate("() => window.TradeValueWorkspace.store.get().id")
                    self.assertEqual(stored["leagues"][league_id][team_id]["anchors"]["draft"], "strong")
                    self.assertEqual(stored["leagues"][league_id][team_id]["tags"], ["rookies"])
                    self.assertTrue(stored["leagues"][league_id][second_id]["excluded"])
                    self.assertTrue(page.locator(f"#v2LgManagers li[data-team-id='{second_id}'] input.v2-mg-excl").is_checked())
                    saved_league = page.evaluate("() => localStorage.getItem('ddf.v2.workspaces')")
                    self.assertNotIn("anchors", saved_league, "profiles are not written into the saved league")
                    self.assertEqual([t["id"] for t in json.loads(saved_league)["workspaces"][0]["teams"]], ids["all"])
                    # Rename keeps the profile.
                    page.evaluate(f"() => window.TradeValueWorkspace.store.update(w => window.TradeValueWorkspace.ops.renameTeam(w, {json.dumps(team_id)}, 'Renamed Manager'))")
                    row = page.locator(f"#v2LgManagers li[data-team-id='{team_id}']")
                    self.assertEqual(row.locator(".v2-mg-name").text_content(), "Renamed Manager")
                    self.assertIn("Mixed", row.locator(".v2-mg-summary").text_content())
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 400)
                        target = page.evaluate("() => { const r = document.querySelector('#v2LgManagers .v2-mg-excl-label').getBoundingClientRect(); return r.height; }")
                        self.assertGreaterEqual(target, 44)
                        self.assertLessEqual(page.evaluate("() => document.getElementById('v2LgIdeas').scrollWidth - document.getElementById('v2LgIdeas').clientWidth"), 0)
                    self.assertEqual(errors, [])
                    context.close()


# JEG-1255: make the profiles store's writes fail (full) while window.__failProfiles is true; everything else saves.
FAIL_PROFILE_WRITES = """(() => {
  const set = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    if (window.__failProfiles && key === 'ddf.v2.managerProfiles') throw new DOMException('full', 'QuotaExceededError');
    return set.call(this, key, value);
  };
})();"""
SHOWN = """() => [...document.querySelectorAll('#v2MiList li.v2-mi-item')].map(li => ({id: li.dataset.tradeId, opp: li.querySelector('.v2-mi-opp').textContent,
  gain: li.querySelector('.v2-mi-gain').textContent, health: (li.querySelector('.v2-mi-health') || {}).textContent || ''}))"""
VIEWS = """() => window.TradeValueTradeIdeas.compute().recommendations.slice(0, 10).map(r => window.TradeValueManagerRecs.view(r))"""


class TradeIdeasRedrawTest(unittest.TestCase):
    """JEG-1255: roster warnings shown, hide/show, rename and value-only redraws, a kept earlier note, and a failed save."""

    def test_warnings_redraws_legacy_note_and_save_failure(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    context = browser.new_context(viewport={"width": width, "height": 844}, accept_downloads=True)
                    page = open_page(browser, base, width=width, height=844, errors=errors, context=context, init_script=FAIL_PROFILE_WRITES)
                    seed(page, "4team")
                    wait_opps(page, timeout=90000)
                    page.wait_for_selector("#v2LgIdeas:not([hidden]) #v2MiList li.v2-mi-item", timeout=30000)
                    page.wait_for_timeout(200)

                    # 59c00401: "None of the usual anchors" only when every anchor is marked doesn't care; one "none" is named.
                    summaries = page.evaluate("""() => { const M = window.TradeValueManagerProfiles, C = window.TradeValueManagersCard;
                      const say = anchors => C.summaryText({description: M.describe({...M.newProfile('x'), anchors: {...M.newProfile('x').anchors, ...anchors}})});
                      return [say({draft: 'none'}), say({draft: 'none', names: 'none'}), say(Object.fromEntries(M.ANCHORS.map(a => [a, 'none'])))]; }""")
                    self.assertEqual(summaries, ["Doesn't care about draft capital; the rest not set.",
                                                 "Doesn't care about draft capital and big names; the rest not set.", "None of the usual anchors."])

                    # Every shown idea carries its row's roster warnings, exactly as the model words them.
                    shown = page.evaluate(SHOWN)
                    views = page.evaluate(VIEWS)
                    self.assertEqual([(x["id"], x["health"]) for x in shown], [(v["id"], v["health"]) for v in views])
                    first = shown[0]["id"]
                    top = shown[0]
                    # Rename the manager of the top idea: Trade ideas shows the new name, like the Managers card.
                    opp_id = page.evaluate("(id) => String(window.TradeValueLeague.ui.result.rows.find(r => r.id === id).opponentId)", first)
                    page.evaluate("(id) => window.TradeValueWorkspace.store.update(w => window.TradeValueWorkspace.ops.renameTeam(w, id, 'Renamed Rival'))", opp_id)
                    page.wait_for_function("""(id) => [...document.querySelectorAll('#v2MiList li.v2-mi-item')].some(li => li.querySelector('.v2-mi-opp').textContent === 'Renamed Rival')
                      && document.querySelector(`#v2LgManagers li[data-team-id="${id}"] .v2-mg-name`).textContent === 'Renamed Rival'""", arg=opp_id, timeout=30000)
                    wait_opps(page, timeout=90000)
                    page.wait_for_timeout(200)
                    stale = page.evaluate("""(id) => [...document.querySelectorAll('#v2MiList li.v2-mi-item')].map(li => ({opp: li.querySelector('.v2-mi-opp').textContent,
                      oid: String((window.TradeValueLeague.ui.result.rows.find(r => r.id === li.dataset.tradeId) || {}).opponentId)})).filter(x => x.oid === id && x.opp !== 'Renamed Rival')""", opp_id)
                    self.assertEqual(stale, [], "no idea keeps the old name")

                    # Value-only change: same id and order, the gain on screen follows.
                    top = next(x for x in page.evaluate(SHOWN) if x["id"] == first)
                    before_gain = top["gain"]
                    page.evaluate("""(id) => { const row = window.TradeValueLeague.ui.result.rows.find(r => r.id === id);
                      row.edge += 0.3; window.TradeValueTradeIdeas.render(); }""", first)
                    top = next(x for x in page.evaluate(SHOWN) if x["id"] == first)
                    self.assertNotEqual(top["gain"], before_gain)
                    self.assertEqual(top["gain"], next(v for v in page.evaluate(VIEWS) if v["id"] == first)["gain"])

                    # Hide and show with unchanged results: the ideas come back.
                    listed = [x["id"] for x in page.evaluate(SHOWN)]
                    page.evaluate("() => { document.getElementById('v2LgOpps').hidden = true; }")
                    page.wait_for_function("() => document.getElementById('v2LgIdeas').hidden")
                    self.assertEqual(page.evaluate(SHOWN), [])
                    page.evaluate("() => { document.getElementById('v2LgOpps').hidden = false; }")
                    page.wait_for_function("() => document.querySelectorAll('#v2MiList li.v2-mi-item').length > 0", timeout=5000)
                    self.assertEqual([x["id"] for x in page.evaluate(SHOWN)], listed)

                    # An unjudged row (no fit for either team) still shows, with both sides named.
                    page.evaluate("""(id) => { const row = window.TradeValueLeague.ui.result.rows.find(r => r.id === id);
                      row.ours = null; row.theirs = null; window.TradeValueTradeIdeas.render(); }""", first)
                    top = next(x for x in page.evaluate(SHOWN) if x["id"] == first)
                    self.assertIn("Your side: roster fit not judged.", top["health"])
                    self.assertIn("'s side: roster fit not judged.", top["health"])

                    # A note and Other preferences level saved by the earlier build are kept and shown read-only.
                    ws_id = page.evaluate("() => window.TradeValueWorkspace.store.get().id")
                    note = "Pays up for rookies; ignores QBs"
                    legacy = {"v": 1, "leagues": {ws_id: {opp_id: {"teamId": opp_id, "anchors": {"draft": "some", "market": "unknown", "rankings": "unknown",
                              "names": "unknown", "subjective": "strong"}, "confidence": "low", "excluded": False, "note": note, "source": "user",
                              "createdAt": 1, "updatedAt": 2}}}}
                    page.evaluate("(text) => { window.TradeValueWorkspace.store.flush(); localStorage.setItem('ddf.v2.managerProfiles', text); }", json.dumps(legacy))
                    page.reload(wait_until="networkidle")
                    page.wait_for_selector("#v2LgManagers:not([hidden])", timeout=60000)
                    row = page.locator(f"#v2LgManagers li[data-team-id='{opp_id}']")
                    self.assertIn("Earlier note kept", row.locator(".v2-mg-summary").text_content())
                    row.locator("details.v2-mg-describe > summary").click()
                    kept = row.locator(".v2-mg-kept")
                    self.assertTrue(kept.is_visible())
                    self.assertIn("Kept from an earlier note", kept.text_content())
                    self.assertIn(note, kept.text_content())
                    self.assertIn("Other preferences: A lot", kept.text_content())
                    self.assertEqual(page.locator("#v2LgManagers textarea, #v2LgManagers input[type=text]").count(), 0, "still no free text")
                    row.locator("input[id^='v2MgT-rookies-']").check()
                    page.evaluate("() => window.TradeValueManagerProfiles.store.flush()")
                    stored = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.managerProfiles')"))["leagues"][ws_id][opp_id]
                    self.assertEqual(stored["note"], note)
                    self.assertEqual(stored["anchors"]["subjective"], "strong")
                    self.assertEqual(stored["tags"], ["rookies"])
                    self.assertEqual(page.locator("#v2MgSave").text_content(), "Saved on this device.")

                    # The browser refuses to save: the card says so and points at Download; the next good save clears it.
                    page.evaluate("() => { window.__failProfiles = true; }")
                    row.locator("input[id^='v2MgT-winNow-']").check()
                    page.wait_for_function("() => document.getElementById('v2MgSave').textContent.startsWith('Not saved')", timeout=5000)
                    message = page.locator("#v2MgSave").text_content()
                    self.assertIn("storage is full", message)
                    self.assertIn("Download profiles", message)
                    self.assertTrue(page.locator("#v2MgDownload").is_visible())
                    self.assertNotIn("Saved on this device", page.locator("#v2LgManagers").text_content())
                    page.evaluate("() => { window.__failProfiles = false; }")
                    row.locator("input[id^='v2MgT-picks-']").check()
                    page.wait_for_function("() => document.getElementById('v2MgSave').textContent === 'Saved on this device.'", timeout=5000)
                    stored = json.loads(page.evaluate("() => localStorage.getItem('ddf.v2.managerProfiles')"))["leagues"][ws_id][opp_id]
                    self.assertEqual(stored["tags"], ["rookies", "picks", "winNow"], "the change made while failing is saved on recovery")
                    self.assertEqual(stored["note"], note)
                    if width == 390:
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 400)
                    self.assertEqual(errors, [])
                    context.close()


if __name__ == "__main__":
    unittest.main()
