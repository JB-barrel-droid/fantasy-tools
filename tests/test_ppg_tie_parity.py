"""GAP-PPG-TIE-FLIP: the browser splits starters from bench on the same order
the baked ESPN leg does.

The browser's live two-tier pool (curve-widget.js espnProjectionsByPos ->
TwoTier.buildPositionTiers) ranks players by players.json espn_ppg. The baked
leg (build_ddf_two_tier_leg.py) ranks the same players by the unrounded
per-game rate from the ESPN CSV. Until 2026-10-08 the bake rounded espn_ppg to
2 dp, so players the leg tells apart tied in the browser and its id tiebreak
could order them the other way. Jordan Mason (8.6469) and Kyle Monangai
(8.6508) both read 8.65: the leg made Monangai the 10-team standard RB
starter, the browser made Mason the starter, and every bias-adjusted chart
value for the two moved ~10 points (cells are fitted per starter/bench tier).

The pool split uses the leg's own build_position_tiers, which
tests/test_ddf_two_tier_leg.py pins bit-exact to the browser's
TwoTier.buildPositionTiers.

Discrimination (2026-10-08, docs/claude-log/2026-10-08-value-small.md): on
origin/main's players.json (2 dp) test_partition_matches_leg fails at
standard 10-team (Mason/Monangai) and test_ppg_published_unrounded fails;
restoring round(..., 2) in bake_players makes test_bake_keeps_precision fail.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

from build_ddf_two_tier_leg import (  # noqa: E402
    DEFAULT_CSV, DEFAULT_FIXTURE, POSITIONS, REF_FLEX_COUNT, REF_FLEX_ELIGIBLE,
    REF_SLOTS, bench_mix_for_teams, build_position_tiers, load_espn_lists,
    resolve_identities,
)
from games_remaining import PPG_DECIMALS  # noqa: E402

PLAYERS_JSON = ROOT / "data" / "fixtures" / "current" / "players.json"
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)


def split(lists, teams):
    pool = build_position_tiers(lists, teams, dict(REF_SLOTS), REF_FLEX_COUNT,
                                list(REF_FLEX_ELIGIBLE), bench_mix_for_teams(teams))
    return pool["starters"], pool["bench"]


def browser_lists(players, scoring):
    """curve-widget.js espnProjectionsByPos: every skill player with a finite
    espn_ppg for the scoring, keyed by player_key."""
    lists = {pos: [] for pos in POSITIONS}
    for p in players:
        x = (p.get("espn_ppg") or {}).get(scoring)
        if p.get("pos") in lists and isinstance(x, (int, float)):
            lists[p["pos"]].append({"id": p["player_key"], "x": float(x)})
    return lists


class PpgTieParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.players = json.loads(PLAYERS_JSON.read_text(encoding="utf-8"))["players"]
        cls.leg_lists = {}
        for scoring in SCORINGS:
            lists, _, _ = load_espn_lists(DEFAULT_CSV, scoring)
            resolved, _, _ = resolve_identities(lists, DEFAULT_FIXTURE)
            cls.leg_lists[scoring] = {
                pos: [{"id": d["player_key"], "x": d["x"]} for d in resolved[pos]]
                for pos in POSITIONS}

    def test_partition_matches_leg(self):
        bad = []
        names = {p["player_key"]: p["name"] for p in self.players}
        for scoring in SCORINGS:
            browser = browser_lists(self.players, scoring)
            for teams in TEAMS:
                leg_s, leg_b = split(self.leg_lists[scoring], teams)
                web_s, web_b = split(browser, teams)
                for label, a, b in (("starter", leg_s, web_s), ("bench", leg_b, web_b)):
                    if a != b:
                        bad.append((scoring, teams, label,
                                    sorted(names.get(k, k) for k in a - b),
                                    sorted(names.get(k, k) for k in b - a)))
        self.assertEqual(bad, [], "browser starter/bench split differs from the leg "
                                  "(leg-only, browser-only)")

    def test_ppg_published_unrounded(self):
        """espn_ppg carries the leg's per-game rate to PPG_DECIMALS, not 2 dp."""
        leg = {d["id"]: d["x"] for pos in POSITIONS for d in self.leg_lists["ppr"][pos]}
        checked, bad = 0, []
        for p in self.players:
            x = (p.get("espn_ppg") or {}).get("ppr")
            if p["player_key"] not in leg or x is None:
                continue
            checked += 1
            if abs(leg[p["player_key"]] - x) > 0.6 * 10 ** -PPG_DECIMALS:
                bad.append((p["name"], x, leg[p["player_key"]]))
        self.assertGreater(checked, 300)
        self.assertEqual(bad[:5], [], f"{len(bad)} players: espn_ppg is not the leg rate")

    def test_bake_keeps_precision(self):
        """Every per-game rate the bake writes rounds to PPG_DECIMALS."""
        src = (ROOT / "pipelines" / "bake_players.py").read_text(encoding="utf-8")
        for field in ("espn_ppg", "blend_ppg", "pm_ppg", "pm_filled_ppg",
                      "rz_ppg", "cbsros_ppg"):
            line = next(l for l in src.splitlines() if f'row["{field}"] = {{' in l)
            self.assertIn("PPG_DECIMALS", line, f"{field}: {line.strip()}")
        self.assertGreaterEqual(PPG_DECIMALS, 6)


if __name__ == "__main__":
    unittest.main()
