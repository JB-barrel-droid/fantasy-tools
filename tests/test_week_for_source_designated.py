"""Regression: weekForSource() must honor each source's own week designation.

JEG-293: the comparison table subtitle ("source weeks current" vs "N stale
Week X sources") is driven by weekForSource(). The pipeline no longer emits
fitwk bake ids, so the old code fell through to the GLOBAL active week for
every source -- the stale-source branch could never fire, and a publisher
that missed a week would still be reported "current".

The data already carries the honest per-source signal
(`sources.<key>.week_designated`, e.g. "Week 4" / "rest of season"); the fix
reads it between the fitwk match and the global fallback.

These tests extract the REAL weekForSource (plus its WEEKED_SOURCE_KEYS set)
from comparison-dashboard.js and execute it in node against stubbed data, so
they discriminate on behavior, not on code shape. They fail against the
pre-fix file (designated "Week 3" resolves to the global 4) and pass after.
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

_STUB_DATA = {
    "value_weeks": {"monday": 4},
    "sources": {
        "usatoday": {"week_designated": "Week 3"},
        "cbs": {"week_designated": "Week 3", "fit_bake_id": "ddf-fitwk5-x"},
        "cbsros": {"week_designated": "rest of season"},
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
    text = JS.read_text()
    m = re.search(r"const WEEKED_SOURCE_KEYS = new Set\(\[.*?\]\);", text, re.DOTALL)
    assert m, "WEEKED_SOURCE_KEYS not found -- test wiring is stale"
    fn = _extract_function(text, "weekForSource")
    script = (
        m.group(0)
        + "\nlet data = "
        + json.dumps(_STUB_DATA)
        + ";\n"
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

    def test_fitwk_bake_id_still_wins(self):
        """Precedence unchanged: fitwk bake id beats week_designated."""
        got = _run_week_for_source(["cbs"])
        self.assertEqual(got["cbs"], 5)

    def test_rest_of_season_keeps_global_fallback(self):
        """ROS sources carry no week; they keep the old global behavior."""
        got = _run_week_for_source(["cbsros", "razzball"])
        self.assertEqual(got["cbsros"], 4)
        self.assertEqual(got["razzball"], 4)

    def test_non_weeked_key_returns_null(self):
        got = _run_week_for_source(["espn"])
        self.assertIsNone(got["espn"])


if __name__ == "__main__":
    unittest.main()
