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
        from unittest import mock

        # VP-4 runs per allocation before the fractional-seat blend. A ratio
        # of blended weights need not equal the blend of the original ratios.
        rest = [g for g in ref.GROUPS if not g.startswith("QB|")]
        native_weights = ref.two_qb_native_weights
        per_allocation = []

        def check_allocation(raw, *args, **kwargs):
            w = native_weights(raw, *args, **kwargs)
            for g in rest[1:]:
                self.assertAlmostEqual(w[g] / w[rest[0]], raw[g] / raw[rest[0]], places=9)
            self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
            per_allocation.append(w)
            return w

        with mock.patch.object(ref, "two_qb_native_weights", side_effect=check_allocation):
            res = ref.Setting(self.inp, "ppr", 12, qb=2).result()
        mix = res["allocation_mix"]
        self.assertGreater(len(mix), 1)
        self.assertEqual(len(per_allocation), len(mix))
        for g in ref.GROUPS:
            want = sum(a["weight"] * w[g] for a, w in zip(mix, per_allocation))
            self.assertAlmostEqual(res["ddf_weights"][g], want, places=9)

    def test_two_qb_prices_qbs_above_superflex(self):
        """On the current 12-team PPR fixture the native QB share and the
        top QB value exceed the corresponding superflex setting."""
        two = ref.Setting(self.inp, "ppr", 12, qb=2)
        sf = ref.Setting(self.inp, "ppr", 12, superflex=1)
        self.assertGreater(qb_weight(two.result()), qb_weight(sf.result()) + 0.02)
        pos = {k: p["pos"] for k, p in self.inp.players.items()}
        top2 = max((v["ddf_value"] or 0) for k, v in two.rows("adj").items() if pos.get(k) == "QB")
        topsf = max((v["ddf_value"] or 0) for k, v in sf.rows("adj").items() if pos.get(k) == "QB")
        self.assertGreater(top2, topsf * 1.05)

    def test_superflex_and_one_qb_untouched(self):
        orig = ref.uses_two_qb_native_share
        for scoring in ref.SCORINGS:
            for kw in ({}, {"superflex": 1}):
                with self.subTest(scoring=scoring, **kw):
                    on = ref.Setting(self.inp, scoring, 12, **kw).rows("adj")
                    ref.uses_two_qb_native_share = lambda shape: False
                    try:
                        off = ref.Setting(self.inp, scoring, 12, **kw).rows("adj")
                    finally:
                        ref.uses_two_qb_native_share = orig
                    self.assertEqual({k: v["ddf_value"] for k, v in on.items()},
                                     {k: v["ddf_value"] for k, v in off.items()})


class ReferenceBenchShare(unittest.TestCase):
    """Review of #1236, findings 1 to 3: the fixed bench-share path, the
    recomputed bench share and the superflex input where the rule is called."""

    @classmethod
    def setUpClass(cls):
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))

    def projections(self, res):
        return [k for k in res["included"] if res["sources"][k]["family"] == "projection"
                and res["sources"][k]["weights"] is not None]

    def test_fixed_bench_share_rescales_starters_and_bench_separately(self):
        res = ref.Setting(self.inp, "ppr", 12, qb=2, bench_share_override=0.1).result()
        w, projs = res["ddf_weights"], self.projections(res)
        self.assertAlmostEqual(sum(w[f"{p}|bench"] for p in ref.POSITIONS), 0.1, places=9)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
        for role, mix, target in (("starter", "starter_mix", 0.9), ("bench", "bench_mix", 0.1)):
            want = target * sum(res["sources"][k][mix]["QB"] for k in projs) / len(projs)
            self.assertAlmostEqual(w[f"QB|{role}"], want, places=9)

    def test_computed_bench_share_is_the_reweighted_bench_total(self):
        res = ref.Setting(self.inp, "ppr", 12, qb=2).result()
        bench = sum(res["ddf_weights"][f"{p}|bench"] for p in ref.POSITIONS)
        self.assertAlmostEqual(res["bench_share_applied"], bench, places=12)
        inc = [k for k in res["included"] if res["sources"][k]["weights"] is not None]
        before = sum(res["sources"][k]["weights"][f"{p}|bench"] for k in inc for p in ref.POSITIONS) / len(inc)
        self.assertGreater(abs(res["bench_share_applied"] - before), 1e-4)  # the step moved it

    def test_two_qb_with_a_superflex_slot_keeps_every_sources_share(self):
        """QB 2 plus a superflex slot is a superflex league: the QB weight is the
        mean over every included source, not the projections' alone."""
        res = ref.Setting(self.inp, "ppr", 12, qb=2, superflex=1).result()
        inc = [k for k in res["included"] if res["sources"][k]["weights"] is not None]
        every = sum(res["sources"][k]["weights"]["QB|starter"] + res["sources"][k]["weights"]["QB|bench"]
                    for k in inc) / len(inc)
        self.assertAlmostEqual(qb_weight(res), every, places=9)
        self.assertGreater(abs(projection_qb_weight(res) - every), 0.01)


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
        self.assertAlmostEqual(bs, sum(w[f"{p}|bench"] for p in spec.POSITIONS), places=12)
        self.assertNotAlmostEqual(bs, .09, places=4)  # the mean bench share before the step
        _, _, _, off = spec.ddf_weights(self.priced(), ["c", "p"], None, None)
        self.assertAlmostEqual(off["QB|starter"], .27)

    def test_fixed_bench_share(self):
        _, _, bs, w = spec.ddf_weights(self.priced(), ["c", "p"], 0.1, None, two_qb_native=True)
        self.assertAlmostEqual(bs, 0.1)
        self.assertAlmostEqual(sum(w[f"{p}|bench"] for p in spec.POSITIONS), 0.1)
        self.assertAlmostEqual(w["QB|starter"], 0.9 * .34 / .91)


