"""Settings in the Fieldnotes design (JEG-1140), without a browser.

Runs tests/settings_fieldnotes_logic.cjs under node and checks:

1. The view model for every fixture state: loading, error, ready, no team, empty league, missing counts and settings,
   storage unavailable or full, long names. A count or setting that is not known reads Unavailable, never 0.
2. The explanations use the JEG-1212 terms (DDF Value, DDF Projections; Projections, Published charts, Observed-trade
   estimates) and name no publisher; nothing claims a platform account or connection.
3. The local-data contracts Settings presents are unchanged and round-trip: the league file (TradeValueWorkspace
   exportJson -> importJson) and the league link (shareHash -> decodeShare, read the way league.js reads it), including
   a kicker's exact identity and the over-budget "my team only" fallback.

Skips when node is missing.
"""
from __future__ import annotations

import functools
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "settings_fieldnotes_logic.cjs"
PUBLISHERS = ("ESPN", "CBS", "Razzball", "USA Today", "FantasyPros", "FantasyCalc")


@functools.lru_cache(maxsize=1)
def results() -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run([node, str(SCRIPT)], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


def actions(section: dict) -> dict:
    return {a["id"]: a["enabled"] for a in section["actions"]}


def rows(vm: dict) -> dict:
    return {r["id"]: r for r in vm["league"]["rows"]}


class ViewModel(unittest.TestCase):
    def test_loading_and_error_say_so_and_show_no_sections(self):
        vm = results()["vm"]
        self.assertEqual(vm["loading"]["status"], "loading")
        self.assertIn("Loading", vm["loading"]["message"])
        self.assertEqual(vm["error"]["status"], "error")
        self.assertIn("The league store did not start.", vm["error"]["message"])
        self.assertEqual(vm["garbage"]["status"], "error")
        for name in ("loading", "error", "garbage"):
            self.assertNotIn("saved", vm[name])

    def test_ready_shows_the_league_and_every_action(self):
        vm = results()["vm"]["ready"]
        self.assertEqual(rows(vm)["saved-league"]["value"], "Synthetic test league · 2 teams · 13 players")
        self.assertEqual(rows(vm)["selected-team"]["value"], "Paper Lions")
        self.assertEqual(rows(vm)["selected-team"]["action"]["text"], "Change team")
        self.assertEqual(rows(vm)["rules"]["value"], "Full PPR · 12 teams · 1 QB")
        self.assertEqual(actions(vm["saved"]), {"exportLeague": True, "importLeague": True, "copyLink": True})
        self.assertEqual(vm["overrides"]["count"], "2 player overrides saved on this device.")
        self.assertEqual(vm["overrides"]["basis"], "Value basis: the default DDF Value.")
        self.assertEqual(actions(vm["overrides"]), {"openOverrides": True, "exportOverrides": True, "importOverrides": True})
        self.assertIn("Sample data", vm["fixture"])
        self.assertIsNone(vm["saved"]["warning"])

    def test_custom_basis_and_one_override(self):
        vm = results()["vm"]["custom_basis"]
        self.assertEqual(vm["overrides"]["count"], "1 player override saved on this device.")
        self.assertEqual(vm["overrides"]["basis"], "Value basis: your own choice of sources and weights.")

    def test_no_team_offers_the_selected_league_entry(self):
        vm = results()["vm"]["no_team"]
        self.assertEqual(rows(vm)["selected-team"]["value"], "No team selected")
        self.assertEqual(rows(vm)["selected-team"]["action"], {"id": "openLeague", "text": "Choose your team", "enabled": True})

    def test_empty_league_cannot_export_or_link_and_says_why(self):
        vm = results()["vm"]["empty"]
        self.assertEqual(actions(vm["saved"]), {"exportLeague": False, "importLeague": True, "copyLink": False})
        self.assertIn("nothing to export or link", vm["saved"]["reason"])
        self.assertEqual(rows(vm)["saved-league"]["value"], "No league saved yet")
        self.assertEqual(rows(vm)["selected-team"]["action"]["text"], "Paste my league")
        self.assertEqual(vm["overrides"]["count"], "No player overrides. Every player uses DDF Value as calculated.")
        self.assertEqual(actions(vm["overrides"]), {"openOverrides": True, "exportOverrides": False, "importOverrides": True})

    def test_missing_counts_and_settings_are_unavailable_never_zero(self):
        vm = results()["vm"]["missing"]
        r = rows(vm)
        self.assertEqual(r["saved-league"]["value"], "Synthetic test league · 2 teams")   # unknown player count left out
        self.assertEqual(r["rules"]["value"], "Unavailable")
        self.assertEqual(vm["overrides"]["count"], "Overrides are unavailable until values load.")
        self.assertIsNone(vm["overrides"]["basis"])
        self.assertEqual(actions(vm["overrides"]), {"openOverrides": True, "exportOverrides": False, "importOverrides": False})
        text = json.dumps(vm)
        self.assertNotIn(" 0 ", text)
        self.assertNotIn("0 players", text)

    def test_unavailable_storage_and_league(self):
        vm = results()["vm"]["unavailable"]
        self.assertIn("Private browsing", vm["saved"]["warning"])
        self.assertIn("Export a file to keep a copy", vm["saved"]["warning"])
        r = rows(vm)
        self.assertEqual(r["saved-league"]["value"], "Unavailable")
        self.assertEqual(r["selected-team"]["value"], "Unavailable")
        self.assertIsNone(vm["saved"]["reason"])
        self.assertIn("storage is full", results()["vm"]["storage_full"]["saved"]["warning"])

    def test_long_names_are_kept_whole(self):
        r = rows(results()["vm"]["long_names"])
        self.assertTrue(r["saved-league"]["value"].startswith("The Extremely Long-Named Synthetic Dynasty League Of Champions"))
        self.assertEqual(r["selected-team"]["value"], "Supercalifragilistic Fixture Falcons With A Very Long Name")


class Terminology(unittest.TestCase):
    def test_jeg1212_terms(self):
        vm = results()["vm"]["ready"]["values"]
        self.assertEqual([v["title"] for v in vm["views"]], ["DDF Value", "DDF Projections", "Combined comparison"])
        self.assertEqual([c["name"] for c in vm["sources"]["categories"]], ["Projections", "Published charts", "Observed-trade estimates"])
        self.assertIn("never zero", vm["points"])
        self.assertIn("not a prediction of acceptance", vm["views"][2]["body"])

    def test_no_publisher_names_or_platform_claims(self):
        text = results()["strings"]
        for name in PUBLISHERS:
            self.assertNotIn(name, text)
        for claim in ("sign in", "log in", "account", "syncs", "connect your"):
            self.assertNotIn(claim, text.lower())
        self.assertIn("doesn't sync", text)
        self.assertIn("a plain URL does not connect tools", text)


class LocalDataContracts(unittest.TestCase):
    def test_league_file_round_trips(self):
        rt = results()["roundTrip"]
        self.assertIsNone(rt["error"])
        self.assertTrue(rt["equal"], "Export then Import changed the league, its teams, rosters, my team or settings")
        self.assertTrue(rt["twice"], "a second Export of an imported league differs")
        self.assertEqual(rt["rejects"], [True, True, True])

    def test_league_link_reopens_the_same_rosters(self):
        link = results()["link"]
        self.assertTrue(link["full"])
        self.assertTrue(link["mineFirst"])
        self.assertTrue(link["sameTeams"])
        self.assertTrue(link["sameKeys"])
        self.assertEqual(link["kicker"], {"key": "x:K:synthetic kicker", "name": "Synthetic Kicker"})
        self.assertEqual(link["settings"], {"scoring": "ppr", "teams": 12, "qb": 1})

    def test_over_budget_link_carries_only_my_team(self):
        link = results()["link"]
        self.assertFalse(link["bigFull"])
        self.assertTrue(link["bigOnlyMine"])

    def test_league_query_reads_for_display_only(self):
        q = results()["query"]
        self.assertEqual(q["fixture"], {"scoring": "ppr", "teams": 12, "qb": 1})
        self.assertEqual(q["superflex"], {"scoring": "half_ppr", "teams": 10, "qb": "superflex"})
        self.assertEqual(q["bad"], [None, None, None])
        self.assertEqual(q["rules"], ["Full PPR · 12 teams · 1 QB", "Standard · 10 teams · Superflex", "Half PPR · 8 teams", None])


if __name__ == "__main__":
    unittest.main()
