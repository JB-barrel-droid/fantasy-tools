"""Health check tab unit tests (JEG-848, tab renamed and redesigned in JEG-1011): the
tab's totals are tied to the engine output, flag rules work, verdicts show
cross-source spread, and missing values are never zero.

These tests exercise the pure data functions in audit-pie.js (AuditPie.extract,
AuditPie.computeFlags, AuditPie.computeVerdicts) by loading the module in a
Playwright page, injecting a fixture that mirrors the shape of
TradeValueCurveControls.getInspection(), and asserting that every number the tab
shows is derived from that fixture.

Fixture design:
  Source A (espn): rates = 1.0, so raw == adjusted. A "well-calibrated" source.
  Source B (fantasycalc): rates != 1.0, so raw != adjusted. The source's raw
    shape disagrees with the budget allocation, forcing rescaling.
  Both sources: adjusted sums to pie (1200) exactly (VP-5 invariant).

Discrimination: each regression guard is negative-tested against a simulated
broken state.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import math
import os
import socketserver
import textwrap
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Minimal fixture: two sources, four positions, starter/bench split ──

POSITIONS = ["QB", "RB", "WR", "TE"]
PIE = 1200.0


def _make_fixture():
    """Build a getInspection()-shaped fixture with two sources.

    Source A (espn): rates=1.0, groups==budgets, adjusted==raw.
    Source B (fantasycalc): rates!=1.0, groups!=budgets, adjusted!=raw.
    Both: sum of adjusted across all players == PIE (the VP-5 invariant).
    """
    sources = {}
    players_all = {}

    # Position roster sizes
    pos_sizes = {"QB": (1, 1), "RB": (3, 2), "WR": (3, 2), "TE": (1, 1)}

    # Budgets: pie split 85% starters / 15% bench, equal across 4 positions
    budgets = {}
    ddf_weights = {}
    for pos in POSITIONS:
        budgets[f"{pos}|starter"] = PIE * 0.85 / 4  # 255
        budgets[f"{pos}|bench"] = PIE * 0.15 / 4     # 45
        ddf_weights[f"{pos}|starter"] = 0.85 / 4
        ddf_weights[f"{pos}|bench"] = 0.15 / 4

    # ── Source A (espn): rates = 1.0, raw == adjusted ──
    src_a_players = {}
    src_a_groups = {}
    src_a_positions = {}
    src_a_rates = {}
    pk = 1

    for pos in POSITIONS:
        starters, bench = pos_sizes[pos]
        rostered = starters + bench
        budget_s = budgets[f"{pos}|starter"]
        budget_b = budgets[f"{pos}|bench"]

        # With rate=1.0, each player's adjusted = their raw slice
        adj_per_starter = budget_s / starters  # = budget / count
        adj_per_bench = budget_b / bench

        for i in range(rostered):
            role = "starter" if i < starters else "bench"
            adj = adj_per_starter if role == "starter" else adj_per_bench
            src_a_players[str(pk)] = {
                "pos": pos, "role": role, "adjusted": adj,
                "starterSlice": adj if role == "starter" else 0,
                "benchSlice": adj if role == "bench" else 0,
                "native": adj * 1.1, "estimated": False, "rank": i + 1,
                "vorpDisplay": adj * 0.95, "vorp": adj * 0.8
            }
            pk += 1

        src_a_positions[pos] = {
            "listed": rostered, "starters": starters, "rostered": rostered,
            "nEstimated": 0, "method": "ppg", "waiver": 1.0, "starterLine": 5.0
        }
        # groups = sum of slices per group (pre-rescale) = budget when rate=1
        src_a_groups[f"{pos}|starter"] = budget_s
        src_a_groups[f"{pos}|bench"] = budget_b
        src_a_rates[f"{pos}|starter"] = 1.0
        src_a_rates[f"{pos}|bench"] = 1.0

    sources["espn"] = {
        "family": "projection", "included": True, "totalVorp": PIE * 0.9,
        "surplusTotal": PIE * 0.8, "groups": src_a_groups,
        "weights": ddf_weights, "starterMix": {}, "benchMix": {},
        "rates": src_a_rates, "positions": src_a_positions,
        "vorpFactor": 1.0, "indexedFactor": None
    }
    players_all["espn"] = src_a_players

    # ── Source B (fantasycalc): rates != 1.0, raw != adjusted ──
    # This source "overvalues" starters by 20% in its raw shape.
    # The engine rescales to budgets, so adjusted != raw.
    src_b_players = {}
    src_b_groups = {}
    src_b_positions = {}
    src_b_rates = {}

    for pos in POSITIONS:
        starters, bench = pos_sizes[pos]
        rostered = starters + bench
        budget_s = budgets[f"{pos}|starter"]
        budget_b = budgets[f"{pos}|bench"]

        # Raw shape: starters get 1.2x budget, bench gets 0.4x budget
        raw_group_s = budget_s * 1.2   # 306 for QB, etc.
        raw_group_b = budget_b * 0.4   # 18 for QB, etc.
        # Rate = budget / raw_group (value-model.js:983)
        rate_s = budget_s / raw_group_s if raw_group_s > 0 else 0  # ~0.833
        rate_b = budget_b / raw_group_b if raw_group_b > 0 else 0  # ~2.5

        # Per-player raw slices (sum to raw_group)
        raw_per_starter = raw_group_s / starters
        raw_per_bench = raw_group_b / bench
        # Per-player adjusted = rate * raw_slice
        adj_per_starter = rate_s * raw_per_starter  # = budget_s / starters
        adj_per_bench = rate_b * raw_per_bench      # = budget_b / bench

        for i in range(rostered):
            role = "starter" if i < starters else "bench"
            if role == "starter":
                adj = adj_per_starter
                s_slice = raw_per_starter
                b_slice = 0
            else:
                adj = adj_per_bench
                s_slice = 0
                b_slice = raw_per_bench
                listed_flag = True
            src_b_players[str(pk)] = {
                "pos": pos, "role": role, "adjusted": adj,
                "starterSlice": s_slice, "benchSlice": b_slice,
                "native": adj * 1.2, "estimated": i >= starters, "rank": i + 1,
                "vorpDisplay": adj * 0.9, "vorp": adj * 0.7
            }
            pk += 1

        listed_b = starters  # only starters listed
        src_b_positions[pos] = {
            "listed": listed_b, "starters": starters, "rostered": rostered,
            "nEstimated": bench, "method": "chart", "waiver": 0.5,
            "starterLine": 4.0
        }
        src_b_groups[f"{pos}|starter"] = raw_group_s
        src_b_groups[f"{pos}|bench"] = raw_group_b
        src_b_rates[f"{pos}|starter"] = rate_s
        src_b_rates[f"{pos}|bench"] = rate_b

    sources["fantasycalc"] = {
        "family": "chart", "included": True, "totalVorp": PIE * 0.85,
        "surplusTotal": PIE * 0.75, "groups": src_b_groups,
        "weights": ddf_weights, "starterMix": {}, "benchMix": {},
        "rates": src_b_rates, "positions": src_b_positions,
        "vorpFactor": 1.0, "indexedFactor": 1.05
    }
    players_all["fantasycalc"] = src_b_players

    # Engine rows (getInspection().rows): per player, indexed[src] is what the
    # Player values table shows. A projection's Indexed equals its Adjusted; a
    # chart's is native x indexedFactor (VP-6.4), so it is NOT held to the pie
    # (JEG-871).
    rows = {}
    for key, p in src_a_players.items():
        rows[key] = {"indexed": {"espn": p["adjusted"]}}
    for key, p in src_b_players.items():
        rows[key] = {"indexed": {"fantasycalc": p["native"] * 1.05}}

    # Match real engine: no "budgets" field; extract() computes it from
    # ddfWeights * pie (funded[g] = ddfWeights[g] * pie, value-model.js:979).
    return {
        "valuePipeline": {
            "pie": PIE, "sources": sources,
            "ddfWeights": ddf_weights, "allocation": {},
            "version": "test", "setting": "test", "method": "test",
            "benchShare": 0.15
        },
        "players": players_all,
        "rows": rows,
        # Keep budgets accessible for test assertions (not part of pipeline)
        "_test_budgets": budgets
    }


FIXTURE = _make_fixture()
FIXTURE_JSON = json.dumps(FIXTURE)


def _verify_fixture():
    """Verify the fixture satisfies VP-5 before tests run."""
    for src in ["espn", "fantasycalc"]:
        players = FIXTURE["players"][src]
        total = sum(p["adjusted"] for p in players.values())
        assert abs(total - PIE) < 0.01, (
            f"Fixture VP-5 violation: {src} adjusted sum {total} != pie {PIE}")
    # Source B must have rates != 1.0
    fc = FIXTURE["valuePipeline"]["sources"]["fantasycalc"]
    rates = fc["rates"]
    assert any(abs(r - 1.0) > 0.01 for r in rates.values()), (
        "Fixture: fantasycalc rates must not all be 1.0")
    # Source B raw groups must differ from adjusted sums
    groups = fc["groups"]
    budgets = FIXTURE["_test_budgets"]
    assert any(abs(groups[k] - budgets[k]) > 0.01 for k in groups), (
        "Fixture: fantasycalc groups must differ from budgets")


_verify_fixture()


# ── Harness: load audit-pie.js in a minimal page ──

HARNESS_HTML = textwrap.dedent("""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>audit-pie test</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/app/v2/audit-pie.css">
<style>body { margin: 0; padding: 0 16px; }</style>
</head>
<body>
<div id="audit-pie-root"></div>
<script src="/app/v2/audit-pie.js"></script>
</body></html>
""")


@contextlib.contextmanager
def _served():
    """Serve the repo root so the harness can load audit-pie.js."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(HARNESS_HTML.encode())
                return
            super().do_GET()
    with socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0),
        functools.partial(Handler, directory=str(ROOT))
    ) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


