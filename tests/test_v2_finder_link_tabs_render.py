"""JEG-1114: an opened Find a trade link keeps its rosters and settings while another tab writes the saved league.

Jeremy's option A: the opened link wins, including across tabs. Its trade settings become the saved ones, so the other
tabs follow them; its rosters stay the opening tab's working copy, because JEG-1219 lets no finder side write a League
roster or the star. Before the fix, any write from another tab (even a rename) put the older saved settings back over
the link's and cleared the search the link had run.
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

    def test_other_tabs_follow_the_link_and_sync_resumes_after_an_edit(self):
        with browser_on_build() as (browser, base):
            a = self.opened(browser, base)
            fx = a.evaluate(SEED)
            a.reload(wait_until="networkidle")
            a.evaluate("location.hash = '#find-trade'")
            a.wait_for_function("window.TradeValueFinder.ui.getMine().length === 2")
            before = a.evaluate(STATE)
            self.assertEqual(a.evaluate(VIEW)["size"], "2")
            link = a.evaluate("""fx => window.TradeValueFinder.encodeFinderHash({mine: fx.linkMine.map(p => p.key),
              theirs: fx.linkTheirs.map(p => p.key), maxSize: 1, keepMine: false})""", fx)
            b = self.open_link(a, base, link)
            b.wait_for_function("!document.getElementById('v2FindOut').hidden", timeout=30000)
            b.evaluate("window.TradeValueWorkspace.store.flush()")
            # The other tab follows the link's trade settings ...
            a.wait_for_function("document.getElementById('v2FindSize').value === '1'", timeout=10000)
            self.assertFalse(a.evaluate(VIEW)["keepMine"])
            saved = a.evaluate(VIEW)["saved"]
            self.assertEqual((saved["maxSize"], saved["keepMine"]), (1, False))
            # ... while its working rosters, the League teams and the star stay as they were (JEG-1219).
            after = a.evaluate(STATE)
            self.assertEqual(after["mine"], before["mine"])
            self.assertEqual(after["teams"], fx["teams"])
            self.assertEqual(after["marked"], "alpha")
            self.assertEqual(b.evaluate(STATE)["marked"], "alpha")
            # A rename in the other tab still reaches the link tab's pickers: normal synchronization is kept.
            a.evaluate(WRITES[0][1])
            b.wait_for_function("document.querySelector('#v2FindSavedTeam option[value=alpha]').textContent.includes('Late storage')", timeout=10000)
            # Once the reader changes a setting in the link tab, it saves and follows other tabs again.
            if b.locator("#v2FindInput").is_hidden():
                b.locator("#v2FindEdit").click()
            b.locator("#v2FindSize").select_option("2")
            b.evaluate("window.TradeValueWorkspace.store.flush()")
            a.wait_for_function("document.getElementById('v2FindSize').value === '2'", timeout=10000)
            a.locator("#v2FindSize").select_option("3")
            a.evaluate("window.TradeValueWorkspace.store.flush()")
            b.wait_for_function("document.getElementById('v2FindSize').value === '3'", timeout=10000)
            self.assertEqual(b.evaluate(STATE)["mine"], fx["linkMine"])
            self.assertEqual(b.evaluate(STATE)["theirs"], fx["linkTheirs"])
            a.context.close()


if __name__ == "__main__":
    unittest.main()
