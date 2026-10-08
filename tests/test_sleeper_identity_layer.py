"""JEG-366: the Sleeper identity base layer must never guess.

The v1 base (a9b5b0a) kept the first player seen per name and added
first-initial variants, so resolve_identity("josh allen") returned a
free-agent guard and "j allen" a defensive tackle. These tests pin the v2
contract: names map to every matching id, ambiguity resolves only by
position or by a single rostered player, and anything else is None.
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import pull_sleeper_identity as P  # noqa: E402
import match_source_snapshot as M  # noqa: E402
from lib import layered_identity as L  # noqa: E402

RAW = {
    # Two Josh Allens: the QB and an unrostered TE (v1 kept whichever came first;
    # on the real base it kept a free-agent guard).
    "100": {"full_name": "Josh Allen", "position": "TE", "team": None, "active": False},
    "4984": {"full_name": "Josh Allen", "position": "QB", "team": "BUF", "active": True,
             "espn_id": 3918298},
    # Two RBs named Ronald Jones, both rostered: genuinely ambiguous.
    "200": {"full_name": "Ronald Jones", "position": "RB", "team": "KC", "active": True},
    "201": {"full_name": "Ronald Jones", "position": "RB", "team": "DAL", "active": True},
    # Same-position namesakes, only one rostered.
    "300": {"full_name": "Ronnie Brown", "position": "RB", "team": None, "active": False},
    "301": {"full_name": "Ronnie Brown", "position": "RB", "team": "NYJ", "active": True},
    "400": {"full_name": "Zed Rookie", "position": "WR", "team": "SEA", "active": True},
    "500": {"full_name": "Some Linebacker", "position": "LB", "team": "SEA", "active": True},
}


def v1_first_write_wins(raw):
    """The a9b5b0a builder's name map, reproduced for the negative test."""
    by_name = {}
    for pid, p in raw.items():
        if p["full_name"].lower() not in by_name:
            by_name[p["full_name"].lower()] = [pid]
    return by_name


class SleeperLayerTest(unittest.TestCase):
    def setUp(self):
        self._saved = (L._base, L._manual)
        self.base = P.build_base(RAW, pulled_at="2026-10-05T00:00:00+00:00")
        L._base = self.base
        L._manual = {"canonical": {}, "alias_to_canonical": {}}

    def tearDown(self):
        L._base, L._manual = self._saved

    def test_names_keep_every_id_and_skip_non_fantasy_positions(self):
        self.assertEqual(["100", "4984"], self.base["by_name"]["josh allen"])
        self.assertNotIn("some linebacker", self.base["by_name"])
        self.assertNotIn("j allen", self.base["by_name"])
        self.assertEqual("3918298", self.base["by_sleeper_id"]["4984"]["espn_id"])

    def test_resolution_never_guesses(self):
        cases = {
            ("josh allen", "QB"): "4984",       # position disambiguates
            ("josh allen", None): "4984",       # only rostered Josh Allen
            ("ronnie brown", "RB"): "301",      # retired namesake is not a rival
            ("zed rookie", "WR"): "400",
            ("ronald jones", "RB"): None,       # two rostered RBs: ambiguous
            ("josh allen", "WR"): None,         # no WR by that name
            ("j allen", None): None,            # no initial variants
            ("some linebacker", None): None,    # not a fantasy position
            ("", None): None,
        }
        for (name, pos), want in cases.items():
            with self.subTest(name=name, pos=pos):
                got = L.resolve_identity(name, pos)
                self.assertEqual(want, got and got["sleeper_id"])

    def test_guard_catches_first_write_wins(self):
        """Negative test: with the v1 name map the QB lookup returns the TE."""
        L._base = {**self.base, "by_name": v1_first_write_wins(RAW)}
        got = L.resolve_identity("josh allen", None)
        self.assertEqual("TE", got and got["pos"])

    def test_v1_file_is_ignored_not_trusted(self):
        L._base = None
        saved = L._INPUTS
        with TemporaryDirectory() as tmp:
            Path(tmp, "sleeper_identity_base.json").write_text(json.dumps(
                {"by_name": {"josh allen": {"name": "Josh Allen", "pos": "G", "team": None}}}))
            L._INPUTS = Path(tmp)
            try:
                self.assertIsNone(L.resolve_identity("josh allen"))
            finally:
                L._INPUTS = saved
                L._base = self.base

    def test_partial_pull_fails_closed(self):
        self.assertTrue(P.check_base(self.base))  # 6 players << floor
        with TemporaryDirectory() as tmp:
            raw = Path(tmp, "raw.json")
            out = Path(tmp, "out.json")
            raw.write_text(json.dumps(RAW))
            self.assertEqual(1, P.main(["--from-file", str(raw), "--out", str(out)]))
            self.assertFalse(out.exists())

    def test_committed_base_is_v2_and_sane(self):
        base = json.loads((ROOT / "data/inputs/sleeper_identity_base.json").read_text(encoding="utf-8"))
        self.assertEqual(P.SCHEMA, base["schema"])
        self.assertEqual([], P.check_base(base))

    def test_matcher_uses_sleeper_after_manual_and_tags_it(self):
        with TemporaryDirectory() as tmp:
            players = Path(tmp, "players.json")
            snap = Path(tmp, "snapshot.json")
            players.write_text(json.dumps({"players": [
                {"player_key": 9001, "name": "Zed Rookie", "team": "SEA", "pos": "WR"},
                {"player_key": 9002, "name": "Ronald Jones", "team": "KC", "pos": "RB"},
            ]}))
            snap.write_text(json.dumps({
                "schema": M.INPUT_SCHEMA, "source": "fantasycalc",
                "fetched_at": "2026-10-05T00:00:00Z", "default_scoring": "ppr",
                "default_teams": 12,
                "rows": [{"player_name": "Zed Rookie", "pos": "WR", "value": 5.0},
                         {"player_name": "Ronald Jones", "pos": "RB", "value": 4.0}]}))
            idmap = Path(tmp, "idmap.json")
            idmap.write_text(json.dumps({"canonical": {}, "alias_to_canonical": {}}))
            out = M.match_snapshot(snap, players, idmap)
            off = M.match_snapshot(snap, players, idmap, use_sleeper=False)
        self.assertEqual([(9001, "sleeper")],
                         [(r["player_key"], r["identity_source"]) for r in out["matched_rows"]])
        self.assertEqual(["unknown_identity"], [r["reason"] for r in out["review_rows"]])
        self.assertEqual(1, out["identity_layers"]["sleeper"])
        self.assertEqual([], off["matched_rows"])


if __name__ == "__main__":
    unittest.main()
