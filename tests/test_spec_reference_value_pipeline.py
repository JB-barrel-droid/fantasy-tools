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
import tempfile
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
        # JEG-1121 stable: new VORP bench method (WR 1, TE 1 instead of WR 2, TE 0).
        self.assertAlmostEqual(out["sources"]["p1"]["players"][201]["adjusted"], 49.445413, 6)
        # JEG-1073: blended DDF = charts average; JEG-1121: updated for new bench allocation.
        self.assertAlmostEqual(out["rows"][201]["ddf_blended"]["value"], 50.760350, 6)
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

        def own_values(setting, order, scores, **kwargs):
            pos_of = {int(k): v["pos"] for k, v in fx["players"].items()}
            if scores is not c1:
                return real(setting, vp.score_order(c1, pos_of), c1, **kwargs)
            return real(setting, order, scores, **kwargs)

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


class NoChartFallback(unittest.TestCase):
    """JEG-1073 (Jeremy, 2026-10-25): DDF Value is the Adjusted trade charts,
    with no fallback to projections (the mirror of JEG-863's option B). When
    no chart is in I, DDF blended must be null for every player (not the
    projection average); the projections version is the alternate and still
    works."""

    def _run_projections_only(self):
        fx = _fx()
        # Remove all chart sources, keep only projections.
        fx["inputs"] = {k: v for k, v in fx["inputs"].items() if v["family"] == "projection"}
        inp = we.fixture_inputs(fx)
        s = copy.deepcopy(fx["setting"])
        setting = vp.Setting.from_fixture(s)
        return vp.run_week(setting, inp["pos_of"], inp["sources"], inp["included"], names=inp["names"])

    def test_projections_only_gives_null_blended(self):
        out = self._run_projections_only()
        for k, row in out["rows"].items():
            self.assertIsNone(row["ddf_blended"]["value"],
                              f"DDF blended must be null with no charts (player {k})")
        # The projections version (the alternate) still works.
        proj_ok = any(row["ddf_projections"]["value"] is not None for row in out["rows"].values())
        self.assertTrue(proj_ok, "projections version should be populated even with no charts")

    def test_charts_are_the_blend(self):
        """DDF blended equals the charts version and differs from the projections version."""
        out = we.run_fixture(_fx())
        rows = out["rows"].values()
        self.assertTrue(all(r["ddf_blended"]["value"] == r["ddf_charts"]["value"] for r in rows))
        self.assertTrue(any(r["ddf_blended"]["value"] != r["ddf_projections"]["value"] for r in rows))

    def test_guard_catches_fallback_restored(self):
        """If a fallback is restored (blended = projections when no chart), this detects it."""
        out = self._run_projections_only()
        all_null = all(row["ddf_blended"]["value"] is None for row in out["rows"].values())
        self.assertTrue(all_null, "the no-fallback guard should see null DDF blended with projections only")
        # Negative test: simulate a fallback by running with the patched pipeline.
        real_run_week = vp.run_week
        def with_fallback(setting, pos_of, sources, included, selection=None, names=None, lineup=None, hidden=None):
            result = real_run_week(setting, pos_of, sources, included, selection, names, lineup, hidden=hidden)
            if all(result["rows"][k]["ddf_blended"]["value"] is None for k in result["rows"]):
                for k in result["rows"]:
                    result["rows"][k]["ddf_blended"] = copy.deepcopy(result["rows"][k]["ddf_projections"])
            return result
        fx = _fx()
        fx["inputs"] = {k: v for k, v in fx["inputs"].items() if v["family"] == "projection"}
        inp = we.fixture_inputs(fx)
        s = copy.deepcopy(fx["setting"])
        setting = vp.Setting.from_fixture(s)
        broken = with_fallback(setting, inp["pos_of"], inp["sources"], inp["included"], names=inp["names"])
        broken_has_values = any(row["ddf_blended"]["value"] is not None for row in broken["rows"].values())
        self.assertTrue(broken_has_values, "the simulated fallback should produce non-null blended")


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
        self._check_live(pl.build(only=["ppr/12/sf0", "ppr/12/sf1"]))

    def test_every_projection_held_is_a_degenerate_week(self):
        # Chain run 573 (2026-10-17, JEG-chain573): the fidelity pulse held
        # espn, cbsros and razzball, so no projection was in I. VP-2.2 f (no
        # projection in I) has no projected-points order, so no bench tier
        # and no ES-14 readout (bench_share_readout is None, the same rule as
        # pipelines/value_reference.py). The live dump must still keep VP-5's
        # pie invariant on that data instead of crashing on the readout.
        #
        # Seeded: builds its own all-held fixture so the guard is
        # data-independent.  JEG-787: red holds no longer exclude -- the
        # sources are eligible but hidden. All sources in `included` but all
        # hidden from the DDF blend, so every DDF value is null.
        import fidelity_hold as fh
        from spec_reference import pipeline_live as pl
        paths = pl.default_paths()
        fixture = json.loads(Path(paths["fixture"]).read_text(encoding="utf-8"))
        all_roots = {root: {"stage": "stored_vs_chart",
                            "reason": "fidelity: stored_vs_chart"}
                     for root in pl.SOURCE_ORDER}
        held, _ = fh.apply_fidelity_holds(fixture, all_roots, 6)
        with tempfile.TemporaryDirectory() as tmp:
            fx_path = Path(tmp) / "comparison-sources-data.json"
            fx_path.write_text(json.dumps(held), encoding="utf-8")
            # JEG-787: pin the history index's content_week to the fixture's
            # served week so the pipeline never sees a newer week than the data
            # (the real index may have advanced past the fixture when Supabase
            # imports are blocked). Copy the history dir with a patched index.
            hist_dir = Path(tmp) / "history"
            hist_dir.mkdir()
            real_hist = Path(paths["history"])
            index = json.loads((real_hist / "index.json").read_text(encoding="utf-8"))
            served_weeks = [s["week"] for s in index.get("served", {}).values()
                            if isinstance(s.get("week"), int)]
            if served_weeks:
                index["content_week"] = max(served_weeks)
            (hist_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
            for p in real_hist.glob("week-*.json"):
                (hist_dir / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
            rep = pl.build({"fixture": fx_path, "history": hist_dir,
                            "out": Path(tmp) / "out.json"},
                           only=["ppr/12/sf0", "ppr/12/sf1"])
        for sid in ("ppr/12/sf0", "ppr/12/sf1"):
            s = rep["settings"][sid]
            excluded = {e["key"]: e["reason"] for e in s["excluded"]}
            # JEG-787: red-held sources are NOT excluded; they are eligible
            # but hidden.  No source should be excluded for "held".
            for root in pl.SOURCE_ORDER:
                self.assertNotEqual(excluded.get(root), "held",
                                    f"{root} should not be excluded for 'held' ({sid})")
            # All DDF blended values must be null (all sources hidden).
            for k, row in s["rows"].items():
                self.assertIsNone(row["ddf"]["blended"]["value"],
                                  f"DDF blended should be null when all hidden ({sid})")

    def test_amber_hold_stays_eligible_and_visible(self):
        """amber-hold-001 / JEG-726: amber holds are eligible and NOT hidden."""
        import fidelity_hold as fh
        from spec_reference import pipeline_live as pl
        paths = pl.default_paths()
        fixture = json.loads(Path(paths["fixture"]).read_text(encoding="utf-8"))
        # Amber-hold all projections: they should remain eligible and visible.
        amber_holds = {root: {"stage": "stored_vs_chart",
                              "reason": "fidelity: stored_vs_chart",
                              "hold_level": "amber"}
                       for root in pl.PROJECTIONS}
        held, _ = fh.apply_fidelity_holds(fixture, amber_holds, 6)
        with tempfile.TemporaryDirectory() as tmp:
            fx_path = Path(tmp) / "comparison-sources-data.json"
            fx_path.write_text(json.dumps(held), encoding="utf-8")
            rep = pl.build({"fixture": fx_path, "out": Path(tmp) / "out.json"},
                           only=["ppr/12/sf0"])
        s = rep["settings"]["ppr/12/sf0"]
        # Amber-held projections must not be excluded for "held".
        for root in pl.PROJECTIONS:
            held_exclusions = [e for e in s["excluded"] if e["key"] == root and e["reason"] == "held"]
            self.assertEqual(held_exclusions, [],
                             f"amber-held {root} should not be excluded for 'held'")
        # Any amber-held projection that made it into included must NOT be
        # hidden from the DDF projections version (the alternate since
        # JEG-1073; DDF Value itself is the charts): it must appear in at
        # least one row's sources -- players that source prices.
        for root in pl.PROJECTIONS:
            if root not in s["included"]:
                continue  # excluded for another reason (e.g. no prior week)
            found = any(root in row["ddf"]["projections"]["sources"]
                        for row in s["rows"].values())
            self.assertTrue(
                found,
                f"amber-held {root} in included but never appears in DDF projections sources")

    def test_red_hold_eligible_but_hidden(self):
        """JEG-569 / JEG-787: red holds are eligible (in pipeline for weights
        and pie) but hidden from the DDF Value blend and Indexed basis."""
        import fidelity_hold as fh
        from spec_reference import pipeline_live as pl
        paths = pl.default_paths()
        fixture = json.loads(Path(paths["fixture"]).read_text(encoding="utf-8"))
        red_holds = {root: {"stage": "stored_vs_chart",
                            "reason": "fidelity: stored_vs_chart",
                            "hold_level": "red"}
                     for root in pl.PROJECTIONS}
        held_r, _ = fh.apply_fidelity_holds(fixture, red_holds, 6)
        with tempfile.TemporaryDirectory() as tmp:
            fx_path = Path(tmp) / "comparison-sources-data.json"
            fx_path.write_text(json.dumps(held_r), encoding="utf-8")
            rep_r = pl.build({"fixture": fx_path, "out": Path(tmp) / "out.json"},
                             only=["ppr/12/sf0"])
        sr = rep_r["settings"]["ppr/12/sf0"]
        excluded_keys = {e["key"] for e in sr["excluded"]}
        # Red-held projections must NOT be excluded (they are eligible).
        for root in pl.PROJECTIONS:
            self.assertNotIn(root, excluded_keys,
                             f"red-held {root} should be eligible, not excluded")
        # Red-held projections must be in included (for weights/pie).
        for root in pl.PROJECTIONS:
            self.assertIn(root, sr["included"],
                          f"red-held {root} should be in the included set")
        # Red-held projections must be hidden from DDF blend.
        for root in pl.PROJECTIONS:
            for k, row in sr["rows"].items():
                ddf = row["ddf"]["blended"]
                if ddf["count"] > 0:
                    self.assertNotIn(
                        root, ddf["sources"],
                        f"red-held {root} should be hidden from DDF blend")
                    break

    def _check_live(self, rep):
        # JEG-563: pie = 12 teams x 28 x skill starting slots; the default roster is now
        # QB1 RB2 WR2 TE1 FLEX1 = 7 slots (was 8), so 2352 (sf1: 8 slots, 2688).
        from spec_reference import pipeline_live as pl
        self.assertEqual(rep["schema"], "spec-reference-pipeline/1")
        for sid, pie in (("ppr/12/sf0", 2352.0), ("ppr/12/sf1", 2688.0)):
            s = rep["settings"][sid]
            self.assertEqual(s["pie"], pie)
            self.assertTrue(s["included"])
            # es-value-001 (Jeremy, 2026-10-09; JEG-536): the bench share is an
            # output of the league settings, no longer fixed at 15%.
            bench = sum(v for k, v in s["ddf_weights"].items() if k.endswith("|bench"))
            self.assertAlmostEqual(bench, s["bench_share_applied"], 12)
            projections_in = [src for src in s["included"] if src in pl.PROJECTIONS]
            if projections_in:
                self.assertAlmostEqual(bench, s["bench_share_readout"]["fill_in_share"], 12)
                self.assertFalse(s["bench_share_readout"]["override"])
            else:
                # VP-2.2 f: a degenerate week has no ES-14 readout.
                self.assertIsNone(s["bench_share_readout"], sid)
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
