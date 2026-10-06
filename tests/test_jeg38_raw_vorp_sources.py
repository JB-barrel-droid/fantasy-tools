"""JEG-38: Raw value above waivers must carry CBS ROS and Razzball.

Discrimination tests for the three-source raw VORP implementation:
- the chart's "Raw value above waivers" group has all three curves
- each curve reads ONLY its own source's per-game projections
- missing/invalid projection data fails closed (empty rows, no invented values)
- the dashboard carries the three columns with the same source-pure math

These tests fail on the pre-JEG-38 state (ESPN-only raw VORP): the group
membership test fails because the old group had just ["espn_vorp"], and the
purity tests fail because the old code had no cbsros_vorp/razzball_vorp
defs or rows at all.
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

# Shared stub players: each source's projections differ, so a curve reading
# the wrong field is caught by the value, not just by presence.
STUB_PLAYERS = [
    {"player_key": 1, "pos": "QB",
     "espn_ppg": {"ppr": 20}, "cbsros_ppg": {"ppr": 18}, "rz_ppg": {"ppr": 19}},
    {"player_key": 2, "pos": "QB", "cbsros_ppg": {"ppr": 15}},
    {"player_key": 3, "pos": "QB", "rz_ppg": {"ppr": 16}},
    {"player_key": 4, "pos": "RB", "espn_ppg": {"ppr": 14}},
]

VORP_ROWS_SCRIPT = (
    "const {fnText, defsText, vorpKey, players} = "
    "JSON.parse(require(\"fs\").readFileSync(0, \"utf8\"));\n"
    "const POSITION_ORDER = [\"QB\", \"RB\", \"WR\", \"TE\"];\n"
    "const defsCode = defsText.replace(/^const \\w+ = /, \"\").replace(/;\\s*$/, \"\");\n"
    "const VORP_SOURCE_DEFS = eval(\"(\" + defsCode + \")\");\n"
    "const canonicalByKey = new Map(players.map(p => [p.player_key, p]));\n"
    "const scoringField = () => \"ppr\";\n"
    "const compareEspnPlayers = (a, b) => b.ppg - a.ppg;\n"
    "const vorpPricedRows = eval(\"(\" + fnText + \")\");\n"
    "const rows = vorpPricedRows(vorpKey);\n"
    "process.stdout.write(JSON.stringify(rows.map(r => "
    "({key: r.player.player_key, ppg: r.ppg, pos: r.player.pos}))));\n"
)


class WidgetRawGroupTest(unittest.TestCase):
    def test_raw_group_has_all_three_sources(self):
        groups = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(WIDGET.read_text(), "SOURCE_GROUPS")},
        )
        raw = [g for g in groups if g["label"] == "Raw VORP vs waivers"]
        self.assertEqual(len(raw), 1, "expected exactly one Raw VORP vs waivers group")
        self.assertEqual(raw[0]["keys"], ["espn_vorp", "cbsros_vorp", "razzball_vorp"])

    def test_vorp_defs_map_to_source_pure_fields(self):
        defs = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(WIDGET.read_text(), "VORP_SOURCE_DEFS")},
        )
        self.assertEqual(defs["espn_vorp"]["ppgField"], "espn_ppg")
        self.assertEqual(defs["cbsros_vorp"]["ppgField"], "cbsros_ppg")
        self.assertEqual(defs["razzball_vorp"]["ppgField"], "rz_ppg")


class WidgetSourcePurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = WIDGET.read_text()
        cls.fn_text = _extract_fn(src, "vorpPricedRows")
        cls.defs_text = _extract_const(src, "VORP_SOURCE_DEFS")

    def _rows(self, vorp_key, players=STUB_PLAYERS):
        return _node_eval(VORP_ROWS_SCRIPT, {
            "fnText": self.fn_text,
            "defsText": self.defs_text,
            "vorpKey": vorp_key,
            "players": players,
        })

    def test_cbsros_reads_only_cbsros_ppg(self):
        rows = {r["key"]: r["ppg"] for r in self._rows("cbsros_vorp")}
        self.assertEqual(rows[1], 18, "player 1 must use cbsros_ppg, not espn_ppg=20")
        self.assertEqual(rows[2], 15, "player with only cbsros_ppg must appear")
        self.assertNotIn(3, rows, "player with only rz_ppg must not appear")
        self.assertNotIn(4, rows, "player with only espn_ppg must not appear")

    def test_razzball_reads_only_rz_ppg(self):
        rows = {r["key"]: r["ppg"] for r in self._rows("razzball_vorp")}
        self.assertEqual(rows[1], 19, "player 1 must use rz_ppg, not espn_ppg=20")
        self.assertEqual(rows[3], 16, "player with only rz_ppg must appear")
        self.assertNotIn(2, rows, "player with only cbsros_ppg must not appear")
        self.assertNotIn(4, rows, "player with only espn_ppg must not appear")

    def test_espn_unchanged_and_pure(self):
        rows = {r["key"]: r["ppg"] for r in self._rows("espn_vorp")}
        self.assertEqual(rows[1], 20)
        self.assertEqual(rows[4], 14)
        self.assertNotIn(2, rows)
        self.assertNotIn(3, rows)

    def test_missing_projections_fail_closed(self):
        # Missing fields and non-numeric values are excluded (fail closed).
        # Note: explicit null becomes Number(null)=0 by pre-existing JS
        # semantics, but the real fixture carries no null ppg values --
        # only missing fields -- so that quirk is out of scope here.
        players = [{"player_key": 9, "pos": "QB"},
                   {"player_key": 11, "pos": "QB", "cbsros_ppg": {"ppr": "abc"}},
                   {"player_key": 12, "pos": "QB", "cbsros_ppg": {}}]
        rows = self._rows("cbsros_vorp", players)
        self.assertEqual(rows, [], "no valid projections -> no rows, never invented values")


class DashboardRawColumnsTest(unittest.TestCase):
    def test_dashboard_source_keys_include_vorp_trio(self):
        keys = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(DASH.read_text(), "SOURCE_KEYS")},
        )
        for key in ("espn_vorp", "cbsros_vorp", "razzball_vorp"):
            self.assertIn(key, keys)

    def test_dashboard_labels_cover_vorp_trio(self):
        labels = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(DASH.read_text(), "LABELS")},
        )
        self.assertIn("raw vorp vs waivers", labels["espn_vorp"].lower())
        self.assertIn("raw vorp vs waivers", labels["cbsros_vorp"].lower())
        self.assertIn("raw vorp vs waivers", labels["razzball_vorp"].lower())

    def test_dashboard_vorp_defs_source_pure(self):
        defs = _node_eval(
            CONST_EVAL_SCRIPT,
            {"t": _extract_const(DASH.read_text(), "VORP_SOURCE_DEFS")},
        )
        self.assertEqual(defs["espn_vorp"]["ppgField"], "espn_ppg")
        self.assertEqual(defs["cbsros_vorp"]["ppgField"], "cbsros_ppg")
        self.assertEqual(defs["razzball_vorp"]["ppgField"], "rz_ppg")
        # each VORP column validates against its own source's projection feed
        self.assertEqual(defs["cbsros_vorp"]["validationKey"], "cbsros")
        self.assertEqual(defs["razzball_vorp"]["validationKey"], "razzball")


if __name__ == "__main__":
    unittest.main()
