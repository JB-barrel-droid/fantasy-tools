"""JEG-1280: the offline projection-influence ledger.

tools/research/projection-influence-ledger/ledger.py holds every chart
observation fixed, changes only projection inputs and splits each chart DDF
Value move into the stages that carry it (lineup, bench, fill_in,
position_weight) plus an unattributed residual. These tests prove the ledger
refuses pairs that are not projection-only, that its split adds up, that the
excluded / held / absent-versus-zero cases read as the engine computes them,
that its output is deterministic, and that the committed ledger reproduces.

Offline: python3 -m unittest tests.test_projection_influence
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "projection-influence-ledger"
_spec = importlib.util.spec_from_file_location(
    "projection_influence_ledger", ROOT / "tools" / "research" / "projection-influence-ledger" / "ledger.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)
vr = L.vr
ENGINE_HOOKED = (vr._source_lines, vr.ddf_weights)
SCORING, TEAMS = "ppr", 2


def tiny() -> dict:
    return json.loads((FIX / "tiny_inputs.json").read_text(encoding="utf-8"))


def pair(frozen, edits, base=None):
    base = base or L.base_case(frozen, SCORING)
    return base, L.edited(base, edits)


def deltas(got) -> dict:
    return {r["key"]: r["delta"] for r in got["rows"]}


class ProjectionOnlyGuardTest(unittest.TestCase):
    """The negative fixture: changed chart inputs (or weekly data passed off as
    rest of season) must not pass as a projection-only experiment."""

    @classmethod
    def setUpClass(cls):
        cls.frozen = tiny()
        cls.neg = json.loads((FIX / "negative_pairs.json").read_text(encoding="utf-8"))

    def build(self, case):
        base = L.base_case(self.frozen, self.neg["scoring"])
        pert = L.with_condition(base, **case.get("perturbed_condition", {}))
        return base, L.edited(pert, case["edits"], case.get("perturbed_horizon"))

    def test_every_disguised_change_is_refused_with_its_reason(self):
        bad = [c for c in self.neg["cases"] if c["expect"]]
        self.assertGreaterEqual(len(bad), 6)
        for case in bad:
            with self.subTest(case["name"]):
                base, pert = self.build(case)
                with self.assertRaises(L.NotProjectionOnly) as ctx:
                    L.attribute(self.frozen, self.neg["scoring"], self.neg["teams"], base, pert)
                self.assertIn(case["expect"], str(ctx.exception))

    def test_the_control_pair_is_accepted(self):
        (case,) = [c for c in self.neg["cases"] if c["expect"] is None]
        base, pert = self.build(case)
        got = L.attribute(self.frozen, self.neg["scoring"], self.neg["teams"], base, pert)
        self.assertTrue(got["rows"])

    def test_the_guard_runs_before_the_engine(self):
        case = next(c for c in self.neg["cases"] if c["expect"] and "chart input" in c["expect"])
        base, pert = self.build(case)
        with mock.patch.object(vr, "run_pipeline", side_effect=AssertionError("engine ran")):
            with self.assertRaises(L.NotProjectionOnly):
                L.attribute(self.frozen, self.neg["scoring"], self.neg["teams"], base, pert)


class AttributionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen = tiny()
        base = L.base_case(cls.frozen, SCORING)
        res, _ = L.captured_run(cls.frozen, SCORING, TEAMS, base)
        line = L._line_player(res, "p1", "TE", "waiver_line")
        cls.waiver = L.attribute(cls.frozen, SCORING, TEAMS, *pair(cls.frozen, {"p1": {line: base["natives"]["p1"][line] + 1}}))
        # Dropping Running back 3 in p1 from 14 to 8 PPG gives both flex seats to receivers.
        cls.flex_flip = L.attribute(cls.frozen, SCORING, TEAMS, *pair(cls.frozen, {"p1": {203: 8.0}}))

    def test_each_move_is_the_sum_of_its_stages_and_the_residual(self):
        for got in (self.waiver, self.flex_flip):
            for r in got["rows"]:
                parts = sum(r[c] for c in L.CHANNELS) + r["residual"]
                self.assertAlmostEqual(r["delta"], parts, places=9, msg=r["key"])

    def test_the_pairs_move_chart_ddf_through_more_than_one_stage(self):
        moved = {c for got in (self.waiver, self.flex_flip) for r in got["rows"] for c in L.CHANNELS
                 if abs(r[c]) > L.NONZERO_EPS}
        self.assertTrue({"lineup", "fill_in", "position_weight"} <= moved, moved)

    def test_a_flex_flip_is_carried_by_the_lineup_stage(self):
        b_alloc = self.flex_flip["base"][0]["allocation"]
        p_alloc = self.flex_flip["perturbed"][0]["allocation"]
        self.assertEqual((b_alloc["RB"]["starters"], b_alloc["WR"]["starters"]), (3, 3))
        self.assertEqual((p_alloc["RB"]["starters"], p_alloc["WR"]["starters"]), (2, 4))
        self.assertGreater(max(abs(r["lineup"]) for r in self.flex_flip["rows"]), 0.05)

    def test_nothing_moves_outside_the_four_stages(self):
        # Residual = chart DDF with all four stage outputs held at baseline,
        # minus baseline. Zero means the four stages are the whole route.
        for got in (self.waiver, self.flex_flip):
            self.assertEqual(max(abs(r["residual"]) for r in got["rows"]), 0.0)

    def test_hooks_restore_the_engine_and_leave_an_unfrozen_run_alone(self):
        self.assertIs(vr._source_lines, ENGINE_HOOKED[0])
        self.assertIs(vr.ddf_weights, ENGINE_HOOKED[1])
        base = L.base_case(self.frozen, SCORING)
        plain = L.chart_ddf(L.run_case(self.frozen, SCORING, TEAMS, base))
        _, stage = L.captured_run(self.frozen, SCORING, TEAMS, base)
        with L._hooks(base=stage, pert=stage, live=frozenset(L.CHANNELS)):
            hooked = L.chart_ddf(L.run_case(self.frozen, SCORING, TEAMS, base))
        self.assertEqual(plain, hooked)
        self.assertIs(vr._source_lines, ENGINE_HOOKED[0])


class ConditionTest(unittest.TestCase):
    """Source-excluded, source-held and absent-versus-zero."""

    @classmethod
    def setUpClass(cls):
        cls.frozen = tiny()
        cls.base = L.base_case(cls.frozen, SCORING)

    def waiver_edit(self, base, src="p2", pos="RB"):
        res, _ = L.captured_run(self.frozen, SCORING, TEAMS, base)
        i = L._line_player(res, src, pos, "waiver_line")
        return {src: {i: base["natives"][src][i] + 1.0}}

    def test_an_excluded_source_moves_nothing(self):
        base = L.with_condition(self.base, excluded=("p2",))
        got = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, self.waiver_edit(base), base))
        self.assertTrue(got["rows"])
        for r in got["rows"]:
            self.assertEqual([r["delta"]] + [r[c] for c in L.CHANNELS], [0.0] * (1 + len(L.CHANNELS)))

    def test_a_held_source_still_reaches_chart_ddf_exactly_as_a_visible_one(self):
        held = L.with_condition(self.base, hidden=("p2",))
        edit = self.waiver_edit(held)
        got_held = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, edit, held))
        got_seen = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, edit))
        self.assertGreater(max(abs(d) for d in deltas(got_held).values()), 0.05)
        self.assertEqual(deltas(got_held), deltas(got_seen))

    def test_listed_at_zero_keeps_a_chart_ddf_row_and_absent_removes_it(self):
        # Tight end 7: listed by p2 only (3.0 PPG) and by no chart.
        zero = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, {"p2": {407: 0.0}}))
        absent = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, {"p2": {407: None}}))
        self.assertEqual(zero["removed"], [])
        self.assertEqual(zero["perturbed_values"][407], 0.0)
        self.assertEqual(absent["removed"], [407])
        self.assertNotIn(407, absent["perturbed_values"])

    def test_zero_and_absent_differ_in_mean_points_and_chart_ddf(self):
        # Running back 5 sits on the fill-in edge. At 0.0 in p2 his mean points
        # fall to 5.0 and he leaves the fill set; absent from p2 they stay 10.0.
        zero = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, {"p2": {205: 0.0}}))
        absent = L.attribute(self.frozen, SCORING, TEAMS, *pair(self.frozen, {"p2": {205: None}}))
        self.assertEqual(zero["perturbed"][0]["mean_ppg"][205], 5.0)
        self.assertEqual(absent["perturbed"][0]["mean_ppg"][205], 10.0)
        self.assertNotIn(205, zero["perturbed"][0]["fill_sets"]["RB"])
        self.assertIn(205, absent["perturbed"][0]["fill_sets"]["RB"])
        self.assertNotEqual(deltas(zero), deltas(absent))
        self.assertGreater(max(abs(r["fill_in"]) for r in zero["rows"]), 0.0)


class DeterminismTest(unittest.TestCase):
    def test_two_runs_write_the_same_bytes(self):
        frozen = tiny()
        first = L.ledger_setting(frozen, SCORING, TEAMS)
        second = L.ledger_setting(copy.deepcopy(frozen), SCORING, TEAMS)
        self.assertGreater(len(first), 20)
        doc = lambda es: L.dump_ledger({"summary": L.summarize(es), "pairs": es})
        self.assertEqual(doc(first), doc(second))


class CommittedLedgerTest(unittest.TestCase):
    """The committed frozen inputs and ledger agree, and sampled pairs
    reproduce at the pinned engine (skipped once the engine files change)."""

    SAMPLE = ("ppr-12/waiver_line/espn/QB/+1", "standard-10/waiver_line/cbsros/WR/-1",
              "half_ppr-14/espn_zero_to_absent/espn/WR", "standard-12/source_hidden/razzball/RB/+1",
              "standard-8/source_excluded/razzball/WR/+1", "standard-14/projection_only_player_absent/all/RB")

    @classmethod
    def setUpClass(cls):
        cls.frozen = json.loads(L.FROZEN.read_text(encoding="utf-8"))
        cls.ledger = json.loads(L.LEDGER.read_text(encoding="utf-8"))
        cls.by_id = {e["id"]: e for e in cls.ledger["pairs"]}

    def test_frozen_inputs_match_their_recorded_hashes(self):
        self.assertEqual(L.sha256_bytes(L.canonical(self.frozen["scorings"])),
                         self.frozen["provenance"]["natives_sha256"])
        self.assertEqual(self.ledger["frozen_inputs"]["sha256"], L.sha256_bytes(L.FROZEN.read_bytes()))
        self.assertEqual(self.ledger["engine_sha"], L.ENGINE_SHA)
        self.assertEqual(self.frozen["provenance"]["setting_equivalence"]["max_abs_difference"], 0.0)

    def test_summary_is_the_summary_of_the_pairs(self):
        self.assertEqual(L.summarize(self.ledger["pairs"]), self.ledger["summary"])

    def test_every_pair_held_the_direct_chart_inputs(self):
        for e in self.ledger["pairs"]:
            self.assertFalse(e["direct_chart_inputs"]["changed"], e["id"])

    def test_sampled_pairs_reproduce(self):
        drift = L.engine_drift(self.frozen)
        if drift:
            self.skipTest(f"engine files changed since the pinned SHA ({', '.join(drift)}); rerun the ledger")
        for pid in self.SAMPLE:
            with self.subTest(pid):
                scoring, teams = pid.split("/")[0].rsplit("-", 1)
                found = None
                for spec, b, p, b_run in L.experiments_for(self.frozen, scoring, int(teams)):
                    if spec["id"] == pid:
                        found = L.ledger_pair(self.frozen, spec, b, p, b_run)
                        break
                self.assertIsNotNone(found, pid)
                self.assertEqual(json.loads(json.dumps(found, sort_keys=True)), self.by_id[pid])


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class JsEngineTest(unittest.TestCase):
    def test_the_production_engine_gives_the_same_moves(self):
        frozen = tiny()
        entries = L.ledger_setting(frozen, SCORING, TEAMS)
        got = L.js_cross_check(frozen, entries, settings=((SCORING, TEAMS),))
        self.assertEqual(got["status"], "ran", got)
        self.assertEqual(got["pairs"], len(entries))
        self.assertLess(got["max_abs_level_difference"], 1e-9)
        self.assertLess(got["max_abs_delta_difference"], 1e-9)


if __name__ == "__main__":
    unittest.main()
