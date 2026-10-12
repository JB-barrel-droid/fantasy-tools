"""JEG-606: universe_only players' team matches their roster status,
and their DDF Value is 0 (not null).

Fixture-level guard: reads data/fixtures/current/players.json and
verifies that every universe_only player's team field agrees with
the team embedded in its unpriced_reason (the Sleeper roster team).
Free agents (unpriced_reason starts with "Free agent") must have
team == "".

Negative-tested: test_broken_state_is_detected injects the pre-fix
stale-team pattern (team from registry, not Sleeper) and confirms
the guard catches it.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "current" / "players.json"


def _load_universe_only():
    with open(FIXTURE) as f:
        data = json.load(f)
    return [p for p in data.get("players", []) if p.get("universe_only")]


def _extract_reason_team(reason: str) -> str | None:
    """Extract the team code from an unpriced_reason like 'Practice squad (LV).'"""
    m = re.search(r"\(([A-Z]{2,3})\)", reason)
    return m.group(1) if m else None


def _check_teams(players: list[dict]) -> list[str]:
    """Return a list of mismatch descriptions."""
    mismatches = []
    for p in players:
        reason = p.get("unpriced_reason", "")
        team = p.get("team", "")
        if reason.startswith("Free agent"):
            if team:
                mismatches.append(
                    f"{p['name']}: free agent but team={team!r}")
        else:
            expected = _extract_reason_team(reason)
            if expected and expected != team:
                mismatches.append(
                    f"{p['name']}: team={team!r} but reason says {expected}")
    return mismatches


class UnpricedTeamFixtureTest(unittest.TestCase):
    """Guard: every universe_only player's team matches its roster status."""

    @classmethod
    def setUpClass(cls):
        if not FIXTURE.exists():
            raise unittest.SkipTest("players.json fixture not present")
        cls.players = _load_universe_only()

    def test_universe_only_players_exist(self):
        self.assertGreater(len(self.players), 0,
                           "No universe_only players in fixture")

    def test_team_matches_roster_status(self):
        mismatches = _check_teams(self.players)
        self.assertEqual([], mismatches,
                         f"{len(mismatches)} team mismatches:\n"
                         + "\n".join(mismatches[:20]))

    def test_every_unpriced_has_a_reason(self):
        missing = [p["name"] for p in self.players
                   if not p.get("unpriced_reason")]
        self.assertEqual([], missing)


class NegativeTest(unittest.TestCase):
    """The guard catches the broken state (stale team from registry)."""

    def test_broken_state_is_detected(self):
        broken = [
            {"name": "Phillip Dorsett", "team": "ATL",
             "unpriced_reason": "Practice squad (LV). No chart or projection prices this player.",
             "universe_only": True},
            {"name": "Trey Sermon", "team": "IND",
             "unpriced_reason": "Injured reserve (ATL). No chart or projection prices this player.",
             "universe_only": True},
        ]
        mismatches = _check_teams(broken)
        self.assertEqual(2, len(mismatches),
                         "Guard must detect stale-team mismatches")

    def test_free_agent_with_stale_team_is_detected(self):
        broken = [
            {"name": "Old Player", "team": "NYJ",
             "unpriced_reason": "Free agent. No chart or projection prices this player.",
             "universe_only": True},
        ]
        mismatches = _check_teams(broken)
        self.assertEqual(1, len(mismatches))


if __name__ == "__main__":
    unittest.main()
