"""JEG-1029: page parity for the connector's analyses (risers_fallers, compare_trade by_source,
audit_values): the live engine page against get-values' analysis blocks (the edge function's own
analysis.ts, run by the parity runner).

The analyses run the page's own modules (movers.js, trade.js, audit-pie.js, audit-source.js) on these
blocks; tests/test_connector_analyses.py shows offline that each tool answers exactly what its module
answers on the same rows, and that the blocks match pipelines/value_reference.py. This test closes the
loop with the page: at each setting, what the page's engine hands those modules is what get-values
returns:

- risers_fallers and compare_trade by_source: TradeValueCurveControls.getAllRows() values (the Indexed
  tab) are include=series, and getPriorWeek(series) for every Risers & fallers series is include=prior
  (available, the week pair, the prior values and, for the DDF Value versions, currentValues).
- audit_values: getInspection()'s pie, included set, each source's player stages (pos, role, native,
  estimated, adjusted) and the rows' Indexed values are include=audit.

Negative: a deliberately wrong bench (the runner's --bench 99) must change the blocks the page is
compared to, so a comparison that cannot fail does not pass.

Requires a built dist/ and build/engine/ (make sync), Playwright Chromium and node 22.6+. Run by
`make test-unit-modules` beside tests/test_endpoint_parity.py; CI sets RENDER_TESTS_REQUIRED=1 so a
missing browser fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _dist_server, _render_env  # noqa: E402
from tests.test_endpoint_parity import LEGACY_APPLY  # noqa: E402
from tests.test_week_history import _fixture_today  # noqa: E402

RUNNER = ROOT / "tests" / "_edge_pipeline_runner.cjs"
SETTINGS = [("ppr", 12, 0), ("half_ppr", 10, 0), ("ppr", 12, 1)]
SERIES = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "fantasycalc", "usatoday", "fantasypros", "cbs",
          "cbsros", "razzball", "espn"]
TOL = 1e-6

# The page's side, after LEGACY_APPLY has set the league: the rows the modules read, the prior week of
# every series, and the inspection the audit tabs read (only the fields include=audit carries).
PAGE_ANALYSES = """async () => {
    const c = window.TradeValueCurveControls;
    const rows = {};
    c.getAllRows().forEach(row => {
        const v = {};
        Object.entries(row.values || {}).forEach(([k, x]) => { if (typeof x === 'number' && Number.isFinite(x)) v[k] = x; });
        rows[row.player_key] = v;
    });
    const prior = {};
    for (const key of %s) prior[key] = await c.getPriorWeek(key);
    const ins = c.getInspection();
    const players = {};
    Object.entries(ins.players || {}).forEach(([src, ps]) => {
        players[src] = {};
        Object.entries(ps).forEach(([pk, p]) => {
            players[src][pk] = {pos: p.pos, role: p.role, native: p.native, estimated: !!p.estimated, adjusted: p.adjusted};
        });
    });
    const indexed = {};
    Object.entries(ins.rows || {}).forEach(([pk, r]) => { indexed[pk] = r.indexed; });
    return {rows, prior, audit: {pie: ins.valuePipeline && ins.valuePipeline.pie, included: ins.included, players, indexed}};
}""" % json.dumps(SERIES)


def run_edge(setting, bench=None):
    scoring, teams, sf = setting
    args = ["node", "--experimental-strip-types", "--no-warnings", str(RUNNER), "--scoring", scoring,
            "--teams", str(teams), "--superflex", str(sf), "--dist", str(ROOT / "dist"),
            "--include", "series,prior,audit"] + (["--bench", str(bench)] if bench is not None else [])
    env = {**os.environ, "TRADE_VALUE_TODAY": _fixture_today()}
    out = subprocess.run(args, capture_output=True, text=True, timeout=120, env=env)
    if out.returncode != 0:
        raise RuntimeError(f"edge runner failed: {out.stderr}")
    return json.loads(out.stdout)


def close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= TOL


def map_diffs(got: dict, want: dict, label: str) -> list[str]:
    return [f"{label} {k}: page {got.get(k)}, edge {want.get(k)}"
            for k in sorted(set(got) | set(want)) if not close(got.get(k), want.get(k))]


def page_errors(page: dict, edge: dict) -> list[str]:
    errors = []
    for key in SERIES:
        got = {str(k): v[key] for k, v in page["rows"].items() if key in v}
        want = {k: v[key] for k, v in edge["series"].items() if key in v}
        errors += map_diffs(got, want, f"series {key}")
        p, e = page["prior"][key], edge["prior"]["series"][key]
        if bool(p.get("available")) != e["available"]:
            errors.append(f"prior {key}: page available {p.get('available')} ({p.get('reason')}), edge {e['available']} ({e['reason']})")
            continue
        if not e["available"]:
            continue
        if (p.get("currentWeek"), p.get("priorWeek")) != (edge["prior"]["current_week"], edge["prior"]["prior_week"]):
            errors.append(f"prior {key}: page pair {p.get('priorWeek')}->{p.get('currentWeek')}")
        errors += map_diffs({str(k): v for k, v in (p.get("values") or {}).items()}, e["values"], f"prior {key}")
        if "current_values" in e:
            errors += map_diffs({str(k): v for k, v in (p.get("currentValues") or {}).items()}, e["current_values"],
                                f"prior {key} current")
    a, e = page["audit"], edge["audit"]
    if not close(a["pie"], e["valuePipeline"]["pie"]):
        errors.append(f"pie: page {a['pie']}, edge {e['valuePipeline']['pie']}")
    for src, players in e["players"].items():
        mine = a["players"].get(src) or {}
        for pk, p in players.items():
            q = mine.get(pk)
            if q is None or any(q[f] != p[f] for f in ("pos", "role", "estimated")) \
                    or not close(q["native"], p["native"]) or not close(q["adjusted"], p["adjusted"]):
                errors.append(f"audit {src} {pk}: page {q}, edge {p}")
        if set(mine) - set(players):
            errors.append(f"audit {src}: page has players the edge lacks: {sorted(set(mine) - set(players))[:5]}")
    for pk, r in e["rows"].items():
        for src, v in (r["indexed"] or {}).items():
            if not close((a["indexed"].get(pk) or {}).get(src), v):
                errors.append(f"audit indexed {pk} {src}: page {(a['indexed'].get(pk) or {}).get(src)}, edge {v}")
    return errors


class ConnectorAnalysesPageParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        if not _dist_server.engine_built():
            raise _render_env.unavailable("build/engine not built (run make sync)")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        cls._pw = sync_playwright().start()
        exe = _dist_server.chromium_executable(cls._pw)
        if not exe:
            cls._pw.stop()
            raise _render_env.unavailable("no Chromium available")
        cls._serve = _dist_server.serve()
        cls._base = cls._serve.__enter__()
        cls._browser = cls._pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._serve.__exit__(None, None, None)
        cls._pw.stop()

    def page_analyses(self, setting):
        page = self._browser.new_page()
        try:
            page.add_init_script(_render_env.pin_data_week_script())
            page.goto(f"{self._base}/{_dist_server.ENGINE_URL}")
            page.wait_for_function(
                "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=120000)
            page.evaluate(LEGACY_APPLY, list(setting))
            return page.evaluate(PAGE_ANALYSES)
        finally:
            page.close()

    def test_page_matches_analysis_blocks(self):
        """risers_fallers, compare_trade by_source and audit_values read what the page's engine reads."""
        for setting in SETTINGS:
            with self.subTest(setting=setting):
                page = self.page_analyses(setting)
                edge = run_edge(setting)
                self.assertGreater(len(page["rows"]), 500)
                self.assertTrue(edge["prior"]["available"], edge["prior"]["reason"])
                errors = page_errors(page, edge)
                self.assertEqual(errors, [], f"{len(errors)} mismatches: {errors[:10]}")

    def test_negative_wrong_bench(self):
        setting = SETTINGS[0]
        page = self.page_analyses(setting)
        self.assertNotEqual(page_errors(page, run_edge(setting, bench=99)), [],
                            "a wrong bench should not match the page")


if __name__ == "__main__":
    unittest.main()
