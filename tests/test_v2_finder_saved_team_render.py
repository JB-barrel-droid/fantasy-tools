"""JEG-1219: saved-team selection never writes a working copy into League."""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page, source


def setUpModule():
    _render_env.ensure_built()


SEED = """() => {
  const W = window.TradeValueWorkspace;
  const rows = window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values?.ddf_value));
  const p = i => ({key: String(rows[i].player_key), name: rows[i].name, pos: rows[i].pos, team: rows[i].team});
  let w = W.newWorkspace({id: 'picker-league', name: 'Picker league'});
  w = W.ops.addTeam(w, 'Same name', {id: 'alpha', entries: [p(0), p(1)]});
  w = W.ops.addTeam(w, 'Same name', {id: 'beta', entries: [p(2), {key:'x:K:test', name:'Test kicker', pos:'K'},
    {key:'missing-price', name:'Unavailable player', pos:'WR'}]});
  w = W.ops.addTeam(w, 'Empty team', {id: 'empty', entries: []});
  w = W.ops.setMyTeam(w, 'alpha');
  W.store.replace(w, 'replace'); W.store.flush();
  return {teams: w.teams, mine: w.teams[0].entries, theirs: [p(3)], linkMine: [p(4)], linkTheirs: [p(5)]};
}"""
STATE = """() => ({mine: window.TradeValueFinder.ui.getMine(), theirs: window.TradeValueFinder.ui.getTheirs(),
  teams: window.TradeValueWorkspace.store.get().teams, marked: window.TradeValueWorkspace.store.get().myTeamId,
  selected: document.getElementById('v2FindSavedTeam').value,
  theirSelected: document.getElementById('v2FindTheirSavedTeam').value})"""


