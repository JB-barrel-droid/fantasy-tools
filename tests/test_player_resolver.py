"""JEG-438: the single player-name resolver.

Unit tests run on small synthetic tables (each rule negative-tested against the
broken behaviour it prevents); the snapshot tests pin the committed registry
(data/inputs/player_registry.json): the known-unmatched names now resolve, and
the universe and alias map have not collapsed.
"""
import json
import unittest
from pathlib import Path

from pipelines.lib import player_resolver as pr

ROOT = Path(__file__).resolve().parents[1]

PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True, "team": "BUF"},
    {"player_key": 5001, "full_name": "Josh Allen", "position": "LB", "active": True, "team": "JAX"},
    {"player_key": 785, "full_name": "Kenneth Gainwell", "position": "RB", "active": True, "team": "PIT"},
    {"player_key": 822, "full_name": "Josh Palmer", "position": "WR", "active": False, "team": "BUF"},
    {"player_key": 1347, "full_name": "Trey Palmer", "position": "WR", "active": True, "team": "TB"},
    {"player_key": 7, "full_name": "Ja'Marr Chase", "position": "WR", "active": True, "team": "CIN"},
    {"player_key": 8, "full_name": "Jaxon Smith-Njigba", "position": "WR", "active": True, "team": "SEA"},
    {"player_key": 9, "full_name": "Kenneth Walker III", "position": "RB", "active": True, "team": "KC"},
    {"player_key": 4247, "full_name": "Chig Okonkwo", "position": "TE", "active": True, "team": "TEN"},
    {"player_key": 1268, "full_name": "Jalen Moreno-Cropper", "position": "WR", "active": False, "team": "DAL"},
    {"player_key": 30, "full_name": "Mike Williams", "position": "WR", "active": True, "team": "PIT"},
    {"player_key": 31, "full_name": "Michael Williams", "position": "WR", "active": True, "team": "NE"},
    {"player_key": 40, "full_name": "Marvin Harrison Jr.", "position": "WR", "active": True, "team": "ARI"},
    {"player_key": 41, "full_name": "Marvin Harrison", "position": "WR", "active": False, "team": None},
    {"player_key": 900, "full_name": "Seattle Seahawks", "position": "DST", "active": True, "team": "SEA"},
    {"player_key": 901, "full_name": "Los Angeles Rams", "position": "DST", "active": True, "team": "LA"},
]
ALIASES = [
    {"source": "*", "source_player_name": "Josh Allen", "position": "QB", "player_key": 869, "status": "verified"},
    {"source": "*", "source_player_name": "Chigoziem Okonkwo", "position": "TE", "player_key": 4247, "status": "verified"},
    {"source": "usatoday", "source_player_name": "J. Cropper", "position": "WR", "player_key": 1268, "status": "provisional",
     "confidence": 0.91},
    {"source": "espn", "source_player_name": "Bogus Alias", "position": "", "player_key": 99999, "status": "verified"},
]
XREFS = {"sleeper": {"4984": 869}, "espn": {"3916387": 869}}


def resolver(**kw):
    return pr.PlayerResolver(PLAYERS, ALIASES, XREFS, **kw)


