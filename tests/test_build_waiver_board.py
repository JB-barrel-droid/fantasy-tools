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

    def test_priced_zero_sorts_ahead_of_unpriced_with_a_lower_key(self):
        # Missing is not zero: a priced 0.0 with key 200 sorts above unpriced 105, 108, 109.
        v = values()
        v["players"]["200"] = {"name": "Zed Zero", "position": "WR", "team": "NYJ", "ddf_value": 0.0}
        order = [r["player_key"] for r in build(v=v)["players"]]
        self.assertEqual(order, [104, 101, 110, 103, 106, 102, 200, 105, 108, 109])

    def test_on_bye_follows_the_board_week(self):
        # A week-9 board: Fay's bye 8 is past, a player whose bye is 9 is on bye.
        w = weekly()
        w["content_week"] = 9
        for leg_id in ("experts.espn_weekly", "status"):
            w["legs"][leg_id]["content_week"] = 9
        ann = next(r for r in w["players"] if r["player_key"] == 101)
        ann["legs"]["bye"]["values"]["bye_week"] = 9
        b = build(w=w)
        self.assertEqual(wb.validate(b), [])
        r = rows(b)
        self.assertEqual((r[101]["this_week"]["bye_week"], r[101]["this_week"]["on_bye"]), (9, True))
        self.assertEqual((r[106]["this_week"]["bye_week"], r[106]["this_week"]["on_bye"]), (8, False))
        self.assertEqual(b["sources"]["values"]["freshness"], "one_week_behind")

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
        self.assertEqual(b["sources"]["values"]["label"], "stale")
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


    def test_stale_status_leg(self):
        w = weekly()
        w["legs"]["status"].update(content_week=6, freshness="stale", label="stale")
        self.assert_disabled(build(w=w), "status", bwb.STATUS_FIELDS, "status is stale (content week 6, board week 8)")

    def test_status_one_week_behind_is_not_this_weeks(self):
        w = weekly()
        w["legs"]["status"].update(content_week=7, freshness="one_week_behind")
        self.assert_disabled(build(w=w), "status", bwb.STATUS_FIELDS, "status is one week behind")

    def test_points_of_unknown_age(self):
        w = weekly()
        w["legs"]["experts.espn_weekly"].update(content_week=None, freshness="unknown", label="modeled")
        self.assert_disabled(build(w=w), "points", ["points"], "of unknown age (content week unknown, board week 8)")

    def test_weekly_inputs_without_status_or_bye_legs(self):
        # The weekly-input contract allows a file without these legs; the board declares them unavailable.
        w = weekly()
        del w["legs"]["status"], w["legs"]["bye"]
        for r in w["players"]:
            r["legs"].pop("status", None)
            r["legs"].pop("bye", None)
        b = build(w=w)
        self.assertEqual(b["sources"]["status"]["availability"], "unavailable")
        self.assertIsNone(b["sources"]["status"]["freshness"])
        self.assert_disabled(b, "status", bwb.STATUS_FIELDS, "the status leg is not in the weekly inputs")
        self.assert_disabled(b, "bye", ["bye_week", "on_bye"], "the bye leg is not in the weekly inputs")
        self.assertTrue(b["sources"]["points"]["enabled"])
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "weekly.json", Path(tmp) / "board.json"
            src.write_text(json.dumps(w), encoding="utf-8")
            p = run_cli("--weekly-inputs", str(src), "--scoring", "half_ppr", "--teams", "12",
                        "--built-at", BUILT_AT, "--values", str(VALUES), "--out", str(out))
            self.assertEqual(p.returncode, 0, p.stderr)   # the contract accepts the file; so does the board
            self.assertEqual(wb.validate_file(out), [])

    def test_values_from_a_later_season(self):
        v = values()
        v["season"] = 2027
        b = build(v=v)
        self.assertEqual(b["sources"]["values"]["label"], "stale")
        self.assert_disabled(b, "values", ["ddf_value"], "season 2027 data; the board is season 2026")

    def test_empty_snapshots_still_build_honest_boards(self):
        for season, week, prior_week in ((2025, 8, 7), (2026, 9, 8), (2026, 8, 5)):
            with self.subTest(season=season, week=week, prior_week=prior_week):
                v = values()
                v["season"], v["content_week"], v["prior"]["week"] = season, week, prior_week
                v["players"] = {}
                b = build(v=v)
                self.assertEqual(wb.validate(b), [])
                self.assertEqual(b["sources"]["values"]["label"], "unavailable")
                self.assertFalse(b["sources"]["values_prior"]["enabled"])

    def test_values_input_pricing_nobody(self):
        v = values()
        v["players"] = {}
        b = build(v=v)
        self.assertEqual(b["sources"]["values"]["availability"], "unavailable")
        self.assertIsNone(b["sources"]["values"]["freshness"])
        self.assert_disabled(b, "values", ["ddf_value"], "prices no player")


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

    def test_snapshot_label_and_source(self):
        for label in ("unavailable", "previous-season"):
            v = values()
            v["label"] = label
            with self.assertRaisesRegex(wb.BoardError, "label must be one of"):
                build(v=v)
        v = values()
        del v["source"]
        with self.assertRaisesRegex(wb.BoardError, "has no source"):
            build(v=v)

    def test_snapshot_view_and_series(self):
        for k, other in (("view", "native"), ("series", "ddf_chart")):
            v = values()
            v[k] = other
            with self.assertRaisesRegex(wb.BoardError, "the board takes view 'adj' series 'ddf_value'"):
                build(v=v)

    def test_values_keys_and_setting_written_one_way(self):
        v = values()
        v["players"]["0101"] = v["players"].pop("101")
        with self.assertRaisesRegex(wb.BoardError, "integer player_key"):
            build(v=v)
        v = values()
        v["setting"]["superflex"] = False
        with self.assertRaisesRegex(wb.BoardError, "values are for setting"):
            build(v=v)
        with self.assertRaisesRegex(wb.BoardError, "superflex 0 or 1"):
            bwb.build_board(weekly(), values(), dict(SETTING, superflex=True), BUILT_AT)

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

    def test_missing_lane_field_is_reported_not_raised(self):
        for lane, f in (("value", "change"), ("value", "ddf_value"), ("this_week", "bye_week"),
                        ("this_week", "on_bye")):
            def edit(b, lane=lane, f=f):
                del b["players"][0][lane][f]
            got = self.problems(edit)
            self.assertTrue(any(f"$.players[0].{lane}: needs exactly" in p for p in got), (lane, f, got))

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

    def assert_caught(self, edit, needle):
        problems = self.problems(edit)
        self.assertTrue(any(needle in p for p in problems), problems)

    # The enable rule, re-derived: a hand-edited board cannot turn old or foreign data on.
    def test_enabled_stale_values(self):
        self.assert_caught(lambda b: b["sources"]["values"].update(freshness="stale", label="stale"),
                           "enabled only when current or one week behind")

    def test_enabled_values_from_another_season(self):
        self.assert_caught(lambda b: b["sources"]["values"].update(content_season=2025, label="previous-season"),
                           "enabled with season 2025 content")

    def test_enabled_values_for_a_later_week(self):
        self.assert_caught(lambda b: b["sources"]["values"].update(content_week=9), "enabled with week 9 content")

    def test_values_freshness_that_its_weeks_contradict(self):
        def edit(b):
            b["sources"]["values"]["content_week"] = 3
            b["sources"]["values_prior"]["content_week"] = 2
        self.assert_caught(edit, "freshness: current disagrees with its weeks (expected stale)")
        self.assert_caught(lambda b: b["sources"]["values"].update(freshness="one_week_behind"),
                           "disagrees with its weeks (expected current)")

    def test_validator_freshness_rule_is_the_contracts(self):
        import weekly_inputs_contract as wic
        for wk in (None, 1, 6, 7, 8, 9):
            self.assertEqual(wb.freshness_for_weeks(8, wk), wic.freshness_for_weeks(8, wk), wk)

    def test_prior_not_the_week_before(self):
        self.assert_caught(lambda b: b["sources"]["values_prior"].update(content_week=6),
                           "the prior DDF Value is the week before")

    def test_change_dropped_although_both_sides_are_there(self):
        def edit(b):
            ann = rows(b)[101]["value"]
            ann["change"] = None
            ann["missing_reason"]["change"] = "dropped"
        self.assert_caught(edit, "change: missing although")

    def test_on_bye_missing_while_bye_week_is_there(self):
        def edit(b):
            ann = rows(b)[101]["this_week"]
            ann["on_bye"] = None
            ann["missing_reason"]["on_bye"] = "dropped"
        self.assert_caught(edit, "on_bye: present exactly when bye_week is")

    def test_unavailable_label_both_ways(self):
        self.assert_caught(lambda b: b["sources"]["rostered_pct"].update(label="published"),
                           "labelled unavailable exactly when")
        self.assert_caught(lambda b: b["sources"]["status"].update(label="unavailable"),
                           "labelled unavailable exactly when")

    def test_previous_season_label_on_this_seasons_content(self):
        self.assert_caught(lambda b: b["sources"]["values"].update(label="previous-season"),
                           "previous-season is only for content from a season before 2026")

    def test_enabled_points_one_week_behind(self):
        self.assert_caught(lambda b: b["sources"]["points"].update(freshness="one_week_behind", content_week=7),
                           "enabled only when current")

    def test_enabled_prior_without_values(self):
        def edit(b):
            b["sources"]["values"].update(enabled=False, disabled_reason="off")
            for r in b["players"]:
                r["value"]["ddf_value"] = None
                r["value"]["missing_reason"]["ddf_value"] = "off"
        self.assert_caught(edit, "enabled only with DDF Value")

    def test_stale_labelled_published(self):
        self.assert_caught(lambda b: b["sources"]["vegas"].update(availability="complete", freshness="stale",
                                                                  label="published"),
                           "stale content is labelled stale")

    def test_previous_season_labelled_published(self):
        self.assert_caught(lambda b: b["sources"]["bye"].update(content_season=2025, label="published"),
                           "is not published")

    def test_freshness_null_on_a_source_with_data(self):
        self.assert_caught(lambda b: b["sources"]["status"].update(freshness=None), "null exactly when")

    def test_listed_leg_turned_on(self):
        self.assert_caught(lambda b: b["sources"]["vegas"].update(enabled=True, disabled_reason=None),
                           "only values, values_prior, points, status, bye can be enabled")

    def test_unavailable_source_enabled(self):
        self.assert_caught(lambda b: b["sources"]["rostered_pct"].update(enabled=True, disabled_reason=None),
                           "an unavailable source cannot be enabled")

    def test_empty_disabled_reason(self):
        self.assert_caught(lambda b: b["sources"]["vegas"].update(disabled_reason=" "), "not a non-empty string")

    def test_feeds_not_matching_the_source(self):
        self.assert_caught(lambda b: b["sources"]["status"].update(feeds=["status"]),
                           "status feeds status, injury_status, practice_participation")

    # Rows, internally consistent.
    def test_change_not_ddf_minus_prior(self):
        self.assert_caught(lambda b: rows(b)[101]["value"].update(change=5.0), "is not DDF Value minus")

    def test_change_with_a_missing_side(self):
        def edit(b):
            ed = rows(b)[105]["value"]
            ed["change"] = 1.0
            del ed["missing_reason"]["change"]
        self.assert_caught(edit, "a change needs both")

    def test_on_bye_disagreeing_with_bye_week(self):
        self.assert_caught(lambda b: rows(b)[101]["this_week"].update(on_bye=True), "disagrees with bye_week 10")

    def test_on_bye_not_a_boolean(self):
        self.assert_caught(lambda b: rows(b)[106]["this_week"].update(on_bye=1), "on_bye: not a boolean")

    def test_bye_week_out_of_range(self):
        self.assert_caught(lambda b: rows(b)[101]["this_week"].update(bye_week=20), "bye_week: not a week")

    def test_status_not_a_string(self):
        self.assert_caught(lambda b: rows(b)[101]["this_week"].update(injury_status=3), "not a string")

    def test_points_not_finite(self):
        self.assert_caught(lambda b: rows(b)[101]["this_week"].update(points=float("inf")), "not a finite number")

    def test_reason_on_a_field_the_lane_does_not_have(self):
        self.assert_caught(lambda b: rows(b)[101]["value"]["missing_reason"].update(points="x"),
                           "not a field of this lane")

    def test_empty_reason(self):
        self.assert_caught(lambda b: rows(b)[104]["this_week"]["missing_reason"].update(points=""),
                           "not a non-empty string")

    def test_disabled_source_field_with_another_reason(self):
        def edit(b):
            b["sources"]["status"].update(enabled=False, disabled_reason="off")
            for r in b["players"]:
                for f in bwb.STATUS_FIELDS:
                    r["this_week"][f] = None
                    r["this_week"]["missing_reason"][f] = "off"
            rows(b)[101]["this_week"]["missing_reason"]["status"] = "something else"
        self.assert_caught(edit, "not source status's disabled reason")

    # The header.
    def test_inputs_not_an_object(self):
        self.assert_caught(lambda b: b.update(inputs=[]), "$.inputs: not an object")

    def test_built_at_without_a_zone(self):
        self.assert_caught(lambda b: b.update(built_at="2026-10-30T12:00:00"), "$.built_at")

    def test_empty_producer(self):
        self.assert_caught(lambda b: b.update(producer=""), "$.producer")

    def test_superflex_true_is_not_one(self):
        self.assert_caught(lambda b: b["setting"].update(superflex=True), "superflex: not 0 or 1")

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
        sys.path.insert(0, str(ROOT))
        from tests.test_connector_analyses import run_edge
        cls.edge = run_edge(("half_ppr", 12, 0))   # get-values' own pipeline.ts, the engine's twin

    def test_matches_get_values_at_12_team_half_ppr(self):
        # An independent read-back: get-values (TypeScript) serves the same week and the same prior pair.
        edge_prior = self.edge["prior"]
        self.assertTrue(edge_prior["available"], edge_prior["reason"])
        self.assertEqual(self.snap["content_week"], self.edge["week"]["week"])
        self.assertEqual(self.snap["content_week"], edge_prior["current_week"])
        self.assertEqual(self.snap["prior"]["week"], edge_prior["prior_week"])
        pair = edge_prior["series"]["ddf_value"]
        got_now = {k: p["ddf_value"] for k, p in self.snap["players"].items()}
        for got, want in ((got_now, pair["current_values"]), (self.snap["prior"]["values"], pair["values"])):
            self.assertEqual(set(got), set(want))
            self.assertGreater(len(got), 500)
            for k in got:
                self.assertAlmostEqual(got[k], want[k], places=6, msg=k)

    def test_week_is_the_served_week_not_the_build_day(self):
        # Built a week after the history's newest week: still the week the reference priced.
        later = bwb.values_from_reference(SETTING, date(2026, 11, 6))
        self.assertEqual((later["content_week"], later["prior"]["week"]),
                         (self.snap["content_week"], self.snap["prior"]["week"]))
        b = bwb.build_board(weekly(), later, SETTING, BUILT_AT)
        self.assertTrue(b["sources"]["values"]["enabled"], b["sources"]["values"]["disabled_reason"])
        self.assertEqual(b["sources"]["values"]["freshness"], "current")
        with tempfile.TemporaryDirectory() as tmp:
            nohist = bwb.values_from_reference(SETTING, date(2026, 11, 6), history=Path(tmp))
        self.assertEqual(nohist["content_week"], self.snap["content_week"])   # the charts' week, not week 9

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
            board = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(board["inputs"]["values"]["sha256"], bwb._sha256(vout.read_bytes()))
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
