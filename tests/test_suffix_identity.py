"""GAP-CBSROS-LIVE-POOL: suffixed names must resolve in the DDF legs.

Root cause (2026-10-08): the CBS ROS and Razzball legs joined each source row
to the fixture's player_keys by exact slug. Those sources strip generational
suffixes ('kenneth walker'), while the fixture slugs keep some of them
('kenneth walker iii'), so 16 CBS ROS players (Kenneth Walker III, Michael
Penix Jr., Marvin Harrison Jr., ...) went to review as unresolved_identity.
bake_players.py, which feeds the browser, resolves through norm_player_name
and priced them, so the live CBS ROS pool and the published section differed
and every waiver and starter line moved (Jaxon Smith-Njigba, standard 12
teams: 50.9 live, 40.2 in the section).

The fix is build_ddf_two_tier_leg.FixtureIdentity: exact slug and verified
ALIASES first, then the slug's norm_player_name form, narrowed by position;
more than one key left is ambiguous and excluded. Legs emit the fixture slug
as player_norm so the sections key on the canonical id.

Negative-tested against origin/main 9b97f88: every test below fails there
(suffix rows go to review; 'mike williams' resolves by exact slug although a
same-position 'michael williams' exists; the committed CBS ROS section lacks
the 16 players and the live pool is 3-6 players larger per position).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_cbsros_ddf_leg as cbsros_leg  # noqa: E402
import build_razzball_ddf_leg as razzball_leg  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
HARNESS = ROOT / "tests" / "cbsros_live_section_harness.js"
COMBOS = [f"{s}_{t}" for s in ("full", "half", "standard") for t in (8, 10, 12, 14)]
# Same tolerance as tests/test_cbsros_8t_qb.py. With identical pools the
# residual is players.json's 2-decimal cbsros_ppg against the leg's 3-decimal
# snapshot (max 0.21, standard_8 QB; <= 0.05 when fed the leg's own natives).
# The identity gap this guards was 10.7.
TOL = 0.25

# The 16 CBS ROS spellings the 2026-10-02 leg dropped, with the player_key
# public.cbs_ros_projections stores for each (verified read-only 2026-10-08).
CBSROS_SUFFIX_KEYS = {
    ("marvin harrison", "WR"): 1726, ("brian thomas", "WR"): 1749,
    ("omar cooper", "WR"): 2467, ("michael penix", "QB"): 1765,
    ("chris rodriguez", "RB"): 1218, ("oronde gadsden", "TE"): 1885,
    ("mike washington", "RB"): 2181, ("kenneth walker", "RB"): 1095,
    ("luther burden", "WR"): 2140, ("ted hurst", "WR"): 2259,
    ("ollie gordon", "RB"): 1891, ("thomas fidone", "TE"): 1902,
    ("tyrone tracy", "RB"): 1483, ("harold fannin", "TE"): 2113,
    ("deebo samuel", "WR"): 480, ("lequint allen", "RB"): 1909,
}


def snapshot_rows(entries):
    """Minimal native snapshot rows: (norm, pos, ppg) -> both legs' fields."""
    rows = []
    for norm, pos, ppg in entries:
        rows.append({"player_name": norm, "player_norm": norm, "pos": pos, "team": None,
                     "per_game_standard": ppg, "per_game_half_ppr": ppg, "per_game_ppr": ppg,
                     "rz_std_ppg": ppg, "rz_half_ppr_ppg": ppg, "rz_ppr_ppg": ppg})
    return rows


def write_snapshot(tmp: Path, entries) -> Path:
    path = tmp / "snapshot.json"
    path.write_text(json.dumps({"vintage_date": "2026-10-02",
                                "rows": snapshot_rows(entries)}), encoding="utf-8")
    return path


def write_fixture(tmp: Path, player_keys: dict, key_pos: dict | None) -> Path:
    """A fixture dir: comparison-sources-data.json (+ players.json when key_pos)."""
    fx = tmp / "comparison-sources-data.json"
    fx.write_text(json.dumps({"player_keys": player_keys}), encoding="utf-8")
    if key_pos is not None:
        (tmp / "players.json").write_text(json.dumps(
            {"players": [{"player_key": k, "pos": p} for k, p in key_pos.items()]}),
            encoding="utf-8")
    return fx


def resolved_keys(resolved):
    return {d["player_norm"]: d["player_key"] for rows in resolved.values() for d in rows}


class SuffixVariantsResolve(unittest.TestCase):
    def test_cbsros_suffix_spellings_resolve_to_canonical_keys(self):
        entries = [(norm, pos, 10.0) for (norm, pos) in CBSROS_SUFFIX_KEYS]
        with tempfile.TemporaryDirectory() as d:
            snap = write_snapshot(Path(d), entries)
            for loader in (cbsros_leg.load_cbsros_lists, razzball_leg.load_razzball_lists):
                resolved, review, _, _ = loader(snap, "ppr", FIXTURE)
                with self.subTest(loader=loader.__module__):
                    self.assertEqual([r for r in review if "identity" in r["reason"]], [])
                    got = {(d["source_norm"], d["pos"]): d["player_key"]
                           for rows in resolved.values() for d in rows}
                    self.assertEqual(got, CBSROS_SUFFIX_KEYS)

    def test_every_suffix_form_matches_the_slug(self):
        # Jr / Jr. / Sr. / II / III spellings against slugs that keep or drop them.
        player_keys = {"kenneth walker iii": 1095, "travis etienne": 810,
                       "marvin harrison jr": 1726, "deebo samuel sr": 480}
        key_pos = {1095: "RB", 810: "RB", 1726: "WR", 480: "WR"}
        cases = [("kenneth walker", "RB", 1095), ("kenneth walker iii", "RB", 1095),
                 ("travis etienne jr", "RB", 810), ("travis etienne jr.", "RB", 810),
                 ("marvin harrison", "WR", 1726), ("marvin harrison jr.", "WR", 1726),
                 ("deebo samuel", "WR", 480), ("deebo samuel sr.", "WR", 480)]
        with tempfile.TemporaryDirectory() as d:
            fx = write_fixture(Path(d), player_keys, key_pos)
            for norm, pos, key in cases:
                snap = write_snapshot(Path(d), [(norm, pos, 10.0)])
                resolved, review, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
                with self.subTest(norm=norm):
                    self.assertEqual(review, [])
                    rows = [r for rows in resolved.values() for r in rows]
                    self.assertEqual([r["player_key"] for r in rows], [key])
                    # Sections join on the fixture slug, not the source spelling.
                    self.assertIn(rows[0]["player_norm"], player_keys)