class NormalizationTest(unittest.TestCase):
    def test_norm_key(self):
        self.assertEqual(pr.norm_key("Ja'Marr Chase"), "jamarr chase")
        self.assertEqual(pr.norm_key("Ja’Marr Chase"), "jamarr chase")
        self.assertEqual(pr.norm_key("Amon-Ra St. Brown"), "amon ra st brown")
        self.assertEqual(pr.norm_key("Kenneth Walker III"), "kenneth walker")
        self.assertEqual(pr.norm_key("A.J. Brown"), "aj brown")
        self.assertEqual(pr.norm_key("José Ramos"), "jose ramos")

    def test_nickname_and_compact(self):
        self.assertEqual(pr.nickname_key("kenny gainwell"), "kenneth gainwell")
        self.assertEqual(pr.compact_key("jaxon smith njigba"), "jaxonsmithnjigba")


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.r = resolver()

    def test_canonical_exact_and_punctuation(self):
        for name in ("Ja'Marr Chase", "JaMarr Chase", "Ja Marr Chase"):
            res = self.r.resolve(name, source="t")
            self.assertEqual(res.player_key, 7, name)
        self.assertEqual(self.r.key("Jaxon Smith Njigba", source="t"), 8)
        self.assertEqual(self.r.key("Jaxon SmithNjigba", source="t"), 8)
        self.assertEqual(self.r.key("Kenneth Walker", source="t"), 9)

    def test_nickname_tier(self):
        res = self.r.resolve("Kenny Gainwell", source="t", pos="RB")
        self.assertEqual((res.player_key, res.status, res.method), (785, "exact", "canonical:nickname"))
        self.assertEqual(self.r.key("Joshua Palmer", source="t", pos="WR"), 822)

    def test_exact_spelling_beats_nickname_collision(self):
        # "Mike Williams" and "Michael Williams" collide after nickname expansion;
        # the exact spelling decides, the expanded one stays ambiguous.
        self.assertEqual(self.r.key("Mike Williams", source="t", pos="WR"), 30)
        self.assertEqual(self.r.key("Michael Williams", source="t", pos="WR"), 31)

    def test_ambiguous_fails_closed(self):
        res = self.r.resolve("Josh Allen", source="t", pos=None, record=True)
        # the '*' alias pins the QB when no position is given
        self.assertEqual(res.player_key, 869)
        lb = self.r.resolve("Josh Allen", source="t", pos="LB")
        self.assertEqual(lb.player_key, 5001)
        r2 = pr.PlayerResolver(PLAYERS, [], {})
        amb = r2.resolve("Josh Allen", source="t")
        self.assertIsNone(amb.player_key)
        self.assertEqual(amb.status, "ambiguous")
        self.assertEqual(set(amb.candidates), {869, 5001})

    def test_active_beats_inactive_namesake(self):
        self.assertEqual(self.r.key("Marvin Harrison", source="t", pos="WR"), 40)

    def test_position_conflict(self):
        res = self.r.resolve("Ja'Marr Chase", source="t", pos="RB")
        self.assertIsNone(res.player_key)
        self.assertEqual(res.status, "position_conflict")

    def test_alias_source_then_global(self):
        res = self.r.resolve("Chigoziem Okonkwo", source="fantasycalc", pos="TE")
        self.assertEqual((res.player_key, res.status, res.method), (4247, "verified", "alias:*"))

    def test_alias_to_unknown_key_is_never_trusted(self):
        self.assertIsNone(self.r.key("Bogus Alias", source="espn"))

    def test_cross_id(self):
        res = self.r.resolve("Somebody Else", source="sleeper", source_id="4984")
        self.assertEqual((res.player_key, res.method), (869, "xref:sleeper"))
        res = self.r.resolve("", source="espn_projections", source_id="3916387", id_type="espn")
        self.assertEqual(res.player_key, 869)

    def test_dst(self):
        for raw in ("Seahawks DST", "Seattle", "SEA", "Seattle Seahawks", "Seahawks D/ST"):
            self.assertEqual(self.r.resolve(raw, source="t", pos="DST").player_key, 900, raw)
        self.assertEqual(self.r.resolve("LAR", source="t", pos="DST").player_key, 901)

    def test_provisional_alias_is_flagged(self):
        res = self.r.resolve("J. Cropper", source="usatoday", pos="WR")
        self.assertEqual((res.player_key, res.status), (1268, "provisional"))
        declined = self.r.resolve("J. Cropper", source="usatoday", pos="WR", allow_provisional=False)
        self.assertIsNone(declined.player_key)


