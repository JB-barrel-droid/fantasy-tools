"""GAP-CBSROS-BAKE-IDENTITY: the browser's CBS ROS pool (players.json
cbsros_ppg, baked from export_cbsros_snapshot.py) must hold the same players
as the chain's CBS ROS legs.

Root cause (2026-10-08 chain run, post-rebuild validate red): the
2026-10-08 save was the first to store 'chigoziem okonkwo' (Chig Okonkwo,
4247 TE) and 'mitch trubisky' (Mitchell Trubisky, 4214 QB), resolved by the
saver through the verified ALIASES in build_ddf_two_tier_leg. The legs
resolve the same spellings through the same ALIASES and priced both. The
exporter dropped the saved player_key and the bake re-resolved the saved
player_norm by name through the canonical registry, which has no such
alias, so both were "unresolved" and missing from players.json. Okonkwo
(6.97 PPR ppg) sits inside the 14-team TE bench, so the browser's TE waiver
line fell one player (6.462 -> 6.108) and every live TE value at full_14
moved, up to 3.72 points against the section (tests.test_cbsros_8t_qb).

Fix: the exporter and the Supabase import carry the saver's player_key, and
bake_players._intake_cbsros prices by it (name resolution only for rows
without one), the same as the Razzball intake.

Negative-tested: dropping "player_key" from export_cbsros_snapshot's rows,
or reverting _intake_cbsros to name-only resolution, fails the tests below.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import bake_players  # noqa: E402
import export_cbsros_snapshot  # noqa: E402
from build_ddf_two_tier_leg import ALIASES, FixtureIdentity  # noqa: E402
from canonical_players import Registry  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"


def registry_from_players() -> Registry:
    """The canonical registry built from players.json (canonical full names)."""
    players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
    return Registry([{"player_key": p["player_key"], "full_name": p["name"],
                      "position": p["pos"], "active": True} for p in players])


def saved_row(key: int, norm: str) -> dict:
    """A public.cbs_ros_projections row as the exporter selects it."""
    return {"player_key": key, "player_norm": norm, "per_game_standard": 5.0,
            "per_game_half_ppr": 6.0, "per_game_ppr": 7.0, "gp": 13,
            "cbs_snapshot_date": "2026-10-08"}


def bake_keys(snapshot: dict, registry: Registry) -> set[int]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        med, _vintage = bake_players._intake_cbsros(path, registry)
    return set(med)


class CbsRosBakeIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = registry_from_players()
        cls.ident = FixtureIdentity.from_fixture(FIXTURE)
        players = json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
        cls.pos = {p["player_key"]: p["pos"] for p in players}

    def test_real_2026_10_08_rows(self):
        # The two rows that broke the 2026-10-08 chain run, as saved.
        rows = [saved_row(4247, "chigoziem okonkwo"), saved_row(4214, "mitch trubisky")]
        snap = export_cbsros_snapshot.build_snapshot(rows, self.registry, "2026-10-08")
        self.assertEqual([r.get("player_key") for r in snap["rows"]], [4247, 4214])
        self.assertEqual(bake_keys(snap, self.registry), {4247, 4214})

    def test_bake_pool_equals_leg_pool_for_every_alias(self):
        # Every verified ALIASES spelling the leg resolves to a fixture key
        # must reach players.json under the same key through export + bake.
        checked = 0
        for spelling in sorted(ALIASES):
            for pos in ("QB", "RB", "WR", "TE"):
                key, _how, _alias = self.ident.resolve(spelling, pos)
                if key is None or self.pos.get(key) != pos:
                    continue
                checked += 1
                with self.subTest(spelling=spelling, pos=pos):
                    snap = export_cbsros_snapshot.build_snapshot(
                        [saved_row(key, spelling)], self.registry, "2026-10-08")
                    self.assertEqual(bake_keys(snap, self.registry), {key},
                                     f"{spelling!r}: leg prices {key}, the bake does not")
        self.assertGreaterEqual(checked, 4)

    def test_row_without_key_still_resolves_by_name_fail_closed(self):
        snap = {"vintage_date": "2026-10-08", "rows": [
            {"player_name": "Chig Okonkwo", "pos": "TE", "per_game_standard": 5.0,
             "per_game_half_ppr": 6.0, "per_game_ppr": 7.0},
            {"player_name": "Nobody Known Here", "pos": "TE", "per_game_standard": 5.0,
             "per_game_half_ppr": 6.0, "per_game_ppr": 7.0},
        ]}
        self.assertEqual(bake_keys(snap, self.registry), {4247})


if __name__ == "__main__":
    unittest.main()
