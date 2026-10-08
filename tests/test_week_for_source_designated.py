"""Regression: weekForSource() must honor each source's own week designation.

JEG-293: the comparison table subtitle ("source weeks current" vs "N stale
Week X sources") is driven by weekForSource(). The pipeline no longer emits
fitwk bake ids, so the old code fell through to the GLOBAL active week for
every source -- the stale-source branch could never fire, and a publisher
that missed a week would still be reported "current".

The data already carries the honest per-source signal
(`sources.<key>.week_designated`, e.g. "Week 4" / "rest of season"); the fix
reads it between the fitwk match and the global fallback.

These tests extract the REAL weekForSource (plus its WEEKED_SOURCE_KEYS set
and freshness helpers) from comparison-dashboard.js and execute it in node
against stubbed data and the real product-data.js freshness record, so they
discriminate on behavior, not on code shape. They fail against the pre-fix
file (designated "Week 3" resolves to the global 4) and pass after.

GAP-043 (2026-10-07) changed the rule these pin: every week label now comes
from product-data.js getSourceFreshness() (week_designated, then
content_vintage, then the source's own dates on the Tuesday-flip content
calendar). So a stale `fitwk` bake id no longer outranks the source's own
designation, and rest-of-season sources are dated by their own vintage
instead of inheriting the global `value_weeks.monday`.
"""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

JS = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "trade-value-chart"
    / "assets"
    / "comparison-dashboard.js"
)

PRODUCT_DATA = JS.parent / "product-data.js"

_STUB_DATA = {
    "value_weeks": {"monday": 4},
    "sources": {
        "usatoday": {"week_designated": "Week 3"},
        "cbs": {"week_designated": "Week 3", "fit_bake_id": "ddf-fitwk5-x"},
        "cbsros": {"week_designated": "rest of season", "vintage": "2026-09-24"},
        "razzball": {},
    },
}


def _extract_function(text, name):
    """Extract `function <name>(...) {...}` by brace matching."""
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", text)
    assert m, f"{name} not found -- test wiring is stale"
    depth = 0
    for i in range(m.start(), len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[m.start() : i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _run_week_for_source(keys):
    text = JS.read_text(encoding="utf-8")
    m = re.search(r"const WEEKED_SOURCE_KEYS = new Set\(\[.*?\]\);", text, re.DOTALL)
    assert m, "WEEKED_SOURCE_KEYS not found -- test wiring is stale"
    fn = "\n".join(_extract_function(text, name) for name in ("sourceFreshness", "weekForSource"))
    row = re.search(r"const freshnessRow = .*?;\n", text)
    assert row, "freshnessRow not found -- test wiring is stale"
    script = (
        "const module = {exports: {}};\nconst window = {};\n"
        + PRODUCT_DATA.read_text(encoding="utf-8")
        + "\nconst pd = module.exports;\n"
        + "window.TradeValueProductData = {getSourceFreshness: () => pd.buildSourceFreshness("
        + json.dumps(_STUB_DATA["sources"])
        + ", {today: '2026-10-07'})};\n"
        + m.group(0)
        + "\nlet data = "
        + json.dumps(_STUB_DATA)
        + ";\n"
        + row.group(0)
        + fn
        + "\nconsole.log(JSON.stringify({"
        + ",".join(f'"{k}": weekForSource("{k}")' for k in keys)
        + "}));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name
    out = subprocess.run(
        ["node", path], capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0, f"node harness failed: {out.stderr[:500]}"
    return json.loads(out.stdout)


class WeekForSourceDesignatedTest(unittest.TestCase):
    def test_designated_week_honored(self):
        """A source designated 'Week 3' resolves to 3, not the global 4."""
        got = _run_week_for_source(["usatoday"])
        self.assertEqual(got["usatoday"], 3)

    def test_designation_beats_fitwk_bake_id(self):
        """GAP-043: the source's own week wins; a fit bake id is not content."""
        got = _run_week_for_source(["cbs"])
        self.assertEqual(got["cbs"], 3)

    def test_rest_of_season_dated_by_own_vintage(self):
        """GAP-043: ROS sources take their vintage's content week, never the
        global value_weeks.monday; an undated source gets no week at all."""
        got = _run_week_for_source(["cbsros", "razzball"])
        self.assertEqual(got["cbsros"], 3)  # 2026-09-24 is content Week 3
        self.assertIsNone(got["razzball"])

    def test_non_weeked_key_returns_null(self):
        got = _run_week_for_source(["espn"])
        self.assertIsNone(got["espn"])


if __name__ == "__main__":
    unittest.main()
