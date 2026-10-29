"""JEG-1228: offline weekly-input producer (pipelines/build_weekly_inputs.py).

Fails before the change: the producer did not exist. Every input here is a
committed fixture or a temp file; no network, Supabase or wall clock.
"""
from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import build_weekly_inputs as bwi  # noqa: E402

try:
    import weekly_inputs_contract as CONTRACT  # JEG-1227
except ImportError:
    CONTRACT = None

FX = ROOT / "tests" / "fixtures" / "weekly_inputs_producer"
AS_OF = "2026-10-29T02:00:00Z"
HEADER = "season,week,player_key,pos,team,std,half_ppr,ppr,snapshot_at,pre_kickoff,basis\n"


def _args(out, **over):
    base = {"season": 2026, "week": 8, "as_of": AS_OF, "out": out,
            "espn_weekly": FX / "espn_weekly.csv", "status": FX / "status.json",
            "byes": FX / "byes.json", "players": FX / "players.json",
            "sleeper_base": FX / "sleeper_base.json"}
    base.update(over)
    argv = ["--season", str(base["season"]), "--week", str(base["week"]),
            "--as-of", base["as_of"], "--out", str(base["out"])]
    for flag in ("espn_weekly", "status", "byes", "players", "sleeper_base"):
        if base[flag] is not None:
            argv += ["--" + flag.replace("_", "-"), str(base[flag])]
    return argv


def _run(argv):
    err, out = io.StringIO(), io.StringIO()
    with redirect_stderr(err), redirect_stdout(out):
        code = bwi.main(argv)
    return code, err.getvalue()


class ProducerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "inputs-wk8.json"

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, **over):
        code, err = _run(_args(self.out, **over))
        self.assertEqual(code, 0, err)
        return json.loads(self.out.read_text())

    def write(self, name, text):
        p = self.dir / name
        p.write_text(text)
        return p

    def row(self, doc, key):
        return next(r for r in doc["players"] if r["player_key"] == key)


class GoldenAndDeterminism(ProducerCase):
    def test_fixture_run_matches_committed_golden_bytes(self):
        self.build()
        self.assertEqual(self.out.read_text(), (FX / "expected_wk8.json").read_text())

    def test_repeat_run_is_byte_stable_and_ignores_the_wall_clock(self):
        self.build()
        first = self.out.read_bytes()
        with mock.patch.dict(os.environ, {"DDF_NOW": "2026-12-25T12:00:00Z"}):
            self.build()
        self.assertEqual(self.out.read_bytes(), first)

    def test_row_order_of_inputs_does_not_change_rows(self):
        lines = (FX / "espn_weekly.csv").read_text().splitlines(keepends=True)
        shuffled = self.write("espn.csv", lines[0] + "".join(reversed(lines[1:])))
        status = json.loads((FX / "status.json").read_text())
        rstatus = self.write("status.json", json.dumps(list(reversed(status))))
        a = self.build()
        b = self.build(espn_weekly=shuffled, status=rstatus)
        # Only the inputs' hashes may differ; the "espn_row" id of the
        # key-less row is its line number, which moves with the shuffle.
        for doc in (a, b):
            for meta in doc["legs"].values():
                meta["inputs"] = []
            for r in doc["players"]:
                if r["source_ids"].pop("espn_row", None) is not None:
                    r["name"] = "Unresolved espn_row"
        self.assertEqual(a, b)

    def test_no_network(self):
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.build()


