"""GAP-026: the direct-series "Published charts agree with the anchor's scale"
ChartHealth check is retired (Jeremy, 2026-10-08).

Publisher shape disagreement is the product, so a peak-vs-anchor band on the
direct published charts only ever flagged the thing the chart exists to show
(it warned in all 12 league shapes). Curve correctness stays guarded by
fixedPieIndexed, the 12-combo sweep and the per-source parity tests; the
adjusted-series agreement check is a different check and stays.

This replaces test_source_scale_agreement_warn.py, which pinned the retired
check's warn routing.

Negative-tested 2026-10-08: run against the pre-retirement curve-widget.js
(origin/main dac0ff2) every assertion in test_widget_has_no_direct_check fails.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGET = REPO_ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"


def retired_check_traces(source: str) -> list[str]:
    """Every trace of the retired check still present in a widget source."""
    traces = []
    if re.search(r'ChartHealth\.(record|warn)\(\s*"source-scale-agreement"', source):
        traces.append("ChartHealth source-scale-agreement entry")
    if "sourceScaleAgreement" in source:
        traces.append("diagnostics.sourceScaleAgreement")
    if "scaleAgreementDiagnostics" in source:
        traces.append("scaleAgreementDiagnostics()")
    return traces


PRE_RETIREMENT_SNIPPET = """\
    const scaleAgreement = scaleAgreementDiagnostics();
    if (scaleAgreement.compared > 0 && !scaleAgreement.ok) {
      ChartHealth.warn(
        "source-scale-agreement",
        "Published charts agree with the anchor's scale", "...");
    }
    const diagnostics = {fixedPieIndexed:fixedPie.ok, sourceScaleAgreement:scaleAgreement.ok};
"""


class TestSourceScaleAgreementRetired(unittest.TestCase):
    def test_guard_catches_the_retired_check(self):
        self.assertEqual(len(retired_check_traces(PRE_RETIREMENT_SNIPPET)), 3)

    def test_widget_has_no_direct_check(self):
        self.assertEqual(retired_check_traces(WIDGET.read_text(encoding="utf-8")), [])

    def test_kept_checks_still_present(self):
        source = WIDGET.read_text(encoding="utf-8")
        self.assertIn('"fixed-pie-indexed"', source)
        self.assertIn('"adjusted-scale-agreement"', source)
        self.assertIn("fixedPieIndexed:fixedPie.ok", source)


if __name__ == "__main__":
    unittest.main()
