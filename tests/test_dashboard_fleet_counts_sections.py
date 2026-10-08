"""Regression: the monitor's fleet headline must count top-level checkpoint
sections, not just per-source cells.

On 2026-10-01 the served monitor showed "60 checkpoints healthy. 0 broken."
while pipeline-checkpoints.json carried methodology_consistency: bad (the 4
parked fp/usat legacy combos). The fleet counter only tallied
data.sources[src].checkpoints (60 cells) and the methodology_consistency
section was never rendered anywhere in the page -- so a bad section was
invisible in both the headline and the body.

These tests fail against that broken state (counter block with no reference
to methodology_consistency/adj_curve_pipeline; no methodologyConsistency
host element) and pass with the fix.
"""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "modules" / "dashboard.html"


class FleetCountsTopLevelSectionsTest(unittest.TestCase):
    def test_counter_tallies_methodology_consistency(self):
        text = HTML.read_text(encoding="utf-8")
        m = re.search(r"// Count all checkpoints.*?(?=// Auto-open|\Z)", text, re.S)
        self.assertTrue(m, "fleet counter block not found -- test wiring is stale")
        block = m.group(0)
        self.assertIn(
            "methodology_consistency",
            block,
            "fleet headline must count the methodology_consistency section; "
            "otherwise it can claim '0 broken' while a section is bad",
        )

    def test_counter_tallies_adj_pipeline_stages(self):
        text = HTML.read_text(encoding="utf-8")
        m = re.search(r"// Count all checkpoints.*?(?=// Auto-open|\Z)", text, re.S)
        self.assertTrue(m, "fleet counter block not found -- test wiring is stale")
        self.assertIn(
            "adj_curve_pipeline",
            m.group(0),
            "fleet headline must count the adj_curve_pipeline stages",
        )

    def test_methodology_section_rendered(self):
        text = HTML.read_text(encoding="utf-8")
        self.assertIn(
            'id="methodologyConsistency"',
            text,
            "methodology_consistency must have a rendered section, not just a count",
        )
        self.assertIn(
            "data.methodology_consistency",
            text,
            "the methodology section renderer must read data.methodology_consistency",
        )


if __name__ == "__main__":
    unittest.main()
