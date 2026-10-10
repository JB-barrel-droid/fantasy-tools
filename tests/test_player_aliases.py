"""One verified alias list for every player-name resolver (GAP-CBSROS-BAKE-IDENTITY).

Defect: the repo had two alias lists. build_ddf_two_tier_leg.ALIASES fed the
reference savers and the DDF legs; data/inputs/player_identity_map.json
alias_to_canonical fed the players.json bake (canonical_players), the
comparison-snapshot matcher and the ESPN pull. An alias added to one only
("chigoziem okonkwo", "mitch trubisky" on 2026-10-08) let the leg price a
player the bake dropped, and every 14-team TE value moved.

Now data/inputs/player_aliases.json is the only list and lib/player_aliases.py
the only reader. These tests:
  * inject a synthetic alias into the shared list and require EVERY resolver
    to resolve it (a resolver on a private list cannot see it), and require
    each to resolve nothing for the same spelling without it (no fuzzy match);
  * scan the code for a private name->name map or a second reader;
  * require the identity map's alias_to_canonical to hold only mechanical
    variants (same norm_player_name form), so no curated alias hides there;
  * check every entry against the chart's public.players mirror.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import player_aliases  # noqa: E402
import canonical_players  # noqa: E402
from canonical_players import Registry, norm_player_name, norm_plain, narrow_candidates  # noqa: E402
import build_ddf_two_tier_leg  # noqa: E402
import save_espn_cbs_references  # noqa: E402
import save_cbsros_references  # noqa: E402
import save_razzball_references  # noqa: E402
import legacy_identity  # noqa: E402
import layered_identity  # noqa: E402
import match_source_snapshot  # noqa: E402
import bake_players  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
IDENTITY_MAP = ROOT / "data" / "inputs" / "player_identity_map.json"

SYNTHETIC = "Zebulon Quixotic"   # nobody's name; normalizes to itself
TARGET_KEY, TARGET_NAME, TARGET_POS = 4214, "Mitchell Trubisky", "QB"


def players_rows() -> list[dict]:
    return json.loads(PLAYERS.read_text(encoding="utf-8"))["players"]


def registry_rows() -> list[dict]:
    return [{"player_key": p["player_key"], "full_name": p["name"],
             "position": p["pos"], "active": True} for p in players_rows()]


def saver_rows() -> list[dict]:
    return [{"player_key": p["player_key"], "full_name": p["name"],
             "position": p["pos"], "active": True} for p in players_rows()]


def resolvers() -> dict:
    """name -> callable(raw_name) -> resolved player_key | canonical name | None."""
    ident = build_ddf_two_tier_leg.FixtureIdentity.from_fixture(FIXTURE)
    imap = json.loads(IDENTITY_MAP.read_text(encoding="utf-8"))

    def fixture_leg(n):
        return ident.resolve(norm_plain(n), TARGET_POS)[0]

    def bake(n):
        reg = Registry(registry_rows())   # alias overrides load at init
        return bake_players._resolve_csv_row(n, TARGET_POS, "test", reg)

    def canonical(n):
        return canonical_players.resolve(n, position=TARGET_POS, registry=Registry(registry_rows()))

    def saver_espn(n):
        reg = save_espn_cbs_references.build_registry(saver_rows())
        return save_espn_cbs_references.resolve_canonical(n, TARGET_POS, reg)[0]

    def saver_cbsros(n):
        idx = save_cbsros_references.build_name_index(saver_rows())
        return save_cbsros_references.resolve_name(n, TARGET_POS, idx)[0]

    def saver_razzball(n):
        reg = save_razzball_references.build_registry(saver_rows())
        return save_razzball_references.resolve_name(n, TARGET_POS, reg)[0]

    def legacy_espn_pull(n):
        m = legacy_identity.IdentityMap(chart_keys=imap["canonical"].keys(),
                                        snapshot_path=IDENTITY_MAP)
        key = m.canon(n)
        return key if key in imap["canonical"] else None

    def layered(n):
        hit = layered_identity.resolve_manual(n)
        return hit["name"] if hit else None

    def sleeper(n):
        hit = layered_identity.resolve_sleeper(n, TARGET_POS)
        return hit["name"] if hit else None

    def matcher(n):
        hit = match_source_snapshot.resolve_identity(n, imap)
        return hit["name"] if hit else None

    return {
        "FixtureIdentity (ESPN/CBS ROS/Razzball legs)": (fixture_leg, TARGET_KEY),
        "bake_players intake (ESPN, prediction markets, CBS ROS, Razzball)": (bake, TARGET_KEY),
        "canonical_players.resolve": (canonical, TARGET_KEY),
        "save_espn_cbs_references (ESPN/CBS/FantasyPros/FantasyCalc/USA Today)": (saver_espn, TARGET_KEY),
        "save_cbsros_references": (saver_cbsros, TARGET_KEY),
        "save_razzball_references": (saver_razzball, TARGET_KEY),
        "legacy_identity (pull_espn_projections)": (legacy_espn_pull, "mitchell trubisky"),
        "layered_identity manual layer": (layered, TARGET_NAME),
        "layered_identity Sleeper layer": (sleeper, TARGET_NAME),
        "match_source_snapshot.resolve_identity": (matcher, TARGET_NAME),
    }


class EveryResolverReadsTheSharedList(unittest.TestCase):
    def tearDown(self):
        player_aliases._reset_for_tests(None)

    def inject(self):
        idx = dict(player_aliases.load())
        idx[norm_player_name(SYNTHETIC)] = {"alias": SYNTHETIC, "player_key": TARGET_KEY,
                                            "full_name": TARGET_NAME, "pos": TARGET_POS}
        player_aliases._reset_for_tests(idx)

    def test_unknown_spelling_resolves_nowhere_without_the_alias(self):
        for label, (fn, _want) in resolvers().items():
            with self.subTest(resolver=label):
                self.assertIsNone(fn(SYNTHETIC), f"{label} resolved an unaliased name")

    def test_an_alias_added_to_the_shared_list_reaches_every_resolver(self):
        self.inject()
        for label, (fn, want) in resolvers().items():
            with self.subTest(resolver=label):
                self.assertEqual(fn(SYNTHETIC), want,
                                 f"{label} does not apply data/inputs/player_aliases.json")

    def test_real_aliases_resolve_to_the_same_key_in_the_key_resolvers(self):
        ident = build_ddf_two_tier_leg.FixtureIdentity.from_fixture(FIXTURE)
        reg = Registry(registry_rows())
        saver_reg = save_espn_cbs_references.build_registry(saver_rows())
        keys = {p["player_key"] for p in players_rows()}
        checked = 0
        for e in player_aliases.entries():
            if e["player_key"] not in keys:
                continue
            checked += 1
            with self.subTest(alias=e["alias"]):
                self.assertEqual(canonical_players.resolve(e["alias"], e["pos"], registry=reg), e["player_key"])
                self.assertEqual(save_espn_cbs_references.resolve_canonical(e["alias"], e["pos"], saver_reg)[0],
                                 e["player_key"])
                if e["player_key"] in ident.slug_by_key:
                    self.assertEqual(ident.resolve(norm_plain(e["alias"]), e["pos"])[0], e["player_key"])
        self.assertGreaterEqual(checked, 8)


SCAN_DIRS = ("pipelines", "producers", "scripts", "ops", "tools")
NAME = re.compile(r"^[a-z][a-z'.\-]+( [a-z][a-z'.\-]+)+$")
# Readers of the identity map's mechanical spelling variants (not aliases).
IDENTITY_MAP_READERS = {
    "pipelines/lib/legacy_identity.py", "pipelines/lib/layered_identity.py",
    "pipelines/match_source_snapshot.py", "pipelines/lib/identity_map_guard.py",
    "pipelines/pull_espn_projections.py",
}


def py_files():
    for d in SCAN_DIRS:
        base = ROOT / d
        if base.exists():
            yield from (p for p in base.rglob("*.py") if "archive" not in p.parts)


def saver_resolve(mod, rows, name, pos):
    """One saver's resolver: the canonical registry (ESPN/CBS/FantasyCalc/FantasyPros/USA Today and
    Razzball, JEG-539) or the CBS ROS saver's legacy name index."""
    if mod is save_cbsros_references:
        return mod.resolve_name(name, pos, mod.build_name_index(rows))[0]
    if mod is save_razzball_references:
        return mod.resolve_name(name, pos, mod.build_registry(rows))[0]
    return mod.resolve_canonical(name, pos, mod.build_registry(rows))[0]


