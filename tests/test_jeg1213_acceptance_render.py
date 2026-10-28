"""JEG-1213: league-wide finder behavior, exercised through the rendered UI.

Numbers in optional columns and filters are checked against independent sums
of engine rows. Sharing uses a fresh browser context with empty storage.
Clean K/DEF imports and a real unresolved player are separate paste cases.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

from tests import _render_env
from tests._league_render import browser_on_build, fixture, open_page, seed, wait_opps
from tests.test_v2_league_parsed_render import espn_league_text


ROOT = Path(__file__).resolve().parents[1]
CLIPBOARD = """Object.defineProperty(navigator, 'clipboard', {configurable: true,
  value: {writeText: async text => { window.__jeg1213Copied = text; }}});"""
TEAM_SNAPSHOT = """() => { const w = window.TradeValueWorkspace.store.get();
  return {teams: w.teams.map(t => ({name:t.name, keys:t.entries.map(e=>e.key).sort()})).sort((a,b)=>a.name.localeCompare(b.name)),
    mine: (w.teams.find(t=>t.id===w.myTeamId)||{}).name || null}; }"""
SHOWN_ROWS = """() => [...document.querySelectorAll('#v2LgOppsTable tr.v2-lg-opp')].map(tr => ({
  id: tr.dataset.oppId, rank: Number(tr.dataset.rank),
  rankText: tr.querySelector('[data-cell="rank"]').textContent.trim(),
  cells: [...tr.children].map(td=>td.dataset.cell||''),
  theirs: tr.querySelector('[data-cell="theirs"]').textContent.trim()}))"""
TOTALS = """() => { const C=window.TradeValueCurveControls, F=window.TradeValueFinder;
  const w=window.TradeValueWorkspace.store.get(), by=new Map(C.getAllRows().map(r=>[String(r.player_key),r]));
  const charts=F.CHART_KEYS.filter(k=>C.getSourceInfo().some(s=>s.key===k && s.available));
  return {mine:w.myTeamId, teams:w.teams.map(t=>{ const rows=t.entries.map(e=>by.get(e.key)).filter(Boolean);
    return {id:t.id, name:t.name, rosterF:F.lineupValue(rows,C.getRosterShape(),'ddf_value').total,
      starterM:F.lineupValue(F.withChartAverage(rows,charts),C.getRosterShape(),'chart_avg').starterValue}; })}; }"""


def setUpModule():
    _render_env.ensure_built()


def open_details(page, selector):
    if not page.locator(selector).evaluate("node => node.open"):
        page.locator(selector + " > summary").click()


def show_all(page):
    if page.locator("#v2LgOppsAll").count() and page.is_visible("#v2LgOppsAll"):
        page.click("#v2LgOppsAll")


class Jeg1213AcceptanceRenderTest(unittest.TestCase):
    def test_transfer_menu_explains_actions_and_fits_phone(self):
        with browser_on_build() as (browser, base):
            for width in (1366, 390):
                with self.subTest(width=width):
                    page = open_page(browser, base, width=width)
                    seed(page, "2team")
                    menu = page.locator("#v2LgTransfer")
                    self.assertEqual(menu.evaluate("node => node.tagName"), "DETAILS")
                    self.assertFalse(menu.evaluate("node => node.open"))
                    for action in ("Download", "Load", "CopyLink"):
                        self.assertEqual(menu.locator("#v2Lg" + action).count(), 1)
                        self.assertFalse(page.is_visible("#v2Lg" + action))
                    open_details(page, "#v2LgTransfer")
                    for action, meaning in (("Download", "file"), ("Load", "file"), ("Copy link", "settings")):
                        info = menu.locator(f'summary[aria-label="About {action}"]')
                        self.assertTrue(info.is_visible())
                        info.click()
                        definition = info.locator("..").inner_text().lower()
                        self.assertIn(meaning, definition)
                        info.click()
                    rect = menu.locator(":scope > summary").bounding_box()
                    self.assertIsNotNone(rect)
                    self.assertLessEqual(rect["x"] + rect["width"], width + 1)
                    if width > 1000:
                        self.assertGreater(rect["x"], width / 2, "Import / export should sit at the top right")
                    page.context.close()

    def test_copy_link_restores_all_rosters_marked_team_and_league_settings(self):
        with browser_on_build() as (browser, base):
            sender = open_page(browser, base, init_script=CLIPBOARD)
            seed(sender, "4team", mine=2)
            sender.evaluate("""() => window.TradeValueV2.applyLinkLeague(new URLSearchParams(
              'scoring=standard&teams=10&roster=QB1.RB2.WR3.TE1.FLEX2.SF1.BN5&regend=14&playoffs=15-17&inj=all&conf=1.5&bso=0.200'))""")
            expected_query = sender.evaluate("() => window.TradeValueV2.leagueQuery()")
            expected_teams = sender.evaluate(TEAM_SNAPSHOT)
            self.assertIn("scoring=standard", expected_query)
            self.assertIn("teams=10", expected_query)
            open_details(sender, "#v2LgTransfer")
            sender.click("#v2LgCopyLink")
            sender.wait_for_function("() => Boolean(window.__jeg1213Copied)")
            link = sender.evaluate("() => window.__jeg1213Copied")
            fragment = urlsplit(link).fragment
            query = parse_qs(fragment.partition("?")[2])
            self.assertTrue(fragment.startswith("find-league?"))
            self.assertIn("workspace", query)
            for key, value in parse_qs(expected_query).items():
                self.assertEqual(query.get(key), value, f"shared league setting {key}")
            # A genuinely fresh context: there is no sender workspace/settings in storage.
            reader = open_page(browser, base)
            reader.goto(link, wait_until="networkidle")
            reader.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready")
            reader.wait_for_function("() => window.TradeValueWorkspace.store.get().teams.length === 4")
            self.assertEqual(reader.evaluate(TEAM_SNAPSHOT), expected_teams)
            self.assertEqual(reader.evaluate("() => window.TradeValueV2.leagueQuery()"), expected_query)
            sender.context.close()
            reader.context.close()

    def test_team_count_warning_starts_at_eight_and_quick_fix_preserves_teams(self):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base)
            page.evaluate("""() => { const W=window.TradeValueWorkspace; let w=W.newWorkspace();
              for(let i=0;i<7;i++)w=W.ops.addTeam(w,`Roster ${i+1}`); W.store.replace(w,'replace'); }""")
            self.assertFalse(page.is_visible("#v2LgMismatch"))
            page.evaluate("""() => { const W=window.TradeValueWorkspace;
              W.store.replace(W.ops.addTeam(W.store.get(),'Roster 8'),'replace'); }""")
            page.wait_for_selector("#v2LgMatchTeams")
            self.assertTrue(page.is_visible("#v2LgMismatch"))
            self.assertIn("8", page.inner_text("#v2LgMismatch"))
            before = page.evaluate(TEAM_SNAPSHOT)
            page.click("#v2LgMatchTeams")
            page.wait_for_function("() => window.TradeValueCurveControls.getState().teams === 8")
            self.assertEqual(page.evaluate(TEAM_SNAPSHOT), before)
            self.assertFalse(page.is_visible("#v2LgMismatch"))
            page.context.close()

    def test_clean_paste_folds_league_and_teams_but_real_issue_stays_open(self):
        text, _ = espn_league_text(teams=4)
        with browser_on_build() as (browser, base):
            for real_issue in (False, True):
                with self.subTest(real_issue=real_issue):
                    page = open_page(browser, base)
                    page.evaluate("""realIssue => { const P=window.DDFRosterPaste, real=P.parseLeague;
                      P.parseLeague=(text, rows)=>{ const r=real(text,rows);
                        if(r.teams[0])r.teams[0].unmatched.push({line:'Jason Myers',pos:'K',team:'SEA'},{line:'Jets',pos:'DEF',team:'NYJ'});
                        if(realIssue && r.teams[1])r.teams[1].unmatched.push({line:'Jalen Qwertyuiop',pos:'WR',reason:'ambiguous'});
                        return r; }; }""", real_issue)
                    page.fill("#v2LgLeaguePaste", text)
                    page.wait_for_function("() => window.TradeValueWorkspace.store.get().teams.length === 4")
                    self.assertEqual(page.locator("#v2LgCard").evaluate("node=>node.open"), real_issue)
                    states = page.locator("#v2LgTeams .v2-lg-toggle").evaluate_all("nodes=>nodes.map(n=>n.getAttribute('aria-expanded'))")
                    self.assertEqual(states, ["false", "true" if real_issue else "false", "false", "false"])
                    kept = page.evaluate("() => window.TradeValueWorkspace.store.get().teams[0].entries.map(e=>e.pos)")
                    self.assertIn("K", kept)
                    self.assertIn("DEF", kept)
                    if real_issue:
                        self.assertIn("Jalen Qwertyuiop", page.inner_text("#v2LgParsed"))
                    page.context.close()

    def test_yahoo_navigation_junk_is_not_a_team_or_visible_paste_result(self):
        text = (ROOT / "tests/fixtures/league_paste/yahoo-league-rosters.txt").read_text()
        text = text.replace("Yahoo Sports", "Yahoo Sports Yahoo Sports Search query S", 1)
        expected_names = list(json.loads((ROOT / "tests/fixtures/league_paste/teams.json").read_text()))
        with browser_on_build() as (browser, base):
            page = open_page(browser, base)
            page.fill("#v2LgLeaguePaste", text)
            page.wait_for_function("() => window.TradeValueWorkspace.store.get().teams.length > 0")
            names = page.evaluate("() => window.TradeValueWorkspace.store.get().teams.map(t=>t.name)")
            self.assertEqual(names, expected_names)
            self.assertNotIn("Yahoo Sports Yahoo Sports Search query S", page.locator("#v2FindLeague").inner_text())
            page.context.close()

    def test_opportunity_order_projection_position_and_fit_explanations(self):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base)
            seed(page, "4team")
            wait_opps(page)
            show_all(page)
            rows = page.evaluate(SHOWN_ROWS)
            self.assertGreater(len(rows), 0)
            self.assertEqual([r["rank"] for r in rows], list(range(1, len(rows) + 1)))
            self.assertEqual(rows[0]["rankText"], "#1")
            for row in rows:
                self.assertEqual(row["cells"].index("proj"), row["cells"].index("capture") + 1)
                self.assertRegex(row["theirs"].lower(), r"market|trade chart")
                self.assertIn("total", row["theirs"].lower())
                self.assertIn("starter", row["theirs"].lower())
                self.assertIn("construction", row["theirs"].lower())
            for variant, words in (("natural", ("roster", "starter")), ("market", ("trade chart",))):
                # The frozen league must exercise both definitions, not pass on an empty list.
                info = page.locator(f'tr.v2-lg-opp[data-overall="{variant}"] .v2-lg-fit-info > summary').first
                self.assertEqual(info.count(), 1, f"fixture has no {variant} info control")
                self.assertIn("About", info.get_attribute("aria-label"))
                info.click()
                definition = info.locator("..").inner_text().lower()
                for word in words:
                    self.assertIn(word, definition)
            page.context.close()

    def test_summary_columns_and_numeric_and_text_filters_use_current_team_values(self):
        required = {"rank", "team", "rosterF", "starterF", "benchF", "rosterM", "starterM", "benchM", "altRank", "projRank", "disagree", "under", "over",
                    "rosterP", "starterP", "benchP", "strengths", "weaknesses", "allocationQB", "allocationRB", "allocationWR", "allocationTE"}
        with browser_on_build() as (browser, base):
            page = open_page(browser, base)
            seed(page, "4team")
            wait_opps(page)
            totals = page.evaluate(TOTALS)
            by_team = {t["id"]: t for t in totals["teams"]}
            row_opponents = page.evaluate("() => Object.fromEntries(window.TradeValueLeague.ui.result.rows.map(r=>[r.id,r.opponentId]))")
            open_details(page, "#v2LgFields")
            choices = set(page.locator("#v2LgFields input[data-summary-column]").evaluate_all("nodes=>nodes.map(n=>n.dataset.summaryColumn)"))
            self.assertTrue({f"{side}:{key}" for side in ("mine", "theirs") for key in required} <= choices)
            for key in ("theirs:rosterF", "mine:starterM"):
                open_details(page, "#v2LgFields")
                page.locator(f'#v2LgFields input[data-summary-column="{key}"]').check()
            show_all(page)
            cells = page.locator("#v2LgOppsTable tr.v2-lg-opp").evaluate_all("""nodes=>nodes.map(n=>({id:n.dataset.oppId,
              roster:n.querySelector('[data-cell="summary:theirs:rosterF"]').textContent,
              starters:n.querySelector('[data-cell="summary:mine:starterM"]').textContent}))""")
            self.assertTrue(cells)
            for row in cells:
                self.assertAlmostEqual(float(row["roster"]), by_team[row_opponents[row["id"]]]["rosterF"], delta=0.051)
                self.assertAlmostEqual(float(row["starters"]), by_team[totals["mine"]]["starterM"], delta=0.051)
            available = {row_opponents[r["id"]] for r in cells}
            values = sorted({round(by_team[key]["rosterF"], 1) for key in available})
            self.assertGreater(len(values), 1, "numeric filter fixture must distinguish opponents")
            threshold = (values[0] + values[-1]) / 2
            open_details(page, "#v2LgSummaryFilters")
            page.select_option("#v2LgSummaryFilterSide", "theirs")
            page.select_option("#v2LgSummaryFilterField", "rosterF")
            page.select_option("#v2LgSummaryFilterOp", "gte")
            page.fill("#v2LgSummaryFilterValue", str(threshold))
            page.click("#v2LgSummaryFilterAdd")
            show_all(page)
            shown = page.evaluate(SHOWN_ROWS)
            got = {row_opponents[r["id"]] for r in shown}
            want = {key for key in available if round(by_team[key]["rosterF"], 1) >= threshold}
            self.assertEqual(got, want)
            self.assertTrue(got)
            self.assertLess(len(got), len(available))
            page.locator("#v2LgSummaryFilters button[aria-label^='Remove ']").click()
            open_details(page, "#v2LgSummaryFilters")
            page.select_option("#v2LgSummaryFilterField", "team")
            page.select_option("#v2LgSummaryFilterOp", "contains")
            target = by_team[next(iter(got))]
            page.fill("#v2LgSummaryFilterValue", target["name"])
            page.click("#v2LgSummaryFilterAdd")
            show_all(page)
            self.assertEqual({row_opponents[r["id"]] for r in page.evaluate(SHOWN_ROWS)}, {target["id"]})
            page.context.close()


if __name__ == "__main__":
    unittest.main()
