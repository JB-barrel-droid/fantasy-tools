"""JEG-1366: a 2-QB league takes its QB share of the pie from its own points
above the 2-QB replacement level.

Jeremy, 2026-10-30 23:36 UTC, pick A on the before/after posted to JEG-1366
("Build and merge it as proposed"). JEG-1365 priced a league that starts 2
dedicated QBs with the charts' superflex / 2-QB lists, so the QB share of the
pie came from the charts' superflex-market mixes (about 30 to 32% at 12
teams). Now, in a league with 2+ QB slots and no superflex slot, the QB groups
of the DDF weights are the mean over the included projections (points above
the league's own 2-QB waiver line, at its own starter line), and RB/WR/TE keep
their relative shares of the rest. Within QB each chart keeps its own list.
A superflex league is unchanged: its extra seat has an RB/WR/TE fallback.

Three paths must agree, so each is pinned here:
  * the Python reference (pipelines/value_reference.py ddf_weights),
  * the clean-room spec reference (pipelines/spec_reference/value_pipeline.py),
  * the engine (value-model.js runValuePipeline), which the page and the
    connector's get-values both run, through the headless edge runner.
Each fails on main before JEG-1366: there the QB weights are the mean over
every included source, charts too, and value-model.js has no helper.
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
from spec_reference import value_pipeline as spec  # noqa: E402

RUNNER = ["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tests" / "_edge_pipeline_runner.cjs")]
TWO_QB = {"scoring": "ppr", "teams": 12, "roster": {"QB": 2}}
TOL = 0.06  # value_check's tolerance


def data_today() -> str:
    from tests.test_week_history import _fixture_today
    return _fixture_today()


def qb_weight(res: dict) -> float:
    return res["ddf_weights"]["QB|starter"] + res["ddf_weights"]["QB|bench"]


def projection_qb_weight(res: dict) -> float:
    projs = [k for k in res["included"] if res["sources"][k]["family"] == "projection"
             and res["sources"][k]["weights"] is not None]
    return sum(res["sources"][k]["weights"]["QB|starter"] + res["sources"][k]["weights"]["QB|bench"]
               for k in projs) / len(projs)


class Rule(unittest.TestCase):
    def test_reference_rule(self):
        self.assertTrue(ref.uses_two_qb_native_share({"QB": 2, "SUPERFLEX": 0}))
        self.assertTrue(ref.uses_two_qb_native_share({"QB": 3, "SUPERFLEX": 0}))
        self.assertFalse(ref.uses_two_qb_native_share({"QB": 1, "SUPERFLEX": 1}))
        self.assertFalse(ref.uses_two_qb_native_share({"QB": 2, "SUPERFLEX": 1}))
        self.assertFalse(ref.uses_two_qb_native_share({"QB": 1, "SUPERFLEX": 0}))

    def test_spec_rule(self):
        self.assertTrue(spec.two_qb_native_share({"QB": 2}, 0))
        self.assertFalse(spec.two_qb_native_share({"QB": 1}, 1))
        self.assertFalse(spec.two_qb_native_share({"QB": 1}, 0))

    def test_engine_rule(self):
        script = """
