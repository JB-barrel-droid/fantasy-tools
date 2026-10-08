"""Regression: the Scale Agreement section must be rendered AND counted.

On 2026-10-01 the methodology_consistency section was invisible in both the
fleet headline and the page body while it was bad. The scale-agreement
section follows the same pattern: it must have a rendered section host, a
renderer that reads the JSON, and its status must be tallied in the fleet
headline counter. These tests fail if any of those three are missing.
"""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "modules" / "dashboard.html"


class ScaleAgreementDashboardTest(unittest.TestCase):
    def test_section_host_rendered(self):
        text = HTML.read_text(encoding="utf-8")
        self.assertIn(
            'id="scaleAgreement"',
            text,
            "scale agreement must have a rendered section host, not just a count",
        )
        self.assertIn(
            'id="scaleAgreementSummary"',
            text,
            "scale agreement must have a summary host",
        )

    def test_renderer_reads_json(self):
        text = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "scale-agreement.json",
            text,
            "the scale agreement renderer must fetch scale-agreement.json",
        )
        # The renderer must surface the three verdicts.
        for verdict in ("agreement", "genuine disagreement", "indexation artifact"):
            self.assertIn(
                verdict,
                text,
                f"renderer must handle the '{verdict}' verdict",
            )

    def test_counter_tallies_scale_agreement(self):
        text = HTML.read_text(encoding="utf-8")
        m = re.search(r"// Count all checkpoints.*?(?=// Render per-source|\\Z)", text, re.S)
        self.assertTrue(m, "fleet counter block not found -- test wiring is stale")
        block = m.group(0)
        self.assertIn(
            "scale_agreement",
            block,
            "fleet headline must count the scale_agreement section; "
            "otherwise it can claim '0 broken' while the section is bad",
        )

    def test_checkpoints_builder_surfaces_scale_agreement(self):
        # The synchronously-loaded pipeline-checkpoints.json must carry the
        # scale_agreement status so the fleet counter can tally it.
        builder = (
            Path(__file__).resolve().parent.parent
            / "pipelines" / "build_pipeline_checkpoints.py"
        )
        text = builder.read_text(encoding="utf-8")
        self.assertIn(
            "scale_agreement",
            text,
            "build_pipeline_checkpoints.py must surface the scale-agreement status",
        )
        self.assertIn(
            "build_scale_agreement_summary",
            text,
            "the checkpoints builder must have a scale-agreement summary function",
        )


if __name__ == "__main__":
    unittest.main()
