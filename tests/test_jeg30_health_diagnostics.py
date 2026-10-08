"""JEG-30: Chart Health structured per-source guard diagnostics.

The fixed-pie guard's per-source numbers must live in a collapsible Chart
Health detail view, not stuffed into the thrown error string.

Discrimination:
- Pre-fix: runRegressionGuards builds fixedPieDetail with ad-hoc formatting
  and appends it to the error message.
- Post-fix: the error message has no bracketed per-source dump; the
  diagnostics are recorded in Chart Health with the full checks array.
"""
import re
import unittest
from pathlib import Path

WIDGET = Path(__file__).resolve().parent.parent / "app" / "trade-value-chart" / "assets" / "curve-widget.js"


def read_widget():
    return WIDGET.read_text(encoding="utf-8")


class TestJEG30HealthDiagnostics(unittest.TestCase):
    def test_no_adhoc_fixed_pie_detail_in_error(self):
        """The thrown error must not contain the hand-stuffed per-source dump."""
        src = read_widget()
        # The old code built: fixedPieDetail = ` [espn: total=... target=... ...]`
        # and appended ${fixedPieDetail} to the thrown error.
        self.assertNotIn(
            "fixedPieDetail",
            src,
            "fixedPieDetail string-stuffing still present; per-source numbers "
            "must live in the Chart Health detail view, not the error string",
        )

    def test_error_points_to_chart_health(self):
        """The plain-words error must direct the reader to Chart Health."""
        src = read_widget()
        self.assertIn("See Chart Health for per-source diagnostics", src)

    def test_chart_health_records_fixed_pie_with_diagnostics(self):
        """The fixed-pie guard result is recorded in Chart Health with the checks."""
        src = read_widget()
        # ChartHealth.record("fixed-pie-indexed", ..., fixedPie.ok, ..., fixedPie)
        self.assertRegex(
            src,
            r'ChartHealth\.record\(\s*"fixed-pie-indexed"',
            "fixed-pie guard must be recorded in Chart Health",
        )

    def test_detail_view_renders_only_on_failure(self):
        """The diagnostics table renders only for failed/warned checks."""
        src = read_widget()
        # render() gates the detail HTML on r.status !== "pass"
        self.assertRegex(
            src,
            r'\(r\.status !== "pass" && r\.diagnostics\)',
            "detail view must render only on failure/warning, keeping the happy path clean",
        )

    def test_detail_view_has_per_source_columns(self):
        """The detail table shows total, target, delta, basis, players per source."""
        src = read_widget()
        for col in ["Total", "Target", "Delta", "Basis", "Players"]:
            self.assertIn(f"<th>{col}</th>", src, f"detail table missing column: {col}")
        # Per-position breakdown rows for the anchor check
        self.assertIn("health-perpos", src)


if __name__ == "__main__":
    unittest.main()
