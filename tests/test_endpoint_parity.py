"""JEG-616 step 4 parity test: the get-values edge function produces the same
DDF blended values as the headless engine page (engine_dump.py).

The test runs the edge function's pipeline logic in Node.js (loading
value-model.js directly, no browser) and compares every player's DDF blended
value against the Playwright-driven engine dump for the same setting.

Negative-tested: a deliberately wrong bench_per_team (99 instead of 6) must
produce at least one value that differs by more than 0.1 from the correct run.

JEG-1031: the same comparison for custom leagues (roster shape, position shares, bench override,
advanced settings, season weeks), with the edge side mapping the league through
supabase/functions/get-values/league.ts, the module the deployed function uses.

JEG-1179: the same comparison for the week priced. On a synthetic week transition (the served history
index with some sources pushed back one week), the edge side's default week, available weeks, the week's
sources and missing_sources, and every DDF Value match the page's (getWeekState, setWeek), for the
default week and each week asked for. The edge side reads the history through
supabase/functions/get-values/pipeline.ts, the module the deployed function uses.

Requires: a built dist/ and build/engine/ (make sync), Playwright chromium, node 22.6+.
Run by `make test-unit-modules`; CI sets RENDER_TESTS_REQUIRED=1 so a missing browser fails.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _dist_server, _render_env  # noqa: E402
from tests.test_week_history import _fixture_today  # noqa: E402


# The Node.js script that runs the edge function's pipeline logic headlessly.
EDGE_RUNNER = ROOT / "tests" / "_edge_pipeline_runner.cjs"
NODE = ["node", "--experimental-strip-types", "--no-warnings", str(EDGE_RUNNER)]

# Test a representative subset of settings (full sweep is slow).
SETTINGS = [
    ("ppr", 12, 0),
    ("half_ppr", 10, 0),
    ("standard", 14, 0),
    ("ppr", 12, 1),  # superflex
]

# JEG-1031: custom leagues (roster shape, shares, bench override, advanced, season weeks), in the
# normalized DDF league form. The page applies them through its own setters, in applyLinkLeague's
# order (league, roster, weeks, advanced, shares last); the endpoint maps them in league.ts.
CUSTOM_LEAGUES = {
    "all_fields": {
        "scoring": "half_ppr", "teams": 10, "roster": {"WR": 3, "BENCH": 6, "SUPERFLEX": 1},
        "shares": {"QB": 0.2, "RB": 0.4, "WR": 0.3, "TE": 0.1}, "bso": 0.2, "inj": "all", "conf": 1.5,
        "weeks": {"regend": 13, "playoffs": [14, 16], "optimize": "playoffs", "week": 5},
    },
    "roster_and_shares": {
        "scoring": "ppr", "teams": 14, "roster": {"QB": 2, "FLEX": 2, "BENCH": 10},
        "shares": {"QB": 0.05, "RB": 0.5, "WR": 0.4, "TE": 0.05},
    },
    "weeks_and_bench": {
        "scoring": "standard", "teams": 8, "bso": 0.05, "conf": 0.5,
        "weeks": {"regend": 12, "playoffs": [13, 15], "optimize": "regular"},
    },
}

PAGE_APPLY_LEAGUE = """(l) => {
    const c = window.TradeValueCurveControls;
    c.setScoring(l.scoring, false); c.setTeams(l.teams, false);
    Object.entries(l.roster || {}).forEach(([k, v]) => c.setRosterSpot(k, v, false));
    const w = l.weeks || {};
    if (w.regend !== undefined || w.playoffs) {
        c.setLeagueWeeks({regularSeasonEnd: w.regend ?? 14, playoffWeeks: w.playoffs || [15, 17]}, false);
    }
    if (w.optimize) c.setOptimizeFor(w.optimize, false);
    if (w.week !== undefined) c.setContentWeek(w.week, false);
    if (l.inj) c.setInjuryHistory(l.inj, false);
    if (l.conf) c.setProjectionConfidence(l.conf, false);
    if (l.bso !== undefined) c.setBenchShareOverride(l.bso, false);
    if (l.shares) c.setPositionWeights(l.shares, false);
    const values = {};
    Object.entries(window.TradeValueCurveHarness.pipeline().rows).forEach(([pk, row]) => {
        const v = row.ddfByVersion?.blended?.value;
        if (typeof v === 'number' && Number.isFinite(v)) values[pk] = v;
    });
    return values;
}"""



def run_edge(extra, override_bench=None):
    """The edge function's pipeline in Node.js, {pk: blended_value}."""
    args = NODE + extra + ["--dist", str(ROOT / "dist")]
    if override_bench is not None:
        args += ["--bench", str(override_bench)]
    # JEG-982: both sides read the clock in the served data's own content week. On the real clock, from
    # the Tuesday flip until the new week's charts land, every chart is "not yet published" and both
    # sides price nothing (the test then fails on "0 not greater than 50").
    env = {**os.environ, "TRADE_VALUE_TODAY": _fixture_today()}
    result = subprocess.run(args, capture_output=True, text=True, timeout=60, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Edge pipeline runner failed: {result.stderr}")
    return json.loads(result.stdout)


def run_edge_pipeline(setting, override_bench=None):
    scoring, teams, sf = setting
    return run_edge(["--scoring", scoring, "--teams", str(teams), "--superflex", str(sf)], override_bench)


def run_edge_league(league, override_bench=None):
    return run_edge(["--league", json.dumps(league)], override_bench)


LEGACY_APPLY = """([scoring, teams, sf]) => {
    const c = window.TradeValueCurveControls;
    c.setScoring(scoring); c.setTeams(teams); c.setRosterSpot('SUPERFLEX', sf);
    const values = {};
    Object.entries(window.TradeValueCurveHarness.pipeline().rows).forEach(([pk, row]) => {
        const v = row.ddfByVersion?.blended?.value;
        if (typeof v === 'number' && Number.isFinite(v)) values[pk] = v;
    });
    return values;
}"""


# JEG-1179: the page's week view (getWeekState) and DDF Value after setWeek (null = the default week).
PAGE_WEEK = """(week) => {
    const c = window.TradeValueCurveControls;
    if (week !== null) c.setWeek(week, false);
    const values = {};
    Object.entries(window.TradeValueCurveHarness.pipeline().rows).forEach(([pk, row]) => {
        const v = row.ddfByVersion?.blended?.value;
        if (typeof v === 'number' && Number.isFinite(v)) values[pk] = v;
    });
    return {values, state: c.getWeekState()};
}"""

WEEK_SOURCES = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"]


def transition_index(lagging_count):
    """The served history index with `lagging_count` sources pushed back one week behind the newest
    served week N: a week transition on the build's own saved weeks. Only sources served from their
    week's own snapshot move (a kept "superseded" version is tied to its week)."""
    index = json.loads((ROOT / "dist" / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    out = copy.deepcopy(index)
    served = out.get("served") or {}
    weeks = [served[k]["week"] for k in WEEK_SOURCES if isinstance((served.get(k) or {}).get("week"), int)]
    newest = max(weeks)
    movable = [k for k in WEEK_SOURCES if (served.get(k) or {}).get("week") == newest
               and served[k].get("version") != "superseded"]
    if len(movable) < lagging_count or str(newest - 2) not in (out.get("weeks") or {}):
        raise unittest.SkipTest(f"the build's history cannot stage a transition from week {newest}")
    lagging = movable[-lagging_count:]
    for k in lagging:
        served[k] = {**served[k], "week": newest - 1}
    return out, newest, lagging


def mismatches(engine, edge):
    """(pk, page, edge) where the page's value is more than 0.01 from the edge's (absent = 0)."""
    return [(pk, ev, edge.get(str(pk))) for pk, ev in engine.items()
            if abs(ev - (edge.get(str(pk)) or 0.0)) > 0.01]


class EndpointParityTests(unittest.TestCase):
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
        base = cls._serve.__enter__()
        cls._browser = cls._pw.chromium.launch(
            executable_path=exe, args=_render_env.HERMETIC_ARGS)
        cls._base = base

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._serve.__exit__(None, None, None)
        cls._pw.stop()

    def page_values(self, script, arg, base=None):
        """A fresh engine page (every run starts from the default league), then `script(arg)`."""
        page = self._browser.new_page()
        try:
            page.add_init_script(_render_env.pin_data_week_script())
            page.goto(f"{base or self._base}/{_dist_server.ENGINE_URL}")
            page.wait_for_function(
                "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()",
                timeout=120000,
            )
            return page.evaluate(script, arg)
        finally:
            page.close()

    def test_parity(self):
        """Edge function pipeline values must match the headless engine page."""
        for setting in SETTINGS:
            with self.subTest(setting=setting):
                engine = self.page_values(LEGACY_APPLY, list(setting))
                edge = run_edge_pipeline(setting)
                self.assertGreater(len(engine), 50)
                self.assertGreater(len(edge), 50)
                bad = mismatches(engine, edge)
                self.assertFalse(bad, f"{len(bad)} mismatches (page, edge): {bad[:10]}")

    def test_custom_league_parity(self):
        """JEG-1031: a custom league prices the same on the endpoint as on the page."""
        for name, league in sorted(CUSTOM_LEAGUES.items()):
            with self.subTest(league=name):
                engine = self.page_values(PAGE_APPLY_LEAGUE, league)
                edge = run_edge_league(league)
                self.assertGreater(len(engine), 50)
                bad = mismatches(engine, edge)
                self.assertFalse(bad, f"{len(bad)} mismatches (page, edge): {bad[:10]}")

    def test_week_parity(self):
        """JEG-1179: on a week transition the endpoint prices the page's default week and each week asked
        for exactly as the page does: same week, weeks, sources, missing_sources and DDF Values."""
        for lagging_count in (3, 4):
            index, newest, lagging = transition_index(lagging_count)
            body = json.dumps(index).encode()
            with tempfile.TemporaryDirectory() as tmp, \
                    _dist_server.serve(overrides={"assets/history/index.json": body}) as base:
                index_path = Path(tmp) / "index.json"
                index_path.write_bytes(body)
                for week in (None, newest, newest - 1):
                    with self.subTest(lagging=lagging, week=week):
                        page = self.page_values(PAGE_WEEK, week, base=base)
                        state = page["state"]
                        self.assertIsNotNone(state, "the page has a week view")
                        self.assertEqual(state["weeks"], [newest, newest - 1])
                        extra = ["--scoring", "ppr", "--teams", "12", "--history-index", str(index_path),
                                 "--with-week", "1"] + ([] if week is None else ["--week", str(week)])
                        edge = run_edge(extra)
                        got = edge["week"]
                        view = state["views"][str(state["week"])]
                        self.assertEqual(
                            (got["week"], got["default_week"], got["weeks"], got["sources"], got["missing_sources"]),
                            (state["week"], state["default_week"], state["weeks"], view["sources"],
                             view["missing_sources"]))
                        if state["week"] == newest:
                            for k in lagging:
                                self.assertIn(k, got["missing_sources"], f"{k} lags: missing, not carried forward")
                        self.assertGreater(len(page["values"]), 50)
                        bad = mismatches(page["values"], edge["values"])
                        self.assertFalse(bad, f"{len(bad)} mismatches (page, edge): {bad[:10]}")

    def test_negative_wrong_bench(self):
        """A wrong bench_per_team must produce different values, proving the test catches bugs."""
        setting = ("ppr", 12, 0)
        correct = run_edge_pipeline(setting)
        wrong = run_edge_pipeline(setting, override_bench=99)
        self.assertTrue(
            any(pk in wrong and abs(v - wrong[pk]) > 0.1 for pk, v in correct.items()),
            "Wrong bench_per_team=99 did not change any values.")

    def test_negative_custom_league_field_changes_values(self):
        """Each custom field moves the values, so a wrongly mapped field would fail the parity above."""
        league = CUSTOM_LEAGUES["all_fields"]
        base = run_edge_league(league)
        variants = {
            "wr": {**league, "roster": {**league["roster"], "WR": 2}},
            "shares": {**league, "shares": {"QB": 0.25, "RB": 0.25, "WR": 0.25, "TE": 0.25}},
            "bso": {**league, "bso": 0.1},
            "inj": {**league, "inj": "recent"},
            "conf": {**league, "conf": 1},
            "weeks": {**league, "weeks": {**league["weeks"], "regend": 12, "playoffs": [13, 16]}},
            "optimize": {**league, "weeks": {**league["weeks"], "optimize": "season"}},
        }
        for name, variant in variants.items():
            with self.subTest(field=name):
                other = run_edge_league(variant)
                self.assertTrue(any(abs(base[pk] - other.get(pk, 0.0)) > 0.1 for pk in base),
                                f"changing {name} did not change any values")


if __name__ == "__main__":
    unittest.main()
