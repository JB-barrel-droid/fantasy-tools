"""Regression: the direct-series scale-agreement check must surface as a warning, not a red FAIL.

The pipeline's scale-agreement monitor verdicts fantasycalc/usatoday "genuine
disagreement" -- their published shapes sit outside the 0.8-1.25x anchor band
*before any indexation* -- and curve-widget.js documents that these
disagreements are "surfaced via ChartHealth as a warning". The old code called
ChartHealth.record(..., scaleAgreement.ok, ...), which renders a red
"Health: 1 FAIL" badge and tells users "a red FAIL means the rendered numbers
are wrong" -- a false alarm for honest publisher shape disagreement.

Fix: offenders route through ChartHealth.warn (mirroring the adjusted family's
adjusted-scale-agreement pattern); the 0.8-1.25x band itself is unchanged.

Negative-tested 2026-10-04: the pre-fix snippet (record with
scaleAgreement.ok) fails this test; the fixed warn-routing passes.
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGET = REPO_ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"

CHECK_ID = '"source-scale-agreement"'

# The old fail-producing pattern: record(id, ...) whose detail names the
# offenders (i.e. the fail path renders the disagreement as a red FAIL).
# The fixed code's remaining record() call only renders the within-band
# happy path and never mentions offenders.
OLD_RECORD_RE = re.compile(
    r'ChartHealth\.record\(\s*' + re.escape(CHECK_ID) + r'[\s\S]{0,400}?'
    r'scaleAgreement\.offenders',
)

# The fixed pattern: a ChartHealth.warn( call carrying the same check id.
WARN_RE = re.compile(
    r'ChartHealth\.warn\(\s*' + re.escape(CHECK_ID),
    re.DOTALL,
)


def uses_warn_routing(source: str) -> bool:
    """True when the source-scale-agreement check warns on offenders instead
    of recording a fail."""
    return bool(WARN_RE.search(source)) and not bool(OLD_RECORD_RE.search(source))


BROKEN_SNIPPET = """\
    ChartHealth.record(
      "source-scale-agreement",
      "Published charts agree with the anchor's scale",
      scaleAgreement.ok,
      scaleAgreement.offenders.length
        ? `positional peaks outside ${scaleAgreement.band.join("-")}x of the anchor: ${scaleAgreement.offenders.join("; ")}`
        : `${scaleAgreement.compared} positional peaks within ${scaleAgreement.band.join("-")}x of the anchor`
    );
"""


class TestSourceScaleAgreementWarn(unittest.TestCase):
    def test_fail_routing_is_rejected(self):
        """The pre-fix record(..., scaleAgreement.ok, ...) pattern fails."""
        self.assertFalse(
            uses_warn_routing(BROKEN_SNIPPET),
            "Guard must fail against the pre-fix fail-routing snippet",
        )

    def test_live_widget_warns_on_disagreement(self):
        """The shipped widget routes the check through ChartHealth.warn."""
        source = WIDGET.read_text(encoding="utf-8")
        self.assertTrue(
            uses_warn_routing(source),
            "source-scale-agreement must warn (not fail) on genuine publisher "
            "shape disagreement in app/trade-value-chart/assets/curve-widget.js",
        )


if __name__ == "__main__":
    unittest.main()
