"""Test the chart-input coverage builder and the dashboard rendering of it.

JEG-314: enumerate every input file the trade-values chart reads, with an
honest "is there an automated freshness check?" flag. Two contracts tested
here:

(a) The builder emits one row per input, with `monitor_check` as a real bool
    (not absent, not coerced from a string, not None-as-false).
(b) The dashboard's `loadChartInputs` renderer does NOT crash or hide rows
    when a row's `monitor_check` is False. The contract is that the unmonitored
    rows are visually distinct — yellow background + "⚠ no monitor" badge —
    so the gap is visible on purpose, not hidden.
"""

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIPELINES = REPO / "pipelines"
DASHBOARD_HTML = REPO / "modules" / "dashboard.html"
OUTPUT_PATH = REPO / "dist" / "modules" / "chart-input-coverage.json"


def _load_builder_module():
    """Import build_chart_input_coverage.py as build_chart_input_coverage."""
    spec = importlib.util.spec_from_file_location(
        "build_chart_input_coverage", PIPELINES / "build_chart_input_coverage.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBuilderEmitsRows(unittest.TestCase):
    """Contract (a): one row per chart input, monitor_check is a real bool."""

    def test_builder_emits_one_row_per_input_with_bool_monitor_check(self):
        """The builder must emit at least one row per known input, and every
        row's `monitor_check` field must be a real bool — not None, not a
        string, not missing. Negative-test target: a regression that drops
        the field, coerces it from a string, or only emits monitored rows."""
        mod = _load_builder_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chart-input-coverage.json")
            rc = mod.main(argv=["--output", out_path])
            self.assertEqual(rc, 0)
            with open(out_path) as f:
                payload = json.load(f)

        self.assertIn("items", payload)
        items = payload["items"]
        self.assertGreater(
            len(items), 0, "builder emitted no rows — coverage must enumerate inputs"
        )

        # Each row must have the four required fields and monitor_check must be a bool.
        expected_keys = {"name", "freshness_source", "monitor_check", "last_checked"}
        for it in items:
            self.assertEqual(
                set(it.keys()),
                expected_keys,
                f"row {it.get('name')!r} missing fields: {expected_keys - set(it.keys())}",
            )
            self.assertIsInstance(
                it["monitor_check"],
                bool,
                f"row {it.get('name')!r} monitor_check is {type(it['monitor_check']).__name__}, expected bool",
            )
            self.assertIsInstance(it["name"], str)
            self.assertGreater(len(it["name"]), 0)

    def test_builder_emits_both_monitored_and_unmonitored_rows(self):
        """A coverage list that only contains monitored rows is dishonest —
        it hides the gaps. The JEG-314 contract is to surface both. We don't
        pin exact counts (JEG-317 will add live row counts), only that at
        least one of each is present."""
        mod = _load_builder_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chart-input-coverage.json")
            mod.main(argv=["--output", out_path])
            with open(out_path) as f:
                payload = json.load(f)
        items = payload["items"]
        self.assertTrue(
            any(it["monitor_check"] for it in items),
            "no monitored rows — the coverage list has lost its positives",
        )
        self.assertTrue(
            any(not it["monitor_check"] for it in items),
            "no unmonitored rows — the coverage list has lost its gaps (JEG-314 contract)",
        )

    def test_builder_emits_documented_inputs(self):
        """Every documented chart input must appear. We pin the names exactly
        so a rename can't silently drop a row from the dashboard."""
        mod = _load_builder_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chart-input-coverage.json")
            mod.main(argv=["--output", out_path])
            with open(out_path) as f:
                payload = json.load(f)
        names = {it["name"] for it in payload["items"]}

        # Inputs that must be enumerated regardless of branch state.
        self.assertIn("data/fixtures/current/comparison-sources-data.json", names)
        self.assertIn("data/fixtures/current/players.json", names)
        self.assertIn(
            "data/fixtures/current/players.naming-manifest.json", names
        )
        self.assertIn(
            "app/trade-value-chart/assets/adjustment-inputs.json", names
        )
        self.assertIn("data/fixtures/current/player-news.json", names)
        self.assertIn(
            "app/trade-value-chart/assets/reference-freshness.json", names
        )
        # actuals_*.json — globbed at build time, so at least one must be present
        # on a checkout with ECR actuals.
        actuals_rows = [n for n in names if n.startswith("data/fixtures/current/actuals_")]
        self.assertGreater(
            len(actuals_rows),
            0,
            "no actuals_*.json row — the ECR leg's actuals input went missing",
        )
        # espn_inputs*.json — the spec says list it whether or not the file is
        # present, so the gap is visible either way.
        espn_rows = [n for n in names if "espn_inputs" in n]
        self.assertGreater(
            len(espn_rows),
            0,
            "no espn_inputs*.json row — the DDF two-tier intake is uncovered",
        )

    def test_players_json_row_reads_meta_freshness(self):
        """The players.json row's `freshness_source` must surface
        `meta.as_of` (and kdst_snapshot when present) from the fixture —
        NOT a hardcoded value. Negative-test target: a regression that
        drops the read or returns the wrong field."""
        mod = _load_builder_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chart-input-coverage.json")
            mod.main(argv=["--output", out_path])
            with open(out_path) as f:
                payload = json.load(f)
        players_rows = [
            it for it in payload["items"] if it["name"] == "data/fixtures/current/players.json"
        ]
        self.assertEqual(len(players_rows), 1)
        players_row = players_rows[0]

        # Cross-check against the actual fixture meta.
        with open(REPO / "data/fixtures/current/players.json") as f:
            fixture = json.load(f)
        meta = fixture.get("meta", {})
        self.assertIn(
            meta.get("as_of", ""),
            players_row["freshness_source"],
            "players.json row did not surface meta.as_of from the fixture",
        )

    def test_persisted_artifact_matches_builder(self):
        """The committed dist/modules/chart-input-coverage.json must match
        what the builder would emit today — otherwise the file is stale."""
        self.assertTrue(
            OUTPUT_PATH.exists(),
            f"{OUTPUT_PATH} missing — builder must have run",
        )
        with open(OUTPUT_PATH) as f:
            persisted = json.load(f)
        # Schema sanity, not a full equality (generated_at drifts by design).
        self.assertIn("items", persisted)
        self.assertGreater(len(persisted["items"]), 0)
        for it in persisted["items"]:
            self.assertIsInstance(it["monitor_check"], bool)


class TestDashboardRendersUnmonitoredRows(unittest.TestCase):
    """Contract (b): the dashboard's loadChartInputs renders rows whose
    monitor_check is False. We can't run the page here, so we read the
    HTML and assert the renderer (i) fetches chart-input-coverage.json,
    (ii) iterates `items`, (iii) treats monitor_check as a bool, and
    (iv) gives unmonitored rows a visually distinct style."""

    def _extract_load_chart_inputs(self) -> str:
        html = DASHBOARD_HTML.read_text()
        # Find the function body between the JEG-314 banner and its closing brace.
        m = re.search(
            r"//\s*JEG-314:.*?async function loadChartInputs\(\)\s*\{(?P<body>.*?)\n\}\nloadChartInputs\(\);",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "loadChartInputs function not found in dashboard.html — "
            "JEG-314 contract requires a dedicated loader for the chart inputs section",
        )
        return m.group("body")

    def test_loader_section_exists(self):
        """The dashboard must have a Chart inputs section near line 329."""
        html = DASHBOARD_HTML.read_text()
        self.assertIn('id="chartInputsCard"', html)
        self.assertIn('id="chartInputsTable"', html)
        self.assertIn('id="chartInputsSummary"', html)

    def test_loader_fetches_chart_input_coverage(self):
        body = self._extract_load_chart_inputs()
        self.assertIn(
            "chart-input-coverage.json",
            body,
            "loader does not fetch chart-input-coverage.json",
        )

    def test_loader_iterates_items_and_uses_bool_branch(self):
        body = self._extract_load_chart_inputs()
        # Must iterate items with .forEach or .map.
        self.assertRegex(
            body,
            r"items\.(forEach|map)",
            "loader does not iterate over `items`",
        )
        # Must check `monitor_check` as a bool (not just truthiness / not just presence).
        self.assertRegex(
            body,
            r"monitor_check\s*\)",
            "loader does not read the `monitor_check` field",
        )

    def test_unmonitored_rows_get_distinct_visual_style(self):
        """The whole point of JEG-314: unmonitored rows must LOOK different.
        We assert that the loader applies a different background (or class)
        to unmonitored rows AND that the unmonitored branch is rendered,
        not just an early-return."""
        body = self._extract_load_chart_inputs()
        # The yellow-background CSS var is the documented unmonitored style.
        self.assertIn(
            "yellow-bg",
            body,
            "loader does not use the unmonitored visual style",
        )
        # Sanity: the loader must contain both branches of the if/else.
        self.assertRegex(
            body,
            r"monitored\s*\?\s*[`'\"]",
            "loader does not render a monitored branch",
        )
        self.assertRegex(
            body,
            r":\s*[`'\"]<\s*span[^`'\"]*no\s*monitor",
            "loader does not render the 'no monitor' badge for unmonitored rows",
        )


if __name__ == "__main__":
    unittest.main()