class NoPrivateAliasList(unittest.TestCase):
    def test_no_module_defines_a_name_to_name_map(self):
        offenders = []
        for path in py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                pairs = [(k.value, v.value) for k, v in zip(node.keys, node.values)
                         if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                         and isinstance(k.value, str) and isinstance(v.value, str)]
                if any(NAME.match(k) and NAME.match(v) for k, v in pairs):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(offenders, [], "player-name alias map outside data/inputs/player_aliases.json")

    def test_only_lib_player_aliases_reads_the_list_and_nobody_reads_alias_to_canonical_privately(self):
        bad = []
        for path in py_files():
            rel = path.relative_to(ROOT).as_posix()  # allowlists use "/" (Windows runs)
            text = path.read_text(encoding="utf-8")
            if rel != "pipelines/lib/player_aliases.py" and any(
                    isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value.endswith("player_aliases.json")
                    for n in ast.walk(ast.parse(text))):
                bad.append(f"{rel}: reads player_aliases.json directly")
            if re.search(r"\bALIASES\s*=\s*\{", text) and "TEAM_ALIASES" not in text:
                bad.append(f"{rel}: defines ALIASES")
            if re.search(r"import\s+ALIASES|ALIASES\s*\)?\s*#|\bALIASES\.get\(", text):
                bad.append(f"{rel}: uses an ALIASES map")
            if "lib.player_aliases" in text:
                bad.append(f"{rel}: imports lib.player_aliases (second module copy, second cache)")
            reads_map = any(
                (isinstance(n, ast.Constant) and n.value == "alias_to_canonical")
                or (isinstance(n, ast.Attribute) and n.attr == "alias_to_canonical")
                for n in ast.walk(ast.parse(text)))
            if reads_map and rel not in IDENTITY_MAP_READERS:
                bad.append(f"{rel}: reads alias_to_canonical")
        self.maxDiff = None
        self.assertEqual(bad, [])

    def test_identity_map_holds_only_mechanical_variants(self):
        imap = json.loads(IDENTITY_MAP.read_text(encoding="utf-8"))
        curated = {a: t for a, t in imap["alias_to_canonical"].items()
                   if norm_player_name(a) != norm_player_name(t)}
        self.assertEqual(curated, {}, "curated aliases belong in data/inputs/player_aliases.json")