class Values(ProducerCase):
    def test_latest_snapshot_wins_and_other_weeks_seasons_are_left_out(self):
        doc = self.build()
        cell = self.row(doc, 101)["legs"]["experts.espn_weekly"]
        self.assertEqual(cell["values"], {"standard": 10.5, "half_ppr": 12.0, "ppr": 13.5})
        meta = doc["legs"]["experts.espn_weekly"]
        self.assertEqual((meta["content_vintage"], meta["captured_at"]), ("2026-10-28", "2026-10-28T12:40:00Z"))
        rep = doc["input_report"]["experts.espn_weekly"]
        self.assertEqual((rep["wrong_week"], rep["wrong_season"], rep["after_as_of"]), (1, 1, 1))

    def test_zero_is_a_value_not_missing(self):
        cell = self.row(self.build(), 102)["legs"]["experts.espn_weekly"]
        self.assertEqual(cell["values"], {"standard": 0.0, "half_ppr": 0.0, "ppr": 0.0})
        self.assertEqual(cell["provenance"], "complete")
        self.assertNotIn("missing_reason", cell)

    def test_partial_row_is_kept_with_null_scoring(self):
        doc = self.build()
        cell = self.row(doc, 103)["legs"]["experts.espn_weekly"]
        self.assertEqual(cell["values"], {"standard": 6.2, "half_ppr": 7.1, "ppr": None})
        self.assertEqual(cell["provenance"], "partial")
        self.assertEqual(cell["missing_reason"], {"ppr": "blank in the ESPN weekly file"})
        self.assertEqual(doc["legs"]["experts.espn_weekly"]["availability"], "partial")

    def test_conflicting_duplicates_give_null_and_reason(self):
        doc = self.build()
        cell = self.row(doc, 104)["legs"]["experts.espn_weekly"]
        self.assertEqual(set(cell["values"].values()), {None})
        self.assertIn("conflicting", cell["missing_reason"]["standard"])
        self.assertEqual(doc["input_report"]["experts.espn_weekly"]["conflict"], 1)

    def test_all_blank_row_is_missing_not_zero(self):
        cell = self.row(self.build(), 105)["legs"]["experts.espn_weekly"]
        self.assertEqual(set(cell["values"].values()), {None})
        self.assertEqual(cell["provenance"], "missing")
        self.assertEqual(cell["missing_reason"]["ppr"], "blank in the ESPN weekly file")

    def test_unresolved_players_stay_in_with_reason(self):
        doc = self.build()
        unresolved = [r for r in doc["players"] if r["player_key"] is None]
        reasons = sorted(r["unresolved_reason"] for r in unresolved)
        self.assertEqual(len(unresolved), 3)
        self.assertIn("player_key 999 not in players snapshot", reasons)
        self.assertIn("espn row has no player_key", reasons)
        self.assertTrue(any(x.startswith("unresolved: name") for x in reasons))
        self.assertEqual(doc["players"][-3:], unresolved)  # resolved rows first, then by name
        self.assertEqual([r["name"] for r in unresolved], sorted(r["name"] for r in unresolved))
        self.assertEqual(doc["input_report"]["unresolved_rows"], 3)

    def test_missing_legs_are_null_with_reason_never_fabricated(self):
        doc = self.build()
        for r in doc["players"]:
            for leg in ("experts.ecr_weekly", "vegas"):
                self.assertEqual(r["legs"][leg], {"provenance": "missing", "values": {
                    "standard": None, "half_ppr": None, "ppr": None}})
        for leg in ("experts.ecr_weekly", "vegas"):
            meta = doc["legs"][leg]
            self.assertEqual((meta["availability"], meta["freshness"], meta["label"]),
                             ("unavailable", None, "unavailable"))
            self.assertTrue(meta["missing_reason"])


class StatusAndByes(ProducerCase):
    def test_latest_status_snapshot_in_week_on_or_before_as_of(self):
        doc = self.build()
        cell = self.row(doc, 101)["legs"]["status"]
        self.assertEqual(cell["values"]["injury_status"], "Questionable")
        meta = doc["legs"]["status"]
        self.assertEqual((meta["content_vintage"], meta["captured_at"]), ("2026-10-28", "2026-10-28T13:10:05Z"))

    def test_status_from_a_later_content_week_is_wrong_week(self):
        doc = self.build(as_of="2026-11-04T02:00:00Z")
        self.assertEqual(self.row(doc, 101)["legs"]["status"]["values"]["injury_status"], "Questionable")
        self.assertEqual(doc["input_report"]["status"]["later_content_week"], 1)

    def test_null_status_key_resolves_through_player_index(self):
        r = self.row(self.build(), 106)
        self.assertEqual(r["resolved_by"], "player_index:sleeper_id")
        self.assertEqual(r["legs"]["experts.espn_weekly"]["missing_reason"]["ppr"], "player not in this input")

    def test_two_sleeper_ids_on_one_key_is_a_conflict(self):
        cell = self.row(self.build(), 108)["legs"]["status"]
        self.assertEqual(cell["provenance"], "missing")
        self.assertEqual(cell["missing_reason"]["status"], "two sleeper ids for one player_key")

    def test_identical_duplicate_status_rows_collapse(self):
        doc = self.build()
        cell = self.row(doc, 109)["legs"]["status"]
        self.assertEqual(cell["values"]["status"], "Active")
        # Sleeper leaves injury fields unset for a healthy player: null plus a reason.
        self.assertEqual(cell["provenance"], "partial")
        self.assertEqual(cell["missing_reason"]["injury_status"], "not set in the Sleeper record")
        self.assertEqual(doc["input_report"]["status"]["duplicate"], 1)

    def test_byes(self):
        doc = self.build()
        self.assertEqual(self.row(doc, 102)["legs"]["bye"], {"provenance": "complete",
                                                              "values": {"bye_week": 8}})
        self.assertEqual(self.row(doc, 101)["legs"]["bye"]["values"], {"bye_week": 10})
        self.assertEqual(self.row(doc, 109)["legs"]["bye"]["missing_reason"],
                         {"bye_week": "team ZZZ not in bye table"})
        self.assertEqual(doc["legs"]["bye"]["availability"], "partial")

    def test_bye_table_for_another_season_is_unavailable(self):
        byes = self.write("byes.json", json.dumps({"season": 2025, "byes": {"AAA": 8}}))
        doc = self.build(byes=byes)
        self.assertEqual(doc["legs"]["bye"]["availability"], "unavailable")
        self.assertEqual(self.row(doc, 101)["legs"]["bye"], {"provenance": "missing",
                                                              "values": {"bye_week": None}})


