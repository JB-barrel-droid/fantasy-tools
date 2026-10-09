"""Clean-room source-neutral value pipeline (pipelines/spec_reference, JEG-508).

VP-12: every implementation must reproduce
tests/fixtures/value_pipeline_worked_example.json (schema /2) to 1e-6, every
intermediate and expected value, including variant_bench_share_0_10. The
negative tests prove the leaf walk catches a perturbed expected value and a
simulated broken pipeline (median read as mean, uncapped estimates, bench
share 35%, flex by a chart's own values), so a green run means agreement,
not a comparator that checks nothing.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

from spec_reference import value_pipeline as vp  # noqa: E402
from spec_reference import worked_example as we  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"


def _fx():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class WorkedExample(unittest.TestCase):
    def test_fixture_schema_is_v2(self):
        self.assertEqual(_fx()["schema"], "value-pipeline-worked-example/2")

    def test_reproduces_every_pinned_value(self):
        res = we.compare_fixture(_fx())
        self.assertGreater(res["compared"], 4000)
        self.assertEqual(res["mismatches"], [], res["mismatches"][:10])

    def test_variant_bench_share_is_walked(self):
        fx = _fx()
        res = we.compare_fixture(fx)
        n_var = sum(len(v) if isinstance(v, dict) else 1
                    for k, v in fx["variant_bench_share_0_10"].items() if k != "rows_ddf_blended")
        self.assertGreater(n_var, 0)
        var = fx["variant_bench_share_0_10"]
        self.assertAlmostEqual(sum(v for k, v in var["ddf_weights"].items() if k.endswith("|bench")), 0.10, 5)
        self.assertEqual(res["mismatches"], [])

    def test_hand_check_rb_delta(self):
        out = we.run_fixture(_fx())
        self.assertAlmostEqual(out["sources"]["p1"]["players"][201]["adjusted"], 47.910397, 6)
        self.assertAlmostEqual(out["rows"][201]["ddf_blended"]["value"], 48.511113, 6)
        self.assertEqual(out["pie"], 280.0)


class WalkCatchesBreakage(unittest.TestCase):
    """Each guard is run against a simulated broken state and must go red."""

    def _mismatches(self, fx=None):
        return we.compare_fixture(fx or _fx())["mismatches"]

    def test_perturbed_expected_value_is_caught(self):
        fx = _fx()
        fx["expected"]["rows"]["201"]["ddf_blended"]["value"] += 2e-6
        bad = self._mismatches(fx)
        self.assertEqual([m["path"] for m in bad], ["expected.rows.201.ddf_blended.value"])

    def test_perturbed_variant_value_is_caught(self):
        fx = _fx()
        fx["variant_bench_share_0_10"]["ddf_weights"]["RB|bench"] += 1e-5
        self.assertEqual(len(self._mismatches(fx)), 1)

    def test_missing_key_is_caught(self):
        fx = _fx()
        fx["expected"]["sources"]["c4"]["not_a_field"] = 1.0
        self.assertEqual(len(self._mismatches(fx)), 1)

    def test_median_read_as_mean_is_caught(self):
        with mock.patch.object(vp, "median", lambda v: sum(v) / len(v)):
            self.assertTrue(self._mismatches())

    def test_uncapped_estimate_is_caught(self):
        real = vp.estimate_player

        def uncapped(*a, **k):
            rec = real(*a, **k)
            rec["value"] = max(rec["raw"], 0.0)
            return rec

        with mock.patch.object(vp, "estimate_player", uncapped):
            self.assertTrue(self._mismatches())

    def test_bench_share_35_is_caught(self):
        fx = _fx()
        broken = copy.deepcopy(fx)
        broken["setting"]["bench_share"] = 0.35
        out = we.run_fixture(broken)
        res = {"compared": 0, "mismatches": []}
        we.walk(fx["expected"]["ddf_weights"], out["ddf_weights"], "w", res)
        self.assertTrue(res["mismatches"])

    def test_flex_by_own_values_is_caught(self):
        # The superseded OC-4 rule: allocate on c1's own natives, not on m.
        fx = _fx()
        c1 = {int(k): float(v) for k, v in fx["inputs"]["c1"]["values"].items()}
        real = vp.allocate

        def own_values(setting, order, scores):
            pos_of = {int(k): v["pos"] for k, v in fx["players"].items()}
            if scores is not c1:
                return real(setting, vp.score_order(c1, pos_of), c1)
            return real(setting, order, scores)

        with mock.patch.object(vp, "allocate", own_values):
            self.assertTrue(self._mismatches())


class Invariants(unittest.TestCase):
    def test_every_included_source_totals_the_pie(self):
        out = we.run_fixture(_fx())
        for s in out["included"]:
            tot = sum(p["adjusted"] for p in out["sources"][s]["players"].values())
            self.assertAlmostEqual(tot, out["pie"], 9, s)
            vtot = sum(p["vorp_display"] for p in out["sources"][s]["players"].values())
            self.assertAlmostEqual(vtot, out["pie"], 9, s)

    def test_scaling_a_chart_changes_nothing(self):
        fx = _fx()
        base = we.run_fixture(fx)
        scaled = copy.deepcopy(fx)
        scaled["inputs"]["c5"]["values"] = {k: v * 7.0 for k, v in fx["inputs"]["c5"]["values"].items()}
        out = we.run_fixture(scaled)
        for k, row in base["rows"].items():
            self.assertAlmostEqual(row["adjusted"]["c5"] or 0.0, out["rows"][k]["adjusted"]["c5"] or 0.0, 9)


class LiveDump(unittest.TestCase):
    """The live entry point runs on the committed snapshot and keeps VP-5's
    invariant: every included source's Adjusted values total the pie."""

    def test_ppr12_and_superflex(self):
        from spec_reference import pipeline_live as pl
        rep = pl.build(only=["ppr/12/sf0", "ppr/12/sf1"])
        self.assertEqual(rep["schema"], "spec-reference-pipeline/1")
        for sid, pie in (("ppr/12/sf0", 2688.0), ("ppr/12/sf1", 3024.0)):
            s = rep["settings"][sid]
            self.assertEqual(s["pie"], pie)
            self.assertTrue(s["included"])
            self.assertAlmostEqual(sum(v for k, v in s["ddf_weights"].items() if k.endswith("|bench")), 0.15, 9)
            for src in s["included"]:
                tot = sum(v for v in s["values"]["adjusted"][src].values() if v)
                self.assertAlmostEqual(tot, pie, 6, f"{sid} {src}")
            n_rows = len(s["rows"])
            for view in s["values"].values():
                for series in view.values():
                    self.assertEqual(len(series), n_rows)


if __name__ == "__main__":
    unittest.main()