const VM = require(process.argv[1]);
const shapes = [{QB: 2, SUPERFLEX: 0}, {QB: 3, SUPERFLEX: 0}, {QB: 1, SUPERFLEX: 1}, {QB: 2, SUPERFLEX: 1}, {QB: 1, SUPERFLEX: 0}];
process.stdout.write(JSON.stringify(shapes.map((s) => typeof VM.usesTwoQbNativeShare === "function" ? VM.usesTwoQbNativeShare(s) : null)));
"""
        out = subprocess.run(["node", "-e", script,
                              str(ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js")],
                             capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        self.assertEqual(json.loads(out.stdout), [True, True, False, False, False])


class ReferenceWeights(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))

    def test_two_qb_share_is_the_projections_share(self):
        for scoring in ref.SCORINGS:
            for teams in ref.TEAM_COUNTS:
                with self.subTest(scoring=scoring, teams=teams):
                    res = ref.Setting(self.inp, scoring, teams, qb=2).result()
                    self.assertAlmostEqual(qb_weight(res), projection_qb_weight(res), places=9)
                    self.assertAlmostEqual(sum(res["ddf_weights"].values()), 1.0, places=9)

    def test_rb_wr_te_keep_their_relative_shares(self):
        res = ref.Setting(self.inp, "ppr", 12, qb=2).result()
        w = res["ddf_weights"]
        raw = {}
        for g in ref.GROUPS:
            vals = [res["sources"][k]["weights"][g] for k in res["included"]
                    if res["sources"][k]["weights"] is not None]
            raw[g] = sum(vals) / len(vals)
        rest = [g for g in ref.GROUPS if not g.startswith("QB|")]
        for g in rest[1:]:
            self.assertAlmostEqual(w[g] / w[rest[0]], raw[g] / raw[rest[0]], places=9)

    def test_two_qb_prices_qbs_above_superflex(self):
        """The share rises at 12-team PPR on the fixture (36.0% against 30.5%
        before JEG-1366), so the top QB is worth more than in superflex."""
        two = ref.Setting(self.inp, "ppr", 12, qb=2)
        sf = ref.Setting(self.inp, "ppr", 12, superflex=1)
        self.assertGreater(qb_weight(two.result()), qb_weight(sf.result()) + 0.02)
        pos = {k: p["pos"] for k, p in self.inp.players.items()}
        top2 = max((v["ddf_value"] or 0) for k, v in two.rows("adj").items() if pos.get(k) == "QB")
        topsf = max((v["ddf_value"] or 0) for k, v in sf.rows("adj").items() if pos.get(k) == "QB")
        self.assertGreater(top2, topsf * 1.05)

    def test_superflex_and_one_qb_untouched(self):
        orig = ref.uses_two_qb_native_share
        for kw in ({}, {"superflex": 1}):
            with self.subTest(**kw):
                on = ref.Setting(self.inp, "ppr", 12, **kw).rows("adj")
                ref.uses_two_qb_native_share = lambda shape: False
                try:
                    off = ref.Setting(self.inp, "ppr", 12, **kw).rows("adj")
                finally:
                    ref.uses_two_qb_native_share = orig
                self.assertEqual({k: v["ddf_value"] for k, v in on.items()},
                                 {k: v["ddf_value"] for k, v in off.items()})


class SpecWeights(unittest.TestCase):
    """The spec reference's VP-4 on a small hand-made priced dict."""

    def priced(self):
        def src(family, w):
            groups = {g: w[g] for g in spec.GROUP_KEYS}
            s = sum(groups[f"{p}|starter"] for p in spec.POSITIONS)
            b = sum(groups[f"{p}|bench"] for p in spec.POSITIONS)
            return {"family": family, "has_weights": True, "weights": groups,
                    "starter_mix": {p: groups[f"{p}|starter"] / s for p in spec.POSITIONS},
                    "bench_mix": {p: groups[f"{p}|bench"] / b for p in spec.POSITIONS},
                    "positions": {p: {"method": "roster_determined"} for p in spec.POSITIONS}}
        chart = {"QB|starter": .20, "QB|bench": .02, "RB|starter": .33, "RB|bench": .03,
                 "WR|starter": .33, "WR|bench": .03, "TE|starter": .05, "TE|bench": .01}
        proj = {"QB|starter": .34, "QB|bench": .04, "RB|starter": .26, "RB|bench": .02,
                "WR|starter": .27, "WR|bench": .02, "TE|starter": .04, "TE|bench": .01}
        return {"c": src("chart", chart), "p": src("projection", proj)}

    def test_computed_share(self):
        _, _, bs, w = spec.ddf_weights(self.priced(), ["c", "p"], None, None, two_qb_native=True)
        self.assertAlmostEqual(w["QB|starter"], .34)
        self.assertAlmostEqual(w["QB|bench"], .04)
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w["WR|starter"] / w["RB|starter"], .30 / .295)
        _, _, _, off = spec.ddf_weights(self.priced(), ["c", "p"], None, None)
        self.assertAlmostEqual(off["QB|starter"], .27)

    def test_fixed_bench_share(self):
        _, _, bs, w = spec.ddf_weights(self.priced(), ["c", "p"], 0.1, None, two_qb_native=True)
        self.assertAlmostEqual(bs, 0.1)
        self.assertAlmostEqual(sum(w[f"{p}|bench"] for p in spec.POSITIONS), 0.1)
        self.assertAlmostEqual(w["QB|starter"], 0.9 * .34 / .91)


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        _render_env.ensure_built()
        cls.env = {**os.environ, "TRADE_VALUE_TODAY": data_today()}
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))

    def test_engine_equals_reference_in_a_two_qb_league(self):
        out = subprocess.run(RUNNER + ["--league", json.dumps(TWO_QB), "--dist", str(ROOT / "dist")],
                             capture_output=True, text=True, timeout=120, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        edge = {int(k): v for k, v in json.loads(out.stdout).items()}
        rows = ref.Setting(self.inp, "ppr", 12, qb=2).rows("adj")
        want = {int(k): v["ddf_value"] for k, v in rows.items()
                if isinstance(v.get("ddf_value"), (int, float))}
        self.assertGreater(len(edge), 50)
        bad = [k for k in set(edge) | set(want) if abs(edge.get(k, 0) - want.get(k, 0)) > TOL]
        self.assertEqual(bad[:10], [], f"{len(bad)} players differ")


if __name__ == "__main__":
    unittest.main()
