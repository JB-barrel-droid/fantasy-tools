"""JEG-1188: league-wide Trade opportunities on frozen engine contexts (tests/fixtures/jeg1188).

The fixture league's count went 89 -> 66 -> 100 -> 34 between 2026-10-26 and 2026-10-27; the step to 34 is #957
(JEG-1121 bench seats), a value change, not the search. tests/node/jeg1188_opportunity_stages.cjs replays the real
modules on contexts dumped from the built page at five revisions and asserts what that diagnosis rests on. Here:
the check passes on this checkout, and fails for each way a search regression would raise or lower the count.
Diagnosis and numbers: docs/claude-log/2026-10-29-jeg-1188-opportunity-count.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "node" / "jeg1188_opportunity_stages.cjs"


def run(*extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(["node", str(SCRIPT), *extra], cwd=ROOT, capture_output=True, text=True, timeout=600)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class OpportunityStages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = run("--json")
        if proc.returncode != 0:
            raise AssertionError(proc.stderr[-2000:])
        cls.report = json.loads(proc.stdout)

    def test_assertions_pass(self):
        proc = run("--assert")
        self.assertEqual(proc.returncode, 0, proc.stdout[-1500:] + proc.stderr[-1500:])
        self.assertIn("assertions passed", proc.stdout)

    def test_fixtures_record_the_historical_page_counts(self):
        # What the built page showed at each revision (tools/jeg1188/dump_context.py). Those are evidence, not targets:
        # the page at that revision, with that revision's code, gave these, and its row ids are stored with them.
        pages = {name: c["page"]["total"] for name, c in self.report["contexts"].items()}
        self.assertEqual(pages, {"oct26-a-fit-rewrite": 89, "oct26-b-throw-ins": 66, "oct27-c-before-957": 100,
                                 "oct27-d-after-957": 34, "oct29-e-main": 59})

    def test_the_957_step_is_the_engine_rows(self):
        step = self.report["step957"]
        cross = step["cross"]
        # #957 changed no search code. Same modules, same before-957 context, the after-957 engine rows: the drop.
        self.assertLess(cross["rowsAfterBenchBefore"]["passGates"], cross["rowsBeforeBenchBefore"]["passGates"])
        self.assertLess(cross["rowsAfterBenchBefore"]["qualified"], cross["rowsBeforeBenchBefore"]["qualified"])
        lost = step["lost"]
        gone = lost["passedBefore"] - lost["stillPass"]
        self.assertGreater(gone, 0)
        # The loss is the DDF Value edge, not the chart gate (all of it at #957's own code, 95%+ under the JEG-1125 band).
        self.assertGreaterEqual(lost["failEdgeOnly"] + lost["failBoth"], 0.95 * gone)

    def test_nothing_is_lost_before_ranking(self):
        # JEG-1072 baseline on real engine values: every qualified trade is shown. The before-957 context has four
        # opponents with more than ten qualified trades, so a per-opponent cap shows here.
        c = self.report["contexts"]["oct27-c-before-957"]
        self.assertGreater(c["qualified"], c["top10"])
        for name, ctx in self.report["contexts"].items():
            self.assertEqual(ctx["shown"], ctx["qualified"], name)

    def test_a_per_opponent_cap_is_caught(self):
        proc = run("--assert", "--mutant", "cap-per-opponent")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("lost before ranking", proc.stderr)

    def test_dropping_the_lineup_boxes_is_caught(self):
        proc = run("--assert", "--mutant", "no-lineup-boxes")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("qualify", proc.stderr)

    def test_a_weaker_chart_gate_is_caught_by_the_independent_judge(self):
        # More trades shown is not a fix: the shown rows must still pass the gates when judged outside finder.js.
        # (--assert fails it earlier, on shown vs qualified, so its exit code says nothing about the judge.)
        proc = run("--json", "--mutant", "weaker-chart-gate")
        self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
        contexts = json.loads(proc.stdout)["contexts"]
        self.assertTrue(any(c["failingGatesHere"] > 0 for c in contexts.values()))


if __name__ == "__main__":
    unittest.main()
