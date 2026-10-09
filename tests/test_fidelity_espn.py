"""Hermetic tests for pipelines/fidelity_sources/espn.py (JEG-480).

Synthetic JSON shaped like ESPN's kona_player_info answer (players[].player
with defaultPositionId, proTeamId, stats[] blocks keyed by seasonId /
statSourceId / statSplitTypeId / scoringPeriodId) and the proTeamSchedules
team list, served by a fake fetch. No network.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from fidelity_sources import espn  # noqa: E402

import fidelity_pulse as fp  # noqa: E402


def block(source, split, week, stats, season=2026):
    return {"seasonId": season, "statSourceId": source, "statSplitTypeId": split, "scoringPeriodId": week,
            "appliedTotal": 0.0, "stats": stats}


def player(pid, name, pos_id, team_id, weekly, actual_weeks=(1, 2, 3, 4), extra=()):
    stats = [block(0, 1, w, {"24": 1.0}) for w in actual_weeks]
    stats += [block(1, 1, w, s) for w, s in weekly.items()]
    stats += list(extra)
    return {"id": pid, "player": {"id": pid, "fullName": name, "defaultPositionId": pos_id,
                                  "proTeamId": team_id, "stats": stats}}


def fillers(n, pos_id, start):
    """Players who make weeks 1-4 count as played (20+ players with actuals)."""
    return [player(start + i, f"Filler {pos_id}-{i}", pos_id, 1, {5: {"24": 1.0}}) for i in range(n)]


# Aaron Jones-shaped RB: weekly components chosen so the ROS sums are exact.
RB_WEEKLY = {w: {"24": 40.0, "25": 0.25, "53": 2.5, "42": 20.0, "43": 0.125} for w in range(5, 19) if w != 6}
RB_WEEKLY[6] = {}  # bye week: ESPN sends an empty block
RB_WEEKLY[3] = {"24": 999.0, "53": 99.0}  # played week: must not count
QB_WEEKLY = {w: {"3": 250.0, "4": 1.5, "24": 20.0, "25": 0.2} for w in range(5, 19)}

PLAYERS = {
    0: [player(1, "Josh Allen", 1, 2, QB_WEEKLY)] + fillers(6, 1, 100),
    2: [player(2, "Aaron Jones Sr.", 2, 16, RB_WEEKLY,
               extra=[block(1, 0, 0, {"24": 5000.0}),             # season block: not used
                      block(1, 1, 7, {"24": 1.0}, season=2025)]),  # 2025 block: not used
        player(3, "Deebo Samuel", 3, 28, {5: {"24": 10.0}})]       # WR listed under the RB slot: skipped
       + fillers(6, 2, 200),
    4: [player(3, "Deebo Samuel", 3, 28, {w: {"53": 4.0, "42": 45.0, "43": 0.25} for w in range(5, 19)}),
        player(4, "No Projection Guy", 3, 0, {}, extra=[block(1, 0, 0, {"53": 1.0})])] + fillers(6, 3, 300),
    6: [player(5, "Travis Kelce", 4, 12, {w: {"53": 4.0, "42": "n/a", "43": None} for w in range(5, 19)})]
       + fillers(6, 4, 400),
}
TEAMS = {"settings": {"proTeams": [{"id": 0, "abbrev": "FA"}, {"id": 2, "abbrev": "BUF", "byeWeek": 7},
                                   {"id": 12, "abbrev": "KC", "byeWeek": 5}, {"id": 16, "abbrev": "MIN", "byeWeek": 6},
                                   {"id": 28, "abbrev": "WSH", "byeWeek": 7}, {"id": 1, "abbrev": "ATL"}]}}


class FakeFetch:
    def __init__(self, players=None, teams=TEAMS, status=200, body=None):
        self.players = PLAYERS if players is None else players
        self.teams, self.status, self.body = teams, status, body
        self.calls = []

    def get(self, url, timeout=60, headers=None):
        self.calls.append((url, headers))
        if url == espn.TEAMS_API:
            return (200, json.dumps(self.teams), url) if self.teams is not None else (503, "", url)
        if self.status != 200:
            return self.status, "", url
        if self.body is not None:
            return 200, self.body, url
        slot = json.loads(headers["X-Fantasy-Filter"])["players"]["filterSlotIds"]["value"][0]
        return 200, json.dumps({"players": self.players.get(slot, [])}), url


class HeaderlessFetch:
    def get(self, url, timeout=60):
        return 200, json.dumps({"players": []}), url


class ReadPublisherTests(unittest.TestCase):
    def setUp(self):
        self.fetch = FakeFetch()
        self.pub = espn.read_publisher(self.fetch)
        self.rows = {r.name: r for r in self.pub["rows"]}

    def test_contract(self):
        self.assertIsNone(self.pub["error"])
        for k in ("rows", "url", "vintage", "dates", "notes", "error"):
            self.assertIn(k, self.pub)
        self.assertEqual(self.pub["dates"], {"dateModified": None})
        self.assertTrue(all(isinstance(r, fp.PubRow) for r in self.pub["rows"]))
        self.assertEqual(espn.SOURCE, "espn")
        self.assertEqual(espn.STORED_TABLE, "espn_season_projections")
        self.assertEqual(espn.CHART_DECIMALS, 2)
        for col in ("player_key", espn.SNAPSHOT_COLUMN, "created_at", "ros_half_ppr", "r_receptions",
                    "weeks_covered"):
            self.assertIn(col, espn.STORED_SELECT.split(","))

    def test_sends_filter_header_per_slot(self):
        sent = [json.loads(h["X-Fantasy-Filter"])["players"] for _, h in self.fetch.calls if h]
        self.assertEqual([f["filterSlotIds"]["value"] for f in sent], [[0], [2], [4], [6]])
        self.assertTrue(all(f["filterStatsForSourceIds"]["value"] == [0, 1] and f["limit"] == 400 for f in sent))

    def test_ros_window_from_actuals(self):
        self.assertEqual(self.pub["ros_weeks"], "5-18")
        self.assertTrue(any("5-18" in n for n in self.pub["notes"]))

    def test_summing_rule_every_scoring(self):
        # RB: 13 non-bye ROS weeks. rush 520.0, rush TD 3.25 -> 3.2 (1 dp), rec 32.5, rec yds 260.0,
        # rec TD 1.625 -> 1.6. half = 52 + 19.2 + 16.25 + 26 + 9.6 = 123.05
        r = self.rows["Aaron Jones Sr."]
        self.assertEqual((r.pos, r.team), ("RB", "MIN"))
        self.assertEqual(r.values, {"half|1": "123.05", "full|1": "139.30", "std|1": "106.80"})
        # QB: 14 weeks. pass 3500 -> 140, pass TD 21 -> 84, rush 280 -> 28, rush TD 2.8 -> 16.8
        q = self.rows["Josh Allen"]
        self.assertEqual((q.pos, q.team), ("QB", "BUF"))
        self.assertEqual(q.values, {"half|1": "268.80", "full|1": "268.80", "std|1": "268.80"})

    def test_non_numeric_stats_count_as_zero(self):
        # rec 56.0 (receptions only; "n/a" yards and None TDs are not numbers)
        self.assertEqual(self.rows["Travis Kelce"].values, {"half|1": "28.00", "full|1": "56.00", "std|1": "0.00"})

    def test_position_from_api_and_skips(self):
        self.assertEqual(self.rows["Deebo Samuel"].pos, "WR")
        self.assertEqual(sum(1 for r in self.pub["rows"] if r.name == "Deebo Samuel"), 1)
        self.assertEqual(self.rows["Deebo Samuel"].team, "WSH")
        self.assertNotIn("No Projection Guy", self.rows)
        self.assertTrue(any("without 2026 weekly projection blocks" in n for n in self.pub["notes"]))

    def test_matches_stored_after_rounding(self):
        r = self.rows["Aaron Jones Sr."]
        stored = espn.stored_publisher_values({"ros_half_ppr": 123.05, "r_receptions": 32.5})
        for grain, text in r.values.items():
            self.assertTrue(fp.equal_after_rounding(text, stored[grain]), grain)

    def test_stored_window_wins_mid_week(self):
        """2026-10-09: Thursday's game gave week 5 actuals; the played-week rule read 6-18
        against stored 5-18 and flagged 906 values. With the stored window both sum 5-18."""
        mid = {slot: [dict(p, player=dict(p["player"], stats=p["player"]["stats"] + [block(0, 1, 5, {"24": 1.0})]))
                      for p in ps] for slot, ps in PLAYERS.items()}
        rule = espn.read_publisher(FakeFetch(players=mid))
        self.assertEqual("6-18", rule["ros_weeks"])  # what the reader alone would sum
        pub = espn.read_publisher(FakeFetch(players=mid), window="5-18")
        self.assertEqual("5-18", pub["ros_weeks"])
        rows = {r.name: r for r in pub["rows"]}
        self.assertEqual({"half|1": "123.05", "full|1": "139.30", "std|1": "106.80"}, rows["Aaron Jones Sr."].values)
        self.assertTrue(any("stored rows' window" in n for n in pub["notes"]))

    def test_framework_passes_the_stored_window(self):
        seen = {}

        class Mod:
            @staticmethod
            def read_publisher(fetch, window=None):
                seen["window"] = window
                return {}
        fp.read_projection_publisher(Mod, None, [{"weeks_covered": "5-18"}, {"weeks_covered": "5-18"},
                                                 {"weeks_covered": "4-18"}])
        self.assertEqual("5-18", seen["window"])

    def test_team_list_failure_is_a_note(self):
        pub = espn.read_publisher(FakeFetch(teams=None))
        self.assertIsNone(pub["error"])
        self.assertTrue(all(r.team is None for r in pub["rows"]))
        self.assertTrue(any("team list" in n for n in pub["notes"]))


class FailureTests(unittest.TestCase):
    def test_http_error(self):
        pub = espn.read_publisher(FakeFetch(status=403))
        self.assertIn("HTTP 403", pub["error"])
        self.assertEqual(pub["rows"], [])

    def test_not_json(self):
        pub = espn.read_publisher(FakeFetch(body="<html>maintenance</html>"))
        self.assertIn("no players list", pub["error"])
        self.assertEqual(pub["rows"], [])

    def test_empty_position(self):
        pub = espn.read_publisher(FakeFetch(players={**PLAYERS, 6: []}))
        self.assertIn("no players", pub["error"])
        self.assertEqual(pub["rows"], [])

    def test_fetcher_without_headers(self):
        pub = espn.read_publisher(HeaderlessFetch())
        self.assertIn("X-Fantasy-Filter", pub["error"])
        self.assertEqual(pub["rows"], [])

    def test_every_week_played(self):
        players = {s: [player(100 * s + i, f"P{s}-{i}", {0: 1, 2: 2, 4: 3, 6: 4}[s], 1, {5: {"24": 1.0}},
                              actual_weeks=range(1, 19)) for i in range(6)] for s in (0, 2, 4, 6)}
        pub = espn.read_publisher(FakeFetch(players=players))
        self.assertIn("no rest-of-season weeks", pub["error"])


class Reg:
    def __init__(self, by_key, dst_by_token=None):
        self.by_key, self.dst_by_token = by_key, dst_by_token or {}


class Ident:
    def __init__(self, reg):
        self.reg = reg


AARON = {"player_key": 164, "scoring": "half_ppr", "ros_half_ppr": 139.68, "r_receptions": 37.2,
         "weeks_covered": "5-18", "espn_snapshot_date": "2026-10-08"}


class StoredTests(unittest.TestCase):
    def test_publisher_values(self):
        v = espn.stored_publisher_values(AARON)
        self.assertAlmostEqual(v["half|1"], 139.68)
        self.assertAlmostEqual(v["full|1"], 158.28)
        self.assertAlmostEqual(v["std|1"], 121.08)
        self.assertEqual(espn.stored_publisher_values({"ros_half_ppr": 10.0}), {"half|1": 10.0})
        self.assertEqual(espn.stored_publisher_values({"ros_half_ppr": None, "r_receptions": 3}), {})

    def test_chart_values_bye_inside_window(self):
        # MIN bye week 6 is inside 5-18: 13 games. Live chart: half 10.74, full 12.18, std 9.31.
        ctx = {"ident": Ident(Reg({164: {"team_id": "t-min"}})), "team_abbr": {"t-min": "MIN"}}
        v = espn.stored_chart_values(AARON, ctx)
        self.assertEqual({g: round(x, 2) for g, x in v.items()}, {"half|1": 10.74, "full|1": 12.18, "std|1": 9.31})
        self.assertAlmostEqual(v["half|1"], 139.68 / 13)

    def test_chart_values_bye_already_passed(self):
        # KC bye week 5; window 6-18 -> 13 games, no bye inside.
        ctx = {"ident": Ident(Reg({1: {"team_id": "t-kc"}})), "team_abbr": {"t-kc": "KC"}}
        v = espn.stored_chart_values({"player_key": 1, "ros_half_ppr": 130.0, "r_receptions": 0,
                                      "weeks_covered": "6-18"}, ctx)
        self.assertAlmostEqual(v["half|1"], 10.0)

    def test_team_alias_and_dst_tokens(self):
        # No team_abbr in ctx: team_id -> abbreviation from the registry's DST tokens; LAR -> LA (bye 11).
        reg = Reg({7: {"team_id": "t-la"}, 900: {"team_id": "t-la", "position": "DST"}},
                  {"los angeles rams": 900, "rams": 900, "lar": 900})
        v = espn.stored_chart_values({"player_key": 7, "ros_half_ppr": 130.0, "r_receptions": 0,
                                      "weeks_covered": "5-18"}, {"ident": Ident(reg)})
        self.assertAlmostEqual(v["half|1"], 10.0)

    def test_free_agent_divides_by_window(self):
        ctx = {"ident": Ident(Reg({8: {"team_id": None}}))}
        v = espn.stored_chart_values({"player_key": 8, "ros_half_ppr": 14.0, "r_receptions": 0,
                                      "weeks_covered": "5-18"}, ctx)
        self.assertAlmostEqual(v["half|1"], 1.0)

    def test_unknown_team_or_window_is_absent_not_guessed(self):
        ctx = {"ident": Ident(Reg({9: {"team_id": "t-unknown"}}))}
        self.assertEqual(espn.stored_chart_values({**AARON, "player_key": 9}, ctx), {})
        self.assertEqual(espn.stored_chart_values({**AARON, "player_key": 10}, ctx), {})
        good = {"ident": Ident(Reg({164: {"team_id": "t-min"}})), "team_abbr": {"t-min": "MIN"}}
        self.assertEqual(espn.stored_chart_values({**AARON, "weeks_covered": None}, good), {})
        self.assertEqual(espn.stored_chart_values({**AARON, "weeks_covered": "x"}, good), {})

    def test_team_of_override(self):
        v = espn.stored_chart_values(AARON, {"team_of": lambda key: "MIN"})
        self.assertAlmostEqual(v["half|1"], 139.68 / 13)


if __name__ == "__main__":
    unittest.main()
