"""Settled JEG-1212 wording outside the site (JEG-1411).

GLOSSARY_REF=origin/main checks the same guard against the unpatched source.
Posts 04–06 belong to open PR #1076; post 02 belongs to #982.
F6 mean and F18 Indexed were settled by Jeremy on 2026-10-31.
"""
import os
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKIPPED = {'02-how-many-backups.md', '04-how-we-rescale-trade-charts.md',
           '05-missing-zero-one-source.md', '06-trade-confidence.md'}


def read(path):
    ref = os.environ.get('GLOSSARY_REF')
    if ref:
        return subprocess.check_output(['git', 'show', f'{ref}:{path.relative_to(ROOT)}'], cwd=ROOT, text=True)
    return path.read_text()


class GlossaryOutsideSiteTest(unittest.TestCase):
    def test_post07_signal_uses_mean(self):
        path = ROOT / 'tools/research/gap_backtest.py'
        namespace = {'__name__': 'post07_guard', '__file__': str(path)}
        exec(compile(read(path), str(path), 'exec'), namespace)
        signal = namespace['market_consensus'](10, {'a': 0, 'b': 6, 'c': 30, 'missing': None})
        self.assertEqual(signal['value'], 12)  # Median would be 6; a real zero counts.
        self.assertEqual(signal['gap'], 2)
        self.assertEqual(signal['of'], 3)
        self.assertIsNone(namespace['market_consensus'](10, {'missing': None})['value'])

    def test_settled_glossary(self):
        paths = list((ROOT / 'supabase/functions/mcp').glob('*.ts'))
        paths += list((ROOT / 'app/llm').rglob('*.txt'))
        paths += [ROOT / p for p in ['app/llm/server-card.json', 'app/llm/skill/SKILL.md',
                  'docs/use-ddf-in-claude-chatgpt.md', 'docs/values-endpoint.md',
                  'dist/llms.txt', 'dist/ddf-skill/SKILL.md']]
        paths += [p for p in (ROOT / 'docs/research').rglob('*.md')
                  if p.parent.name == 'posts' and p.name not in SKIPPED]
        forbidden = [r'market[- ]value\b', r'the market \(DDF Value\)',
                     r'the market and the projections disagree',
                     r'four adjusted trade charts',
                     r'DDF Value\*{0,2} is (?:our own value for a player: )?the (?:equal-weight )?(?:average|mean) of the projection',
                     r'equal-weight average of every included source',
                     r'DDF Value \(blended\)', r'DDF Projections',
                     r'plain mean of the chart results', r'\(rescaled\)|\*\*Rescaled\*\*|chart.s Rescaled',
                     r'Market consensus', r'Market vs projections',
                     r'the market says no', r'our value and the\s+market most disagree',
                     r'preserves the publisher.s scale', r'the publisher.s original scale']
        for p in paths:
            text = read(p)
            # Generic investing analogy, not the four-chart mean.
            text = text.replace("Market value and fundamental value are different things.", "")
            for pattern in forbidden:
                # Post 02's generic investing analogy is excluded above.
                with self.subTest(path=str(p.relative_to(ROOT)), pattern=pattern):
                    self.assertIsNone(re.search(pattern, text, re.I))
            for sentence in re.split(r'[.!?]\s', text):
                if re.search(r'market[-_ ]activity', sentence, re.I):
                    self.assertIn('FantasyCalc', sentence, str(p))
                if re.search(r'DDF Value(?:\*\*)? is (?:our one number|the average)', sentence):
                    self.assertNotRegex(sentence, r'ESPN|CBS|Razzball|FantasyCalc|FantasyPros|USA Today')
        post = read(ROOT / 'docs/research/posts/07-does-the-gap-predict.md')
        self.assertIn('Trade chart average (mean)', post)
        self.assertIn('mean-based', post)
        self.assertNotIn('median of', post)
        definition = "the average of the four trade charts' weight-adjusted indexed values"
        for name in ['app/llm/llms.txt', 'app/llm/skill/SKILL.md',
                     'supabase/functions/mcp/rpc.ts', 'supabase/functions/mcp/tools.ts']:
            self.assertIn(definition, read(ROOT / name), name)
