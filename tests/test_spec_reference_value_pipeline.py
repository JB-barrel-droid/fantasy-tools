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


class Rulings(unittest.TestCase):
    """Lead's spec rulings 2026-10-09 (methodology.md "Spec rulings")."""

    def test_null_indexed_factor_nulls_whole_chart(self):
        # A held chart whose only listed player has native 0 has a native sum
        # of 0 (VP-6.4 null case): every value on it is null, below-depth too.
        fx = _fx()
        fx["players"]["299"] = {"name": "RB Nobody", "pos": "RB"}
        fx["inputs"]["c6"] = {"family": "chart", "status": "held", "values": {"299": 0.0}}
        out = we.run_fixture(fx)
        self.assertIsNone(out["indexed"]["c6"]["factor"])
        self.assertTrue(all(v is None for v in out["indexed"]["c6"]["values"].values()))
        # 201 is an RB c6 neither lists nor estimates (old reading gave 0).
        self.assertIsNone(out["rows"][201]["indexed"]["c6"])
        self.assertEqual(out["rows"][201]["adjusted"]["c6"], 0.0)

    def test_live_projection_natives_and_overlay(self):
        from spec_reference import pipeline_live as pl
        data = pl.load(pl.default_paths())
        espn = pl.current_natives(data, "espn", "ppr", 12, 0, {})
        players = {int(p["player_key"]): p for p in data["players"]}
        ineligible = [k for k, p in players.items()
                      if p.get("espn_status") == "ineligible" and not p.get("espn_ppg") and k in data["pos_of"]]
        self.assertTrue(ineligible)
        self.assertTrue(all(espn.get(k) == 0.0 for k in ineligible))
        full = [k for k, p in players.items() if (p.get("espn_ppg") or {}).get("ppr") is not None]
        self.assertTrue(all(espn[k] == float(players[k]["espn_ppg"]["ppr"]) for k in full))
        # CBS's superflex list adds QBs its 1-QB list lacks.
        one_qb = pl.current_natives(data, "cbs", "ppr", 12, 0, {})
        sf = pl.current_natives(data, "cbs", "ppr", 12, 1, {})
        self.assertTrue(set(sf) - set(one_qb))


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
            # es-value-001 (Jeremy, 2026-10-09; JEG-536): the bench share is an
            # output of the league settings, no longer fixed at 15%.
            bench = sum(v for k, v in s["ddf_weights"].items() if k.endswith("|bench"))
            self.assertAlmostEqual(bench, s["bench_share_readout"]["fill_in_share"], 12)
            self.assertFalse(s["bench_share_readout"]["override"])
            self.assertTrue(0.02 < bench < 0.15, bench)
            for src in s["included"]:
                tot = sum(v for v in s["values"]["adjusted"][src].values() if v)
                self.assertAlmostEqual(tot, pie, 6, f"{sid} {src}")
            n_rows = len(s["rows"])
            for view in s["values"].values():
                for series in view.values():
                    self.assertEqual(len(series), n_rows)



class ExpectedStartsVariant(unittest.TestCase):
    """JEG-536 (ES-11): the clean-room reference reproduces the worked
    example's expected-starts variants to 1e-6."""

    def run_variant(self, name: str, fx=None):
        sys.path.insert(0, str(REPO))
        from tests import _es_worked_example as esx
        fx = fx or _fx()
        var = fx[name]
        inp = we.fixture_inputs(fx)
        s = copy.deepcopy(fx["setting"])
        s.update(var["setting_change"])
        res = vp.run_week(vp.Setting.from_fixture(s), inp["pos_of"], inp["sources"], inp["included"],
                          names=inp["names"], lineup=var["lineup"])
        return esx.variant_problems(fx, name, res)

    def test_variants_reproduced(self):
        for name in ("variant_expected_starts", "variant_expected_starts_override"):
            self.assertEqual(self.run_variant(name), [])

    def test_perturbed_variant_is_caught(self):
        fx = _fx()
        fx["variant_expected_starts"]["expected"]["rows"]["201"]["lineup_share"] += 2e-6
        self.assertEqual(len(self.run_variant("variant_expected_starts", fx)), 1)

    def test_point_mass_level_is_caught(self):
        # sigma ignored (a level is known exactly): the parts change.
        real = vp.es_parts
        with mock.patch.object(vp, "es_parts", lambda *a: real(*a[:7], 0.0, 0.0)):
            self.assertNotEqual(self.run_variant("variant_expected_starts"), [])

    def test_resolve_matches_the_python_reference(self):
        import derive_lineup_parameters as dl
        cfg = json.loads((REPO / "config" / "lineup_parameters.json").read_text(encoding="utf-8"))
        for kw in ({}, {"objective": "playoffs"}, {"objective": "regular", "injury_history": "all"},
                   {"projection_confidence": 1.5},
                   {"league_weeks": {"regular_season_end": 13, "playoff_weeks": [14, 16]}}):
            a, b = vp.resolve_lineup(cfg, **kw), dl.resolve(cfg, **kw)
            self.assertAlmostEqual(a["bye"], b["bye"], places=15)
            for p in vp.POSITIONS:
                for k in ("m", "sigma_rel", "sigma_floor"):
                    self.assertAlmostEqual(a["positions"][p][k], b["positions"][p][k], places=14)

if __name__ == "__main__":
    unittest.main()
