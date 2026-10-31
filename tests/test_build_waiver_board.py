"""Offline waiver-board builder and schema (JEG-1415, slice 1 of JEG-1196).

Inputs: the JEG-1228 producer's own expected week-8 artifact
(tests/fixtures/weekly_inputs_producer/expected_wk8.json, so the board is tested
against what the producer really writes) and a hand-written DDF Value snapshot
(tests/fixtures/waiver_board/values_half_ppr_12.json). Every number asserted
below was worked out by hand from those two files, not read back from the code:

  Ann Alpha   DDF 14.25, week 7 10.0  -> change 4.25; ESPN half 12.0, Questionable, bye 10
  Fay Foxtrot DDF 3.25,  week 7 0.0   -> change 3.25 (a real zero, not missing); bye 8 = board week
  Ben Bravo   DDF 0.0 (a real zero, on the waiver line), no week-7 value -> change missing; ESPN 0.0
  Di Delta    DDF 22.0, week 7 22.0   -> change 0.0; ESPN points missing (conflicting duplicates)
  Gus Golf    priced, not in the weekly inputs -> This week all missing
  Ed Echo     in the weekly inputs, not priced -> DDF Value missing
  three weekly rows with no player_key -> listed as unresolved, never joined

The reference test builds dist/ (as `make sync` does) and checks the board passes
value_reference's own numbers through unchanged at 12-team Half PPR.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import build_waiver_board as bwb  # noqa: E402
import waiver_board as wb  # noqa: E402

BUILDER = ROOT / "pipelines" / "build_waiver_board.py"
WEEKLY = ROOT / "tests" / "fixtures" / "weekly_inputs_producer" / "expected_wk8.json"
FIX = ROOT / "tests" / "fixtures" / "waiver_board"
VALUES = FIX / "values_half_ppr_12.json"
EXPECTED = FIX / "expected_half_ppr_12.json"
INVALID_WEEKLY = ROOT / "tests" / "fixtures" / "weekly_inputs" / "invalid" / "ros_leg_id.json"
SETTING = {"scoring": "half_ppr", "teams": 12, "superflex": 0}
BUILT_AT = "2026-10-30T12:00:00Z"


def weekly() -> dict:
    return json.loads(WEEKLY.read_text(encoding="utf-8"))


def values(**setting) -> dict:
    v = json.loads(VALUES.read_text(encoding="utf-8"))
    v["setting"].update(setting)
    return v


def build(w=None, v=None, setting=None, **kw) -> dict:
    s = dict(SETTING, **(setting or {}))
    vv = v if v is not None else values(**(setting or {}))
    return bwb.build_board(w if w is not None else weekly(), vv, s, BUILT_AT, **kw)


def rows(board: dict) -> dict:
    return {r["player_key"]: r for r in board["players"]}


def run_cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BUILDER), *args], capture_output=True, text=True, cwd=str(ROOT))


class HandWorkedRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = build()
        cls.rows = rows(cls.board)

    def test_valid_and_sorted_by_value_only(self):
        self.assertEqual(wb.validate(self.board), [])
        order = [r["player_key"] for r in self.board["players"]]
        # 22.0, 14.25, 9.0, 6.5, 3.25, 0.0, then the three unpriced by player_key.
        self.assertEqual(order, [104, 101, 110, 103, 106, 102, 105, 108, 109])

    def test_value_lane(self):
        r = self.rows
        self.assertEqual(r[101]["value"]["ddf_value"], 14.25)
        self.assertAlmostEqual(r[101]["value"]["change"], 4.25)
        self.assertEqual(r[106]["value"]["prior_ddf_value"], 0.0)
        self.assertAlmostEqual(r[106]["value"]["change"], 3.25)
        self.assertEqual(r[104]["value"]["change"], 0.0)
        self.assertEqual(r[104]["value"]["missing_reason"], {})

    def test_zero_is_a_value_missing_is_null_with_reason(self):
        ben = self.rows[102]
        self.assertEqual(ben["value"]["ddf_value"], 0.0)
        self.assertNotIn("ddf_value", ben["value"]["missing_reason"])
        self.assertIsNone(ben["value"]["change"])
        self.assertEqual(ben["value"]["missing_reason"]["change"], "no DDF Value in week 7")
        self.assertEqual(ben["this_week"]["points"], 0.0)
        self.assertNotIn("points", ben["this_week"]["missing_reason"])
        ed = self.rows[105]
        self.assertIsNone(ed["value"]["ddf_value"])
        self.assertEqual(ed["value"]["missing_reason"]["ddf_value"], "not priced by DDF Value at this setting")
        self.assertEqual(ed["value"]["missing_reason"]["change"], "not priced by DDF Value at this setting")

    def test_this_week_lane(self):
        ann, di = self.rows[101]["this_week"], self.rows[104]["this_week"]
        self.assertEqual(ann["points"], 12.0)
        self.assertEqual(ann["injury_status"], "Questionable")
        self.assertEqual(ann["practice_participation"], "Limited")
        self.assertEqual((ann["bye_week"], ann["on_bye"]), (10, False))
        self.assertIsNone(di["points"])
        self.assertEqual(di["missing_reason"]["points"], "conflicting duplicate rows at the same snapshot")
        self.assertEqual((self.rows[106]["this_week"]["bye_week"], self.rows[106]["this_week"]["on_bye"]), (8, True))
        ivy = self.rows[109]["this_week"]
        self.assertIsNone(ivy["on_bye"])
        self.assertTrue(ivy["missing_reason"]["on_bye"])

    def test_value_only_row_has_no_weekly_fields(self):
        gus = self.rows[110]
        self.assertEqual(gus["value"]["ddf_value"], 9.0)
        for f in wb.WEEK_FIELDS:
            self.assertIsNone(gus["this_week"][f])
            self.assertEqual(gus["this_week"]["missing_reason"][f], "not in the weekly inputs")

    def test_unresolved_rows_are_listed_not_joined(self):
        self.assertEqual(len(self.board["unresolved"]), 3)
        self.assertTrue(all(u["unresolved_reason"] for u in self.board["unresolved"]))
        self.assertEqual(sorted(u["name"] for u in self.board["unresolved"]),
                         ["Nobody Known", "Unresolved espn_player_key 999", "Unresolved espn_row 12"])

    def test_sources_strip(self):
        s = self.board["sources"]
        for sid in ("values", "values_prior", "points", "status", "bye"):
            self.assertTrue(s[sid]["enabled"], sid)
        self.assertEqual(s["points"]["source"], "espn")
        self.assertEqual(self.board["points_leg"], "experts.espn_weekly")
        for sid, reason in (("vegas", "no Vegas producer yet (JEG-1195 slice S3)"),
                            ("experts.ecr_weekly", "no weekly ECR producer yet (JEG-1195 slice S3b)")):
            self.assertFalse(s[sid]["enabled"])
            self.assertEqual(s[sid]["disabled_reason"], reason)
        for sid in ("rostered_pct", "kickoff"):
            self.assertFalse(s[sid]["enabled"])
            self.assertEqual(s[sid]["availability"], "unavailable")
            self.assertIn("JEG-1416", s[sid]["disabled_reason"])
        self.assertFalse(self.board["sections"]["available"])
        self.assertFalse(self.board["swaps"]["available"])

    def test_every_scoring_builds(self):
        for scoring in wb.SCORINGS:
            with self.subTest(scoring=scoring):
                b = build(setting={"scoring": scoring})
                self.assertEqual(wb.validate(b), [])
        ppr = rows(build(setting={"scoring": "ppr"}))
        self.assertEqual(ppr[101]["this_week"]["points"], 13.5)
        self.assertIsNone(ppr[103]["this_week"]["points"])
        self.assertEqual(ppr[103]["this_week"]["missing_reason"]["points"], "blank in the ESPN weekly file")
        self.assertEqual(rows(build(setting={"scoring": "standard"}))[101]["this_week"]["points"], 10.5)

    def test_kicker_and_defense_are_not_priced(self):
        w = weekly()
        k = copy.deepcopy(next(r for r in w["players"] if r["player_key"] == 101))
        k.update(player_key=120, name="Kay Kilo", position="K")
        w["players"].append(k)
        kay = rows(build(w=w))[120]
        self.assertIsNone(kay["value"]["ddf_value"])
        self.assertEqual(kay["value"]["missing_reason"]["ddf_value"], "DDF Value does not price kickers or defenses")
        self.assertEqual(kay["this_week"]["points"], 12.0)


class DisabledSources(unittest.TestCase):
    def assert_disabled(self, board, sid, fields, needle):
        src = board["sources"][sid]
        self.assertFalse(src["enabled"])
        self.assertIn(needle, src["disabled_reason"])
        lane = "value" if sid.startswith("values") else "this_week"
        for r in board["players"]:
            for f in fields:
                self.assertIsNone(r[lane][f], (r["player_key"], f))
                self.assertEqual(r[lane]["missing_reason"][f], src["disabled_reason"])
        self.assertEqual(wb.validate(board), [])

    def test_stale_points_leg(self):
        w = weekly()
        leg = w["legs"]["experts.espn_weekly"]
        leg.update(content_week=6, freshness="stale", label="stale")
        b = build(w=w)
        self.assert_disabled(b, "points", ["points"], "stale (content week 6, board week 8)")

    def test_points_one_week_behind_is_not_this_weeks(self):
        w = weekly()
        w["legs"]["experts.espn_weekly"].update(content_week=7, freshness="one_week_behind")
        self.assert_disabled(build(w=w), "points", ["points"], "one week behind")

    def test_points_leg_without_the_scoring(self):
        w = weekly()
        w["legs"]["experts.espn_weekly"]["scoring"] = ["standard", "ppr"]
        self.assert_disabled(build(w=w), "points", ["points"], "has no half_ppr points")

    def test_unavailable_status_leg(self):
        w = weekly()
        w["legs"]["status"].update(availability="unavailable", freshness=None, label="unavailable",
                                   missing_reason="no status export this week")
        self.assert_disabled(build(w=w), "status", bwb.STATUS_FIELDS, "no status export this week")

    def test_bye_table_from_another_season(self):
        w = weekly()
        w["legs"]["bye"]["content_season"] = 2025
        self.assert_disabled(build(w=w), "bye", ["bye_week", "on_bye"], "season 2025 data; the board is season 2026")

    def test_values_from_last_season_are_not_shown_as_this_season(self):
        v = values()
        v["season"] = 2025
        b = build(v=v)
        self.assertEqual(b["sources"]["values"]["label"], "previous-season")
        self.assert_disabled(b, "values", ["ddf_value"], "season 2025 data; the board is season 2026")
        self.assert_disabled(b, "values_prior", ["prior_ddf_value", "change"], "DDF Value is disabled")

    def test_stale_values(self):
        v = values()
        v["content_week"], v["prior"]["week"] = 6, 5
        b = build(v=v)
        self.assertEqual(b["sources"]["values"]["freshness"], "stale")
        self.assert_disabled(b, "values", ["ddf_value"], "stale (content week 6, board week 8)")

    def test_values_one_week_behind_still_price(self):
        v = values()
        v["content_week"], v["prior"]["week"] = 7, 6
        b = build(v=v)
        self.assertTrue(b["sources"]["values"]["enabled"])
        self.assertEqual(b["sources"]["values"]["freshness"], "one_week_behind")
        self.assertEqual(rows(b)[101]["value"]["ddf_value"], 14.25)

    def test_values_for_a_later_week(self):
        v = values()
        v["content_week"], v["prior"]["week"] = 9, 8
        self.assert_disabled(build(v=v), "values", ["ddf_value"], "later than the board week 8")

    def test_prior_from_the_wrong_week(self):
        v = values()
        v["prior"]["week"] = 6
        self.assert_disabled(build(v=v), "values_prior", ["prior_ddf_value", "change"], "not week 7")

    def test_prior_unavailable(self):
        v = values()
        v["prior"] = {"available": False, "week": None, "values": {}, "missing_reason": "no history"}
        self.assert_disabled(build(v=v), "values_prior", ["prior_ddf_value", "change"], "no history")


class LanesNeverBlend(unittest.TestCase):
    def test_weekly_changes_leave_the_value_lane_alone(self):
        w = weekly()
        for r in w["players"]:
            for cell in (r["legs"]["experts.espn_weekly"]["values"],):
                for k, x in cell.items():
                    if x is not None:
                        cell[k] = x + 50.0
            r["legs"]["status"]["values"]["injury_status"] = "Out"
        a, b = rows(build()), rows(build(w=w))
        for key in a:
            self.assertEqual(a[key]["value"], b[key]["value"], key)
        self.assertNotEqual(a[101]["this_week"], b[101]["this_week"])

    def test_value_changes_leave_the_weekly_lane_alone(self):
        v = values()
        for p in v["players"].values():
            p["ddf_value"] += 7.0
        v["prior"]["values"] = {k: x - 3.0 for k, x in v["prior"]["values"].items()}
        a, b = rows(build()), rows(build(v=v))
        for key in a:
            self.assertEqual(a[key]["this_week"], b[key]["this_week"], key)
        self.assertNotEqual(a[101]["value"], b[101]["value"])


class Refusals(unittest.TestCase):
    def test_values_for_another_setting(self):
        with self.assertRaisesRegex(wb.BoardError, "values are for setting"):
            bwb.build_board(weekly(), values(), dict(SETTING, teams=10), BUILT_AT)

    def test_malformed_values(self):
        v = values()
        v["players"]["101"]["ddf_value"] = None
        with self.assertRaisesRegex(wb.BoardError, "finite ddf_value"):
            build(v=v)

    def test_unknown_points_leg(self):
        with self.assertRaisesRegex(wb.BoardError, "not in the weekly inputs"):
            build(points_leg="experts.nobody")

    def test_cli_refuses_weekly_inputs_that_fail_the_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "board.json"
            p = run_cli("--weekly-inputs", str(INVALID_WEEKLY), "--scoring", "half_ppr", "--teams", "12",
                        "--built-at", BUILT_AT, "--values", str(VALUES), "--out", str(out))
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertIn("weekly-input contract", p.stderr)
            self.assertFalse(out.exists())


class Determinism(unittest.TestCase):
    def test_cli_output_matches_the_committed_board_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for i in range(2):
                out = Path(tmp) / f"board{i}.json"
                p = run_cli("--weekly-inputs", str(WEEKLY), "--scoring", "half_ppr", "--teams", "12",
                            "--built-at", BUILT_AT, "--values", str(VALUES), "--out", str(out))
                self.assertEqual(p.returncode, 0, p.stderr)
                outs.append(out.read_bytes())
            self.assertEqual(outs[0], outs[1])
            self.assertEqual(outs[0], EXPECTED.read_bytes(),
                             "board changed: re-check the hand-worked rows, then regenerate expected_half_ppr_12.json")
        self.assertEqual(wb.validate_file(EXPECTED), [])


class ValidatorCatches(unittest.TestCase):
    def setUp(self):
        self.board = build()

    def problems(self, edit) -> list[str]:
        b = copy.deepcopy(self.board)
        edit(b)
        return wb.validate(b)

    def test_value_under_a_disabled_source(self):
        def edit(b):
            b["sources"]["points"].update(enabled=False, disabled_reason="off")
        self.assertTrue(any("source points is disabled" in p for p in self.problems(edit)))

    def test_null_with_no_reason(self):
        def edit(b):
            r = b["players"][0]["value"]
            r["ddf_value"] = None
        self.assertTrue(any("null with no reason" in p for p in self.problems(edit)))

    def test_zero_carrying_a_reason(self):
        def edit(b):
            ben = next(r for r in b["players"] if r["player_key"] == 102)
            ben["value"]["missing_reason"]["ddf_value"] = "filled"
        self.assertTrue(any("a value carrying a reason" in p for p in self.problems(edit)))

    def test_weekly_field_in_the_value_lane(self):
        def edit(b):
            b["players"][0]["value"]["points"] = 12.0
        self.assertTrue(any("needs exactly ddf_value" in p for p in self.problems(edit)))

    def test_weekly_source_feeding_a_value_field(self):
        def edit(b):
            b["sources"]["points"]["feeds"].append("ddf_value")
        self.assertTrue(any("value-lane field on a week-lane source" in p for p in self.problems(edit)))

    def test_unsorted_and_duplicate_rows(self):
        self.assertTrue(any("not sorted" in p for p in self.problems(lambda b: b["players"].reverse())))
        self.assertTrue(any("duplicate" in p for p in self.problems(lambda b: b["players"].append(b["players"][0]))))

    def test_unresolved_row_among_players(self):
        def edit(b):
            b["players"][-1]["player_key"] = None
        self.assertTrue(any("unresolved rows go in" in p for p in self.problems(edit)))

    def test_other_major_version(self):
        self.assertTrue(any("schema_version" in p for p in self.problems(lambda b: b.update(schema_version="1.0.0"))))


class FromReference(unittest.TestCase):
    """The board passes value_reference's numbers through unchanged (no pricing of its own)."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tests"))
        import _render_env
        _render_env.ensure_built()   # dist/ and its week history, as `make sync` writes them
        import value_reference as ref
        cls.ref = ref
        cls.today = date(2026, 10, 30)
        cls.snap = bwb.values_from_reference(SETTING, cls.today)

    def test_values_are_the_references_adjusted_ddf_value(self):
        ref = self.ref
        inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS, today=self.today)
        hist = ref.History(ref.HISTORY)
        wk = ref.freshness(inp)["current_week"]
        out = ref.compute(inp, SETTING, hist=hist, divergence_exclusions=ref.load_divergence_exclusions(week=wk))
        want = {str(int(k)): r["ddf_value"] for k, r in out["views"]["adj"].items()
                if r.get("ddf_value") is not None and int(k) in inp.players}
        got = {k: p["ddf_value"] for k, p in self.snap["players"].items()}
        self.assertGreater(len(got), 500)
        self.assertEqual(got, want)

    def test_board_on_reference_values(self):
        w = weekly()
        snap = copy.deepcopy(self.snap)
        b = bwb.build_board(w, snap, SETTING, BUILT_AT)
        self.assertEqual(wb.validate(b), [])
        self.assertEqual(b["sources"]["values"]["source"], "value_reference")
        self.assertTrue(b["sources"]["values_prior"]["enabled"], b["sources"]["values_prior"]["disabled_reason"])
        priced = [r for r in b["players"] if r["value"]["ddf_value"] is not None]
        for r in priced:
            v = r["value"]
            if v["change"] is not None:
                self.assertEqual(v["change"], v["ddf_value"] - v["prior_ddf_value"])
        self.assertGreater(sum(r["value"]["change"] is not None for r in priced), 300)

    def test_no_history_disables_change_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            snap = bwb.values_from_reference(SETTING, self.today, history=Path(tmp))
        self.assertFalse(snap["prior"]["available"])
        b = bwb.build_board(weekly(), snap, SETTING, BUILT_AT)
        self.assertFalse(b["sources"]["values_prior"]["enabled"])
        self.assertIn("no week", b["sources"]["values_prior"]["disabled_reason"])

    def test_cli_from_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, vout = Path(tmp) / "board.json", Path(tmp) / "values.json"
            p = run_cli("--weekly-inputs", str(WEEKLY), "--scoring", "ppr", "--teams", "10", "--superflex", "1",
                        "--built-at", BUILT_AT, "--from-reference", "--out", str(out), "--values-out", str(vout))
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(wb.validate_file(out), [])
            snap = json.loads(vout.read_text(encoding="utf-8"))
            self.assertEqual(snap["setting"], {"scoring": "ppr", "teams": 10, "superflex": 1})
            # The saved snapshot rebuilds the same board.
            p2 = run_cli("--weekly-inputs", str(WEEKLY), "--scoring", "ppr", "--teams", "10", "--superflex", "1",
                         "--built-at", BUILT_AT, "--values", str(vout), "--out", str(Path(tmp) / "again.json"))
            self.assertEqual(p2.returncode, 0, p2.stderr)
            a = json.loads(out.read_text(encoding="utf-8"))
            again = json.loads((Path(tmp) / "again.json").read_text(encoding="utf-8"))
            self.assertEqual(a["players"], again["players"])
            self.assertEqual(a["sources"], again["sources"])


if __name__ == "__main__":
    unittest.main()
