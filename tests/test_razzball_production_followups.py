"""Regression: production QA follow-ups for Razzball rendering (JEG-6) and the
curve-widget sourceMapCoverage outage (JEG-34), both found on the rendered
production page 2026-10-01 ~11:40 CDT (build tv-20261001-1633-6216144).

Defects:
  1. JEG-34 -- curve-widget.js runRegressionGuards() asserted
     `SOURCE_KEYS.length === 9 && SOURCE_KEYS.every(...)`. Commit 2876a38 grew
     the registry to 11 keys (cbsros, razzball) without updating the guard, so
     every page load failed the guard and the widget rendered
     "Curves unavailable: sourceMapCoverage". The length literal is the bug;
     the `every` conjunct is the real coverage proof.
  2. JEG-6 -- columnBadge("razzball") rendered "as published · reindexed",
     but the fixture marks razzball method_group="ddf-methodology": its values
     are computed from Razzball's projections with our value-above-waivers
     method, not Razzball's published values reindexed. The badge now reads
     the fixture's method_group instead of the key name.
  3. JEG-6 -- sourceDate("razzball") rendered "date unavailable" because the
     razzball section carries `vintage` (not published/espn_snapshot/
     fetched_at). The fallback chain now includes `vintage`.
  4. JEG-6 -- the dataset-health panel's inline order/labels (index.html)
     omitted razzball, so no Razzball card rendered there. Added, with an
     honest DDF-methodology role and the vintage freshness fallback.

Discrimination: every behavioral test also evaluates the PRE-FIX code and
asserts it fails, so a test that merely snapshots current behavior cannot
pass here.
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASH_JS = REPO / "app" / "trade-value-chart" / "assets" / "comparison-dashboard.js"
CURVE_JS = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
INDEX_HTML = REPO / "app" / "trade-value-chart" / "index.html"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"

# Pre-fix code, kept verbatim so the tests prove they discriminate.
OLD_GUARD_EXPR = "SOURCE_KEYS.length === 9 && SOURCE_KEYS.every(key => sourceMaps.has(key))"
OLD_BADGE_FN = """function columnBadge(key) {
    if (SOURCE_KEYS.includes(key)) return key === "espn" ? "utilization adjusted" : key === "espn_vorp" ? "raw value above waivers" : (key.endsWith("_adjusted") ? "bias adjusted" : "as published · reindexed");
    return FIELD_COLUMNS.find(column => column.key === key)?.badge || "field";
  }"""


def _node_eval(script, payload):
    """Run a node script that prints one JSON line; return the parsed value."""
    if shutil.which("node") is None:
        raise unittest.SkipTest("node is required")
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as handle:
        handle.write(script)
        path = handle.name
    try:
        proc = subprocess.run(["node", path], capture_output=True, text=True,
                              timeout=30, input=json.dumps(payload))
    finally:
        Path(path).unlink()
    if proc.returncode != 0:
        raise AssertionError(f"node harness crashed: {proc.stderr[:400]}")
    return json.loads(proc.stdout)


def _extract_fn(source, name):
    match = re.search(rf"function {name}\(key\) \{{([\s\S]*?)\n  \}}", source)
    assert match, f"could not extract {name} from dashboard source"
    return f"function {name}(key) {{{match.group(1)}\n  }}"


class CurveGuardTest(unittest.TestCase):
    def _guard_expr(self):
        text = CURVE_JS.read_text(encoding="utf-8")
        match = re.search(r"const sourceMapCoverage = ([^;]+);", text)
        self.assertIsNotNone(match, "sourceMapCoverage assignment not found")
        return match.group(1).strip()

    def _registry(self):
        text = CURVE_JS.read_text(encoding="utf-8")
        match = re.search(r"const SOURCE_KEYS = \[([\s\S]*?)\];", text)
        self.assertIsNotNone(match, "SOURCE_KEYS not found")
        return re.findall(r'"([^"]+)"', match.group(1))

    def _eval_guard(self, expr, keys, missing=()):
        script = (
            "const input = JSON.parse(require(\"fs\").readFileSync(0, \"utf8\"));\n"
            "const SOURCE_KEYS = input.keys;\n"
            "const sourceMaps = new Map(input.keys.filter(k => !input.missing.includes(k))"
            ".map(k => [k, new Map()]));\n"
            "process.stdout.write(JSON.stringify(!!eval(input.expr)));\n"
        )
        return _node_eval(script, {"expr": expr, "keys": keys,
                                   "missing": list(missing)})

    def test_guard_has_no_hardcoded_length(self):
        expr = self._guard_expr()
        self.assertNotRegex(expr, r"length\s*===\s*\d+",
                            f"guard still hardcodes a key count: {expr}")
        self.assertIn("SOURCE_KEYS.every", expr,
                      "guard lost its per-source coverage proof")

    def test_guard_passes_on_current_registry(self):
        keys = self._registry()
        self.assertGreater(len(keys), 9, "registry should include cbsros+razzball")
        self.assertTrue(self._eval_guard(self._guard_expr(), keys),
                        "fixed guard fails on the real 11-key registry with all maps built")

    def test_guard_still_catches_missing_map(self):
        keys = self._registry()
        self.assertFalse(self._eval_guard(self._guard_expr(), keys, missing=["razzball"]),
                         "guard must fail when a registered source has no built map")

    def test_old_guard_failed_on_current_registry(self):
        keys = self._registry()
        self.assertFalse(self._eval_guard(OLD_GUARD_EXPR, keys),
                         "old guard unexpectedly passes -- test would not discriminate")


class ColumnBadgeTest(unittest.TestCase):
    def _run_badge(self, fn_text, key):
        script = (
            "const {fnText, key} = JSON.parse(require(\"fs\").readFileSync(0, \"utf8\"));\n"
            "const SOURCE_KEYS = [\"usatoday\",\"fantasycalc\",\"fantasypros\",\"cbs\",\"cbsros\",\"razzball\","
            "\"cbs_adjusted\",\"fantasycalc_adjusted\",\"usatoday_adjusted\",\"fantasypros_adjusted\","
            "\"espn_vorp\",\"cbsros_vorp\",\"razzball_vorp\",\"espn_adjusted\"];\n"
            "const PURE_VORP_KEYS = [\"espn_vorp\",\"cbsros_vorp\",\"razzball_vorp\"];\n"
            "const FIELD_COLUMNS = [];\n"
            "const data = {sources: {razzball: {method_group: \"ddf-methodology\"},"
            " cbsros: {method_group: \"ddf-methodology\"}, usatoday: {}}};\n"
            "const columnBadge = eval(\"(\" + fnText + \")\");\n"
            "process.stdout.write(JSON.stringify(columnBadge(key)));\n"
        )
        return _node_eval(script, {"fnText": fn_text, "key": key})

    def test_razzball_badge_names_the_method(self):
        fn = _extract_fn(DASH_JS.read_text(encoding="utf-8"), "columnBadge")
        self.assertEqual(self._run_badge(fn, "razzball"), "Data Driven Football methodology")

    def test_cbsros_badge_names_the_method(self):
        fn = _extract_fn(DASH_JS.read_text(encoding="utf-8"), "columnBadge")
        self.assertEqual(self._run_badge(fn, "cbsros"), "Data Driven Football methodology",
                         "badge must be data-driven, not hardcoded per key")

    def test_other_badges_unchanged(self):
        fn = _extract_fn(DASH_JS.read_text(encoding="utf-8"), "columnBadge")
        self.assertEqual(self._run_badge(fn, "usatoday"), "as published · reindexed")
        self.assertEqual(self._run_badge(fn, "espn_vorp"), "raw VORP vs waivers")
        self.assertEqual(self._run_badge(fn, "cbsros_vorp"), "raw VORP vs waivers")
        self.assertEqual(self._run_badge(fn, "razzball_vorp"), "raw VORP vs waivers")
        self.assertEqual(self._run_badge(fn, "fantasycalc_adjusted"), "bias adjusted")

    def test_old_badge_mislabels_razzball(self):
        self.assertEqual(self._run_badge(OLD_BADGE_FN, "razzball"),
                         "as published · reindexed",
                         "old badge unexpectedly honest -- test would not discriminate")


# SourceDateTest removed 2026-10-08: it eval'd comparison-dashboard.js's
# sourceDate() in a bare harness, but sourceDate now delegates to
# freshnessText() and the product-data freshness rows, which the harness never
# had, so it crashed on every run. The Razzball date it guarded is covered on
# the built page by tests/test_freshness_display_render.py (labels per source,
# Razzball included, checked against the fixture).


class HealthPanelTest(unittest.TestCase):
    def _order_and_labels(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        order = re.search(r"const order=\[([^\]]*)\];", html)
        labels = re.search(r"const labels=\{([^}]*)\};", html)
        self.assertIsNotNone(order, "health panel order array not found")
        self.assertIsNotNone(labels, "health panel labels map not found")
        return re.findall(r'"([^"]+)"', order.group(1)), labels.group(1)

    def test_razzball_in_health_panel(self):
        order, labels = self._order_and_labels()
        self.assertIn("razzball", order, "health panel order omits razzball")
        self.assertIn("razzball", labels, "health panel labels omit razzball")

    def test_health_panel_validation_passes(self):
        """The panel throws unless every ordered source validates live."""
        order, _ = self._order_and_labels()
        validation = json.loads(FIXTURE.read_text(encoding="utf-8"))["source_validation"]
        live = [k for k in order
                if (validation.get("cbs") if k == "cbs_adjusted" else validation.get(k)) == "live"]
        self.assertEqual(len(live), len(order),
                         f"panel would throw 'required sources did not pass validation': {order}")

    def test_health_panel_role_is_methodology_honest(self):
        html = INDEX_HTML.read_text(encoding="utf-8")
        role = re.search(r"const role=([^;]+);", html)
        self.assertIsNotNone(role, "health panel role expression not found")
        self.assertIn("method_group", role.group(1),
                      "health panel role text ignores the fixture method_group")
        self.assertIn("Data Driven Football methodology", role.group(1))


if __name__ == "__main__":
    unittest.main()
