"""JEG-438 acceptance: "a test fails if any pipeline matches names any other way".

The one way to match a player name: canonical_players.norm_player_name (the
single normalization rule, suffixes and nicknames included) plus the verified
aliases from lib/player_aliases (tests/test_player_aliases.py guards that
list). Fuzzy matching exists only as the nightly job's provisional proposals
(pipelines/reconcile_player_identity.py), never in a value path.

This scan (pipelines/, producers/, scripts/, ops/, tools/) fails on code that
matches names another way:

  fuzzy     imports a fuzzy-matching library (difflib, rapidfuzz, ...)
  normalizer defines its own name normalizer (norm/normalize/norm_name/
            identity_keys-style function that lowercases, strips or
            regex-cleans text)
  suffix    carries its own generational-suffix regex (jr|sr|ii|iii...)

LEGACY lists the files that predate the rule. It can only shrink: an entry
that no longer violates fails the test until it is removed, and any new file
or new rule in a listed file fails at once. Migrating a remaining LEGACY
matcher (match_source_snapshot, legacy_identity, the staged-bundle producer)
changes its output and needs the 12-combo sweep; tracked as
GAP-IDENTITY-LEGACY-MATCHERS in docs/risk-register.md.

Limits: a one-off lambda or inline `.lower()` used as a join key is not
detected; the rule names in a code review still apply.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("pipelines", "producers", "scripts", "ops", "tools")

FUZZY_MODULES = {"difflib", "rapidfuzz", "fuzzywuzzy", "thefuzz", "jellyfish", "Levenshtein",
                 "textdistance", "fuzzyset", "polyleven"}
NORMALIZER_NAME = re.compile(
    r"^_?(norm|normalize|normalise|canon|clean)(_?(player_?)?name|_plain|_key|_player)?$|"
    r"^_?(norm|normalize|normalise|clean)_?(player_?)?names?$|^_?identity_keys$|^_?name_keys?$")
SUFFIX_RE = re.compile(r"(?i)\bjr\b\s*\\?\.?\??\s*\|\s*sr\b|\bsr\b\s*\|\s*jr\b|\bii\s*\|\s*iii\b")

SANCTIONED = {
    # the single rule and the alias list
    "pipelines/lib/canonical_players.py": {"normalizer", "suffix"},
    # nightly provisional proposals only (identity-fuzzy-001: never written to values)
    "pipelines/reconcile_player_identity.py": {"fuzzy"},
}

# Shrink-only ratchet (GAP-IDENTITY-LEGACY-MATCHERS). 2026-10-08: 8 files
# -> 3. Migrated with identical output on current data: the suffix rules of
# build_ddf_two_tier_leg and legacy_identity (canonical_players
# has_generational_suffix / strip_generational_suffix) and build_player_trace
# (norm_player_name + aliases). Archived (no caller): rebuild_fp_fixture_section,
# rebuild_fp_natives_from_snapshot, refresh_players_espn_fields.
# Each remaining entry would change output if migrated:
LEGACY = {
    # norm_name is the key format of the identity snapshot's chart keys and of
    # espn_projections.csv player_norm, which the ESPN leg joins on.
    "pipelines/lib/legacy_identity.py": {"normalizer"},
    # normalize_name is the `player_norm` label form of the reference savers
    # (a label since JEG-539; only save_cbsros_references still matches on
    # it, LEGACY_INDEX_USERS below) and the chain matcher's own key.
    "pipelines/match_source_snapshot.py": {"normalizer", "suffix"},
    # _norm is the staged bundle's player_key for ESPN rows (loader contract).
    "producers/build_staged_bundle_espn.py": {"normalizer"},
}


# Second shrink-only ratchet (JEG-539): files that resolve player names
# through the legacy name index (match_source_snapshot.normalize_name keys:
# no nickname table, a single same-name row taken at any position) instead of
# lib/canonical_players. A file "uses" it when it builds or calls
# build_name_index, or keys a dict lookup by normalize_name(...). Using
# normalize_name for a `player_norm` label is not matching and is allowed.
# 2026-10-10: 6 files -> 2. Moved to the canonical resolver with identical
# resolved keys on current data: the CBS saver, FantasyCalc saver and
# FantasyPros puller (0 of 139 / 198 / 178 names differ). Razzball moved by
# Jeremy's rule ("Use canonical resolver", 2026-10-10): after the JEG-539
# position fix, 1 of 681 names differs (Max Hurleman, now at review).
LEGACY_INDEX_USERS = {
    # the chain's comparison-snapshot matcher (LEGACY above; GAP-IDENTITY-LEGACY-MATCHERS)
    "pipelines/match_source_snapshot.py",
    # CBS ROS prints Connor Heyward "(FB)" in its TE table; the canonical
    # resolver refuses that position, so moving it would drop a stored player.
    "pipelines/save_cbsros_references.py",
}


def uses_legacy_index(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(a.name == "build_name_index" for a in node.names):
            return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_name_index":
            return True
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        if name == "build_name_index":
            return True
        if (name in ("setdefault", "get") and node.args and isinstance(node.args[0], ast.Call)
                and getattr(node.args[0].func, "id", None) == "normalize_name"):
            return True
    return False


def legacy_index_users() -> set[str]:
    out = set()
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "archive" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                if uses_legacy_index(path.read_text(encoding="utf-8")):
                    out.add(path.relative_to(ROOT).as_posix())
            except SyntaxError:
                continue
    return out


def _cleans_text(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("lower", "casefold", "normalize", "sub", "replace", "translate"):
                return True
    return False


def violations_in(source: str) -> set[str]:
    tree = ast.parse(source)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in FUZZY_MODULES for a in node.names):
                found.add("fuzzy")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in FUZZY_MODULES:
                found.add("fuzzy")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if NORMALIZER_NAME.match(node.name) and _cleans_text(node):
                found.add("normalizer")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SUFFIX_RE.search(node.value):
                found.add("suffix")
    return found


def scan() -> dict[str, set[str]]:
    out = {}
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "archive" in path.parts or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            try:
                found = violations_in(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            found -= SANCTIONED.get(rel, set())
            if found:
                out[rel] = found
    return out


class OneWayToMatchANameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = scan()

    def test_no_new_name_matcher(self):
        new = {f: sorted(r - LEGACY.get(f, set())) for f, r in self.found.items() if r - LEGACY.get(f, set())}
        self.assertEqual(new, {}, "match player names through canonical_players.norm_player_name and "
                                  "lib/player_aliases (fuzzy only in reconcile_player_identity.py)")

    def test_legacy_list_only_shrinks(self):
        stale = {f: sorted(r - self.found.get(f, set())) for f, r in LEGACY.items()
                 if r - self.found.get(f, set())}
        self.assertEqual(stale, {}, "these LEGACY entries no longer violate: remove them so they cannot come back")


class LegacyNameIndexOnlyShrinks(unittest.TestCase):
    """JEG-539: the savers resolve through lib/canonical_players; the legacy name index keeps only
    the files listed in LEGACY_INDEX_USERS, and the list can only shrink."""

    @classmethod
    def setUpClass(cls):
        cls.found = legacy_index_users()

    def test_no_new_user_of_the_legacy_name_index(self):
        self.assertEqual(sorted(self.found - LEGACY_INDEX_USERS), [],
                         "resolve names through canonical_players (save_espn_cbs_references.build_registry / "
                         "resolve_canonical), not a normalize_name index")

    def test_the_list_only_shrinks(self):
        self.assertEqual(sorted(LEGACY_INDEX_USERS - self.found), [],
                         "these files no longer use the legacy name index: remove them from LEGACY_INDEX_USERS")

    def test_the_savers_jeremy_moved_stay_canonical(self):
        for rel in ("pipelines/save_razzball_references.py", "pipelines/save_espn_cbs_references.py",
                    "pipelines/save_fantasycalc_references.py", "ops/watchdog/pull_fantasypros.py",
                    "pipelines/save_usatoday_references.py", "pipelines/save_fantasypros_references.py"):
            with self.subTest(rel=rel):
                self.assertNotIn(rel, self.found)

    def test_the_detector_fires_on_each_form_and_not_on_a_label(self):
        self.assertTrue(uses_legacy_index("from save_espn_cbs_references import build_name_index\n"))
        self.assertTrue(uses_legacy_index("idx = mod.build_name_index(rows)\n"))
        self.assertTrue(uses_legacy_index("index.setdefault(normalize_name(n), []).append(r)\n"))
        self.assertTrue(uses_legacy_index("hit = index.get(normalize_name(n))\n"))
        self.assertFalse(uses_legacy_index("row = {'player_norm': normalize_name(n)}\n"))


class TheScanDiscriminatesTest(unittest.TestCase):
    """Each rule fires on the pattern it names and not on its neighbour."""

    def test_fuzzy_import(self):
        self.assertEqual(violations_in("import difflib\n"), {"fuzzy"})
        self.assertEqual(violations_in("from rapidfuzz import process\n"), {"fuzzy"})
        self.assertEqual(violations_in("import json\n"), set())

    def test_private_normalizer(self):
        bad = "def norm_name(n):\n    return n.lower().strip()\n"
        nested = "def f(rows):\n    def normalize(s):\n        return s.replace('.', '')\n    return normalize\n"
        self.assertEqual(violations_in(bad), {"normalizer"})
        self.assertEqual(violations_in(nested), {"normalizer"})
        self.assertEqual(violations_in("def identity_keys(n):\n    return [n.lower()]\n"), {"normalizer"})
        # neighbours: a non-name normalizer, and a name helper that only delegates
        self.assertEqual(violations_in("def normalize_scoring(v):\n    return v.lower()\n"), set())
        self.assertEqual(violations_in("def norm_name(n):\n    return norm_player_name(n)\n"), set())

    def test_suffix_regex(self):
        self.assertEqual(violations_in("import re\nR = re.compile(r'\\s(jr|sr|ii|iii|iv|v)\\.?$')\n"), {"suffix"})
        self.assertEqual(violations_in("R = r'\\b(jr|sr|ii|iii|iv)\\.?\\b'\n"), {"suffix"})
        self.assertEqual(violations_in("TEAMS = 'jax|sf'\n"), set())

    def test_shared_suffix_helpers_match_the_rules_they_replaced(self):
        # build_ddf_two_tier_leg tested r"\s(jr|sr|ii|iii|iv|v)\.?$" on
        # lowercased player_norm labels; legacy_identity stripped
        # r"\s+(jr|sr|ii|iii|iv|v)$". The shared helpers must agree on both.
        import sys
        sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
        from canonical_players import has_generational_suffix, strip_generational_suffix
        old_leg = re.compile(r"\s(jr|sr|ii|iii|iv|v)\.?$")
        old_strip = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")
        for label in ("kenneth walker iii", "travis etienne jr.", "travis etienne jr", "marvin harrison jr",
                      "kenneth walker", "aj brown", "brian thomas", "will levis", "devon achane",
                      "patrick mahomes ii", "odell beckham", "jr.", "michael pittman jr  "):
            with self.subTest(label=label):
                self.assertEqual(has_generational_suffix(label), bool(old_leg.search(label)))
                self.assertEqual(strip_generational_suffix(label), old_strip.sub("", label))
        self.assertTrue(has_generational_suffix("Kenneth Walker III"))
        self.assertFalse(has_generational_suffix("Steve Smith Sr Fan"))

    def test_a_new_file_with_its_own_matcher_fails_the_ratchet(self):
        found = {"pipelines/new_saver.py": {"normalizer"}}
        new = {f: r - LEGACY.get(f, set()) for f, r in found.items() if r - LEGACY.get(f, set())}
        self.assertTrue(new)


if __name__ == "__main__":
    unittest.main()
