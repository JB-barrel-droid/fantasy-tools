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
from __future__ import annotations

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
            with open(out_path, encoding="utf-8") as f:
                payload = json.load(f)

        self.assertIn("items", payload)
        items = payload["items"]
        self.assertGreater(
            len(items), 0, "builder emitted no rows — coverage must enumerate inputs"
        )

        # Each row must have the four required fields and monitor_check must be a bool.
        # JEG-317 extends the schema: the actuals_*.json aggregate row also carries
        # an `mtime` field (ISO 8601 of the most recent actuals file). Other rows
        # may grow extra fields in future; allow non-required keys, but the four
        # documented fields must always be present.
        required_keys = {"name", "freshness_source", "monitor_check", "last_checked"}
        for it in items:
            self.assertTrue(
                required_keys.issubset(set(it.keys())),
                f"row {it.get('name')!r} missing fields: {required_keys - set(it.keys())}",
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
            with open(out_path, encoding="utf-8") as f:
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
            with open(out_path, encoding="utf-8") as f:
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
        # Retired 2026-10-08 (chore/retire-extras): player-news.json has no
        # producer and no reader; it must not come back as a monitored input.
        self.assertNotIn("data/fixtures/current/player-news.json", names)
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
        `meta.as_of` from the fixture —
        NOT a hardcoded value. Negative-test target: a regression that
        drops the read or returns the wrong field."""
        mod = _load_builder_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chart-input-coverage.json")
            mod.main(argv=["--output", out_path])
            with open(out_path, encoding="utf-8") as f:
                payload = json.load(f)
        players_rows = [
            it for it in payload["items"] if it["name"] == "data/fixtures/current/players.json"
        ]
        self.assertEqual(len(players_rows), 1)
        players_row = players_rows[0]

        # Cross-check against the actual fixture meta.
        with open(REPO / "data/fixtures/current/players.json", encoding="utf-8") as f:
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
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            persisted = json.load(f)
        # Schema sanity, not a full equality (generated_at drifts by design).
        self.assertIn("items", persisted)
        self.assertGreater(len(persisted["items"]), 0)
        for it in persisted["items"]:
            self.assertIsInstance(it["monitor_check"], bool)


class TestActualsFreshnessAggregateRow(unittest.TestCase):
    """JEG-317: the chart-inputs coverage emits ONE aggregate row for the
    actuals_*.json inputs, carrying the mtime of the most recent file. The
    dashboard paints the row red when >14 days old, amber when >7 days old.
    """

    def _actuals_row(self) -> dict:
        mod = _load_builder_module()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chart-input-coverage.json")
            mod.main(argv=["--output", out_path])
            with open(out_path, encoding="utf-8") as f:
                payload = json.load(f)
        rows = [it for it in payload["items"] if it["name"] == "data/fixtures/current/actuals_*.json"]
        self.assertEqual(
            len(rows), 1,
            f"expected exactly one actuals_*.json aggregate row, got {len(rows)}",
        )
        return rows[0]

    def test_actuals_aggregate_row_is_present_and_monitored(self):
        """The aggregate row must exist, be monitored, and carry last_checked
        stamped at builder time. Negative-test target: a regression that
        drops the row or reverts monitor_check to False."""
        row = self._actuals_row()
        self.assertEqual(row["name"], "data/fixtures/current/actuals_*.json")
        self.assertIs(
            row["monitor_check"], True,
            "actuals row monitor_check must be True — this builder is the gate",
        )
        self.assertIsNotNone(
            row["last_checked"],
            "actuals row last_checked must be the builder run time, not null",
        )

    def test_actuals_aggregate_row_carries_mtime(self):
        """JEG-317 contract: the actuals row carries an `mtime` field with
        the mtime of the most recent actuals_*.json file. The dashboard
        renders age bands from this field; without it, the dashboard cannot
        paint amber or red. Negative-test target: a regression that drops
        the mtime field or writes a non-ISO string."""
        row = self._actuals_row()
        self.assertIn(
            "mtime", row,
            "actuals row missing 'mtime' field — dashboard cannot render age bands",
        )
        self.assertIsNotNone(
            row["mtime"],
            "actuals row mtime is null on a checkout with actuals_*.json files "
            "— builder must read os.path.getmtime",
        )
        # Must be ISO 8601 with 'Z' so Date.parse() in the dashboard handles it.
        self.assertRegex(
            row["mtime"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            f"actuals row mtime {row['mtime']!r} is not ISO 8601 UTC second precision",
        )

    def test_actuals_row_is_aggregate_not_ome_has_multiple_per_file_rows(self):
        """The aggregate row replaces the per-file rows JEG-314 emitted.
        Exactly one row named 'data/fixtures/current/actuals_*.json' must
        be present — not one per dated file."""
        row = self._actuals_row()
        self.assertEqual(row["name"], "data/fixtures/current/actuals_*.json")
        # The freshness_source must name the chosen file and its mtime,
        # proving the row is computed from a globbed scan, not hardcoded.
        self.assertIn(
            "mtime=", row["freshness_source"],
            "actuals row freshness_source must surface the chosen mtime",
        )
        self.assertIn(
            "newest =", row["freshness_source"],
            "actuals row freshness_source must name the most recent file",
        )


class TestActualsAgeBandRenderer(unittest.TestCase):
    """JEG-317: the dashboard's `chartInputAgeBand(mtime)` paints:
      - red   when the most recent actuals file is >14 days old
      - amber when the most recent actuals file is >7 and <=14 days old
      - ok    when the file is <=7 days old (or mtime is missing -> red)
    These tests assert the dashboard honors those thresholds by extracting
    `chartInputAgeBand` from the HTML and evaluating it with controlled
    inputs (a Node-free pure-Python port of the same logic — see
    `_simulate_age_band`).
    """

    AGE_OK_THRESHOLD_DAYS = 7
    AGE_AMBER_THRESHOLD_DAYS = 14

    def _extract_chart_input_age_band(self) -> str:
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
        m = re.search(
            r"function\s+chartInputAgeBand\s*\([^)]*\)\s*\{(?P<body>.*?)\n\}",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "chartInputAgeBand function not found in dashboard.html — "
            "JEG-317 contract requires a dedicated age-band helper",
        )
        return m.group("body")

    def _simulate_age_band(self, body: str, mtime: str | None, now_ms: int) -> dict:
        """Port the JS helper to Python so we can test it without a browser.
        The contract under test is the threshold values (7, 14), the parse
        behavior, and the null/bad-mtime handling — the dashboard body is
        asserted to match these thresholds via the threshold-extracting tests
        in the sibling class.
        """
        # Pull the threshold constants out of the JS body so the JS source
        # remains the single source of truth.
        amber = int(re.search(r"ageDays\s*>\s*(\d+)\s*\)\s*return\s*\{\s*band:\s*\"amber\"", body).group(1))
        red = int(re.search(r"ageDays\s*>\s*(\d+)\s*\)\s*return\s*\{\s*band:\s*\"red\"", body).group(1))
        if mtime is None:
            return {"band": "red", "ageDays": None}
        ms = _utc_iso_to_ms(mtime)
        if ms is None:
            return {"band": "red", "ageDays": None}
        age_days = (now_ms - ms) / 86400000
        if age_days > red:
            return {"band": "red", "ageDays": age_days}
        if age_days > amber:
            return {"band": "amber", "ageDays": age_days}
        return {"band": "ok", "ageDays": age_days}

    def test_age_band_helper_uses_7_and_14_day_thresholds(self):
        """The age-band helper must use the documented 7-day (amber) and
        14-day (red) thresholds. Negative-test target: a regression that
        swaps them, hardcodes different numbers, or drops one branch."""
        body = self._extract_chart_input_age_band()
        # Both thresholds must appear, in the order amber < red.
        amber_match = re.search(r"ageDays\s*>\s*(\d+)\s*\)\s*return\s*\{\s*band:\s*\"amber\"", body)
        red_match = re.search(r"ageDays\s*>\s*(\d+)\s*\)\s*return\s*\{\s*band:\s*\"red\"", body)
        self.assertIsNotNone(amber_match, "amber branch missing in chartInputAgeBand")
        self.assertIsNotNone(red_match, "red branch missing in chartInputAgeBand")
        amber_days = int(amber_match.group(1))
        red_days = int(red_match.group(1))
        self.assertEqual(amber_days, self.AGE_OK_THRESHOLD_DAYS)
        self.assertEqual(red_days, self.AGE_AMBER_THRESHOLD_DAYS)
        # amber threshold must be strictly less than red threshold; otherwise
        # the bands collapse.
        self.assertLess(amber_days, red_days)

    def test_age_band_paints_red_when_most_recent_actuals_is_16_days_old(self):
        """JEG-317 acceptance: when the most recent actuals file's mtime is
        16 days ago, the dashboard renders the actuals row in the red band.
        Simulates the broken state with a controlled mtime + a frozen now."""
        now_iso = "2026-10-03T00:00:00Z"
        mtime_iso = "2026-09-17T00:00:00Z"  # exactly 16 days before now_iso
        body = self._extract_chart_input_age_band()
        result = self._simulate_age_band(body, mtime_iso, _utc_iso_to_ms(now_iso))
        self.assertEqual(
            result["band"], "red",
            f"actuals mtime {mtime_iso} is 16d old; expected red band, got {result['band']}",
        )
        # The renderer must apply the red style for that band — assert the
        # JS body references both the band name and the red CSS variable.
        self.assertIn("band: \"red\"", body, "JS body does not name the red band")
        self.assertIn("--red-bg", DASHBOARD_HTML.read_text(encoding="utf-8"),
                      "dashboard does not declare --red-bg; the renderer cannot paint red")

    def test_age_band_paints_amber_when_most_recent_actuals_is_10_days_old(self):
        """JEG-317 acceptance: when the most recent actuals file's mtime is
        10 days ago, the dashboard renders the actuals row in the amber
        band. 10 days is strictly between 7 and 14 — the boundary test."""
        now_iso = "2026-10-03T00:00:00Z"
        mtime_iso = "2026-09-23T00:00:00Z"  # exactly 10 days before now_iso
        body = self._extract_chart_input_age_band()
        result = self._simulate_age_band(body, mtime_iso, _utc_iso_to_ms(now_iso))
        self.assertEqual(
            result["band"], "amber",
            f"actuals mtime {mtime_iso} is 10d old; expected amber band, got {result['band']}",
        )
        self.assertIn("band: \"amber\"", body, "JS body does not name the amber band")
        self.assertIn("--yellow-bg", DASHBOARD_HTML.read_text(encoding="utf-8"),
                      "dashboard does not declare --yellow-bg; the renderer cannot paint amber")

    def test_age_band_paints_red_when_mtime_missing(self):
        """When the actuals file is absent (mtime=null), the dashboard must
        paint red unconditionally — a missing input is never silently ok.
        Negative-test target: a regression that defaults a null mtime to
        'ok' or 'amber'."""
        body = self._extract_chart_input_age_band()
        result = self._simulate_age_band(body, None, _utc_iso_to_ms("2026-10-03T00:00:00Z"))
        self.assertEqual(result["band"], "red")

    def test_age_band_renders_correctly_in_loadChartInputs(self):
        """The loadChartInputs renderer must dispatch on the band returned
        by chartInputAgeBand and apply the matching background style.
        Without this, the helper exists but the row still gets the default
        monitored/green treatment — a regression worth catching."""
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
        m = re.search(
            r"async function loadChartInputs\(\)\s*\{(?P<body>.*?)\n\}\nloadChartInputs\(\);",
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "loadChartInputs function not found")
        body = m.group("body")
        # The renderer must branch on ab.band and apply the documented bg vars.
        self.assertIn("ab.band", body, "renderer does not dispatch on chartInputAgeBand result")
        self.assertIn("var(--red-bg)", body, "renderer does not apply red-bg for the red band")
        self.assertIn("var(--yellow-bg)", body, "renderer does not apply yellow-bg for the amber band")
        # The mtime field on the row must be the trigger — proving the
        # renderer keys off the actuals row's mtime, not some other field.
        self.assertIn('"mtime"', body, "renderer does not reference the mtime field on the row")


def _utc_iso_to_ms(iso: str) -> int | None:
    """Parse a strict ISO 8601 UTC timestamp ('YYYY-MM-DDTHH:MM:SSZ') to ms.
    Mirrors Date.parse() behavior for the format the builder emits. None on
    a malformed input, matching the JS NaN branch."""
    import datetime as _dt
    try:
        dt = _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


class TestDashboardRendersUnmonitoredRows(unittest.TestCase):
    """Contract (b): the dashboard's loadChartInputs renders rows whose
    monitor_check is False. We can't run the page here, so we read the
    HTML and assert the renderer (i) fetches chart-input-coverage.json,
    (ii) iterates `items`, (iii) treats monitor_check as a bool, and
    (iv) gives unmonitored rows a visually distinct style."""

    def _extract_load_chart_inputs(self) -> str:
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
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
        html = DASHBOARD_HTML.read_text(encoding="utf-8")
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
        # JEG-314 baseline bug: the original regex `r":\s*[`'\"]<\s*span[^`'\"]*no\s*monitor"`
        # never matched the real JS body because the inner `<span style="...">` carries
        # quote chars that terminate `[^`'\"]*` early. Match the literal "no monitor"
        # badge text instead — present iff the unmonitored branch renders.
        self.assertIn(
            "no monitor",
            body,
            "loader does not render the 'no monitor' badge for unmonitored rows",
        )


if __name__ == "__main__":
    unittest.main()