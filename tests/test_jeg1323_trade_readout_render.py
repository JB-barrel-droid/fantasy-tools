"""JEG-1323: draw the five shared readout rows under every scoring format."""
import unittest

from tests._league_render import browser_on_build, fixture, open_page
from tests.test_jeg1230_trade_readout_render import BUILD


class TradeReadoutRowsRenderTest(unittest.TestCase):
    def test_rows_all_scoring_formats_desktop_and_phone(self):
        build = BUILD.replace(
            'const direct = F.rosterImpact',
            "const summary = R.renderRows(out); "
            "document.getElementById('v2LgCard').appendChild(summary); "
            'const direct = F.rosterImpact',
        ).replace(
            'give: give.map(r => r.player_key)',
            'context: {scoring: C.getState().scoring, teams: C.getState().teams, week: 8}, '
            'give: give.map(r => r.player_key)',
        )
        with browser_on_build() as (browser, base):
            for scoring, label in [('standard', 'Standard'), ('half_ppr', 'Half PPR'), ('ppr', 'Full PPR')]:
                for width in (1366, 390):
                    with self.subTest(scoring=scoring, width=width):
                        errors = []
                        page = open_page(browser, base, width=width, errors=errors)
                        page.evaluate('(s) => window.TradeValueCurveControls.setScoring(s)', scoring)
                        result = page.evaluate(build, [fixture('20team')])
                        self.assertTrue(result['ready'])
                        self.assertTrue(result['same'])
                        rows = page.locator('#v2LgCard [data-row]')
                        self.assertEqual(rows.evaluate_all('(nodes) => nodes.map(n => n.dataset.row)'),
                                         ['verdict', 'accept', 'sell-gap', 'data-labels', 'context'])
                        for row in rows.all():
                            self.assertTrue(row.is_visible())
                            self.assertTrue(row.inner_text().strip())
                        self.assertIn(label, rows.last.inner_text())
                        self.assertIn('Week 8', rows.last.inner_text())
                        self.assertNotIn('2027', ' '.join(rows.all_inner_texts()))
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
                        self.assertEqual(errors, [])
                        page.context.close()
