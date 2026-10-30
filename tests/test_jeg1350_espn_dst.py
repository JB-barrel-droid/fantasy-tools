"""ESPN team-defense spellings ("Broncos D/ST") resolve to the team defense (JEG-1350).

Defect: norm_player_name keeps the "/", so "Broncos D/ST" normalizes to
"broncos d/st". Neither the DST detection in resolve_with_reason nor the
suffix strip in Registry.lookup_dst knew "d/st", so ESPN's spelling of every
team defense came back unmatched (8 known gaps in the JEG-1202 audit).

The registry here is built offline from the committed players snapshot, so
the keys are the ones the audit grounds (Broncos DST = 60).
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import canonical_players  # noqa: E402

SNAPSHOT = ROOT / "data" / "inputs" / "players_identity_snapshot.json"


class EspnDstSpellingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.reg = canonical_players.load_registry(rows=rows)
        cls.dst = {r["full_name"]: int(r["player_key"]) for r in rows if r["position"] == "DST"}

    def resolve(self, name, pos=None):
        return canonical_players.resolve_with_reason(name, position=pos, registry=self.reg)

    def test_broncos_d_st_resolves_with_and_without_position(self):
        self.assertEqual(self.dst["Denver Broncos"], 60)
        self.assertEqual(self.resolve("Broncos D/ST", "DST"), (60, "dst"))
        self.assertEqual(self.resolve("Broncos D/ST"), (60, "dst"))

    def test_every_team_resolves_from_its_espn_nickname_spelling(self):
        for full, key in self.dst.items():
            nick = full.split(" ")[-1]
            with self.subTest(team=full):
                self.assertEqual(self.resolve(f"{nick} D/ST"), (key, "dst"))
                self.assertEqual(self.resolve(f"{nick} D/ST", "DST"), (key, "dst"))

    def test_the_old_spellings_still_resolve(self):
        # Team abbreviations ("DEN") come from the live teams table, so they
        # are not in this offline registry.
        for name in ("Broncos DST", "Broncos Defense", "Broncos DEF", "Denver Broncos"):
            with self.subTest(name=name):
                self.assertEqual(self.resolve(name, "DST"), (60, "dst"))

    def test_an_unknown_team_d_st_stays_unmatched(self):
        # Fail closed: the new form opens no fuzzy path to some other defense.
        self.assertEqual(self.resolve("Wildcats D/ST"), (None, "unmatched"))
        self.assertEqual(self.resolve("D/ST"), (None, "unmatched"))

    def test_a_skill_player_name_does_not_take_the_dst_path(self):
        # A real player stays on the name path; only the D/ST token sends a
        # name to team defenses.
        self.assertEqual(self.resolve("DeVonta Smith", "WR")[1], "ok")


if __name__ == "__main__":
    unittest.main()
