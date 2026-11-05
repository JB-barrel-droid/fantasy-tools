"""JEG-1410: pin Jeremy's article byte for byte and require the separate block."""
import hashlib
import os
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ManifestoCopyTest(unittest.TestCase):
    def test_verbatim_article_and_block_below(self):
        shell = Path(os.environ.get("MANIFESTO_SHELL", ROOT / "app/v2/shell.html")).read_bytes()
        article = re.search(rb'<article class="v2-mf-text">.*?</article>', shell, re.S)
        self.assertIsNotNone(article)
        self.assertEqual(hashlib.sha256(article.group()).hexdigest(), "456641bd0b7348aed8144570b679d56cb7b3d5bd0738c6cb7b9705be075bf451")
        block = re.search(rb'<section[^>]+id="v2ManifestoUses".*?</section>', shell, re.S)
        self.assertIsNotNone(block, "How the tool uses this block missing")
        self.assertGreater(block.start(), article.end())
        self.assertLess(block.end(), shell.index(b'</main>', article.end()))
        for text in (b'How the tool uses this', b'DDF Value', b'DDF Value (projections)', b'Trade chart average', b'not built yet'):
            self.assertIn(text, block.group())

    def test_mapping_uses_the_current_screen_name(self):
        shell = Path(os.environ.get("MANIFESTO_SHELL", ROOT / "app/v2/shell.html")).read_bytes()
        block = re.search(rb'<section[^>]+id="v2ManifestoUses".*?</section>', shell, re.S)
        nav = re.search(rb'<a\b[^>]*data-key="values"[^>]*>.*?<span class="v2-tab-full">([^<]+)</span>', shell, re.S)
        self.assertIsNotNone(block)
        self.assertIsNotNone(nav)
        self.assertIn(nav.group(1) + b' shows DDF Value', block.group())

    def test_existing_calculations_are_not_called_unbuilt(self):
        shell = Path(os.environ.get("MANIFESTO_SHELL", ROOT / "app/v2/shell.html")).read_bytes()
        block = re.search(rb'<section[^>]+id="v2ManifestoUses".*?</section>', shell, re.S)
        self.assertIsNotNone(block)
        text = re.sub(rb'<[^>]+>', b' ', block.group())
        sentences = re.split(rb'(?<=[.!?])\s+', text.lower())
        unbuilt = [s for s in sentences if b'not built yet' in s]
        self.assertEqual(len(unbuilt), 1)
        self.assertNotRegex(unbuilt[0], rb'\b(?:option|timing|time discounts?)\b')
        calculations = [s for s in sentences if b'calculates' in s]
        self.assertEqual(len(calculations), 1)
        self.assertIn(b'option', calculations[0])
        self.assertIn(b'timing', calculations[0])
        self.assertRegex(calculations[0], rb'not.*(?:show|expos)')
