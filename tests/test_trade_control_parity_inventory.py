"""JEG-1220 source-level UI parity inventory; not numerical/browser proof.

Expected-failure list: package choices, keep-starters widgets, guardrail
forwarding. Remove each decorator when its owning slice closes the gap.
Unexpected successes fail so resolved exceptions cannot silently accumulate.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TradeControlParityInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pair = (ROOT / 'app/v2/finder.js').read_text()
        cls.league = (ROOT / 'app/v2/league.js').read_text()
        cls.opportunities = (ROOT / 'app/v2/opportunities.js').read_text()
        # Broken extraction must fail outside the expected-failure methods.
        cls.pair_sizes = re.search(r'const MAX_SIZE_CHOICES = \[([^]]+)\]', cls.pair)
        cls.league_sizes = re.search(r'sel\("v2LgSize",.*?\[\[(.*?)\]\], ws.ui.maxSize', cls.league)
        if not cls.pair_sizes or not cls.league_sizes:
            raise AssertionError('Package control anchors moved; update inventory extraction')
        if 'const res = find(' not in cls.opportunities or 'const market =' not in cls.opportunities or 'function* pairingSteps(' not in cls.opportunities:
            raise AssertionError('Pairing entrypoint moved; inspect guardrail forwarding')

    @unittest.expectedFailure
    def test_package_size_choices_match(self):
        pair = [int(n) for n in self.pair_sizes[1].split(',')]
        league = [int(n) for n in re.findall(r'(?:^|\], \[)(\d+),', self.league_sizes[1])]
        self.assertEqual(pair, league)

    @unittest.expectedFailure
    def test_both_scopes_offer_keep_starters_widgets(self):
        self.assertIn('v2FindKeepMine', self.pair)
        self.assertIn('v2FindKeepTheirs', self.pair)
        self.assertRegex(self.league, r'id: "v2LgKeepMine"')
        self.assertRegex(self.league, r'id: "v2LgKeepTheirs"')

    @unittest.expectedFailure
    def test_league_pairing_forwards_guardrails(self):
        call = self.opportunities.split('const res = find(', 1)[1].split('const market =', 1)[0]
        self.assertRegex(call, r'guardrails\s*:')


if __name__ == '__main__':
    unittest.main()
