"""Opt-in local swaps: saved artifact, shared-rule replay and clean CLI refusal."""
from __future__ import annotations

import copy
from decimal import Decimal
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import test_build_waiver_board as base
import waiver_board_swaps as swaps


def request():
    return {
        "setting": dict(base.SETTING),
        "roster_keys": [104, 102, 101, 103, 106], "wire_keys": [110],
        "wire_overrides": {"add": [], "remove": []},
        "context": {
            "shape": {"QB": 1, "RB": 1, "WR": 1, "TE": 1, "FLEX": 0, "SUPERFLEX": 0, "BENCH": 1},
            "expected": {p: {"lo": 1, "hi": 2} for p in ("QB", "RB", "WR", "TE")},
            "weights": {"QB": .1, "RB": .2, "WR": .2, "TE": .1},
        },
        # A test-supplied policy, never a production default.
        "gain_policy": {"minimum": 1, "comparison": "gte"},
    }


class SwapArtifact(unittest.TestCase):
    def setUp(self):
        self.values = base.values()
        self.values["players"]["102"]["ddf_value"] = 10
        self.request = request()

    def build(self, req=None, **kwargs):
        return base.build(v=self.values, swap_request=self.request if req is None else req, **kwargs)

    def test_hand_worked_rows_and_no_changes_to_either_value_lane(self):
        plain = base.build(v=self.values)
        board = self.build()
        self.assertEqual(board["schema_version"], "0.2.0")
        self.assertTrue(board["swaps"]["available"])
        self.assertEqual(board["swaps"]["rows"], [{"add": 110, "drop": 106, "gain": 5.75}])
        self.assertEqual(board["swaps"]["request"], self.request)
        for field in ("players", "sources", "unresolved", "sections", "setting"):
            self.assertEqual(board[field], plain[field])
        self.assertEqual(base.wb.validate(board), [])

    def test_default_remains_byte_identical_and_does_not_need_node(self):
        expected = json.loads(base.EXPECTED.read_text())
        with mock.patch.object(swaps.subprocess, "run", side_effect=AssertionError("Node not needed")):
            board = base.bwb.build_board(base.weekly(), base.values(), base.SETTING, base.BUILT_AT,
                                         inputs=expected["inputs"])
            self.assertEqual(base.bwb.dumps(board), base.EXPECTED.read_text())
            self.assertEqual(base.wb.validate(board), [])

    def test_exact_cutoff_boundary_is_supplied_by_caller(self):
        self.request["gain_policy"] = {"minimum": 5.75, "comparison": "gt"}
        self.assertEqual(self.build()["swaps"]["rows"], [])
        self.request["gain_policy"]["comparison"] = "gte"
        self.assertEqual(self.build()["swaps"]["rows"][0]["gain"], 5.75)

    def test_decimal_policy_boundaries_match_an_independent_decimal_oracle(self):
        pairs = [(3.35, 3.25, .1), (3.55, 3.25, .3),
                 (3.3500000001, 3.25, .1), (3.3499999999, 3.25, .1),
                 (1e-7, 9e-8, 1e-8)]
        for arriving, departing, minimum in pairs:
            exact_gain = Decimal(str(arriving)) - Decimal(str(departing))
            for comparison in ("gt", "gte"):
                with self.subTest(arriving=arriving, departing=departing, comparison=comparison):
                    self.values["players"]["106"]["ddf_value"] = departing
                    self.values["players"]["110"]["ddf_value"] = arriving
                    self.request["gain_policy"] = {"minimum": minimum, "comparison": comparison}
                    board = self.build()
                    accepted = exact_gain > Decimal(str(minimum)) if comparison == "gt" else exact_gain >= Decimal(str(minimum))
                    expected = [{"add": 110, "drop": 106, "gain": float(exact_gain)}] if accepted else []
                    self.assertEqual(board["swaps"]["rows"], expected)
                    self.assertEqual(base.wb.validate(board), [])

    def test_validator_refuses_a_swap_at_a_strict_decimal_equality_boundary(self):
        self.values["players"]["106"]["ddf_value"] = 3.25
        self.values["players"]["110"]["ddf_value"] = 3.35
        self.request["gain_policy"] = {"minimum": .1, "comparison": "gt"}
        board = self.build()
        self.assertEqual(board["swaps"]["rows"], [])
        board["swaps"]["rows"] = [{"add": 110, "drop": 106, "gain": .1}]
        self.assertTrue(base.wb.validate(board))

    def test_missing_and_unsupported_candidate_positions_never_produce_swap_rows(self):
        for position in (None, "FB", "FLEX", "rb"):
            with self.subTest(position=position):
                self.values["players"]["110"]["position"] = position
                board = self.build()
                self.assertEqual(board["swaps"]["rows"], [])
                self.assertEqual(base.wb.validate(board), [])
                board["swaps"]["rows"] = [{"add": 110, "drop": 106, "gain": 5.75}]
                self.assertTrue(base.wb.validate(board))

    def test_overrides_and_unknown_wire_keys_are_serialized(self):
        self.request["wire_overrides"] = {"add": [105, 999], "remove": [110]}
        block = self.build()["swaps"]
        self.assertEqual(block["rows"], [])
        self.assertEqual(block["unresolved_wire_keys"], [999])

    def test_unknown_roster_and_partial_roster_have_explicit_reasons(self):
        self.request["roster_keys"].append(999)
        block = self.build()["swaps"]
        self.assertFalse(block["available"])
        self.assertIn("999", block["missing_reason"])
        self.request["roster_keys"] = [104]
        block = self.build()["swaps"]
        self.assertFalse(block["available"])
        self.assertIn("complete starting roster", block["missing_reason"])

    def test_stale_values_disable_swaps_with_the_source_reason(self):
        self.values["content_week"] = 3
        board = self.build()
        self.assertFalse(board["sources"]["values"]["enabled"])
        self.assertFalse(board["swaps"]["available"])
        self.assertEqual(board["swaps"]["missing_reason"], board["sources"]["values"]["disabled_reason"])
        self.assertEqual(base.wb.validate(board), [])

    def test_validator_replays_gain_identity_order_and_depth(self):
        good = self.build()
        mutations = {
            "wrong gain": lambda b: b["swaps"]["rows"][0].update(gain=9),
            "starter drop": lambda b: b["swaps"]["rows"][0].update(drop=104),
            "already owned add": lambda b: b["swaps"]["rows"][0].update(add=101),
            "reused player": lambda b: b["swaps"]["rows"].append(copy.deepcopy(b["swaps"]["rows"][0])),
            "false unknown wire": lambda b: b["swaps"].update(unresolved_wire_keys=[999]),
            "bench became starter": lambda b: b["swaps"]["request"]["context"]["shape"].update(WR=2, BENCH=0),
            "policy violation": lambda b: b["swaps"]["request"]["gain_policy"].update(minimum=100),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                bad = copy.deepcopy(good)
                mutate(bad)
                self.assertTrue(base.wb.validate(bad))

    def test_a_cross_position_swap_cannot_thin_the_dropped_position(self):
        self.values["players"]["110"]["position"] = "RB"
        self.request["context"]["expected"]["WR"] = {"lo": 2, "hi": 2}
        self.assertEqual(self.build()["swaps"]["rows"], [])

    def test_two_move_artifact_preserves_shared_order_and_single_use(self):
        self.values["players"].update({
            "111": {"name": "Bench TE", "position": "TE", "team": "AAA", "ddf_value": 2},
            "112": {"name": "Arriving RB", "position": "RB", "team": "BBB", "ddf_value": 12},
        })
        self.request["context"]["shape"]["BENCH"] = 2
        self.request["roster_keys"].append(111)
        self.request["wire_keys"].append(112)
        board = self.build()
        self.assertEqual(board["swaps"]["rows"], [
            {"add": 112, "drop": 111, "gain": 10}, {"add": 110, "drop": 106, "gain": 5.75},
        ])
        board["swaps"]["rows"].reverse()
        self.assertTrue(base.wb.validate(board))

    def test_validator_refuses_malformed_blocks_without_crashing(self):
        good = self.build()
        for value in (None, [], {}, {"available": True}, {**good["swaps"], "rows": [None]},
                      {**good["swaps"], "rows": [{"add": True, "drop": 106, "gain": 1}]},
                      {**good["swaps"], "available": "yes"}):
            with self.subTest(value=value):
                bad = copy.deepcopy(good)
                bad["swaps"] = value
                self.assertTrue(base.wb.validate(bad))

    def test_populated_swaps_require_the_opt_in_minor_version(self):
        board = self.build()
        board["schema_version"] = "0.1.0"
        self.assertTrue(base.wb.validate(board))
        board["schema_version"] = "0.3.0"
        self.assertTrue(base.wb.validate(board))

    def test_missing_node_refuses_an_opt_in_build(self):
        with mock.patch.object(swaps.subprocess, "run", side_effect=FileNotFoundError("node missing")):
            with self.assertRaisesRegex(base.wb.BoardError, "could not run"):
                self.build()

    def test_cli_provenance_and_deterministic_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            value_path, req_path, out = root / "values.json", root / "request.json", root / "board.json"
            value_path.write_text(json.dumps(self.values))
            req_bytes = (json.dumps(self.request, indent=2) + "\n").encode()
            req_path.write_bytes(req_bytes)
            args = ("--weekly-inputs", str(base.WEEKLY), "--values", str(value_path),
                    "--scoring", "half_ppr", "--teams", "12", "--built-at", base.BUILT_AT,
                    "--swap-request", str(req_path), "--out", str(out))
            first = base.run_cli(*args)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = out.read_bytes()
            board = json.loads(before)
            self.assertEqual(board["inputs"]["swap_request"],
                             {"name": "request.json", "sha256": hashlib.sha256(req_bytes).hexdigest()})
            self.assertEqual(board["swaps"]["rows"], [{"add": 110, "drop": 106, "gain": 5.75}])
            self.assertEqual(base.wb.validate(board), [])
            second = base.run_cli(*args)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(out.read_bytes(), before)

    def test_cli_missing_policy_or_null_request_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            req_path, out = root / "request.json", root / "board.json"
            out.write_bytes(b"keep this existing file")
            for invalid in ({k: v for k, v in self.request.items() if k != "gain_policy"}, None):
                req_path.write_text(json.dumps(invalid))
                result = base.run_cli("--weekly-inputs", str(base.WEEKLY), "--values", str(base.VALUES),
                                      "--scoring", "half_ppr", "--teams", "12", "--built-at", base.BUILT_AT,
                                      "--swap-request", str(req_path), "--out", str(out))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("refused, nothing written", result.stderr)
                self.assertEqual(out.read_bytes(), b"keep this existing file")


class RequestBoundary(unittest.TestCase):
    def test_malformed_context_and_policy_are_refused_without_node(self):
        changes = [
            ("wire_keys", [True]), ("roster_keys", [104, 104]), ("wire_keys", [2**53]),
            ("gain_policy", None), ("gain_policy", {"minimum": True, "comparison": "gte"}),
            ("gain_policy", {"minimum": float("nan"), "comparison": "gt"}),
            ("gain_policy", {"minimum": 1, "comparison": "unknown"}),
            ("gain_policy", {"minimum": 10**1000, "comparison": "gt"}),
            ("context", None), ("context", {"shape": {}, "expected": {}, "weights": {}}),
            ("context", {**request()["context"], "weights": {"WR": .2}}),
            ("context", {**request()["context"], "rosterSize": True}),
            ("wire_overrides", {"add": [110], "remove": [110]}),
            ("setting", {**base.SETTING, "superflex": False}),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                req = request()
                req[field] = value
                self.assertTrue(swaps.validate_request(req, base.SETTING))


if __name__ == "__main__":
    unittest.main()
