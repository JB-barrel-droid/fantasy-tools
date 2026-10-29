"""JEG-1114: an opened Find a trade link keeps its rosters and settings while another tab writes the saved league.

The link wins in the tab that opened it. Its rosters and trade settings stay that tab's (JEG-1219 lets no finder side
write a League roster or the star, and nothing authorizes saving a link's settings for every tab). Before the fix, any
write from another tab (even a rename) put the older saved settings back over the link's and cleared the search the
link had run. A same-tab load or replace (League Load/Undo) still reconciles, even after an ignored other-tab update.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build
from tests import test_v2_finder_saved_team_render as saved_team

SEED, STATE = saved_team.SEED, saved_team.STATE


def setUpModule():
    _render_env.ensure_built()


VIEW = """() => ({size: document.getElementById('v2FindSize').value,
  keepMine: document.getElementById('v2FindKeepMine').checked,
  results: !document.getElementById('v2FindOut').hidden && document.getElementById('v2FindOut').childElementCount > 0,
  saved: window.TradeValueWorkspace.store.get().ui.finderSettings})"""
WRITES = [
    ("rename", "() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.renameTeam(w,'alpha','Late storage')); W.store.flush();}"),
    ("star", "() => {const W=window.TradeValueWorkspace; W.store.update(w=>W.ops.setMyTeam(w,'beta')); W.store.flush();}"),
    ("marked roster", "() => {const W=window.TradeValueWorkspace; W.store.setMyRoster([]); W.store.flush();}"),
    ("replace", "() => {const W=window.TradeValueWorkspace; W.store.replace(W.store.get(),'replace'); W.store.flush();}"),
]


class FinderLinkTabsRenderTest(unittest.TestCase):
    # The saved-team test's page opener, borrowed without importing its class (unittest would collect it again here).
    opened = saved_team.FinderSavedTeamRenderTest.opened

    def open_link(self, a, base, link):
        b = a.context.new_page()
        b.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        b.goto(base + link, wait_until="networkidle")
        b.wait_for_function("() => window.TradeValueFinder && document.getElementById('v2FindSavedTeam')", timeout=60000)
        return b

    def assert_link_holds(self, b, fx, label):
        state = b.evaluate(STATE)
        self.assertEqual(state["mine"], fx["linkMine"], f"{label}: link's roster replaced")
        self.assertEqual(state["theirs"], fx["linkTheirs"], f"{label}: link's opponent replaced")
        view = b.evaluate(VIEW)
        self.assertEqual((view["size"], view["keepMine"]), ("1", False), f"{label}: link's trade settings replaced")
        self.assertTrue(view["results"], f"{label}: the link's search was cleared")

    def test_link_rosters_and_settings_survive_other_tab_writes(self):
        with browser_on_build() as (browser, base):
            a = self.opened(browser, base)
            fx = a.evaluate(SEED)
            a.reload(wait_until="networkidle")
            a.evaluate("location.hash = '#find-trade'")
            a.wait_for_function("window.TradeValueFinder.ui.getMine().length === 2")
            a_mine = a.evaluate(STATE)["mine"]
            self.assertEqual(a_mine, fx["teams"][0]["entries"])
            link = a.evaluate("""fx => window.TradeValueFinder.encodeFinderHash({mine: fx.linkMine.map(p => p.key),
              theirs: fx.linkTheirs.map(p => p.key), maxSize: 1, keepMine: false})""", fx)
            # The other tab keeps writing the saved league while the link opens: none of it may undo the link.
            a.evaluate("""() => { const W = window.TradeValueWorkspace; let n = 0;
              window.__writes = setInterval(() => { W.store.update(w => W.ops.renameTeam(w, 'beta', 'Busy ' + (n++))); W.store.flush(); }, 40); }""")
            b = self.open_link(a, base, link)
            b.wait_for_function("!document.getElementById('v2FindOut').hidden", timeout=30000)
            b.wait_for_timeout(1500)
            a.evaluate("() => clearInterval(window.__writes)")
            b.wait_for_timeout(500)
            self.assert_link_holds(b, fx, "writes while opening")
            for label, write in WRITES:
                a.evaluate(write)
                b.wait_for_function("name => document.querySelector('#v2FindSavedTeam option[value=alpha]').textContent.includes(name)",
                                    arg="Late storage", timeout=10000)
                b.wait_for_timeout(300)
                self.assert_link_holds(b, fx, label)
            # A newer settings change in the other tab does not replace the settings this tab opened with.
            a.evaluate("""() => { const W = window.TradeValueWorkspace;
              W.store.update(w => W.ops.setUi(w, {finderSettings: W.normalizeFinderSettings({...w.ui.finderSettings, maxSize: 3, keepMine: true})}), 'finder-settings');
              W.store.flush(); }""")
            b.wait_for_timeout(500)
            self.assert_link_holds(b, fx, "other tab's settings")
            b.reload(wait_until="networkidle")
            b.wait_for_function("!document.getElementById('v2FindOut').hidden", timeout=60000)
            self.assert_link_holds(b, fx, "reload")
            a.context.close()

    def seeded_pair(self, browser, base):
        a = self.opened(browser, base)
        fx = a.evaluate(SEED)
        a.reload(wait_until="networkidle")
        a.evaluate("location.hash = '#find-trade'")
        a.wait_for_function("window.TradeValueFinder.ui.getMine().length === 2")
        link = a.evaluate("""fx => window.TradeValueFinder.encodeFinderHash({mine: fx.linkMine.map(p => p.key),
          theirs: fx.linkTheirs.map(p => p.key), maxSize: 1, keepMine: false})""", fx)
        return a, fx, link

    def set_size(self, page, n):
        page.evaluate("""n => { const W = window.TradeValueWorkspace;
          W.store.update(w => W.ops.setUi(w, {finderSettings: W.normalizeFinderSettings({...w.ui.finderSettings, maxSize: n})}), 'finder-settings');
          W.store.flush(); }""", n)

    def test_link_stays_in_its_tab_and_sync_resumes_after_an_edit(self):
        with browser_on_build() as (browser, base):
            a, fx, link = self.seeded_pair(browser, base)
            before = a.evaluate(STATE)
            b = self.open_link(a, base, link)
            b.wait_for_function("!document.getElementById('v2FindOut').hidden", timeout=30000)
            b.evaluate("window.TradeValueWorkspace.store.flush()")
            b.wait_for_timeout(500)
            # The link's settings are not written to the saved league: the other tab keeps its own.
            view = a.evaluate(VIEW)
            self.assertEqual((view["size"], view["keepMine"]), ("2", True))
            self.assertEqual((view["saved"]["maxSize"], view["saved"]["keepMine"]), (2, True))
            self.assertEqual((b.evaluate(VIEW)["saved"]["maxSize"], b.evaluate(VIEW)["saved"]["keepMine"]), (2, True))
            # Its working rosters, the League teams and the star stay as they were (JEG-1219).
            after = a.evaluate(STATE)
            self.assertEqual(after["mine"], before["mine"])
            self.assertEqual(after["teams"], fx["teams"])
            self.assertEqual(after["marked"], "alpha")
            self.assertEqual(b.evaluate(STATE)["marked"], "alpha")
            # A rename in the other tab still reaches the link tab's pickers: normal synchronization is kept.
            a.evaluate(WRITES[0][1])
            b.wait_for_function("document.querySelector('#v2FindSavedTeam option[value=alpha]').textContent.includes('Late storage')", timeout=10000)
            # Once the reader changes a setting in the link tab, it saves and the two tabs sync settings again.
            if b.locator("#v2FindInput").is_hidden():
                b.locator("#v2FindEdit").click()
            b.locator("#v2FindSize").select_option("3")
            b.evaluate("window.TradeValueWorkspace.store.flush()")
            a.wait_for_function("document.getElementById('v2FindSize').value === '3'", timeout=10000)
            a.locator("#v2FindSize").select_option("2")
            a.evaluate("window.TradeValueWorkspace.store.flush()")
            b.wait_for_function("document.getElementById('v2FindSize').value === '2'", timeout=10000)
            self.assertEqual(b.evaluate(STATE)["mine"], fx["linkMine"])
            self.assertEqual(b.evaluate(STATE)["theirs"], fx["linkTheirs"])
            a.context.close()

    def test_same_tab_replace_after_an_ignored_other_tab_update_reconciles(self):
        # Codex's review of ef5dfef: held size 1, other-tab size 3, then a same-tab replace (League Load/Undo) carrying
        # size 3 left size 1 and the hold on, because the ignored value had been recorded as seen.
        with browser_on_build() as (browser, base):
            a, fx, link = self.seeded_pair(browser, base)
            b = self.open_link(a, base, link)
            b.wait_for_function("!document.getElementById('v2FindOut').hidden", timeout=30000)
            self.set_size(a, 3)
            b.wait_for_function("window.TradeValueWorkspace.store.get().ui.finderSettings.maxSize === 3", timeout=10000)
            self.assert_link_holds(b, fx, "ignored other-tab settings")
            b.evaluate("() => { const W = window.TradeValueWorkspace; W.store.replace(W.store.get(), 'replace'); W.store.flush(); }")
            view = b.evaluate(VIEW)
            self.assertEqual(view["size"], "3", "same-tab replace did not apply the loaded settings")
            self.assertFalse(view["results"], "stale results kept after the loaded settings changed")
            # The hold is released: a later other-tab settings change reaches this tab again.
            self.set_size(a, 2)
            b.wait_for_function("document.getElementById('v2FindSize').value === '2'", timeout=10000)
            state = b.evaluate(STATE)
            self.assertEqual(state["mine"], fx["linkMine"])
            self.assertEqual(state["theirs"], fx["linkTheirs"])
            self.assertEqual(state["marked"], "alpha")
            self.assertEqual(state["teams"], fx["teams"])
            a.context.close()

if __name__ == "__main__":
    unittest.main()
