"""Regression: comparison-dashboard.js LABELS must not hardcode a week.

sourceLabel() appends the data-driven week (" Wk N" from weekForSource) to
every weeked source. On 2026-10-01 the LABELS map ALSO hardcoded "(Week 4)"
into each label, so the rendered UI showed duplicated week markers:
"CBS Adjusted (Week 4) Wk 4", "Locked to USAT Adjusted (Week 4) Wk 4 value".

The week marker now lives in exactly one place: the data-driven append in
sourceLabel(). This test fails against the duplicated state (any LABELS
value containing "(Week N)") and passes with week-free labels.

Bonus effect: labels can no longer go stale when the data week rolls --
the C10 stale-hardcoded-label monitor check has nothing to flag.
"""
import re
import unittest
from pathlib import Path

JS = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "trade-value-chart"
    / "assets"
    / "comparison-dashboard.js"
)


def _labels_block(text):
    m = re.search(r"const LABELS = \{(.*?)\};", text, re.DOTALL)
    assert m, "LABELS block not found -- test wiring is stale"
    return m.group(1)


class NoHardcodedWeekLabelsTest(unittest.TestCase):
    def test_labels_carry_no_week(self):
        block = _labels_block(JS.read_text())
        hardcoded = re.findall(r"\((Week \d+)\)", block)
        self.assertFalse(
            hardcoded,
            "LABELS hardcodes week markers that sourceLabel() also appends, "
            f"producing '(Week N) Wk N' duplication: {hardcoded}",
        )

    def test_source_label_appends_data_driven_week(self):
        """The single week marker must come from weekForSource via sourceLabel."""
        text = JS.read_text()
        self.assertIn("const week = weekForSource(key);", text)
        self.assertRegex(text, r"return week && key !== \"espn\" \? `\$\{base\} Wk \$\{week\}` : base;")


if __name__ == "__main__":
    unittest.main()
