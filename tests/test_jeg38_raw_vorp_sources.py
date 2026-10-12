"""JEG-38: Raw value above waivers must carry CBS ROS and Razzball.

Discrimination tests for the three-source raw VORP implementation:
- the chart's "Raw value above waivers" group has all three curves
- the dashboard carries the three columns with the same source-pure math

JEG-608: the widget's browser-side vorpPricedRows (and its source-purity and
fail-closed tests) was deleted by JEG-508 (#491): raw VORP now comes from the
value pipeline engine (tests/test_value_pipeline_engine.py).
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIDGET = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
DASH = REPO / "app" / "trade-value-chart" / "assets" / "comparison-dashboard.js"


def _extract_fn(src, name):
    """Extract `function name(...)` source by brace matching."""
    start = src.index(f"function {name}(")
    depth = 0
    for i in range(src.index("{", start), len(src)):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"unbalanced braces extracting {name}")


def _extract_const(src, name):
    """Extract `const name = <array|object>` up to the matching close."""
    start = src.index(f"const {name} =")
    # value starts at the first [ or { after the =
    open_idx = None
    for i in range(src.index("=", start) + 1, len(src)):
        if src[i] in "[{":
            open_idx = i
            break
    assert open_idx is not None, f"no array/object for {name}"
    open_ch = src[open_idx]
    close_ch = "]" if open_ch == "[" else "}"
    depth = 0
    for i in range(open_idx, len(src)):
        ch = src[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError(f"unbalanced brackets extracting {name}")


def _node_eval(script, payload):
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        proc = subprocess.run(["node", path], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, f"node harness crashed: {proc.stderr[:400]}"
    return json.loads(proc.stdout)


# Eval a `const NAME = <literal>;` extraction by stripping the declaration
# and wrapping the literal in parens (a bare {...} evals as a block).
CONST_EVAL_SCRIPT = (
    "const {t} = JSON.parse(require(\"fs\").readFileSync(0, \"utf8\"));\n"
    "const code = t.replace(/^const \\w+ = /, \"\").replace(/;\\s*$/, \"\");\n"
    "process.stdout.write(JSON.stringify(eval(\"(\" + code + \")\")));\n"
)

class WidgetRawGroupTest(unittest.TestCase):
    def test_raw_group_has_all_three_sources(self):
        groups = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(WIDGET.read_text(encoding="utf-8"), "SOURCE_GROUPS")},
        )
        # The group was "Raw VORP vs waivers" until the public-copy rule limited
        # VORP to the exact phrase "VORP vs waivers".
        raw = [g for g in groups if g["label"] == "Projections (VORP vs waivers)"]
        self.assertEqual(len(raw), 1, "expected exactly one projections VORP vs waivers group")
        self.assertEqual(raw[0]["keys"], ["espn_vorp", "cbsros_vorp", "razzball_vorp"])

    def test_vorp_defs_map_to_source_pure_fields(self):
        defs = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(WIDGET.read_text(encoding="utf-8"), "VORP_SOURCE_DEFS")},
        )
        self.assertEqual(defs["espn_vorp"]["ppgField"], "espn_ppg")
        self.assertEqual(defs["cbsros_vorp"]["ppgField"], "cbsros_ppg")
        self.assertEqual(defs["razzball_vorp"]["ppgField"], "rz_ppg")


class DashboardRawColumnsTest(unittest.TestCase):
    def test_dashboard_source_keys_include_vorp_trio(self):
        keys = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(DASH.read_text(encoding="utf-8"), "SOURCE_KEYS")},
        )
        for key in ("espn_vorp", "cbsros_vorp", "razzball_vorp"):
            self.assertIn(key, keys)

    def test_dashboard_labels_cover_vorp_trio(self):
        labels = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(DASH.read_text(encoding="utf-8"), "LABELS")},
        )
        self.assertIn("raw vorp vs waivers", labels["espn_vorp"].lower())
        self.assertIn("raw vorp vs waivers", labels["cbsros_vorp"].lower())
        self.assertIn("raw vorp vs waivers", labels["razzball_vorp"].lower())

    def test_dashboard_vorp_defs_source_pure(self):
        defs = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(DASH.read_text(encoding="utf-8"), "VORP_SOURCE_DEFS")},
        )
        self.assertEqual(defs["espn_vorp"]["ppgField"], "espn_ppg")
        self.assertEqual(defs["cbsros_vorp"]["ppgField"], "cbsros_ppg")
        self.assertEqual(defs["razzball_vorp"]["ppgField"], "rz_ppg")
        # each VORP column validates against its own source's projection feed
        self.assertEqual(defs["cbsros_vorp"]["validationKey"], "cbsros")
        self.assertEqual(defs["razzball_vorp"]["validationKey"], "razzball")


if __name__ == "__main__":
    unittest.main()