class Freshness(ProducerCase):
    def test_stale_vintage_keeps_availability(self):
        espn = self.write("espn.csv", HEADER +
                          "2026,8,101,WR,AAA,1.0,1.5,2.0,2026-10-13T12:40:00+00:00,false,team_week\n")
        doc = self.build(espn_weekly=espn, status=None)
        meta = doc["legs"]["experts.espn_weekly"]
        self.assertEqual((meta["availability"], meta["freshness"], meta["label"], meta["content_week"]),
                         ("complete", "stale", "stale", 6))
        self.assertEqual(self.row(doc, 101)["legs"]["experts.espn_weekly"]["values"]["standard"], 1.0)
        self.assertEqual(bwi.validate(doc), [])

    def test_one_week_behind_status(self):
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-23", "sleeper_id": "S101", "player_key": 101,
             "team": "AAA", "position": "WR", "status": "Active"}]))
        meta = self.build(status=status, espn_weekly=None)["legs"]["status"]
        self.assertEqual((meta["availability"], meta["freshness"]), ("complete", "one_week_behind"))
        self.assertEqual(bwi.validate(json.loads(self.out.read_text())), [])

    def test_wrong_week_only_input_is_unavailable_not_substituted(self):
        espn = self.write("espn.csv", HEADER +
                          "2026,7,101,WR,AAA,9.0,10.0,11.0,2026-10-21T12:40:00+00:00,false,team_week\n")
        doc = self.build(espn_weekly=espn, status=None)
        self.assertEqual(doc["legs"]["experts.espn_weekly"]["availability"], "unavailable")
        self.assertEqual(doc["players"], [])


class EmptyAndMissingInputs(ProducerCase):
    def test_empty_inputs_write_a_valid_artifact_with_no_rows(self):
        espn = self.write("espn.csv", HEADER)
        status = self.write("status.json", "[]")
        doc = self.build(espn_weekly=espn, status=status)
        self.assertEqual(doc["players"], [])
        for leg in ("experts.espn_weekly", "status"):
            self.assertEqual(doc["legs"][leg]["availability"], "unavailable")
        self.assertEqual(bwi.validate(doc), [])

    def test_inputs_not_supplied(self):
        doc = self.build(espn_weekly=None, status=None, byes=None, sleeper_base=None)
        for meta in doc["legs"].values():
            self.assertEqual(meta["availability"], "unavailable")
        self.assertEqual(doc["legs"]["status"]["missing_reason"], "input not supplied")

    def test_players_snapshot_is_required(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bwi.main(_args(self.out, players=None))

    def test_another_season_is_refused_not_guessed(self):
        code, err = _run(_args(self.out, season=2027))
        self.assertEqual(code, 2)
        self.assertIn("2026", err)
        self.assertFalse(self.out.exists())


class RosNeverMixes(ProducerCase):
    def assertRefused(self, **over):
        code, err = _run(_args(self.out, **over))
        self.assertEqual(code, 2)
        self.assertIn("ROS", err)
        self.assertFalse(self.out.exists())

    def test_the_real_espn_ros_file_is_refused(self):
        self.assertRefused(espn_weekly=ROOT / "data" / "inputs" / "espn_projections.csv")

    def test_a_ros_column_is_refused(self):
        espn = self.write("espn.csv", HEADER.rstrip("\n") + ",ros_half_ppr\n"
                          "2026,8,101,WR,AAA,1,1,1,2026-10-28T12:40:00+00:00,false,team_week,90\n")
        self.assertRefused(espn_weekly=espn)

    def test_a_ros_horizon_row_is_refused(self):
        espn = self.write("espn.csv", HEADER.rstrip("\n") + ",horizon\n"
                          "2026,8,101,WR,AAA,1,1,1,2026-10-28T12:40:00+00:00,false,team_week,ros\n")
        self.assertRefused(espn_weekly=espn)

    def test_a_ros_status_row_is_refused(self):
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-28", "sleeper_id": "S1", "player_key": 101, "horizon": "ros"}]))
        self.assertRefused(status=status)

    def test_artifact_says_weekly(self):
        self.assertEqual(self.build()["horizon"], "week")


class Validation(ProducerCase):
    def test_fixture_output_validates(self):
        self.assertEqual(bwi.validate(self.build()), [])

    @unittest.skipUnless(CONTRACT is not None, "JEG-1227 contract module not on this branch yet")
    def test_validates_against_the_jeg1227_contract(self):
        issues = CONTRACT.validate_file(FX / "expected_wk8.json")
        self.assertEqual([str(i) for i in issues], [])
        self.assertEqual(bwi.validate(self.build()), [])

    def test_invalid_document_is_not_written(self):
        with mock.patch.object(bwi, "validate", return_value=["boom"]):
            code, err = _run(_args(self.out))
        self.assertEqual(code, 1)
        self.assertIn("boom", err)
        self.assertFalse(self.out.exists())

    def test_cli_entry_point(self):
        proc = subprocess.run([sys.executable, str(ROOT / "pipelines" / "build_weekly_inputs.py"),
                               *_args(self.out)], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.out.read_text(), (FX / "expected_wk8.json").read_text())

    def test_out_is_required(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bwi.main(["--season", "2026", "--week", "8", "--as-of", AS_OF])


if __name__ == "__main__":
    unittest.main()
