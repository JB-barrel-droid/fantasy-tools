"""Intentional starter-fit/source differences, independent of display columns."""
import json
import subprocess
import unittest
from pathlib import Path
from pipelines.starter_fit_reference import classify, published_quote

ROOT = Path(__file__).resolve().parents[1]


class StarterContract(unittest.TestCase):
    def test_complete_league_compare_pricing(self):
        run = subprocess.run(["node", "tests/node/jeg1483_compare_pricing_check.cjs"], cwd=ROOT,
                             text=True, capture_output=True, check=True)
        receipt = json.loads(run.stdout)
        self.assertTrue(receipt["passed"])
        self.assertGreaterEqual(receipt["checks"], 58)
        self.assertEqual(receipt["leagues"], ["uso", "charlotte"])

    def test_unfiltered_authoritative_candidate_pipeline(self):
        run = subprocess.run(["node", "tests/node/jeg1483_candidate_check.cjs"], cwd=ROOT, text=True, capture_output=True, check=True)
        receipt = json.loads(run.stdout)
        self.assertTrue(receipt["passed"])
        self.assertGreaterEqual(receipt["checks"], 20)
        self.assertTrue(receipt["recovered"]["record"]["natural"])

    def test_synthetic_contract_and_legacy_readout(self):
        run = subprocess.run(["node", "tests/node/jeg1483_starter_contract_check.cjs"], cwd=ROOT, text=True, capture_output=True, check=True)
        receipt = json.loads(run.stdout)
        self.assertTrue(receipt["passed"])
        self.assertGreaterEqual(receipt["checks"], 60)
        actual = receipt["canonicalDefault"]
        expected = classify(actual["questions"], actual["settings"])
        self.assertEqual(actual["natural"], expected["natural"])
        self.assertEqual([q["pass"] for q in actual["questions"]], expected["predicates"])
        for case in receipt["policyCases"]:
            with self.subTest(policy=case["name"]):
                oracle = classify(case["questions"], case["settings"])
                self.assertEqual(case["label"], oracle["label"])
                self.assertEqual(case["natural"], oracle["natural"])
                self.assertEqual([q["pass"] for q in case["questions"]], oracle["predicates"])

    def test_real_starter_witness_and_intentional_source_difference(self):
        witness = json.loads((ROOT / "tests/fixtures/jeg1483-starter-real-witness.json").read_text())
        self.assertIn("not later design-next", witness["baselineRuntime"])
        for case in witness["cases"]:
            with self.subTest(case=case["name"]):
                generated = subprocess.run(["node", "-e", "require('./app/trade-value-chart/assets/value-model.js');const R=require('./app/v2/trade-readout.js');let s='';process.stdin.on('data',b=>s+=b).on('end',()=>console.log(JSON.stringify(R.summary(R.build(JSON.parse(s))))));"], cwd=ROOT, input=json.dumps(case["input"]), text=True, capture_output=True, check=True)
                actual = json.loads(generated.stdout)
                # Full before/after lineup and every quantity retain their
                # pinned same-input oracle, not just a predeclared fit word.
                self.assertEqual(actual, case["record"])
                decision = actual["decision"]
                oracle = classify(decision["questions"], decision["settings"])
                self.assertEqual(decision["natural"], oracle["natural"])
                self.assertEqual([q["pass"] for q in decision["questions"]], oracle["predicates"])
                self.assertNotIn("fantasycalc", actual["decision"]["questions"][2]["sources"])
        first = witness["cases"][0]["record"]["decision"]
        self.assertAlmostEqual(first["questions"][0]["value"], 3.387049840730242)
        self.assertAlmostEqual(first["questions"][2]["value"], 1.5478261163094373)
        self.assertNotEqual(first["questions"][2]["value"], -first["supporting"]["mine"]["market"]["package"]["value"])

    def test_published_coverage_zero_one_two_three(self):
        keys = ["usatoday", "fantasypros", "cbs"]
        for count in range(4):
            values = {key: 0 for key in keys[:count]}
            values["fantasycalc"] = 1000
            expected = published_quote(values)
            run = subprocess.run(["node", "-e", "const R=require('./app/v2/trade-readout.js');console.log(JSON.stringify(R.marketQuote({values:JSON.parse(process.argv[1])},{market:'published-average'})));", json.dumps(values)], cwd=ROOT, text=True, capture_output=True, check=True)
            actual = json.loads(run.stdout)
            self.assertEqual(actual["value"], expected["value"])
            self.assertEqual(actual["average"], expected["average"])
            self.assertEqual(actual["fitAvailable"], expected["fitAvailable"])
            self.assertEqual(actual["sources"], expected["sources"])
            self.assertEqual(actual["coverage"]["text"], expected["coverage"])


if __name__ == "__main__":
    unittest.main()
