"""Snapshot matching must find punctuated and nickname-variant names.

285ab24 (2026-10-05) routed match_source_snapshot through the canonical
identity table but looked names up with normalize_name(), which turns
punctuation into a space ("Ja'Marr" -> "ja marr") while the table is keyed
by canonical_players.norm_plain ("jamarr"). On the FantasyCalc week-4
snapshot that sent 33 rows to review as unknown_identity -- Ja'Marr Chase,
Jaxon Smith-Njigba, Amon-Ra St. Brown, A.J. Brown, C.J. Stroud and six
more -- and the roster join then missed "Cam Ward" / "Cam Skattebo"
because the table's canonical name is "Cameron ...". The coverage gate
would have held FantasyCalc on the next chain run.

These tests use the real identity map. Each fails on the 285ab24 code.
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import match_source_snapshot as M  # noqa: E402

ROSTER = [
    {"player_key": 2730, "name": "Ja'Marr Chase", "team": "CIN", "pos": "WR"},
    {"player_key": 468, "name": "A.J. Brown", "team": "PHI", "pos": "WR"},
    {"player_key": 3289, "name": "Amon-Ra St. Brown", "team": "DET", "pos": "WR"},
    {"player_key": 3247, "name": "Jaxon Smith-Njigba", "team": "SEA", "pos": "WR"},
    {"player_key": 697, "name": "Cam Ward", "team": "TEN", "pos": "QB"},
]
ROWS = [
    ("Ja'Marr Chase", "WR", 2730),
    ("A.J. Brown", "WR", 468),
    ("Amon-Ra St. Brown", "WR", 3289),
    ("Jaxon Smith-Njigba", "WR", 3247),
    ("Cam Ward", "QB", 697),
]


def run_match(rows):
    with TemporaryDirectory() as tmp:
        players = Path(tmp) / "players.json"
        snapshot = Path(tmp) / "snapshot.json"
        players.write_text(json.dumps({"players": ROSTER}), encoding="utf-8")
        snapshot.write_text(json.dumps({
            "schema": M.INPUT_SCHEMA, "source": "fantasycalc",
            "fetched_at": "2026-10-05T00:00:00Z", "default_scoring": "ppr",
            "default_teams": 12,
            "rows": [{"player_name": n, "value": 1.0, "pos": p} for n, p, _ in rows],
        }), encoding="utf-8")
        return M.match_snapshot(snapshot, players)


class MatchIdentityKeysTest(unittest.TestCase):
    def test_punctuated_and_nickname_names_match_their_player_key(self):
        out = run_match(ROWS + [("Totally Fabricated Player", "WR", None)])
        got = {r["source_player_name"]: r["player_key"] for r in out["matched_rows"]}
        self.assertEqual({n: k for n, _, k in ROWS}, got)
        # Fail-closed is preserved: an unknown name is never guessed.
        self.assertEqual(["unknown_identity"], [r["reason"] for r in out["review_rows"]])

    def test_identity_lookup_uses_the_map_key_convention(self):
        imap = M.load_identity_map(M.DEFAULT_IDENTITY_MAP)
        for name in ("Ja'Marr Chase", "A.J. Brown", "C.J. Stroud", "D'Andre Swift"):
            with self.subTest(name=name):
                self.assertIsNotNone(M.resolve_identity(name, imap))

    def test_guard_catches_the_285ab24_lookup(self):
        """Negative test: restore the space-substituting lookup and the
        punctuated rows must fall out again (proves the test above bites)."""
        original = M.identity_keys
        M.identity_keys = lambda name: [M.normalize_name(name)]
        try:
            out = run_match(ROWS)
        finally:
            M.identity_keys = original
        lost = {r["source_player_name"] for r in out["review_rows"]}
        self.assertTrue({"Ja'Marr Chase", "A.J. Brown", "Amon-Ra St. Brown"} <= lost, lost)

    def test_guard_catches_the_raw_name_roster_join(self):
        """Negative test: index the roster by raw name only (285ab24) and
        Cam Ward is lost to no_match."""
        original = M.build_canonical_index
        M.build_canonical_index = lambda records, imap: M.build_name_index(records)
        try:
            out = run_match(ROWS)
        finally:
            M.build_canonical_index = original
        reasons = {r["source_player_name"]: r["reason"] for r in out["review_rows"]}
        self.assertEqual("no_match", reasons.get("Cam Ward"))


if __name__ == "__main__":
    unittest.main()