class CollisionsStayAmbiguous(unittest.TestCase):
    def test_same_position_collision_is_excluded(self):
        # Two WRs whose names normalize to one form: neither is guessed, even
        # when the source spelling hits one slug exactly.
        player_keys = {"mike williams": 1, "michael williams": 2}
        with tempfile.TemporaryDirectory() as d:
            fx = write_fixture(Path(d), player_keys, {1: "WR", 2: "WR"})
            snap = write_snapshot(Path(d), [("mike williams", "WR", 9.0)])
            resolved, review, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
            self.assertEqual(resolved_keys(resolved), {})
            self.assertEqual([r["reason"] for r in review], ["ambiguous_identity"])

    def test_suffix_only_difference_is_ambiguous_without_the_suffix(self):
        player_keys = {"byron young": 1, "byron young ii": 2}
        with tempfile.TemporaryDirectory() as d:
            fx = write_fixture(Path(d), player_keys, {1: "RB", 2: "RB"})
            snap = write_snapshot(Path(d), [("byron young", "RB", 9.0)])
            resolved, review, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
            self.assertEqual(resolved_keys(resolved), {})
            self.assertEqual([r["reason"] for r in review], ["ambiguous_identity"])
            # The suffixed spelling names its player exactly.
            snap = write_snapshot(Path(d), [("byron young ii", "RB", 9.0)])
            resolved, review, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
            self.assertEqual(resolved_keys(resolved), {"byron young ii": 2})

    def test_position_disambiguates_and_unknown_position_fails_closed(self):
        player_keys = {"michael carter": 777, "michael carter ii": 661}
        with tempfile.TemporaryDirectory() as d:
            fx = write_fixture(Path(d), player_keys, {777: "RB", 661: "DB"})
            snap = write_snapshot(Path(d), [("michael carter", "RB", 9.0)])
            resolved, _, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
            self.assertEqual(resolved_keys(resolved), {"michael carter": 777})
        with tempfile.TemporaryDirectory() as d:
            fx = write_fixture(Path(d), player_keys, None)  # no positions known
            snap = write_snapshot(Path(d), [("michael carter", "RB", 9.0)])
            resolved, review, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
            self.assertEqual(resolved_keys(resolved), {})
            self.assertEqual([r["reason"] for r in review], ["ambiguous_identity"])

    def test_two_spellings_of_one_player_are_both_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            fx = write_fixture(Path(d), {"kenneth walker iii": 1095}, {1095: "RB"})
            snap = write_snapshot(Path(d), [("kenneth walker", "RB", 15.0),
                                            ("kenneth walker iii", "RB", 12.0)])
            resolved, review, _, _ = cbsros_leg.load_cbsros_lists(snap, "ppr", fx)
            self.assertEqual(resolved_keys(resolved), {})
            self.assertEqual([r["reason"] for r in review],
                             ["duplicate_identity", "duplicate_identity"])


class PublishedCbsRosMatchesLivePool(unittest.TestCase):
    def test_section_prices_every_live_cbsros_player(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        slug_by_key = {k: s for s, k in fixture["player_keys"].items()}
        live = {p["player_key"] for p in json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]
                if p.get("cbsros_ppg") and p.get("pos") in ("QB", "RB", "WR", "TE")}
        for combo in COMBOS:
            values = fixture["sources"]["cbsros"]["combos"][combo]["values"]
            with self.subTest(combo=combo):
                missing = sorted(slug_by_key.get(k, k) for k in live
                                 if slug_by_key.get(k) not in values)
                self.assertEqual(missing, [])

    def test_live_matches_section_on_browser_pool(self):
        out = subprocess.run(["node", str(HARNESS), "browser-pool"], cwd=ROOT,
                             capture_output=True, text=True, timeout=120, check=True)
        result = json.loads(out.stdout)
        for combo in COMBOS:
            for pos, stats in result[combo]["stats"].items():
                with self.subTest(combo=combo, pos=pos):
                    self.assertEqual((stats["nLive"], stats["n"]),
                                     (stats["nSection"], stats["nSection"]),
                                     f"{combo} {pos}: live pool {stats['nLive']}, "
                                     f"section {stats['nSection']}, both {stats['n']}")
                    self.assertLessEqual(stats["maxErr"], TOL,
                                         f"{combo} {pos}: max |live - section| {stats['maxErr']:.3f}")


if __name__ == "__main__":
    unittest.main()
