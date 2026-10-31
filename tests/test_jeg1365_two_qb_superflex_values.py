"""JEG-1365: a 2-QB league is priced with the charts' own superflex / 2-QB values.

Jeremy, 2026-10-29 (audit decision 9, option A): "A for now, but back ticket
to actually use the value replacement and starter bench logic here." Before
this, a league that starts 2 dedicated QBs and has no superflex slot read
every published chart's 1-QB list, so QBs ranked 13 to 24 sat far too low
(C.J. Stroud 14.4 against 27.1 in superflex at 12-team PPR on the 2026-10-30
fixture), while the connector's explain text said the superflex lists apply.

What changes: only which natives a chart contributes (native_superflex
overlaid on the 1-QB list, as with a superflex slot). Seats, starters and the
waiver line still come from the league's own roster (QB 2, no SF). The real
2-QB replacement and starter/bench logic is JEG-1366.

Three paths must agree, so each is pinned here:
  * the Python reference (pipelines/value_reference.py, Setting.natives),
  * the page's engine helper (value-model.js usesSuperflexValues, which
    curve-widget.js savedPublishedNative calls),
  * the connector's endpoint (supabase/functions/get-values/pipeline.ts),
    through the same headless runner the parity tests use.
Each of these fails on main before JEG-1365: the reference and the endpoint
give a 2-QB league the 1-QB natives, and value-model.js has no helper.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT))

import value_reference as ref  # noqa: E402

CHARTS = ("fantasycalc", "cbs", "fantasypros", "usatoday")
RUNNER = ["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tests" / "_edge_pipeline_runner.cjs")]
TWO_QB = {"scoring": "ppr", "teams": 12, "roster": {"QB": 2}}
SUPERFLEX = {"scoring": "ppr", "teams": 12, "roster": {"SUPERFLEX": 1}}
ONE_QB = {"scoring": "ppr", "teams": 12}
TOL = 0.06  # tests/node/get_values_handler_check.mjs and value_check's tolerance


def data_today() -> str:
    from tests.test_week_history import _fixture_today
    return _fixture_today()


def charts_with_superflex(inp) -> list[str]:
    return [src for src in CHARTS
            if inp.section(src) is not None
            and inp.cell(src, "ppr", ref.SAVED_TEAMS, "native_superflex")]


class Rule(unittest.TestCase):
    def test_reference_rule(self):
        self.assertTrue(ref.uses_superflex_values({"QB": 2, "SUPERFLEX": 0}))
        self.assertTrue(ref.uses_superflex_values({"QB": 3, "SUPERFLEX": 0}))
        self.assertTrue(ref.uses_superflex_values({"QB": 1, "SUPERFLEX": 1}))
        self.assertFalse(ref.uses_superflex_values({"QB": 1, "SUPERFLEX": 0}))

    def test_page_and_endpoint_rule(self):
        script = """
const VM = require(process.argv[1]);
const { usesSuperflexValues } = require(process.argv[2]);
const shapes = [{QB: 2, SUPERFLEX: 0}, {QB: 3, SUPERFLEX: 0}, {QB: 1, SUPERFLEX: 1}, {QB: 1, SUPERFLEX: 0}];
const page = shapes.map((s) => typeof VM.usesSuperflexValues === "function" ? VM.usesSuperflexValues(s) : null);
const edge = shapes.map((s) => usesSuperflexValues({ superflex: s.SUPERFLEX, slots: { QB: s.QB } }));
process.stdout.write(JSON.stringify({ page, edge }));
"""
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings", "-e", script,
             str(ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"),
             str(ROOT / "supabase" / "functions" / "get-values" / "pipeline.ts")],
            capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        got = json.loads(out.stdout)
        self.assertEqual(got["page"], [True, True, True, False])
        self.assertEqual(got["edge"], [True, True, True, False])

    def test_page_overlay_reads_the_rule(self):
        widget = (ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn('if (native.size && ValueModel.usesSuperflexValues(rosterShape)) '
                      'take(savedPublishedRow(key, "native_superflex"));', widget)


class ReferenceNatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))
        cls.charts = charts_with_superflex(cls.inp)

    def test_fixture_has_superflex_lists(self):
        self.assertGreaterEqual(len(self.charts), 2, self.charts)

    def test_two_qb_league_reads_the_superflex_lists(self):
        two = ref.Setting(self.inp, "ppr", 12, qb=2)
        sf = ref.Setting(self.inp, "ppr", 12, superflex=1)
        one = ref.Setting(self.inp, "ppr", 12)
        for src in self.charts:
            with self.subTest(src=src):
                self.assertEqual(two.natives(src), sf.natives(src))
                self.assertNotEqual(two.natives(src), one.natives(src))

    def test_league_keeps_its_own_seats(self):
        two = ref.Setting(self.inp, "ppr", 12, qb=2)
        self.assertEqual(two.league.slots["QB"], 2)
        self.assertEqual(two.league.superflex, 0)


class EndpointNatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        _render_env.ensure_built()
        cls.env = {**os.environ, "TRADE_VALUE_TODAY": data_today()}
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))
        cls.charts = charts_with_superflex(cls.inp)

    def run_edge(self, league, *extra):
        out = subprocess.run(RUNNER + ["--league", json.dumps(league), "--dist", str(ROOT / "dist"), *extra],
                             capture_output=True, text=True, timeout=120, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        return json.loads(out.stdout)

    def test_two_qb_league_reads_the_superflex_lists(self):
        for src in self.charts:
            with self.subTest(src=src):
                two = self.run_edge(TWO_QB, "--dump-natives", src)
                sf = self.run_edge(SUPERFLEX, "--dump-natives", src)
                one = self.run_edge(ONE_QB, "--dump-natives", src)
                if two is None and sf is None:
                    continue  # the chart sits outside this week's view on both sides
                self.assertEqual(two, sf)
                self.assertNotEqual(two, one)

    def test_endpoint_equals_reference_in_a_two_qb_league(self):
        edge = {int(k): v for k, v in self.run_edge(TWO_QB).items()}
        rows = ref.Setting(self.inp, "ppr", 12, qb=2).rows("adj")
        want = {int(k): v["ddf_value"] for k, v in rows.items()
                if isinstance(v.get("ddf_value"), (int, float))}
        self.assertGreater(len(edge), 50)
        bad = [k for k in set(edge) | set(want) if abs(edge.get(k, 0) - want.get(k, 0)) > TOL]
        self.assertEqual(bad[:10], [], f"{len(bad)} players differ")


if __name__ == "__main__":
    unittest.main()
