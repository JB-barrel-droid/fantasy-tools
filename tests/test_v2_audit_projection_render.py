"""JEG-1199: projection readouts tied to the actual pipeline and displayed values."""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_v2_audit_source_render import SELECT
from tests.test_v2_panels_render import _built_dist

RAW_STEP = {'espn': 'What ESPN publishes', 'cbsros': 'What CBS publishes',
            'razzball': 'What Razzball publishes'}

READ_PATH = """() => {
  const card = document.querySelector('.as-projection');
  const key = card.querySelector('.as-path').dataset.playerKey;
  const src = window.DDFAuditSource.current().source;
  const i = window.TradeValueCurveControls.getInspection();
  const p = i.players[src][key], d = i.valuePipeline.sources[src], pos = d.positions[p.pos];
  const fin = v => typeof v === 'number' && Number.isFinite(v) ? v : null;
  const field = i.setting.scoringField;
  const rec = window.TradeValueProductData.getPlayers().find(r => String(r.player_key) === key) || {};
  return {
    steps: [...card.querySelectorAll('.as-path-step h4')].map(e => e.textContent),
    expected: {input: fin(p.native), waiver: fin(pos.waiver), starterLine: fin(pos.starterLine),
      availability: fin(pos.avail), aboveWaivers: fin(p.vorp), startWorthy: fin(p.startWorthy), lineupShare: fin(p.lineupShare), starterPart: fin(p.starterSlice),
      fillInPart: fin(p.benchSlice), starterRate: fin(d.rates[p.pos + '|starter']),
      fillInRate: fin(d.rates[p.pos + '|bench']), pie: fin(i.valuePipeline.pie),
      output: fin(i.rows[key].adjusted[src]),
      // The publisher's own number, read from the player records the engine loads.
      ...(src === 'espn' ? {rawTotal: fin((rec.espn_ros || {})[field])} : {}),
      ...(src === 'razzball' ? {rawPerGame: fin((rec.rz_ppg || {})[field])} : {})},
    actual: Object.fromEntries([...card.querySelectorAll('[data-readout]')].map(e =>
      [e.dataset.readout, e.dataset.value === '' ? null : Number(e.dataset.value)])),
    published: window.TradeValueCurveControls.getAllRows().find(r => String(r.player_key) === key).values[src],
    text: card.textContent,
    headers: [...document.querySelectorAll('.as-table th')].map(e => e.textContent),
    overflow: [...card.querySelectorAll('*')].some(e => e.getBoundingClientRect().right > innerWidth + 1),
    indexed: Boolean(document.querySelector('.as-line-indexed'))
  };
}"""


class ProjectionPathRenderTest(unittest.TestCase):
    def test_projection_readouts_and_missing_held_honesty(self):
        from playwright.sync_api import sync_playwright
        _render_env.ensure_built()
        with _built_dist() as url, sync_playwright() as p:
            browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                        executable_path=_render_env.chromium_executable(p))
            try:
                for width in (1440, 375):
                    with self.subTest(width=width):
                        page = browser.new_page(viewport={"width": width, "height": 900})
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                        page.goto(url.split('#')[0] + '#values-auditing/single-source', wait_until='networkidle')
                        page.wait_for_function('() => window.TradeValueCurveControls?.isReady()')
                        page.wait_for_selector('#audit-source-root .as-seg')
                        active = page.evaluate('() => window.TradeValueCurveControls.getActiveSources()')
                        for source in ('espn', 'cbsros', 'razzball'):
                            page.evaluate(SELECT, source)
                            for index in (0, 1):
                                # A second player guards against a hard-coded example.
                                page.select_option('#as-worked-player', index=index)
                                got = page.evaluate(READ_PATH)
                                self.assertEqual(got['actual'], got['expected'], source)
                                self.assertEqual(got['actual']['output'], got['published'], source)
                                self.assertIn('Projected points/game', got['headers'])
                                self.assertIn('Published value', got['headers'])
                                self.assertNotIn('Published', got['headers'])
                                self.assertFalse(got['indexed'])
                                self.assertFalse(got['overflow'], (width, source))
                                self.assertIn('not a trade value supplied', got['text'])
                                self.assertIn('Expected lineup share', got['text'])
                                # JEG-1199: the trace starts at the publisher's own number.
                                self.assertEqual(got['steps'][:2], [RAW_STEP[source], 'Points per game the engine reads'], source)
                                if source == 'razzball':
                                    # Razzball publishes per game: the engine reads the published number as is.
                                    self.assertEqual(got['actual']['rawPerGame'], got['actual']['input'])
                                if source == 'espn' and got['actual']['rawTotal'] and got['actual']['input']:
                                    # ESPN's total, divided by games left, is the engine's input.
                                    self.assertGreater(got['actual']['rawTotal'], got['actual']['input'])
                        # Changing a real league setting must produce a fresh engine trace.
                        page.evaluate('() => window.TradeValueCurveControls.setTeams(10)')
                        for source in ('espn', 'cbsros', 'razzball'):
                            page.evaluate(SELECT, source)
                            got = page.evaluate(READ_PATH)
                            self.assertEqual(got['actual'], got['expected'], source)
                            self.assertEqual(got['actual']['output'], got['published'], source)
                        self.assertEqual(page.evaluate('() => window.TradeValueCurveControls.getActiveSources()'), active)
                        # Retained numbers for an excluded source are not proof it is live.
                        # Missing intermediates remain missing, zero remains zero, and the final
                        # readout is never recomputed from the deliberately inconsistent rates.
                        page.evaluate("""() => {
                          const C = window.TradeValueCurveControls, real = C.getInspection.bind(C);
                          C.getInspection = () => {
                            const i = real(), src = 'razzball';
                            i.excluded.push({key: src, reason: 'held for review'});
                            delete i.valuePipeline.sources[src].rates;
                            for (const [key, p] of Object.entries(i.players[src])) {
                              p.starterSlice = null; p.benchSlice = 0;
                              i.rows[key].adjusted[src] = null;
                            }
                            return i;
                          };
                          window.DDFAuditSource.render();
                        }""")
                        got = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.as-projection [data-readout]')]
                          .map(e => [e.dataset.readout, {value: e.dataset.value, text: e.textContent}]))""")
                        for field in ('starterPart', 'starterRate', 'fillInRate', 'output'):
                            self.assertEqual(got[field]['value'], '')
                            self.assertEqual(got[field]['text'], '— (unavailable)')
                        self.assertEqual(got['fillInPart']['value'], '0')
                        self.assertEqual(got['fillInPart']['text'], '0.0000')
                        text = page.locator('.as-projection').inner_text()
                        self.assertIn('held for review', text)
                        self.assertIn('does not establish', text)
                        self.assertEqual(errors, [])
                        page.close()
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