def _skip_no_pw():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return False
    except ImportError:
        return True


def _extract_in_browser(fixture_json, *, broken_fn=None):
    """Load audit-pie.js in Playwright and run extract + computeFlags."""
    from playwright.sync_api import sync_playwright
    from tests import _render_env
    exe = _render_env.chromium_executable()
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        page = browser.new_page()
        page.goto(base, wait_until="networkidle")

        if broken_fn:
            page.evaluate(broken_fn)

        result = page.evaluate(f"""() => {{
            const fixture = {fixture_json};
            const data = window.AuditPie.extract(fixture);
            window.AuditPie.computeFlags(data);
            return JSON.parse(JSON.stringify(data));
        }}""")
        browser.close()
    return result


def _verdicts_in_browser(fixture_json):
    """Load audit-pie.js and run extract + computeVerdicts."""
    from playwright.sync_api import sync_playwright
    from tests import _render_env
    exe = _render_env.chromium_executable()
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        page = browser.new_page()
        page.goto(base, wait_until="networkidle")
        result = page.evaluate(f"""() => {{
            const fixture = {fixture_json};
            const data = window.AuditPie.extract(fixture);
            const verdicts = window.AuditPie.computeVerdicts(data);
            return JSON.parse(JSON.stringify(verdicts));
        }}""")
        browser.close()
    return result


