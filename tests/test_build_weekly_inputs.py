"""JEG-1228: offline weekly-input producer (pipelines/build_weekly_inputs.py).

Fails before the change: the producer did not exist. Every input here is a
committed fixture or a temp file; no network, Supabase or wall clock.

JEG-1245: ContractFailsClosed and OfflineIdentity fail on 2da0242 (the
validator fell back to a structural check that accepted schema_version 999.0.0,
and Identity attempted a Supabase alias read when credentials were set).

Until JEG-1227's contract module is on this branch, producer-logic tests run
against _StubContract below (test-only; the producer has no stand-in and
refuses to run without the real module). With the module importable they use
the real validator.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.request
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


def _stub_validate(doc):
    """Test-only structural check, used only while CONTRACT is None."""
    errs = []
    if doc.get("schema") != bwi.SCHEMA or doc.get("schema_version") != bwi.SCHEMA_VERSION:
        errs.append("schema/schema_version")
    if doc.get("horizon") != "week":
        errs.append("horizon")
    for leg, m in doc["legs"].items():
        if (m["availability"] == "unavailable") != (m["freshness"] is None):
            errs.append(f"{leg}: freshness is null exactly when unavailable")
    for r in doc["players"]:
        if r["player_key"] is None and not r.get("unresolved_reason"):
            errs.append(f"{r['name']}: unresolved without a reason")
        for leg, c in r["legs"].items():
            for k, v in c["values"].items():
                reason = (c.get("missing_reason") or {}).get(k)
                if v is not None and reason:
                    errs.append(f"{r['name']}/{leg}.{k}: value with a missing_reason")
                if v is None and not reason and doc["legs"][leg]["availability"] != "unavailable":
                    errs.append(f"{r['name']}/{leg}.{k}: null without a reason")
    return errs


_StubContract = types.SimpleNamespace(validate=_stub_validate, errors=lambda issues: issues)

FX = ROOT / "tests" / "fixtures" / "weekly_inputs_producer"
AS_OF = "2026-10-29T02:00:00Z"
HEADER = "season,week,player_key,pos,team,std,half_ppr,ppr,snapshot_at,pre_kickoff,basis\n"


def _args(out, **over):
    base = {"season": 2026, "week": 8, "as_of": AS_OF, "out": out,
            "espn_weekly": FX / "espn_weekly.csv", "status": FX / "status.json",
            "byes": FX / "byes.json", "players": FX / "players.json",
            "sleeper_base": FX / "sleeper_base.json", "aliases": None,
            "espn_roster": None, "slate": None}
    base.update(over)
    argv = ["--season", str(base["season"]), "--week", str(base["week"]),
            "--as-of", base["as_of"], "--out", str(base["out"])]
    for flag in ("espn_weekly", "status", "byes", "players", "sleeper_base", "aliases",
                 "espn_roster", "slate"):
        if base[flag] is not None:
            argv += ["--" + flag.replace("_", "-"), str(base[flag])]
    return argv


def _run(argv):
    err, out = io.StringIO(), io.StringIO()
    with redirect_stderr(err), redirect_stdout(out):
        code = bwi.main(argv)
    return code, err.getvalue()


class ProducerCase(unittest.TestCase):
    stub_contract = True

    def setUp(self):
        if CONTRACT is None and self.stub_contract:
            patcher = mock.patch.object(bwi, "_load_contract", return_value=_StubContract)
            patcher.start()
            self.addCleanup(patcher.stop)
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

    def test_earlier_week_status_is_not_carried_forward(self):
        # JEG-1305: pick A (JEG-1228, 10-28) is "within the week, older days not
        # carried forward". A week-7 snapshot never fills week 8; the leg is empty
        # with a reason. (This test asserted one_week_behind before the fix.)
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-23", "fetched_at": "2026-10-23T13:00:00+00:00",
             "sleeper_id": "S101", "player_key": 101,
             "team": "AAA", "position": "WR", "status": "Active"}]))
        doc = self.build(status=status, espn_weekly=None)
        meta = doc["legs"]["status"]
        self.assertEqual((meta["availability"], meta["freshness"], meta["label"]),
                         ("unavailable", None, "unavailable"))
        self.assertEqual(meta["missing_reason"],
                         "no status snapshot in content week 8 on or before --as-of")
        self.assertIsNone(meta["captured_at"])
        self.assertEqual(doc["input_report"]["status"]["wrong_week"], 1)
        self.assertFalse(any(v is not None for r in doc["players"]
                             for v in r["legs"]["status"]["values"].values()))
        self.assertEqual(bwi.validate(doc), [])

    def test_earlier_week_rows_beside_target_week_rows_are_left_out(self):
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-26", "fetched_at": "2026-10-26T13:00:00+00:00",
             "sleeper_id": "S102", "player_key": 102, "team": "BBB", "position": "RB",
             "status": "Active", "injury_status": "Out"},
            {"snapshot_date": "2026-10-28", "fetched_at": "2026-10-28T13:00:00+00:00",
             "sleeper_id": "S101", "player_key": 101, "team": "AAA", "position": "WR",
             "status": "Active"}]))
        doc = self.build(status=status, espn_weekly=None)
        self.assertEqual(doc["input_report"]["status"]["wrong_week"], 1)
        self.assertEqual(doc["legs"]["status"]["content_week"], 8)
        self.assertFalse(any(r["player_key"] == 102 and r["legs"]["status"]["values"]["injury_status"]
                             for r in doc["players"]))

    def test_status_captured_after_the_as_of_time_is_left_out(self):
        # JEG-1305 repro: same New York day as --as-of, captured hours after it.
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-28", "fetched_at": "2026-10-28T23:30:00+00:00",
             "sleeper_id": "S101", "player_key": 101, "team": "AAA", "position": "WR",
             "status": "Active"}]))
        doc = self.build(status=status, espn_weekly=None, as_of="2026-10-28T20:00:00Z")
        meta = doc["legs"]["status"]
        self.assertEqual(meta["availability"], "unavailable")
        self.assertIsNone(meta["captured_at"])
        self.assertEqual(doc["input_report"]["status"]["after_as_of"], 1)
        self.assertEqual(bwi.validate(doc), [])

    def test_only_rows_captured_by_the_as_of_time_set_the_vintage(self):
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-28", "fetched_at": "2026-10-28T13:00:00+00:00",
             "sleeper_id": "S101", "player_key": 101, "team": "AAA", "position": "WR",
             "status": "Active"},
            {"snapshot_date": "2026-10-28", "fetched_at": "2026-10-28T23:30:00+00:00",
             "sleeper_id": "S102", "player_key": 102, "team": "BBB", "position": "RB",
             "status": "Active", "injury_status": "Out"}]))
        doc = self.build(status=status, espn_weekly=None, as_of="2026-10-28T20:00:00Z")
        meta = doc["legs"]["status"]
        self.assertEqual(meta["captured_at"], "2026-10-28T13:00:00Z")
        self.assertLessEqual(meta["captured_at"], doc["built_at"])
        self.assertEqual(doc["input_report"]["status"]["after_as_of"], 1)
        self.assertEqual(self.row(doc, 101)["legs"]["status"]["values"]["status"], "Active")
        self.assertFalse(any(r["player_key"] == 102 and r["legs"]["status"]["values"]["injury_status"]
                             for r in doc["players"]))

    def test_unreadable_status_capture_time_is_a_bad_row(self):
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-28", "fetched_at": "not a time",
             "sleeper_id": "S101", "player_key": 101, "team": "AAA", "position": "WR",
             "status": "Active"}]))
        doc = self.build(status=status, espn_weekly=None)
        self.assertEqual(doc["legs"]["status"]["availability"], "unavailable")
        self.assertEqual(doc["input_report"]["status"]["bad_row"], 1)

    def test_status_without_a_capture_time_is_unknown_not_aged(self):
        # JEG-1267: no fetched_at means no captured_at, so no age or published claim.
        status = self.write("status.json", json.dumps([
            {"snapshot_date": "2026-10-28", "sleeper_id": "S101", "player_key": 101,
             "team": "AAA", "position": "WR", "status": "Active"}]))
        doc = self.build(status=status, espn_weekly=None)
        meta = doc["legs"]["status"]
        self.assertEqual((meta["availability"], meta["freshness"], meta["label"]),
                         ("complete", "unknown", "modeled"))
        self.assertIsNone(meta["captured_at"])
        self.assertIsNone(meta["content_week"])
        self.assertEqual(meta["content_vintage"], "2026-10-28")  # what the input stamps stays
        self.assertEqual(bwi.validate(doc), [])

    def test_unstamped_bye_table_is_unknown_and_not_published(self):
        # JEG-1245/JEG-1267: the bye table stamps no date, so none is invented.
        meta = self.build()["legs"]["bye"]
        self.assertEqual((meta["availability"], meta["freshness"], meta["label"]),
                         ("partial", "unknown", "modeled"))
        for name in ("content_week", "content_vintage", "captured_at"):
            self.assertIsNone(meta[name], name)
        self.assertEqual(meta["content_season"], 2026)

    @unittest.skipUnless(CONTRACT is not None, "JEG-1227 contract module not on this branch yet")
    def test_contract_rejects_the_old_published_bye_leg(self):
        # The shape 86031bb emitted: current/published with no vintage or capture time.
        if "leg.provenance_unknown" not in getattr(CONTRACT, "CODES", {}):
            self.skipTest("contract predates JEG-1267")
        doc = self.build()
        self.assertEqual(bwi.validate(doc), [])
        doc["legs"]["bye"].update(content_week=8, freshness="current", label="published")
        doc["legs"]["bye"].pop("note")
        codes = {i.code for i in CONTRACT.errors(CONTRACT.validate(doc))}
        self.assertIn("leg.provenance_unknown", codes)

    def test_wrong_week_only_input_is_unavailable_not_substituted(self):
        espn = self.write("espn.csv", HEADER +
                          "2026,7,101,WR,AAA,9.0,10.0,11.0,2026-10-21T12:40:00+00:00,false,team_week\n")
        doc = self.build(espn_weekly=espn, status=None)
        self.assertEqual(doc["legs"]["experts.espn_weekly"]["availability"], "unavailable")
        self.assertEqual(doc["players"], [])


class RosterAndSlate(ProducerCase):
    """JEG-1416: weekly-inputs 1.1 roster (ESPN) and slate (kickoff) legs.

    Both legs read explicit stored local files only, like every other leg.
    The stored shapes are defined in docs/weekly-inputs-contract.md (1.1):
    the roster file is {season, week, captured_at, rows[{player_key, team,
    rostered_pct, adds_trend}]}; the slate file is {season, week, captured_at,
    games[{home_team, away_team, kickoff_at}]}.
    """

    GAMES = [{"home_team": "AAA", "away_team": "CCC", "kickoff_at": "2026-11-01T17:00:00Z"},
             {"home_team": "BBB", "away_team": "DDD", "kickoff_at": "2026-11-01T21:25:00Z"}]

    def roster_file(self, rows, captured_at="2026-10-28T12:00:00Z", season=2026, week=8):
        doc = {"season": season, "week": week, "rows": rows}
        if captured_at is not None:
            doc["captured_at"] = captured_at
        return self.write("espn_roster.json", json.dumps(doc))

    def slate_file(self, games, captured_at="2026-10-28T09:00:00Z", season=2026, week=8):
        doc = {"season": season, "week": week, "games": games}
        if captured_at is not None:
            doc["captured_at"] = captured_at
        return self.write("slate.json", json.dumps(doc))

    def full(self, **over):
        over.setdefault("espn_roster", self.roster_file([
            {"player_key": 101, "team": "AAA", "rostered_pct": 84.2, "adds_trend": 6.4},
            {"player_key": 102, "team": "BBB", "rostered_pct": 0.0, "adds_trend": 0.0},
            {"player_key": 103, "team": "AAA", "rostered_pct": 45.5, "adds_trend": None}]))
        over.setdefault("slate", self.slate_file(self.GAMES))
        return self.build(**over)

    def test_producer_writes_schema_1_1_0(self):
        doc = self.build()
        self.assertEqual(doc["schema_version"], "1.1.0")
        self.assertEqual(bwi.SCHEMA_VERSION, "1.1.0")
        for leg in ("roster", "slate"):
            self.assertEqual(doc["legs"][leg]["availability"], "unavailable")

    def test_committed_fixtures_build_both_legs(self):
        doc = self.build(espn_roster=FX / "espn_roster.json", slate=FX / "slate.json")
        self.assertEqual(doc["schema_version"], "1.1.0")
        self.assertEqual(self.row(doc, 101)["legs"]["roster"]["values"],
                         {"rostered_pct": 84.2, "adds_trend": 6.4})
        self.assertEqual(self.row(doc, 101)["legs"]["slate"]["values"],
                         {"kickoff_at": "2026-11-01T17:00:00Z"})
        self.assertEqual(bwi.validate(doc), [])

    def test_roster_and_slate_values_land(self):
        doc = self.full()
        roster = self.row(doc, 101)["legs"]["roster"]
        self.assertEqual(roster["values"], {"rostered_pct": 84.2, "adds_trend": 6.4})
        self.assertEqual(roster["provenance"], "complete")
        self.assertEqual(self.row(doc, 101)["legs"]["slate"]["values"],
                         {"kickoff_at": "2026-11-01T17:00:00Z"})
        self.assertEqual(self.row(doc, 103)["legs"]["slate"]["values"],
                         {"kickoff_at": "2026-11-01T17:00:00Z"})  # CCC is the away team
        meta = doc["legs"]["roster"]
        self.assertEqual((meta["kind"], meta["source"], meta["units"], meta["scoring"]),
                         ("roster", "espn", "roster", None))
        self.assertEqual((meta["availability"], meta["freshness"], meta["label"]),
                         ("partial", "current", "published"))
        slate_meta = doc["legs"]["slate"]
        self.assertEqual((slate_meta["kind"], slate_meta["units"], slate_meta["game_week"]),
                         ("slate", "kickoff", 8))
        self.assertEqual(slate_meta["availability"], "partial")  # team ZZZ has no game
        self.assertEqual(bwi.validate(doc), [])

    def test_roster_zero_is_a_value_not_missing(self):
        cell = self.row(self.full(), 102)["legs"]["roster"]
        self.assertEqual(cell["values"], {"rostered_pct": 0.0, "adds_trend": 0.0})
        self.assertEqual(cell["provenance"], "complete")
        self.assertNotIn("missing_reason", cell)

    def test_partial_roster_row_keeps_null_with_reason(self):
        doc = self.full()
        cell = self.row(doc, 103)["legs"]["roster"]
        self.assertEqual(cell["values"], {"rostered_pct": 45.5, "adds_trend": None})
        self.assertEqual(cell["provenance"], "partial")
        self.assertEqual(cell["missing_reason"], {"adds_trend": "not set in the ESPN roster file"})
        absent = self.row(doc, 104)["legs"]["roster"]
        self.assertEqual(absent["provenance"], "missing")
        self.assertEqual(absent["missing_reason"]["rostered_pct"], "player not in this input")

    def test_team_without_a_game_has_no_kickoff(self):
        cell = self.row(self.full(), 109)["legs"]["slate"]
        self.assertEqual(cell, {"provenance": "missing", "values": {"kickoff_at": None},
                                "missing_reason": {"kickoff_at": "team ZZZ not in slate file"}})

    def test_roster_leg_can_supply_the_player_universe(self):
        roster = self.roster_file([{"player_key": 101, "team": "AAA",
                                    "rostered_pct": 84.2, "adds_trend": 6.4}])
        doc = self.build(espn_weekly=None, status=None, byes=None,
                         espn_roster=roster, slate=self.slate_file(self.GAMES))
        self.assertEqual([r["player_key"] for r in doc["players"]], [101])
        row = doc["players"][0]
        self.assertEqual((row["name"], row["position"], row["team"]), ("Ann Alpha", "WR", "AAA"))
        self.assertEqual(row["resolved_by"], "espn_roster.player_key")
        self.assertEqual(row["legs"]["roster"]["provenance"], "complete")
        self.assertEqual(row["legs"]["slate"]["values"], {"kickoff_at": "2026-11-01T17:00:00Z"})
        self.assertEqual(doc["legs"]["roster"]["availability"], "complete")
        self.assertEqual(bwi.validate(doc), [])

    def test_stale_captures_are_used_but_labelled_stale(self):
        roster = self.roster_file([{"player_key": 101, "team": "AAA",
                                    "rostered_pct": 84.2, "adds_trend": 6.4}],
                                  captured_at="2026-10-13T12:00:00Z")
        slate = self.slate_file(self.GAMES, captured_at="2026-10-13T09:00:00Z")
        doc = self.build(espn_roster=roster, slate=slate)
        for leg in ("roster", "slate"):
            meta = doc["legs"][leg]
            self.assertEqual((meta["freshness"], meta["label"], meta["content_week"]),
                             ("stale", "stale", 6), leg)
        self.assertEqual(self.row(doc, 101)["legs"]["roster"]["values"]["rostered_pct"], 84.2)
        self.assertEqual(self.row(doc, 101)["legs"]["slate"]["values"]["kickoff_at"],
                         "2026-11-01T17:00:00Z")
        self.assertEqual(bwi.validate(doc), [])

    def test_missing_inputs_leave_both_legs_unavailable_and_null(self):
        doc = self.build()
        for leg in ("roster", "slate"):
            meta = doc["legs"][leg]
            self.assertEqual((meta["availability"], meta["freshness"], meta["label"]),
                             ("unavailable", None, "unavailable"))
            self.assertEqual(meta["missing_reason"], "input not supplied")
        for r in doc["players"]:
            self.assertEqual(r["legs"]["roster"], {"provenance": "missing", "values": {
                "rostered_pct": None, "adds_trend": None}})
            self.assertEqual(r["legs"]["slate"], {"provenance": "missing",
                                                  "values": {"kickoff_at": None}})
        self.assertEqual(bwi.validate(doc), [])

    def test_empty_files_are_unavailable_not_invented(self):
        doc = self.build(espn_roster=self.roster_file([]), slate=self.slate_file([]))
        for leg in ("roster", "slate"):
            self.assertEqual(doc["legs"][leg]["availability"], "unavailable")
        self.assertFalse(any(v is not None for r in doc["players"]
                             for v in r["legs"]["roster"]["values"].values()))
        self.assertEqual(bwi.validate(doc), [])

    def test_roster_without_a_capture_time_is_unknown_not_published(self):
        roster = self.roster_file([{"player_key": 101, "team": "AAA",
                                    "rostered_pct": 84.2, "adds_trend": 6.4}], captured_at=None)
        doc = self.build(espn_roster=roster)
        meta = doc["legs"]["roster"]
        self.assertEqual((meta["freshness"], meta["label"]), ("unknown", "modeled"))
        self.assertIsNone(meta["captured_at"])
        self.assertIsNone(meta["content_week"])
        self.assertEqual(self.row(doc, 101)["legs"]["roster"]["values"]["rostered_pct"], 84.2)
        self.assertEqual(bwi.validate(doc), [])

    def test_wrong_week_files_are_left_out(self):
        roster = self.roster_file([{"player_key": 101, "team": "AAA",
                                    "rostered_pct": 84.2, "adds_trend": 6.4}], week=7)
        slate = self.slate_file(self.GAMES, week=7)
        doc = self.build(espn_roster=roster, slate=slate)
        self.assertEqual(doc["legs"]["roster"]["availability"], "unavailable")
        self.assertEqual(doc["legs"]["slate"]["availability"], "unavailable")
        self.assertEqual(doc["input_report"]["roster"]["wrong_week"], 1)
        self.assertEqual(doc["input_report"]["slate"]["wrong_week"], 2)
        self.assertIsNone(self.row(doc, 101)["legs"]["roster"]["values"]["rostered_pct"])
        self.assertIsNone(self.row(doc, 101)["legs"]["slate"]["values"]["kickoff_at"])

    def test_conflicting_duplicates_stay_null(self):
        roster = self.roster_file([
            {"player_key": 101, "team": "AAA", "rostered_pct": 84.2, "adds_trend": 6.4},
            {"player_key": 101, "team": "AAA", "rostered_pct": 50.0, "adds_trend": 6.4}])
        games = self.GAMES + [{"home_team": "AAA", "away_team": "DDD",
                               "kickoff_at": "2026-11-01T20:00:00Z"}]
        doc = self.build(espn_roster=roster, slate=self.slate_file(games))
        cell = self.row(doc, 101)["legs"]["roster"]
        self.assertEqual(set(cell["values"].values()), {None})
        self.assertIn("conflicting", cell["missing_reason"]["rostered_pct"])
        self.assertEqual(doc["input_report"]["roster"]["conflict"], 1)
        slate_cell = self.row(doc, 101)["legs"]["slate"]
        self.assertIsNone(slate_cell["values"]["kickoff_at"])
        self.assertEqual(slate_cell["missing_reason"],
                         {"kickoff_at": "conflicting kickoff times in slate file"})
        self.assertEqual(doc["input_report"]["slate"]["conflict"], 1)
        self.assertEqual(bwi.validate(doc), [])

    def test_unknown_roster_key_is_counted_and_left_out(self):
        roster = self.roster_file([{"player_key": 999, "team": "AAA",
                                    "rostered_pct": 10.0, "adds_trend": 1.0}])
        doc = self.build(espn_roster=roster)
        self.assertEqual(doc["input_report"]["roster"]["bad_row"], 1)
        self.assertFalse(any(r["player_key"] == 999 for r in doc["players"]))
        self.assertEqual(doc["legs"]["roster"]["availability"], "unavailable")

    def test_roster_run_is_byte_stable_on_rerun(self):
        self.full()
        first = self.out.read_bytes()
        self.full()
        self.assertEqual(self.out.read_bytes(), first)


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
        if CONTRACT is None:  # a real process has no stub: it must refuse, not write
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertIn("cannot be imported", proc.stderr)
            self.assertFalse(self.out.exists())
            return
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.out.read_text(), (FX / "expected_wk8.json").read_text())

    def test_out_is_required(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bwi.main(["--season", "2026", "--week", "8", "--as-of", AS_OF])


class ContractFailsClosed(ProducerCase):
    """JEG-1245 finding 1: no validator, no artifact."""
    stub_contract = False

    def golden_with_version(self, version):
        doc = json.loads((FX / "expected_wk8.json").read_text())
        doc["schema_version"] = version
        return doc

    def assert_refused(self, err_fragment):
        code, err = _run(_args(self.out))
        self.assertEqual(code, 3, err)
        self.assertIn(err_fragment, err)
        self.assertFalse(self.out.exists())
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [])

    def test_missing_contract_refuses_and_writes_nothing(self):
        with mock.patch.dict(sys.modules, {bwi.CONTRACT_MODULE: None}):
            self.assert_refused("cannot be imported")

    def test_contract_that_raises_on_import_refuses(self):
        pkg = self.dir.parent / (self.dir.name + "-broken")
        pkg.mkdir()
        self.addCleanup(shutil.rmtree, pkg, True)
        (pkg / f"{bwi.CONTRACT_MODULE}.py").write_text("raise RuntimeError('half-written module')\n")
        saved = sys.modules.pop(bwi.CONTRACT_MODULE, None)
        self.addCleanup(lambda: sys.modules.__setitem__(bwi.CONTRACT_MODULE, saved) if saved
                        else sys.modules.pop(bwi.CONTRACT_MODULE, None))
        with mock.patch.object(sys, "path", [str(pkg), *sys.path]):
            self.assert_refused("RuntimeError: half-written module")

    def test_contract_without_validate_refuses(self):
        with mock.patch.dict(sys.modules, {bwi.CONTRACT_MODULE: types.ModuleType("empty")}):
            self.assert_refused("has no validate, errors()")

    def test_crashing_validator_refuses(self):
        def boom(doc):
            raise KeyError("scoring")
        crashing = types.SimpleNamespace(validate=boom, errors=lambda i: i)
        with mock.patch.dict(sys.modules, {bwi.CONTRACT_MODULE: crashing}):
            self.assert_refused("failed (KeyError")

    def test_unsupported_schema_version_is_never_accepted_without_the_contract(self):
        # 2da0242: validate() returned [] for this (the structural fallback).
        doc = self.golden_with_version("999.0.0")
        with mock.patch.dict(sys.modules, {bwi.CONTRACT_MODULE: None}), \
                self.assertRaises(bwi.ContractUnavailable):
            bwi.validate(doc)

    @unittest.skipUnless(CONTRACT is not None, "JEG-1227 contract module not on this branch yet")
    def test_real_contract_rejects_unsupported_schema_version(self):
        self.assertNotEqual(bwi.validate(self.golden_with_version("999.0.0")), [])
        self.assertEqual(bwi.validate(self.golden_with_version(bwi.SCHEMA_VERSION)), [])


class _NetworkSpy:
    """Records every attempted connection without raising, so a caller that
    swallows request errors cannot hide an attempt."""

    def __init__(self):
        self.calls = []

    def urlopen(self, req, *a, **k):
        self.calls.append(("urlopen", getattr(req, "full_url", req)))
        raise OSError("network spy: blocked")

    def create_connection(self, address, *a, **k):
        self.calls.append(("create_connection", address))
        raise OSError("network spy: blocked")

    def connect(self, sock, address):
        self.calls.append(("socket.connect", address))
        raise OSError("network spy: blocked")

    def __enter__(self):
        spy = self
        self._patches = [
            mock.patch.object(urllib.request, "urlopen", self.urlopen),
            mock.patch.object(socket, "create_connection", self.create_connection),
            mock.patch.object(socket.socket, "connect", lambda s, a: spy.connect(s, a)),
            mock.patch.object(socket.socket, "connect_ex", lambda s, a: spy.connect(s, a)),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()


DUMMY_SUPABASE = {"SUPABASE_URL": "https://dummy-project.supabase.co",
                  "SUPABASE_SERVICE_KEY": "dummy-service-key",
                  "SUPABASE_ANON_KEY": "dummy-anon-key"}


class OfflineIdentity(ProducerCase):
    """JEG-1245 finding 2: zero attempted network calls with credentials set."""

    def setUp(self):
        super().setUp()
        import player_aliases
        self.pa = player_aliases
        saved = (player_aliases._cache, player_aliases._loaded_from)
        player_aliases._cache = player_aliases._loaded_from = None  # no warm cache hiding a read

        def restore():
            player_aliases._cache, player_aliases._loaded_from = saved
        self.addCleanup(restore)
        env = {k: v for k, v in os.environ.items() if k != "PLAYER_ALIASES_SOURCE"}
        env.update(DUMMY_SUPABASE)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_spy_sees_the_dependency_attempt_the_producer_must_prevent(self):
        # Control: the shared registry, built directly, does try Supabase here.
        import canonical_players
        with _NetworkSpy() as spy, redirect_stderr(io.StringIO()):
            canonical_players.Registry([])
        self.assertGreaterEqual(len(spy.calls), 1, "spy would not catch the leak")
        self.assertIn("dummy-project.supabase.co", str(spy.calls[0]))

    def test_identity_makes_zero_network_attempts(self):
        with _NetworkSpy() as spy:
            bwi.Identity(FX / "players.json", FX / "sleeper_base.json")
        self.assertEqual(spy.calls, [])

    def test_full_run_makes_zero_network_attempts_and_matches_golden(self):
        with _NetworkSpy() as spy:
            code, err = _run(_args(self.out))
        self.assertEqual(spy.calls, [])
        self.assertEqual(code, 0, err)
        self.assertNotIn("Supabase", err)
        self.assertEqual(self.out.read_text(), (FX / "expected_wk8.json").read_text())

    def test_alias_pin_is_restored_after_build(self):
        real = self.pa.load
        bwi.Identity(FX / "players.json", FX / "sleeper_base.json")
        self.assertIs(self.pa.load, real)

    def test_aliases_file_is_in_provenance_and_changes_follow_it(self):
        doc = self.build()
        ident = doc["input_report"]["identity"]
        self.assertEqual(ident["alias_source"], "local_file")
        self.assertEqual(ident["aliases"]["name"], bwi.ALIAS_FILE.name)
        alt = self.write("aliases.json", json.dumps({"schema": "player-aliases-v1", "aliases": []}))
        doc2 = self.build(aliases=alt)
        self.assertNotEqual(doc2["input_report"]["identity"]["aliases"]["sha256"],
                            ident["aliases"]["sha256"])

    def test_alias_file_is_what_resolves_names(self):
        # A local alias entry is honoured: resolution follows the file, not Supabase.
        alt = self.write("aliases.json", json.dumps({"schema": "player-aliases-v1", "aliases": [
            {"alias": "Zzz Nobody", "player_key": 999999, "full_name": "Real Name"}]}))
        with _NetworkSpy() as spy:
            ident = bwi.Identity(FX / "players.json", FX / "sleeper_base.json", alt)
        self.assertEqual(spy.calls, [])
        self.assertEqual(ident.index.registry.alias_overrides.get("zzz nobody"), "real name")


if __name__ == "__main__":
    unittest.main()