class SpecWiring(unittest.TestCase):
    """run_week passes the league's own QB and superflex counts to VP-4."""

    def calls(self, slots_qb, superflex):
        from unittest import mock
        from spec_reference import worked_example as we
        fx = json.loads(we.FIXTURE.read_text(encoding="utf-8"))
        inp = we.fixture_inputs(fx)
        s = json.loads(json.dumps(fx["setting"]))
        s["slots"] = {**s["slots"], "QB": slots_qb}
        s["superflex"] = superflex
        with mock.patch.object(spec, "ddf_weights", wraps=spec.ddf_weights) as dw:
            spec.run_week(spec.Setting.from_fixture(s), inp["pos_of"], inp["sources"], inp["included"],
                          names=inp["names"])
        return [c.args[4] if len(c.args) > 4 else c.kwargs.get("two_qb_native", False) for c in dw.call_args_list]

    def test_two_qb_league_takes_the_native_share(self):
        self.assertTrue(self.calls(2, 0))
        self.assertTrue(all(self.calls(2, 0)))

    def test_superflex_and_one_qb_do_not(self):
        self.assertFalse(any(self.calls(2, 1)))
        self.assertFalse(any(self.calls(1, 0)))


class Engine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import _render_env
        _render_env.ensure_built()
        cls.env = {**os.environ, "TRADE_VALUE_TODAY": data_today()}
        cls.inp = ref.Inputs.load(today=date.fromisoformat(data_today()))

    def test_engine_equals_reference_in_a_two_qb_league(self):
        for scoring in ref.SCORINGS:
            for teams in (10, 12, 14):
                with self.subTest(scoring=scoring, teams=teams):
                    league = {**TWO_QB, "scoring": scoring, "teams": teams}
                    edge = {int(k): v for k, v in self.edge(league).items()}
                    rows = ref.Setting(self.inp, scoring, teams, qb=2).rows("adj")
                    want = {int(k): v["ddf_value"] for k, v in rows.items()
                            if isinstance(v.get("ddf_value"), (int, float))}
                    self.assertGreater(len(edge), 50)
                    bad = [k for k in set(edge) | set(want) if abs(edge.get(k, 0) - want.get(k, 0)) > TOL]
                    self.assertEqual(bad[:10], [], f"{len(bad)} players differ")

    def edge(self, league, *extra):
        out = subprocess.run(RUNNER + ["--league", json.dumps(league), "--dist", str(ROOT / "dist"), *extra],
                             capture_output=True, text=True, timeout=120, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        return json.loads(out.stdout)

    def assert_weights_match(self, league, res, *extra):
        got = self.edge(league, "--dump-weights", "1", *extra)
        for g, v in res["ddf_weights"].items():
            self.assertAlmostEqual(got["ddf_weights"][g], v, places=9, msg=g)
        self.assertAlmostEqual(got["bench_share_applied"], res["bench_share_applied"], places=9)

    def test_engine_weights_and_bench_share_equal_the_reference(self):
        self.assert_weights_match(TWO_QB, ref.Setting(self.inp, "ppr", 12, qb=2).result())

    def test_engine_fixed_bench_share_equals_the_reference(self):
        setting = ref.Setting(self.inp, "ppr", 12, qb=2, bench_share_override=0.1)
        self.assert_weights_match(TWO_QB, setting.result(), "--bench-share-override", "0.1")
        edge = {int(k): v for k, v in self.edge(TWO_QB, "--bench-share-override", "0.1").items()}
        want = {int(k): v["ddf_value"] for k, v in setting.rows("adj").items()
                if isinstance(v.get("ddf_value"), (int, float))}
        self.assertGreater(len(edge), 50)
        bad = [k for k in set(edge) | set(want) if abs(edge.get(k, 0) - want.get(k, 0)) > TOL]
        self.assertEqual(bad[:10], [], f"{len(bad)} players differ")

    def test_engine_two_qb_with_superflex_slot_equals_the_reference(self):
        league = {"scoring": "ppr", "teams": 12, "roster": {"QB": 2, "SUPERFLEX": 1}}
        self.assert_weights_match(league, ref.Setting(self.inp, "ppr", 12, qb=2, superflex=1).result())


if __name__ == "__main__":
    unittest.main()