class AliasesAreVerified(unittest.TestCase):
    def test_every_entry_matches_the_players_table_mirror_and_collides_with_nobody(self):
        by_key = {p["player_key"]: p for p in players_rows()}
        by_form: dict[str, set[int]] = {}
        for p in players_rows():
            by_form.setdefault(norm_player_name(p["name"]), set()).add(p["player_key"])
        doc = json.loads((ROOT / "data" / "inputs" / "player_aliases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(doc["aliases"]), len(player_aliases.entries()), "duplicate alias forms")
        for e in doc["aliases"]:
            with self.subTest(alias=e["alias"]):
                self.assertTrue(e.get("verified"), "record how the entry was checked")
                row = by_key.get(e["player_key"])
                if row is not None:
                    self.assertEqual(row["name"], e["full_name"])
                    self.assertEqual(row["pos"], e["pos"])
                others = by_form.get(norm_player_name(e["alias"]), set()) - {e["player_key"]}
                self.assertEqual(others, set(), "alias spelling is another player's name")

    def test_conflicting_entries_fail_closed(self):
        with self.assertRaises(ValueError):
            player_aliases._index([
                {"alias": "Joe Example", "player_key": 1, "full_name": "Joseph Example"},
                {"alias": "Joseph Example", "player_key": 2, "full_name": "Joseph Example"},
            ])


class SleeperBaseSeesEverySpelling(unittest.TestCase):
    """The Sleeper base spells some players the source way ("Kenny Gainwell",
    "Joshua Palmer", "Drew Ogletree") and others the public.players way ("Chig
    Okonkwo", "Mitchell Trubisky"). Either spelling must reach the same id."""

    def test_both_spellings_resolve_to_one_sleeper_player(self):
        for e in player_aliases.entries():
            with self.subTest(alias=e["alias"]):
                a = layered_identity.resolve_sleeper(e["alias"], e["pos"])
                b = layered_identity.resolve_sleeper(e["full_name"], e["pos"])
                self.assertIsNotNone(a)
                self.assertEqual(a["sleeper_id"], b["sleeper_id"])


class DuplicatePlayersRowIsDeterministic(unittest.TestCase):
    """GAP-RAZZBALL-REFRESH-FOLLOWUPS (2): public.players has Audric Estime
    4642 (active) and 1475 "Audric Estimé" (inactive). The savers' accent-
    folding normalization made them one name, so every Razzball save sent him
    to review as ambiguous. Active beats inactive, the canonical rule."""

    ROWS = [
        {"player_key": 1475, "full_name": "Audric Estimé", "position": "RB", "active": False},
        {"player_key": 4642, "full_name": "Audric Estime", "position": "RB", "active": True},
    ]

    def test_each_saver_picks_the_active_row(self):
        for mod in (save_espn_cbs_references, save_cbsros_references, save_razzball_references):
            with self.subTest(saver=mod.__name__):
                self.assertEqual(saver_resolve(mod, self.ROWS, "Audric Estime", "RB"), 4642)

    def test_two_active_namesakes_stay_ambiguous(self):
        rows = [dict(r, active=True) for r in self.ROWS]
        self.assertEqual(narrow_candidates(rows, "RB"), (None, "ambiguous"))

    def test_unknown_active_flag_stays_ambiguous(self):
        rows = [{k: v for k, v in r.items() if k != "active"} for r in self.ROWS]
        self.assertEqual(narrow_candidates(rows, "RB"), (None, "ambiguous"))


class CbsRosNicknameMisses(unittest.TestCase):
    """GAP-CBSROS-NICKNAME-MISSES: the CBS ROS saver (run 37800639004,
    vintage 2026-10-08) left "Christopher Brooks" and "Zonovan Knight"
    unresolved. Its matcher has no nickname folding, so they resolve only
    through a verified alias."""

    CASES = (("Christopher Brooks", "RB", 2515), ("Zonovan Knight", "RB", 868))

    def tearDown(self):
        player_aliases._reset_for_tests(None)

    def resolve_all(self, mods=(save_cbsros_references, save_espn_cbs_references, save_razzball_references)):
        out = {}
        for mod in mods:
            for name, pos, _key in self.CASES:
                out[(mod.__name__, name)] = saver_resolve(mod, saver_rows(), name, pos)
        return out

    def test_the_savers_resolve_both_spellings(self):
        player_aliases._reset_for_tests(player_aliases._index(player_aliases.json_entries()))
        got = self.resolve_all()
        for (mod, name), key in got.items():
            with self.subTest(saver=mod, name=name):
                self.assertEqual(key, dict((n, k) for n, _p, k in self.CASES)[name])

    def test_without_the_aliases_they_stay_unresolved(self):
        # The CBS ROS saver's legacy matcher only. The savers on the canonical resolver (ESPN, CBS,
        # FantasyCalc, FantasyPros, USA Today, Razzball: JEG-539) fold "Christopher" through the
        # curated nickname table.
        names = {norm_player_name(n) for n, _p, _k in self.CASES}
        player_aliases._reset_for_tests({f: e for f, e in player_aliases._index(
            player_aliases.json_entries()).items() if f not in names})
        self.assertEqual(set(self.resolve_all((save_cbsros_references,)).values()), {None})


if __name__ == "__main__":
    unittest.main()
