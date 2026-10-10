"""GAP-POSITION-CONFLICT-NAMES (JEG-539 item 3).

Six public.players rows held a position that ESPN, Razzball and Sleeper's depth
charts contradict, so the canonical resolver refused the publishers' names
(position_conflict) and ESPN stored none of them. The data fix is
supabase/migrations/players_positions_jeg539_20261010.sql.

This pins the migration to the committed Sleeper identity base: each corrected
position is the position Sleeper lists for that player, and the publishers'
listed positions resolve once the rows carry it.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import canonical_players  # noqa: E402

MIGRATION = ROOT / "supabase" / "migrations" / "players_positions_jeg539_20261010.sql"
SLEEPER = ROOT / "data" / "inputs" / "sleeper_identity_base.json"

# (player_key, name, old position, position ESPN / Razzball list) as found on 2026-10-10
CONFLICTS = (
    (2724, "Brady Russell", "TE", "RB"),
    (914, "Connor Heyward", "TE", "RB"),
    (3963, "Riley Nowakowski", "TE", "RB"),
    (3889, "Colson Yankoff", "RB", "TE"),
    (4000, "Jackson Meeks", "WR", "TE"),
    (3087, "Ty Pezza", "WR", "TE"),
)


def migration_updates() -> dict[int, str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    values = re.search(r"FROM \(VALUES (.*?)\) AS v\(player_key, new_position\)", sql, re.S)
    return {int(k): pos for k, pos in re.findall(r"\((\d+), '([A-Z]+)'\)", values.group(1))}


class PositionConflictNames(unittest.TestCase):
    def test_the_migration_corrects_exactly_the_six_rows_to_the_publishers_position(self):
        self.assertTrue(MIGRATION.exists(), "the position data fix is missing")
        self.assertEqual({k: pos for k, _n, _old, pos in CONFLICTS}, migration_updates())

    def test_each_corrected_position_is_sleepers(self):
        base = json.loads(SLEEPER.read_text(encoding="utf-8"))
        players = base["by_sleeper_id"]
        for key, name, _old, pos in CONFLICTS:
            with self.subTest(name=name):
                ids = base["by_name"][name.lower()]
                self.assertEqual(1, len(ids), f"{name}: Sleeper has namesakes")
                self.assertEqual(pos, players[ids[0]]["pos"])

    def test_the_identity_snapshot_agrees(self):
        """The ESPN puller checks positions against data/inputs/player_identity_map.json first: the
        04:46Z sync after the fix stored Russell, Yankoff, Nowakowski and Meeks, but dropped Connor
        Heyward ("identity-pos-mismatch: ESPN=RB registry=TE")."""
        snap = json.loads((ROOT / "data" / "inputs" / "player_identity_map.json").read_text(encoding="utf-8"))
        for _key, name, _old, pos in CONFLICTS:
            entry = snap["canonical"].get(name.lower())
            if entry is None:
                continue
            with self.subTest(name=name):
                self.assertEqual(pos, entry["pos"])

    def test_the_publishers_names_resolve_after_the_fix_and_not_before(self):
        before = canonical_players.Registry(
            [{"player_key": k, "full_name": n, "position": old, "active": True} for k, n, old, _p in CONFLICTS])
        updates = migration_updates() if MIGRATION.exists() else {}
        after = canonical_players.Registry(
            [{"player_key": k, "full_name": n, "position": updates.get(k, old), "active": True}
             for k, n, old, _p in CONFLICTS])
        for key, name, _old, pos in CONFLICTS:
            with self.subTest(name=name):
                self.assertEqual((None, "position_conflict"),
                                 canonical_players.resolve_with_reason(name, pos, registry=before))
                self.assertEqual((key, "ok"), canonical_players.resolve_with_reason(name, pos, registry=after))


class PulseKeepsAPositionConflictStoredByKey(unittest.TestCase):
    """After the fix, CBS rest of season still prints "Connor Heyward (FB)" in its TE table, while
    public.players says RB. Its saver stores him under his key, and its stored rows carry no name or
    position, so the pulse cannot match the page row by stored name. Without a fallback he read as
    "stored player not on the page" and an unresolved page name: a red that would hold CBS rest of
    season on correct data."""

    def test_a_page_name_refused_on_position_matches_the_stored_key_of_that_name(self):
        sys.path.insert(0, str(ROOT / "pipelines"))
        from tests import test_fidelity_pulse as T  # noqa: PLC0415
        env = T.ProjEnv()
        name, _pos, vals = env.pub[2]
        env.pub[2] = (name, "TE", vals)  # the page lists Gibbs (RB in public.players) in its TE table
        r, _ = env.run()
        s1 = r["stages"]["publisher_vs_stored"]
        self.assertEqual("green", s1["status"], s1["summary"])
        self.assertEqual(0, s1["counts"]["unresolved_names"])
        self.assertIsNone(r["hold"])

    def test_a_refused_name_whose_key_is_not_stored_stays_unresolved(self):
        from tests import test_fidelity_pulse as T  # noqa: PLC0415
        env = T.ProjEnv()
        name, _pos, vals = env.pub[2]
        env.pub[2] = (name, "TE", vals)
        env.stored = [r for r in env.stored if r["player_key"] != 2]
        r, _ = env.run()
        self.assertEqual(1, r["stages"]["publisher_vs_stored"]["counts"]["unresolved_names"])


if __name__ == "__main__":
    unittest.main()