class FinderSavedTeamRenderTest(unittest.TestCase):
    def test_fresh_backup_controls_click_keyboard_bounds_and_persistence(self):
        # Do not reset/import/apply settings before these checks: those paths repaired the old broken initial DOM.
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    errors = []
                    page = open_page(browser, base, width=width, errors=errors,
                                     init_script="window.initialStorage = [localStorage.length, sessionStorage.length];")
                    page.evaluate("location.hash = '#find-trade'")
                    self.assertEqual(page.evaluate('window.initialStorage'), [0, 0])
                    for pos in ('QB', 'RB', 'WR', 'TE'):
                        up = page.locator(f'#v2FindBackups{pos}Up')
                        down = page.locator(f'#v2FindBackups{pos}Down')
                        readout = page.locator(f'#v2FindBackups{pos}')
                        self.assertEqual(readout.inner_text(), '0')
                        self.assertTrue(down.is_disabled())
                        self.assertFalse(up.is_disabled(), f'{pos} + must work before any settings update')
                        self.assertFalse(up.evaluate("button => button.hasAttribute('disabled')"))
                        if pos in ('QB', 'TE'):
                            up.click()
                        else:
                            up.focus()
                            page.keyboard.press('Enter' if pos == 'RB' else 'Space')
                        self.assertEqual(readout.inner_text(), '1')
                        self.assertFalse(down.is_disabled())
                    up = page.locator('#v2FindBackupsRBUp')
                    down = page.locator('#v2FindBackupsRBDown')
                    readout = page.locator('#v2FindBackupsRB')
                    for _ in range(19):
                        up.click()
                    self.assertEqual(readout.inner_text(), '20')
                    self.assertTrue(up.is_disabled())
                    down.focus()
                    page.keyboard.press('Enter')
                    self.assertEqual(readout.inner_text(), '19')
                    self.assertFalse(up.is_disabled())
                    page.evaluate('window.TradeValueWorkspace.store.flush()')
                    page.reload(wait_until='networkidle')
                    self.assertEqual(page.locator('#v2FindBackupsRB').inner_text(), '19')
                    self.assertFalse(page.locator('#v2FindBackupsRBUp').is_disabled())
                    self.assertFalse(page.locator('#v2FindBackupsRBDown').is_disabled())
                    page.locator('.v2-find-advanced summary').click()
                    page.locator('#v2FindResetSettings').click()
                    for pos in ('QB', 'RB', 'WR', 'TE'):
                        self.assertEqual(page.locator(f'#v2FindBackups{pos}').inner_text(), '0')
                        self.assertTrue(page.locator(f'#v2FindBackups{pos}Down').is_disabled())
                        self.assertFalse(page.locator(f'#v2FindBackups{pos}Up').is_disabled())
                    page.locator('#v2FindBackupsRBUp').focus()
                    page.keyboard.press('Space')
                    page.locator('#v2FindBackupsRBDown').focus()
                    page.keyboard.press('Enter')
                    self.assertEqual(page.locator('#v2FindBackupsRB').inner_text(), '0')
                    self.assertTrue(page.locator('#v2FindBackupsRBDown').is_disabled())
                    link = page.evaluate("""() => {
                      const rows = window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values?.ddf_value));
                      return window.TradeValueFinder.encodeFinderHash({mine: [String(rows[0].player_key)],
                        theirs: [String(rows[1].player_key)], guardrails: {minBackups: {TE: 20, WR: 2}}});
                    }""")
                    page.goto(base + link, wait_until='networkidle')
                    self.assertEqual(page.locator('#v2FindBackupsTE').inner_text(), '20')
                    self.assertTrue(page.locator('#v2FindBackupsTEUp').is_disabled())
                    self.assertFalse(page.locator('#v2FindBackupsTEDown').is_disabled())
                    self.assertEqual(page.locator('#v2FindBackupsWR').inner_text(), '2')
                    self.assertFalse(page.locator('#v2FindBackupsWRUp').is_disabled())
                    page.locator('#v2FindBackupsWRUp').click()
                    self.assertEqual(page.locator('#v2FindBackupsWR').inner_text(), '3')
                    page.reload(wait_until='networkidle')
                    self.assertEqual(page.locator('#v2FindBackupsTE').inner_text(), '20')
                    self.assertEqual(page.locator('#v2FindBackupsWR').inner_text(), '2')
                    # Reopening a link replays its controls; a plain route reload retains the reader's saved choice.
                    page.goto(base + '#find-trade', wait_until='networkidle')
                    page.locator('#v2FindBackupsWRUp').click()
                    page.evaluate('window.TradeValueWorkspace.store.flush()')
                    page.reload(wait_until='networkidle')
                    self.assertEqual(page.locator('#v2FindBackupsWR').inner_text(), '3')
                    self.assertEqual(errors, [])
                    page.context.close()

    def opened(self, browser, base, width=1366, context=None, overrides=None):
        page = open_page(browser, base, width=width, context=context, overrides=overrides)
        page.evaluate("location.hash = '#find-trade'")
        self.assertEqual(page.locator('#v2FindSavedTeam').count(), 1, 'saved-team picker missing')
        self.assertEqual(page.locator('#v2FindTheirSavedTeam').count(), 1, 'opponent saved-team picker missing')
        return page

    def test_both_sides_starred_default_swap_and_no_same_team(self):
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base)
            fx = page.evaluate(SEED)
            state = page.evaluate(STATE)
            self.assertEqual(state['selected'], 'alpha')
            self.assertEqual(state['mine'], fx['mine'])
            self.assertEqual(state['theirSelected'], '')
            self.assertEqual(state['theirs'], [])
            # The hidden finder is built at app startup: an untouched default follows the League star until engaged.
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'beta')); }")
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            self.assertEqual(page.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'alpha')); }")
            page.locator('#v2FindTheirSavedTeam').select_option('beta')
            state = page.evaluate(STATE)
            self.assertEqual(state['mine'], fx['mine'])
            self.assertEqual(state['theirs'], fx['teams'][1]['entries'])
            self.assertEqual(state['teams'], fx['teams'])
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'empty')); }")
            self.assertEqual(page.evaluate(STATE)['selected'], 'alpha')
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'beta')
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'alpha')); }")
            self.assertTrue(page.locator('#v2FindSavedTeam option[value=beta]').evaluate('option => option.disabled'))
            self.assertTrue(page.locator('#v2FindTheirSavedTeam option[value=alpha]').evaluate('option => option.disabled'))
            page.locator('#v2FindTheirSavedTeam').select_option('empty')
            self.assertEqual(page.evaluate(STATE)['theirs'], [])
            self.assertEqual(page.evaluate(STATE)['mine'], fx['mine'])
            page.locator('#v2FindUndo').click()
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'beta')
            page.locator('#v2FindSwap').click()
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'alpha')
            page.reload(wait_until='networkidle')
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'alpha')
            self.assertEqual(page.evaluate(STATE)['marked'], 'alpha')
            self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            # Guard malformed/old session state too, even if a browser bypasses disabled options.
            page.evaluate("""fx => sessionStorage.setItem('ddf.v2.finder-roster-copy', JSON.stringify({v:1,
              workspaceId:'picker-league', teamId:'alpha', theirTeamId:'alpha', mine:fx.mine, theirs:fx.mine}))""", fx)
            page.reload(wait_until='networkidle')
            page.locator('#v2FindGo').click()
            self.assertIn('different saved teams', page.locator('#v2FindOut').inner_text())
            self.assertEqual(page.locator('#v2FindList').count(), 0)
            self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            page.context.close()

    def test_no_star_manual_fallback_and_fresh_link_precedence(self):
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base)
            fx = page.evaluate(SEED)
            page.evaluate("""() => { const W=window.TradeValueWorkspace;
              W.store.update(w=>W.ops.setMyTeam(w,null)); W.store.flush();
              sessionStorage.removeItem('ddf.v2.finder-roster-copy'); }""")
            page.reload(wait_until='networkidle')
            state = page.evaluate(STATE)
            self.assertEqual(state['selected'], '')
            self.assertEqual(state['mine'], [])
            self.assertEqual(state['theirs'], [])
            page.locator('#v2FindMineSearch').fill(fx['mine'][0]['name'])
            page.locator('#v2FindMineResults button:not([disabled])').first.click()
            manual = page.evaluate(STATE)['mine']
            self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            self.assertIsNone(page.evaluate(STATE)['marked'])
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'beta')); W.store.flush(); }")
            self.assertEqual(page.evaluate(STATE)['mine'], manual)
            page.reload(wait_until='networkidle')
            self.assertEqual(page.evaluate(STATE)['mine'], manual)
            self.assertEqual(page.evaluate(STATE)['selected'], '')
            fresh = self.opened(browser, base, context=page.context)
            self.assertEqual(fresh.evaluate(STATE)['selected'], 'beta')
            self.assertEqual(fresh.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            self.assertEqual(fresh.evaluate(STATE)['theirs'], [])
            link = fresh.evaluate("fx=>window.TradeValueFinder.encodeFinderHash({mine:fx.linkMine.map(p=>p.key),theirs:fx.linkTheirs.map(p=>p.key)})", fx)
            fresh.goto(base + link, wait_until='networkidle')
            self.assertEqual(fresh.evaluate(STATE)['mine'], fx['linkMine'])
            self.assertEqual(fresh.evaluate(STATE)['theirs'], fx['linkTheirs'])
            self.assertEqual(fresh.evaluate(STATE)['selected'], '')
            self.assertEqual(fresh.evaluate(STATE)['marked'], 'beta')
            self.assertEqual(fresh.evaluate(STATE)['teams'], fx['teams'])
            page.context.close()

    def test_their_rename_delete_pending_cancel_and_imported_ids(self):
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base)
            fx = page.evaluate(SEED)
            page.locator('#v2FindTheirSavedTeam').select_option('beta')
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.renameTeam(w,'beta','Renamed opponent')); }")
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'beta')
            self.assertIn('Renamed opponent', page.locator('#v2FindTheirSavedTeam option:checked').inner_text())
            page.locator('#v2FindTheirsSearch').fill('unfinished opponent search')
            page.once('dialog', lambda dialog: dialog.dismiss())
            page.locator('#v2FindTheirSavedTeam').select_option('empty')
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'beta')
            self.assertEqual(page.locator('#v2FindTheirsSearch').input_value(), 'unfinished opponent search')
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('#v2FindTheirSavedTeam').select_option('empty')
            page.locator('#v2FindUndo').click()
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'beta')
            page.evaluate("() => { const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.removeTeam(w,'beta')); W.store.flush(); }")
            self.assertEqual(page.evaluate(STATE)['theirs'], fx['teams'][1]['entries'])
            self.assertIn('no longer', page.locator('#v2FindTheirSavedTeamNote').inner_text())
            page.reload(wait_until='networkidle')
            self.assertEqual(page.evaluate(STATE)['theirSelected'], 'beta')
            self.assertEqual(page.evaluate(STATE)['theirs'], fx['teams'][1]['entries'])
            # Imported IDs may collide with the previous league; they must not redirect either working copy.
            page.evaluate("""() => { const W=window.TradeValueWorkspace;
              let w=W.newWorkspace({id:'another-league',name:'Another league'});
              w=W.ops.addTeam(w,'Imported alpha',{id:'alpha',entries:[]});
              w=W.ops.addTeam(w,'Imported beta',{id:'beta',entries:[]});
              W.store.replace(W.ops.setMyTeam(w,'beta'),'replace'); }
            """)
            self.assertEqual(page.evaluate(STATE)['selected'], '')
            self.assertEqual(page.evaluate(STATE)['theirSelected'], '')
            self.assertEqual(page.evaluate(STATE)['mine'], fx['mine'])
            self.assertEqual(page.evaluate(STATE)['theirs'], fx['teams'][1]['entries'])
            page.locator('#v2FindTheirSavedTeam').select_option('beta')
            self.assertEqual(page.evaluate(STATE)['theirs'], [])
            self.assertEqual(page.evaluate(STATE)['mine'], fx['mine'])
            self.assertEqual(page.evaluate(STATE)['selected'], '')
            page.context.close()

    def test_pending_move_ticks_and_alternate_paste_block_defaults(self):
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base)
            fx = page.evaluate(SEED)
            tick = page.locator('#v2FindMinePlayers .v2-find-pick').first
            tick.check()
            page.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'beta'));}")
            self.assertEqual(page.evaluate(STATE)['selected'], 'alpha')
            self.assertEqual(page.evaluate(STATE)['mine'], fx['mine'])
            self.assertTrue(tick.is_checked())
            page.once('dialog', lambda dialog: dialog.dismiss())
            page.locator('#v2FindSavedTeam').select_option('empty')
            self.assertTrue(tick.is_checked())
            tick.uncheck()
            paste = page.locator('#v2FindMinePaste')
            paste.evaluate("e => e.closest('details').open = true")
            paste.fill('unfinished name list')
            page.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'empty'));}")
            self.assertEqual(page.evaluate(STATE)['selected'], 'alpha')
            self.assertEqual(page.evaluate(STATE)['mine'], fx['mine'])
            self.assertEqual(paste.input_value(), 'unfinished name list')
            page.once('dialog', lambda dialog: dialog.dismiss())
            page.locator('#v2FindSavedTeam').select_option('empty')
            self.assertEqual(paste.input_value(), 'unfinished name list')
            page.once('dialog', lambda dialog: dialog.accept())
            page.locator('#v2FindSavedTeam').select_option('empty')
            self.assertEqual(paste.input_value(), '')
            self.assertEqual(page.evaluate(STATE)['mine'], [])
            self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            page.evaluate('fx=>window.TradeValueFinder.ui.setSides(fx.mine,fx.theirs)', fx)
            page.locator('#v2FindMinePlayers .v2-find-pick').first.check()
            page.locator('#v2FindTheirSavedTeam').select_option('beta')
            self.assertTrue(page.locator('#v2FindMinePlayers .v2-find-pick').first.is_checked())
            page.context.close()

    def test_selection_identity_edits_undo_navigation_and_reload(self):
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base)
            fx = page.evaluate(SEED)
            page.evaluate("p => window.TradeValueFinder.ui.setSides(window.TradeValueFinder.ui.getMine(), p)", fx['theirs'])
            options = page.locator('#v2FindSavedTeam option').evaluate_all('(xs) => xs.map(x => [x.value, x.textContent])')
            self.assertEqual([o[0] for o in options], ['', 'alpha', 'beta', 'empty'])
            self.assertNotEqual(options[1][1], options[2][1])
            page.locator('#v2FindGo').click()
            page.locator('#v2FindEdit').click()
            page.locator('#v2FindSavedTeam').select_option('beta')
            state = page.evaluate(STATE)
            self.assertEqual(state['mine'], fx['teams'][1]['entries'])
            self.assertEqual(state['theirs'], fx['theirs'])
            self.assertEqual(state['teams'], fx['teams'])
            self.assertEqual(state['marked'], 'alpha')
            self.assertTrue(page.locator('#v2FindOut').is_hidden())
            self.assertIn('Not evaluated', page.locator('#v2FindMinePlayers').inner_text())
            self.assertNotIn('0.0', page.locator('#v2FindMinePlayers li').last.inner_text())
            page.locator('#v2FindMinePlayers .v2-find-remove').first.click()
            edited = page.evaluate(STATE)['mine']
            self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            for _ in range(3):
                page.evaluate("location.hash = '#find-league'")
                page.evaluate("location.hash = '#find-trade'")
            self.assertEqual(page.evaluate(STATE)['mine'], edited)
            page.reload(wait_until='networkidle')
            page.locator('#v2FindSavedTeam').wait_for()
            self.assertEqual(page.evaluate(STATE)['mine'], edited)
            self.assertEqual(page.evaluate(STATE)['theirs'], fx['theirs'])
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            page.locator('#v2FindSavedTeam').select_option('empty')
            self.assertEqual(page.evaluate(STATE)['mine'], [])
            page.locator('#v2FindUndo').click()
            self.assertEqual(page.evaluate(STATE)['mine'], edited)
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            page.locator('#v2FindSavedTeam').select_option('alpha')
            page.locator('#v2FindSavedTeam').select_option('beta')
            self.assertEqual(page.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            page.context.close()

    def test_rename_delete_import_and_empty_league(self):
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base)
            self.assertTrue(page.locator('#v2FindSavedTeam').is_disabled())
            self.assertIn('No saved teams', page.locator('#v2FindSavedTeamNote').inner_text())
            fx = page.evaluate(SEED)
            page.locator('#v2FindSavedTeam').select_option('beta')
            page.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.renameTeam(w,'beta','Renamed'));}")
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            self.assertIn('Renamed', page.locator('#v2FindSavedTeam option:checked').inner_text())
            page.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.removeTeam(w,'beta'));}")
            self.assertEqual(page.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            self.assertIn('no longer', page.locator('#v2FindSavedTeamNote').inner_text())
            self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
            page.evaluate("() => {const W=window.TradeValueWorkspace; const w=W.newWorkspace({id:'imported',name:'Imported'}); W.store.replace(W.ops.addTeam(w,'New team',{id:'new-id',entries:[]}), 'replace');}")
            self.assertEqual(page.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            self.assertIn('new-id', page.locator('#v2FindSavedTeam option').evaluate_all('(xs)=>xs.map(x=>x.value)'))
            page.locator('#v2FindSavedTeam').select_option('new-id')
            self.assertEqual(page.evaluate(STATE)['mine'], [])
            page.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(W.ops.clearLeague); W.store.flush();}")
            self.assertTrue(page.locator('#v2FindSavedTeam').is_disabled())
            self.assertEqual(page.evaluate(STATE)['teams'], [])
            page.reload(wait_until='networkidle')
            page.locator('#v2FindSavedTeam').wait_for()
            self.assertEqual(page.evaluate(STATE)['teams'], [])
            self.assertEqual(page.evaluate(STATE)['mine'], [])
            page.context.close()

    def test_cross_tab_share_context_and_pending_input_cancel(self):
        with browser_on_build() as (browser, base):
            a = self.opened(browser, base)
            fx = a.evaluate(SEED)
            b = self.opened(browser, base, context=a.context)
            b.locator('#v2FindSavedTeam').select_option('beta')
            a.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.renameTeam(w,'beta','Other tab')); W.store.setMyRoster([]); W.store.flush();}")
            b.wait_for_function("document.querySelector('#v2FindSavedTeam option:checked').textContent.includes('Other tab')")
            self.assertEqual(b.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            shared = b.evaluate("fx => window.TradeValueFinder.encodeFinderHash({mine:fx.linkMine.map(p=>p.key), theirs:fx.linkTheirs.map(p=>p.key)})", fx)
            b.goto(base + shared, wait_until='networkidle')
            b.wait_for_function('window.TradeValueFinder.ui.getMine().length === 1')
            self.assertEqual(b.evaluate(STATE)['mine'], fx['linkMine'])
            a.evaluate("() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.renameTeam(w,'alpha','Late storage')); W.store.flush();}")
            b.wait_for_function("document.querySelector('#v2FindSavedTeam option[value=alpha]').textContent.includes('Late storage')")
            self.assertEqual(b.evaluate(STATE)['mine'], fx['linkMine'])
            if b.locator('#v2FindInput').is_hidden():
                b.locator('#v2FindEdit').click()
            b.locator('#v2FindMineSearch').fill('unfinished search')
            b.once('dialog', lambda dialog: dialog.dismiss())
            b.locator('#v2FindSavedTeam').select_option('alpha')
            self.assertEqual(b.evaluate(STATE)['mine'], fx['linkMine'])
            self.assertEqual(b.locator('#v2FindMineSearch').input_value(), 'unfinished search')
            b.once('dialog', lambda dialog: dialog.accept())
            b.locator('#v2FindSavedTeam').select_option('beta')
            self.assertEqual(b.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            self.assertEqual(b.locator('#v2FindMineSearch').input_value(), '')
            b.locator('#v2FindUndo').click()
            self.assertEqual(b.evaluate(STATE)['mine'], fx['linkMine'])
            self.assertEqual(b.evaluate(STATE)['theirs'], fx['linkTheirs'])
            self.assertEqual(b.evaluate(STATE)['teams'], a.evaluate(STATE)['teams'])
            # An explicit newer pick must win over the older URL rosters on reload, without losing link context.
            contextual = b.evaluate("""fx => window.TradeValueFinder.encodeFinderHash({mine:fx.linkMine.map(p=>p.key),
              theirs:fx.linkTheirs.map(p=>p.key), maxSize:1, keepMine:false},
              'teams=10&scoring=half&basis=fantasycalc&ov=' + fx.linkMine[0].key + ':37')""", fx)
            b.goto(base + contextual, wait_until='networkidle')
            b.locator('#v2FindSavedTeam').wait_for(state='attached')
            if b.locator('#v2FindInput').is_hidden():
                b.locator('#v2FindEdit').click()
            before = b.evaluate('Object.fromEntries(new URLSearchParams(location.hash.split("?")[1]))')
            context_before = b.evaluate('({values: window.DDFOverrides.shareParams(), teams: window.TradeValueCurveControls.getState().teams, scoring: window.TradeValueCurveControls.getState().scoring})')
            b.locator('#v2FindSavedTeam').select_option('beta')
            b.reload(wait_until='networkidle')
            self.assertEqual(b.evaluate(STATE)['selected'], 'beta')
            self.assertEqual(b.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            self.assertEqual(b.evaluate(STATE)['theirs'], fx['linkTheirs'])
            after = b.evaluate('Object.fromEntries(new URLSearchParams(location.hash.split("?")[1]))')
            self.assertEqual(after, {k: v for k, v in before.items() if k not in ('mine', 'theirs')})
            self.assertEqual(b.evaluate('({values: window.DDFOverrides.shareParams(), teams: window.TradeValueCurveControls.getState().teams, scoring: window.TradeValueCurveControls.getState().scoring})'), context_before)
            self.assertEqual(b.locator('#v2FindSize').input_value(), '1')
            self.assertFalse(b.locator('#v2FindKeepMine').is_checked())
            b.locator('#v2FindMinePlayers .v2-find-remove').first.click()
            b.locator('#v2FindReloadTeam').click()
            self.assertEqual(b.evaluate(STATE)['mine'], fx['teams'][1]['entries'])
            a.context.close()

    def test_keyboard_mobile_and_overlap_guard(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390, 320):
                page = self.opened(browser, base, width=width)
                fx = page.evaluate(SEED)
                page.evaluate('fx => window.TradeValueFinder.ui.setSides(fx.mine, fx.teams[1].entries)', fx)
                picker = page.get_by_label('Your saved League team', exact=True)
                picker.focus()
                picker.press('Home')
                picker.press('ArrowDown')
                picker.press('ArrowDown')
                picker.press('Tab')
                self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
                self.assertEqual(page.evaluate(STATE)['theirs'], fx['teams'][1]['entries'])
                self.assertGreaterEqual(picker.bounding_box()['height'], 44)
                page.locator('#v2FindGo').click()
                self.assertIn('both rosters', page.locator('#v2FindOut').inner_text())
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'), width)
                if page.locator('#v2FindInput').is_hidden():
                    page.locator('#v2FindEdit').click()
                their_picker = page.get_by_label('Their saved League team', exact=True)
                their_picker.focus()
                their_picker.press('Home')
                their_picker.press('ArrowDown')
                their_picker.press('Tab')
                self.assertEqual(page.evaluate(STATE)['theirSelected'], 'alpha')
                self.assertEqual(page.evaluate(STATE)['selected'], 'beta')
                self.assertGreaterEqual(their_picker.bounding_box()['height'], 44)
                self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
                page.context.close()

    def test_no_overwrite_guard_catches_render_writing_to_marked_team(self):
        original = source('finder.js')
        anchor = 'const mineChanged = () => { saveRosterCopy();'
        self.assertIn(anchor, original)
        broken = original.replace(anchor, 'const mineChanged = () => { if (JSON.stringify(sharedStore().getMyRoster()) !== JSON.stringify(S.mine)) sharedStore().setMyRoster(S.mine); saveRosterCopy();', 1)
        with browser_on_build() as (browser, base):
            page = self.opened(browser, base, overrides={'finder.js': broken})
            fx = page.evaluate(SEED)
            page.locator('#v2FindSavedTeam').select_option('beta')
            # The same preservation assertion used by the real regression rejects the original write-through hazard.
            with self.assertRaises(AssertionError):
                self.assertEqual(page.evaluate(STATE)['teams'], fx['teams'])
            page.context.close()


if __name__ == '__main__':
    unittest.main()