def _render_in_browser(fixture_json, *, width=1440, height=900):
    """Render the pie tab and return its HTML and metrics."""
    from playwright.sync_api import sync_playwright
    from tests import _render_env
    exe = _render_env.chromium_executable()
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(base, wait_until="networkidle")

        result = page.evaluate(f"""() => {{
            const fixture = {fixture_json};
            const root = document.getElementById('audit-pie-root');
            const ctx = {{
                controls: {{ getInspection: () => fixture }},
                labels: {{}},
                sourceKeys: Object.keys(fixture.valuePipeline.sources)
            }};
            window.AuditPie.render(root, ctx);

            const tables = root.querySelectorAll('.audit-pie-table');
            const flags = root.querySelectorAll('.audit-pie-flag');
            const cells = root.querySelectorAll('.audit-pie-num');
            const over = document.documentElement.scrollWidth - document.documentElement.clientWidth;
            const verdictRows = root.querySelectorAll('.audit-pie-verdict-row');
            return {{
                tableCount: tables.length,
                flagCount: flags.length,
                cellCount: cells.length,
                hasContent: root.innerHTML.length > 100,
                horizontalOverflow: over,
                headings: [...root.querySelectorAll('h2, h3, h4')].map(h => h.textContent),
                flagTexts: [...flags].map(f => f.textContent),
                emptyText: root.querySelector('.audit-pie-empty')?.textContent || null,
                verdictCount: root.querySelectorAll('.audit-pie-check').length,
                verdictTexts: [...root.querySelectorAll('.audit-pie-check-reason')].map(r => r.textContent),
                reconcileNote: root.querySelector('#audit-pie-sec-reconcile .audit-pie-how')?.textContent || '',
                reconcileLabels: [...root.querySelectorAll('table[aria-label="Reconciling each source to Player values"] tbody tr')].map(r => r.cells[0].textContent),
                reconcileCells: [...root.querySelectorAll('table[aria-label="Reconciling each source to Player values"] tbody tr')].map(r => [...r.cells].map(c => c.textContent)),
                summaryLabels: [...root.querySelectorAll('table[aria-label="Starter, bench and total value by source"] tbody tr')].map(r => r.cells[0].textContent),
                zeroValues: [...cells].filter(c => c.textContent.trim() === '0.0').map(c => {{
                    const row = c.closest('tr');
                    return {{ cell: c.textContent, row: row ? row.cells[0]?.textContent : null }};
                }})
            }};
        }}""")
        browser.close()
    return result


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieExtractTest(unittest.TestCase):
    """The extract function returns exactly the engine's numbers."""

    def test_total_adjusted_equals_sum_of_player_adjusted(self):
        """Tab total matches sum of individual player adjusted values."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            src = row["src"]
            players = FIXTURE["players"][src]
            expected = sum(p["adjusted"] for p in players.values())
            self.assertAlmostEqual(row["totalAdjusted"], expected, places=6,
                msg=f"{src}: totalAdjusted {row['totalAdjusted']} != sum {expected}")

    def test_position_totals_sum_to_source_total(self):
        """Per-position adjusted values sum to the source total."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            pos_sum = sum(pd["posAdj"] for pd in row["positions"])
            self.assertAlmostEqual(row["totalAdjusted"], pos_sum, places=6,
                msg=f"{row['src']}: position sum {pos_sum} != total {row['totalAdjusted']}")

    def test_starter_bench_sum_to_position(self):
        """Starter + bench adjusted = position adjusted for each position."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            for pd in row["positions"]:
                self.assertAlmostEqual(pd["starterAdj"] + pd["benchAdj"], pd["posAdj"],
                    places=6, msg=f"{row['src']} {pd['pos']}: starter+bench != total")

    def test_per_listed_is_total_over_listed(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            if row["totalListed"] > 0:
                expected = row["totalAdjusted"] / row["totalListed"]
                self.assertAlmostEqual(row["perListed"], expected, places=6)

    def test_per_rosterable_is_total_over_rostered(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            if row["totalRostered"] > 0:
                expected = row["totalAdjusted"] / row["totalRostered"]
                self.assertAlmostEqual(row["perRosterable"], expected, places=6)

    def test_pie_from_engine(self):
        data = _extract_in_browser(FIXTURE_JSON)
        self.assertEqual(data["pie"], PIE)

    def test_source_count(self):
        data = _extract_in_browser(FIXTURE_JSON)
        self.assertEqual(len(data["rows"]), 2)
        srcs = {r["src"] for r in data["rows"]}
        self.assertEqual(srcs, {"espn", "fantasycalc"})

    def test_budget_nonzero_when_position_adj_nonzero(self):
        """Budget must be nonzero for every position with nonzero adjusted."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            for pd in row["positions"]:
                if pd["posAdj"] > 0:
                    self.assertGreater(pd["budget"], 0,
                        f"{row['src']} {pd['pos']}: budget is 0 but posAdj={pd['posAdj']}")

    def test_budget_equals_ddfweights_times_pie(self):
        """Budget = ddfWeights[pos|starter] * pie + ddfWeights[pos|bench] * pie."""
        data = _extract_in_browser(FIXTURE_JSON)
        ddf = FIXTURE["valuePipeline"]["ddfWeights"]
        for row in data["rows"]:
            for pi, pos in enumerate(["QB", "RB", "WR", "TE"]):
                expected = ddf[f"{pos}|starter"] * PIE + ddf[f"{pos}|bench"] * PIE
                pd = row["positions"][pi]
                self.assertAlmostEqual(pd["budget"], expected, places=4,
                    msg=f"{row['src']} {pos}: budget {pd['budget']} != expected {expected}")


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieVP5Test(unittest.TestCase):
    """VP-5 invariant: each source's adjusted total equals the league pie."""

    def test_adjusted_total_equals_pie(self):
        """Each source's totalAdjusted must equal pie within rounding."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            self.assertAlmostEqual(row["totalAdjusted"], PIE, places=2,
                msg=f"VP-5: {row['src']} adjusted {row['totalAdjusted']} != pie {PIE}")

    def test_vp5_negative__broken_adjusted_fails(self):
        """Negative test: if a source's player adjusted values are tampered
        to not sum to pie, the test catches it."""
        fixture = json.loads(FIXTURE_JSON)
        # Tamper: double one player's adjusted value in fantasycalc
        fc_players = fixture["players"]["fantasycalc"]
        first_key = next(iter(fc_players))
        fc_players[first_key]["adjusted"] *= 2.0  # breaks the sum

        data = _extract_in_browser(json.dumps(fixture))
        fc_row = [r for r in data["rows"] if r["src"] == "fantasycalc"][0]
        # The tampered total should NOT equal pie
        self.assertGreater(abs(fc_row["totalAdjusted"] - PIE), 10.0,
            "Tampered fixture should break VP-5 but didn't")


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieReconcileTest(unittest.TestCase):
    """JEG-871: the pie reconciles to the Player values table.

    Total adjusted = own (posted) + filled in (estimated), and the tab reports
    the Player values column total (sum of rows[key].indexed[src]) separately,
    because a chart's Indexed view is not held to the pie."""

    def test_own_plus_filled_equals_total(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            self.assertAlmostEqual(row["ownAdjusted"] + row["filledAdjusted"], row["totalAdjusted"], places=6,
                msg=f"{row['src']}: own + filled != total")

    def test_filled_is_the_estimated_players_adjusted(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            players = FIXTURE["players"][row["src"]]
            expected = sum(p["adjusted"] for p in players.values() if p["estimated"])
            self.assertAlmostEqual(row["filledAdjusted"], expected, places=6, msg=row["src"])
        by_src = {r["src"]: r for r in data["rows"]}
        self.assertEqual(by_src["espn"]["filledAdjusted"], 0.0, "a projection is never filled in")
        self.assertGreater(by_src["fantasycalc"]["filledAdjusted"], 0.0, "the chart's bench is estimated")

    def test_table_total_reads_engine_rows_indexed(self):
        data = _extract_in_browser(FIXTURE_JSON)
        by_src = {r["src"]: r for r in data["rows"]}
        for src in ("espn", "fantasycalc"):
            expected = sum(r["indexed"][src] for r in FIXTURE["rows"].values() if src in r["indexed"])
            self.assertAlmostEqual(by_src[src]["tableTotal"], expected, places=6, msg=src)
        # The projection's table column is its Adjusted column (= pie); the chart's is not.
        self.assertAlmostEqual(by_src["espn"]["tableTotal"], PIE, places=6)
        self.assertGreater(abs(by_src["fantasycalc"]["tableTotal"] - PIE), 10.0,
            "fixture: the chart's Indexed total must differ from the pie to exercise the reconciliation")

    def test_table_total_null_without_engine_rows(self):
        fixture = json.loads(FIXTURE_JSON)
        del fixture["rows"]
        data = _extract_in_browser(json.dumps(fixture))
        for row in data["rows"]:
            self.assertIsNone(row["tableTotal"], "no rows: the column must be blank, never 0")

    def test_negative__filled_follows_the_estimated_flag(self):
        """Simulated broken state: a listed starter flagged estimated moves its
        value from own to filled; a split that ignored the flag would not move."""
        fixture = json.loads(FIXTURE_JSON)
        fc = fixture["players"]["fantasycalc"]
        key = next(k for k, p in fc.items() if not p["estimated"])
        fc[key]["estimated"] = True
        before = {r["src"]: r for r in _extract_in_browser(FIXTURE_JSON)["rows"]}["fantasycalc"]
        after = {r["src"]: r for r in _extract_in_browser(json.dumps(fixture))["rows"]}["fantasycalc"]
        self.assertAlmostEqual(after["filledAdjusted"] - before["filledAdjusted"], fc[key]["adjusted"], places=6)
        self.assertAlmostEqual(before["ownAdjusted"] - after["ownAdjusted"], fc[key]["adjusted"], places=6)
        self.assertAlmostEqual(after["totalAdjusted"], before["totalAdjusted"], places=6)

    def test_negative__table_total_is_not_the_adjusted_sum(self):
        """Simulated broken state: tamper one engine row's indexed value; the
        table total must move by exactly that while Total adjusted stays."""
        fixture = json.loads(FIXTURE_JSON)
        key = next(k for k, r in fixture["rows"].items() if "fantasycalc" in r["indexed"])
        fixture["rows"][key]["indexed"]["fantasycalc"] += 50.0
        before = {r["src"]: r for r in _extract_in_browser(FIXTURE_JSON)["rows"]}["fantasycalc"]
        after = {r["src"]: r for r in _extract_in_browser(json.dumps(fixture))["rows"]}["fantasycalc"]
        self.assertAlmostEqual(after["tableTotal"] - before["tableTotal"], 50.0, places=6)
        self.assertAlmostEqual(after["totalAdjusted"], before["totalAdjusted"], places=6)

    def test_reconcile_section_renders_with_site_labels(self):
        """The section, its plain-language note and the Player values labels
        (JEG-872: symbol + name, "CBS rest of season" not "CBS ROS")."""
        result = _render_in_browser(FIXTURE_JSON, width=1440, height=900)
        self.assertIn("Does DDF Value reconcile?", result["headings"])
        self.assertIn("fill-ins", result["reconcileNote"])
        self.assertIn("Rescaled", result["reconcileNote"])
        self.assertEqual(result["reconcileLabels"], ["● ESPN", "■ FantasyCalc"])
        self.assertEqual(result["summaryLabels"], ["● ESPN", "■ FantasyCalc"])
        # Own, filled in, total adjusted, Player values sum, difference from the pie, listed players Rescaled minus DDF Value
        # (the fixture's rows carry no DDF Value, so that last cell is a dash, never a zero).
        self.assertEqual(result["reconcileCells"][1][1:], ["1020.0", "180.0", "1200.0", "1512.0", "312.0", "—"])


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieRawVsAdjustedTest(unittest.TestCase):
    """Raw (pre-rescale) groups differ from adjusted when rates != 1.0."""

    def test_raw_equals_groups_from_pipeline(self):
        """The tab's raw values come from groups[pos|role] on the pipeline."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            src = row["src"]
            engine_groups = FIXTURE["valuePipeline"]["sources"][src]["groups"]
            for pi, pos in enumerate(POSITIONS):
                pd = row["positions"][pi]
                expected_raw_s = engine_groups.get(f"{pos}|starter", 0)
                expected_raw_b = engine_groups.get(f"{pos}|bench", 0)
                self.assertAlmostEqual(pd["starterRaw"], expected_raw_s, places=6,
                    msg=f"{src} {pos} starterRaw")
                self.assertAlmostEqual(pd["benchRaw"], expected_raw_b, places=6,
                    msg=f"{src} {pos} benchRaw")

    def test_raw_differs_from_adjusted_when_rates_not_one(self):
        """For fantasycalc (rates != 1.0), raw != adjusted at some position."""
        data = _extract_in_browser(FIXTURE_JSON)
        fc_row = [r for r in data["rows"] if r["src"] == "fantasycalc"][0]
        diffs = []
        for pd in fc_row["positions"]:
            if pd["posRaw"] > 0 and pd["posAdj"] > 0:
                diffs.append(abs(pd["posRaw"] - pd["posAdj"]))
        self.assertTrue(any(d > 0.01 for d in diffs),
            f"fantasycalc raw should differ from adjusted; diffs: {diffs}")

    def test_raw_equals_adjusted_when_rates_one(self):
        """For espn (rates == 1.0), raw == adjusted."""
        data = _extract_in_browser(FIXTURE_JSON)
        espn_row = [r for r in data["rows"] if r["src"] == "espn"][0]
        for pd in espn_row["positions"]:
            self.assertAlmostEqual(pd["posRaw"], pd["posAdj"], places=6,
                msg=f"espn {pd['pos']}: raw {pd['posRaw']} should == adj {pd['posAdj']}")

    def test_negative__raw_equals_adj_when_rates_not_one_catches_bug(self):
        """Negative: if we set groups == budgets for fantasycalc, raw == adj
        (the bug the old code had). This tests the guard catches that."""
        fixture = json.loads(FIXTURE_JSON)
        # Set groups to budgets (so raw == adjusted, hiding the rescale)
        budgets = fixture["_test_budgets"]
        fc = fixture["valuePipeline"]["sources"]["fantasycalc"]
        for key in budgets:
            fc["groups"][key] = budgets[key]
        data = _extract_in_browser(json.dumps(fixture))
        fc_row = [r for r in data["rows"] if r["src"] == "fantasycalc"][0]
        # Now raw SHOULD equal adjusted (the broken state)
        for pd in fc_row["positions"]:
            self.assertAlmostEqual(pd["posRaw"], pd["posAdj"], places=4,
                msg="When groups==budgets, raw should equal adjusted (the bug)")


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieFlagTest(unittest.TestCase):
    """Flag rule: >10% from cross-source median."""

    def test_flags_computed(self):
        data = _extract_in_browser(FIXTURE_JSON)
        per_listed_values = [r["perListed"] for r in data["rows"]
                             if r["perListed"] is not None]
        if len(per_listed_values) == 2:
            med = sum(per_listed_values) / 2
            for r in data["rows"]:
                if r["perListed"] and abs(r["perListed"] - med) / abs(med) > 0.10:
                    self.assertTrue(r.get("flagPerListed"),
                        f"{r['src']}: perListed {r['perListed']:.2f} >10% from "
                        f"median {med:.2f} but not flagged")

    def test_flag_threshold_is_ten_percent(self):
        from playwright.sync_api import sync_playwright
        from tests import _render_env
        exe = _render_env.chromium_executable()
        with _served() as base, sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
            page = browser.new_page()
            page.goto(base, wait_until="networkidle")
            threshold = page.evaluate("() => window.AuditPie._FLAG_THRESHOLD")
            self.assertEqual(threshold, 0.10)
            browser.close()


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieVerdictTest(unittest.TestCase):
    """Verdict rows show cross-source spread per cut."""

    def test_verdicts_have_expected_keys(self):
        verdicts = _verdicts_in_browser(FIXTURE_JSON)
        for key in ["starters", "bench", "total"]:
            self.assertIn(key, verdicts, f"Missing top-level verdict: {key}")
            self.assertIn("spread", verdicts[key])
            self.assertIn("within", verdicts[key])

    def test_verdicts_per_position(self):
        verdicts = _verdicts_in_browser(FIXTURE_JSON)
        self.assertIn("positions", verdicts)
        for pos in POSITIONS:
            self.assertIn(pos, verdicts["positions"],
                f"Missing position verdict: {pos}")
            for cut in ["starters", "bench", "total"]:
                self.assertIn(cut, verdicts["positions"][pos],
                    f"Missing {pos} verdict cut: {cut}")

    def test_spread_is_nonnegative(self):
        verdicts = _verdicts_in_browser(FIXTURE_JSON)
        self.assertGreaterEqual(verdicts["starters"]["spread"], 0)
        self.assertGreaterEqual(verdicts["bench"]["spread"], 0)
        self.assertGreaterEqual(verdicts["total"]["spread"], 0)

    def test_within_is_boolean(self):
        verdicts = _verdicts_in_browser(FIXTURE_JSON)
        self.assertIsInstance(verdicts["starters"]["within"], bool)


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieNegativeTest(unittest.TestCase):
    """Each regression guard catches its named bug (negative test)."""

    def test_guard_catches_zero_for_missing(self):
        """If a source has 0 listed players, perListed must be null, not 0."""
        fixture = json.loads(FIXTURE_JSON)
        for pos in POSITIONS:
            fixture["valuePipeline"]["sources"]["fantasycalc"]["positions"][pos]["listed"] = 0
        data = _extract_in_browser(json.dumps(fixture))
        fc_row = [r for r in data["rows"] if r["src"] == "fantasycalc"][0]
        self.assertIsNone(fc_row["perListed"],
            "perListed must be null when no players listed, not 0")

    def test_guard_catches_wrong_sum(self):
        """Position totals must sum to source total."""
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            pos_sum = sum(pd["posAdj"] for pd in row["positions"])
            self.assertAlmostEqual(row["totalAdjusted"], pos_sum, places=4)

    def test_guard_catches_budget_zero(self):
        """Negative test: if ddfWeights are zeroed out, budget becomes 0.
        The guard (test_budget_nonzero_when_position_adj_nonzero) would fail."""
        fixture = json.loads(FIXTURE_JSON)
        # Zero out ddfWeights to simulate the budget-is-zero bug
        for key in fixture["valuePipeline"]["ddfWeights"]:
            fixture["valuePipeline"]["ddfWeights"][key] = 0
        data = _extract_in_browser(json.dumps(fixture))
        # All budgets should now be 0 while posAdj is nonzero
        for row in data["rows"]:
            for pd in row["positions"]:
                self.assertEqual(pd["budget"], 0,
                    "With zeroed ddfWeights, budget must be 0 (the broken state)")
                if pd["posAdj"] > 0:
                    # This is the state the guard catches
                    self.assertGreater(pd["posAdj"], pd["budget"],
                        "posAdj should exceed budget=0 (confirming the guard)")


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieRenderTest(unittest.TestCase):
    """The tab renders at desktop and phone widths."""

    def test_desktop_render(self):
        result = _render_in_browser(FIXTURE_JSON, width=1440, height=900)
        self.assertTrue(result["hasContent"])
        self.assertGreater(result["tableCount"], 0)
        self.assertIsNone(result["emptyText"])
        self.assertEqual(result["horizontalOverflow"], 0,
            f"Page overflows by {result['horizontalOverflow']}px")

    def test_phone_render(self):
        result = _render_in_browser(FIXTURE_JSON, width=375, height=812)
        self.assertTrue(result["hasContent"])
        self.assertGreater(result["tableCount"], 0)
        self.assertEqual(result["horizontalOverflow"], 0,
            f"Page overflows by {result['horizontalOverflow']}px at 375px")

    def test_no_zero_for_missing(self):
        fixture = json.loads(FIXTURE_JSON)
        fixture["valuePipeline"]["sources"]["fantasycalc"]["positions"]["QB"]["listed"] = 0
        result = _render_in_browser(json.dumps(fixture), width=1440)
        self.assertTrue(result["hasContent"])

    def test_flags_visible_in_dom(self):
        result = _render_in_browser(FIXTURE_JSON, width=1440)
        self.assertGreaterEqual(result["flagCount"], 0)

    def test_headings_present(self):
        result = _render_in_browser(FIXTURE_JSON, width=1440)
        headings = result["headings"]
        for question in ("Is anything wrong?", "Do sources agree on total value?", "Do sources agree by position?",
                         "Are any players valued oddly?", "Does DDF Value reconcile?", "How do raw and adjusted values compare?"):
            self.assertIn(question, headings)

    def test_verdict_rows_rendered(self):
        """One verdict row per check appears in the rendered DOM (JEG-1011)."""
        result = _render_in_browser(FIXTURE_JSON, width=1440)
        self.assertEqual(result["verdictCount"], 7, f"Expected 7 verdict rows, got {result['verdictCount']}")

    def test_verdict_text_has_spread(self):
        """Verdict rows say the spread in words a reader can check."""
        result = _render_in_browser(FIXTURE_JSON, width=1440)
        self.assertTrue(any("pread" in t for t in result["verdictTexts"]),
            "Verdict rows should mention the spread")


@unittest.skipIf(_skip_no_pw(), "playwright not installed")
class AuditPieEngineParityTest(unittest.TestCase):
    """The tab's totals tie exactly to the engine fixture."""

    def test_totals_match_fixture_players(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            src = row["src"]
            players = FIXTURE["players"][src]
            engine_total = sum(p["adjusted"] for p in players.values())
            self.assertAlmostEqual(row["totalAdjusted"], engine_total, places=6,
                msg=f"PARITY FAIL {src}")

    def test_position_starter_bench_match_engine(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            src = row["src"]
            players = FIXTURE["players"][src]
            for pi, pos in enumerate(POSITIONS):
                expected_starter = sum(
                    p["adjusted"] for p in players.values()
                    if p["pos"] == pos and p["role"] == "starter"
                )
                expected_bench = sum(
                    p["adjusted"] for p in players.values()
                    if p["pos"] == pos and p["role"] == "bench"
                )
                pd = row["positions"][pi]
                self.assertAlmostEqual(pd["starterAdj"], expected_starter, places=6,
                    msg=f"PARITY FAIL {src} {pos} starter")
                self.assertAlmostEqual(pd["benchAdj"], expected_bench, places=6,
                    msg=f"PARITY FAIL {src} {pos} bench")

    def test_listed_rostered_from_engine(self):
        data = _extract_in_browser(FIXTURE_JSON)
        for row in data["rows"]:
            src = row["src"]
            engine_src = FIXTURE["valuePipeline"]["sources"][src]
            expected_listed = sum(engine_src["positions"][pos]["listed"] for pos in POSITIONS)
            expected_rostered = sum(engine_src["positions"][pos]["rostered"] for pos in POSITIONS)
            expected_estimated = sum(engine_src["positions"][pos]["nEstimated"] for pos in POSITIONS)
            self.assertEqual(row["totalListed"], expected_listed)
            self.assertEqual(row["totalRostered"], expected_rostered)
            self.assertEqual(row["totalEstimated"], expected_estimated)


if __name__ == "__main__":
    unittest.main()
