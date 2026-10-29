"""JEG-1205: live fill peers, with JS and both Python engines on one input.

The worked example uses c1 as FantasyCalc. Its explicit fill_peer flag keeps
the example's generic source names while exercising the production rule.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from spec_reference import worked_example as spec
from tests.test_value_reference_worked_example import FIXTURE, league_of, sources_of
from tests import test_value_reference_worked_example as ref_test

DRIVER = ROOT / "tests/value_pipeline_driver.js"
MODEL = ROOT / "app/trade-value-chart/assets/value-model.js"


def run_all(fx: dict, model: Path = MODEL) -> dict:
    pos_of = {int(k): v["pos"] for k, v in fx["players"].items()}
    included = [k for k, v in fx["inputs"].items() if v["status"] == "included"]
    ref = ref_test.ref.run_pipeline(league_of(fx), sources_of(fx), pos_of, included)
    sp = spec.run_fixture(fx)
    with tempfile.NamedTemporaryFile("w", suffix=".json") as tmp:
        json.dump(fx, tmp)
        tmp.flush()
        proc = subprocess.run(["node", str(DRIVER), str(model), tmp.name],
                              capture_output=True, text=True, check=True, timeout=60)
    return {"ref": ref, "spec": sp, "js": json.loads(proc.stdout)}


def estimate(result: dict, engine: str, source: str, pos: str, player: int) -> dict:
    key = str(player) if engine == "js" else player
    return result[engine]["sources"][source]["positions"][pos]["imputation_ratios"][key]


class LiveFillPeers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = json.loads(FIXTURE.read_text())
        cls.base = run_all(cls.fx)

    def test_values_logic_names_only_live_fill_peers(self):
        template = (ROOT / "app/values-explainer/template.html").read_text()
        fill_step = template.split('["Fill in what a chart doesn\'t list", `', 1)[1].split('`],', 1)[0]
        self.assertIn("included FantasyCalc and projection sources", fill_step)
        self.assertIn("FantasyCalc itself uses projections only", fill_step)
        self.assertIn("other weekly charts never supply an estimate", fill_step)
        self.assertIn('"live peers: "', template)
        self.assertNotIn("scaled from other charts", template)
        self.assertNotIn("other charts' values", fill_step)

    def test_only_fantasycalc_and_projections_supply_estimates(self):
        for engine in self.base:
            with self.subTest(engine=engine):
                self.assertEqual(set(estimate(self.base, engine, "c5", "TE", 404)["peers"]),
                                 {"c1", "p1", "p2"})
                self.assertEqual(set(estimate(self.base, engine, "c1", "RB", 207)["peers"]),
                                 {"p1"})

    def test_weekly_chart_edits_cannot_change_another_charts_estimate(self):
        fx = copy.deepcopy(self.fx)
        for source in ("c2", "c4"):
            fx["inputs"][source]["values"]["404"] = 0.01
        changed = run_all(fx)
        for engine in self.base:
            with self.subTest(engine=engine):
                before = estimate(self.base, engine, "c5", "TE", 404)
                after = estimate(changed, engine, "c5", "TE", 404)
                self.assertEqual(after["raw"], before["raw"])
                self.assertEqual(after["peers"], before["peers"])

    def test_excluded_live_source_is_not_a_peer(self):
        fx = copy.deepcopy(self.fx)
        fx["inputs"]["c1"]["status"] = "held"
        changed = run_all(fx)
        for engine in changed:
            with self.subTest(engine=engine):
                self.assertEqual(set(estimate(changed, engine, "c5", "TE", 404)["peers"]),
                                 {"p1", "p2"})

        fx = copy.deepcopy(self.fx)
        fx["inputs"]["p1"]["status"] = "held"
        changed = run_all(fx)
        for engine in changed:
            with self.subTest(engine=engine, held="p1"):
                self.assertEqual(set(estimate(changed, engine, "c5", "TE", 404)["peers"]),
                                 {"c1", "p2"})

    def test_explicit_zero_is_listed_but_missing_is_not(self):
        zero = copy.deepcopy(self.fx)
        zero["inputs"]["p1"]["values"]["404"] = 0.0
        missing = copy.deepcopy(zero)
        del missing["inputs"]["p1"]["values"]["404"]
        results = (run_all(zero), run_all(missing))
        for engine in self.base:
            with self.subTest(engine=engine):
                present = estimate(results[0], engine, "c5", "TE", 404)["peers"]
                absent = estimate(results[1], engine, "c5", "TE", 404)["peers"]
                self.assertIn("p1", present)
                self.assertTrue(present["p1"]["usable"])
                self.assertEqual(present["p1"]["estimate"], 0)
                self.assertNotIn("p1", absent)

    def test_curve_fallback_when_live_peer_cannot_fit(self):
        fx = copy.deepcopy(self.fx)
        fx["inputs"]["c1"]["status"] = "held"
        fx["inputs"]["p2"]["status"] = "held"
        for key in fx["inputs"]["p1"]["values"]:
            if self.fx["players"][key]["pos"] == "TE" and key != "404":
                fx["inputs"]["p1"]["values"][key] = 0.0
        changed = run_all(fx)
        for engine in changed:
            with self.subTest(engine=engine):
                rec = estimate(changed, engine, "c5", "TE", 404)
                self.assertEqual(rec["path"], "curve")
                self.assertFalse(rec["peers"]["p1"]["usable"])
                self.assertGreaterEqual(rec["value"], 0)

    def test_old_chart_peer_rule_is_a_negative_control(self):
        old = 'return included.filter(function (k) {'
        source = MODEL.read_text()
        self.assertEqual(source.count(old), 1)
        # Mutate only the peer selector, keeping the rest of the engine intact.
        start = source.index(old, source.index('var fillPeersFor = function (src)'))
        end = source.index('\n    };', start)
        broken = source[:start] + 'return chartsI.filter(function (k) { return k !== src; });' + source[end:]
        with tempfile.NamedTemporaryFile('w', suffix='.js') as model:
            model.write(broken)
            model.flush()
            fx = copy.deepcopy(self.fx)
            for weekly in ("c2", "c4"):
                fx["inputs"][weekly]["values"]["404"] = 0.01
            before = estimate(run_all(self.fx, Path(model.name)), "js", "c5", "TE", 404)
            after = estimate(run_all(fx, Path(model.name)), "js", "c5", "TE", 404)
        self.assertNotEqual(before["raw"], after["raw"])

    def test_rosterable_fill_set_and_ddf_definitions(self):
        for engine, res in self.base.items():
            with self.subTest(engine=engine):
                fill = res["fill_sets"]
                for source in ("c1", "c2", "c4", "c5"):
                    for pos, players in fill.items():
                        if not self.fx["inputs"][source]["values"]:
                            continue
                        own = {int(k) for k in self.fx["inputs"][source]["values"]
                               if self.fx["players"][k]["pos"] == pos}
                        if not own:
                            continue
                        priced = res["sources"][source]["players"]
                        for key in players:
                            self.assertIn(str(key) if engine == "js" else key, priced)
                row = res["rows"]["201" if engine == "js" else 201]
                adj = row["adjusted"]
                chart_avg = sum(adj[k] for k in ("c1", "c2", "c4", "c5")) / 4
                projection_avg = sum(adj[k] for k in ("p1", "p2")) / 2
                ddf = row["ddf"] if engine == "ref" else row
                if engine == "ref":
                    self.assertAlmostEqual(ddf["blended"]["value"], chart_avg)
                    self.assertAlmostEqual(ddf["projections"]["value"], projection_avg)
                else:
                    self.assertAlmostEqual(ddf["ddf_blended"]["value"], chart_avg)
                    self.assertAlmostEqual(ddf["ddf_projections"]["value"], projection_avg)


if __name__ == "__main__":
    unittest.main()