class FuzzyTest(unittest.TestCase):
    def test_fuzzy_is_provisional_and_recorded(self):
        r = pr.PlayerResolver(PLAYERS, [], {})
        res = r.resolve("Jalen Cropper", source="cbs", pos="WR")
        self.assertEqual((res.player_key, res.status, res.method), (1268, "provisional", "fuzzy"))
        self.assertGreaterEqual(res.confidence, pr.PROVISIONAL_FLOOR)
        pend = r.pending_rows()
        self.assertEqual(len(pend), 1)
        self.assertEqual((pend[0]["status"], pend[0]["player_key"], pend[0]["source"]),
                         ("provisional", 1268, "cbs"))

    def test_fuzzy_never_guesses_between_close_candidates(self):
        r = pr.PlayerResolver(PLAYERS, [], {})
        # two Palmers: a bare initial is not enough
        res = r.resolve("T. Palmer", source="cbs", pos="WR")
        self.assertIsNone(res.player_key)
        res2 = r.resolve("Zed Palmer", source="cbs", pos="WR")
        self.assertIsNone(res2.player_key)
        self.assertEqual(r.pending_rows()[-1]["status"], "unmatched")

    def test_fuzzy_respects_position(self):
        r = pr.PlayerResolver(PLAYERS, [], {})
        self.assertIsNone(r.resolve("Jalen Cropper", source="cbs", pos="RB").player_key)

    def test_rejected_alias_blocks_fuzzy(self):
        rej = [{"source": "cbs", "source_player_name": "Jalen Cropper", "position": "WR",
                "player_key": 1268, "status": "rejected"}]
        r = pr.PlayerResolver(PLAYERS, rej, {})
        self.assertIsNone(r.resolve("Jalen Cropper", source="cbs", pos="WR").player_key)

    def test_floor_is_enforced(self):
        r = pr.PlayerResolver(PLAYERS, [], {}, provisional_floor=0.99)
        self.assertIsNone(r.resolve("Jalen Cropper", source="cbs", pos="WR").player_key)

    def test_exact_matches_are_never_recorded_as_pending(self):
        r = resolver()
        r.resolve("Ja'Marr Chase", source="t")
        r.resolve("Kenny Gainwell", source="t", pos="RB")
        self.assertEqual(r.pending_rows(), [])


class SnapshotTest(unittest.TestCase):
    """The committed registry snapshot."""

    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "data" / "inputs" / "player_registry.json"
        cls.payload = json.loads(cls.path.read_text(encoding="utf-8"))
        pr.clear_cache()
        cls.r = pr.get_resolver(cls.path)

    def test_schema_and_size(self):
        self.assertEqual(self.payload["schema"], pr.REGISTRY_SCHEMA)
        self.assertGreaterEqual(self.payload["meta"]["n_players"], 4000)
        self.assertGreaterEqual(len(self.payload["xrefs"]["sleeper"]), 3500)
        self.assertGreaterEqual(self.payload["meta"]["n_aliases"], 590)

    def test_known_unmatched_names_resolve(self):
        cases = {
            ("Kenny Gainwell", "RB"): 785, ("Joshua Palmer", "WR"): 822,
            ("Chigoziem Okonkwo", "TE"): 4247, ("Jalen Cropper", "WR"): 1268,
            ("J. Sturdivant", "WR"): 2201, ("Mitch Trubisky", "QB"): 4214,
            ("Audric Estime", "RB"): 4642, ("Tyreek Hill", "WR"): 3081, ("Joe Mixon", "RB"): 3735,
            ("Cameron Ward", "QB"): 697, ("Cam Ward", "QB"): 697,
        }
        for (name, pos), key in cases.items():
            res = self.r.resolve(name, source="test", pos=pos, record=False)
            self.assertEqual(res.player_key, key, f"{name}: {res}")
            self.assertIn(res.status, ("verified", "exact"), f"{name}: {res}")

    def test_every_chart_player_resolves_to_itself(self):
        players = json.loads((ROOT / "data" / "fixtures" / "current" / "players.json").read_text())["players"]
        bad = []
        for p in players:
            res = self.r.resolve(p["name"], source="chart", pos=p.get("pos"), record=False)
            if res.player_key != p["player_key"]:
                bad.append((p["name"], p["player_key"], res.player_key, res.status))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
