"""JEG-438 guard: one player-name resolver.

"All partial solves for player name should be replaced with a tie to the player
name table" (Jeremy, 2026-10-07). Every pipeline that matches a player NAME must
go through pipelines/lib/player_resolver.py. This test scans the trade-chart
pipeline code (pipelines/, producers/) and fails on any other way of matching
names:

  - defining a name normalizer or matcher (normalize_name, norm_plain, _norm,
    identity_keys, resolve_name, resolve_identity, ...);
  - importing the retired helpers (canonical_players.norm_plain /
    norm_player_name, layered_identity, match_source_snapshot.normalize_name,
    build_ddf_two_tier_leg.ALIASES);
  - a hand-kept spelling map (ALIASES = {...}) or a read of the retired identity
    files (player_identity_map.json, sleeper_identity_base.json).

LEGACY is the ratchet: offenders not yet migrated, each with the reason. A new
offender fails; a LEGACY entry that no longer offends also fails (delete it), so
the list only shrinks. Negative tests below prove each detector fires.

Out of scope (separate products, not the trade-value chart): waiver_wire/ and
weekly_vegas/. Tracked in docs/risk-register.md GAP-IDENTITY-LEGACY.
"""
import ast
import re
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ("pipelines", "producers")
RESOLVER = "pipelines/lib/player_resolver.py"

DEF_RE = re.compile(
    r"^_?(norm|normalize|normalise)(_?(player_?)?names?|_plain|_player_name|_case_only)?$"
    r"|^identity_keys$|^_?resolve_(identity|name|key|sleeper|manual|names)$|^_?name_keys?$"
    r"|^compact$|^_norm_index$|^normalize_phrase$")
RETIRED_IMPORTS = {
    "norm_plain", "norm_player_name", "layered_identity", "resolve_sleeper", "resolve_manual",
    "resolve_identity", "sleeper_candidates", "normalize_name", "ALIASES", "identity_map_guard",
}
RETIRED_FILES = ("player_identity_map.json", "sleeper_identity_base.json")
ALIAS_ASSIGN_RE = re.compile(r"^[A-Z_]*ALIASES?$")

# Files that may keep a hit, and why. Shrinks to empty as call sites migrate.
LEGACY: dict[str, set[str]] = {
    "pipelines/bake_players.py": {'import:norm_plain'},
    "pipelines/build_cbsros_ddf_leg.py": {'import:ALIASES'},
    "pipelines/build_ddf_two_tier_leg.py": {'aliases:ALIASES'},
    "pipelines/build_espn_input_comparison.py": {'import:norm_player_name'},
    "pipelines/build_player_trace.py": {'def:norm_name'},
    "pipelines/build_razzball_ddf_leg.py": {'import:ALIASES'},
    "pipelines/build_source_value_lineage.py": {'import:norm_player_name'},
    "pipelines/ingest_player_news.py": {'def:normalize_phrase'},
    "pipelines/lib/canonical_players.py": {'def:norm_plain', 'def:norm_player_name', 'file:player_identity_map.json'},
    "pipelines/lib/identity_map_guard.py": {'def:_norm_index', 'def:norm_case_only', 'file:player_identity_map.json'},
    "pipelines/lib/layered_identity.py": {'def:resolve_identity', 'def:resolve_manual', 'def:resolve_sleeper', 'file:player_identity_map.json', 'file:sleeper_identity_base.json', 'import:norm_plain'},
    "pipelines/load_ddf_leg_to_supabase.py": {'import:norm_plain'},
    "pipelines/match_source_snapshot.py": {'def:identity_keys', 'def:normalize_name', 'def:resolve_identity', 'file:player_identity_map.json', 'import:layered_identity', 'import:norm_plain', 'import:resolve_sleeper'},
    "pipelines/pull_cbs_ros_projections.py": {'import:norm_plain'},
    "pipelines/pull_espn_projections.py": {'def:resolve_identity', 'file:player_identity_map.json'},
    "pipelines/pull_razzball_ros.py": {'import:norm_plain'},
    "pipelines/rebuild_fp_fixture_section.py": {'def:normalize'},
    "pipelines/rebuild_fp_natives_from_snapshot.py": {'def:normalize'},
    "pipelines/refresh_fantasycalc_supabase.py": {'def:normalize_name'},
    "pipelines/refresh_players_espn_fields.py": {'def:norm'},
    "pipelines/review_comparison_candidate.py": {'import:norm_player_name'},
    "pipelines/save_cbsros_references.py": {'def:resolve_name', 'import:ALIASES', 'import:normalize_name'},
    "pipelines/save_espn_cbs_references.py": {'def:resolve_name', 'import:ALIASES', 'import:normalize_name'},
    "pipelines/save_fantasycalc_references.py": {'import:ALIASES', 'import:normalize_name'},
    "pipelines/save_fantasypros_references.py": {'import:normalize_name'},
    "pipelines/save_razzball_references.py": {'def:compact', 'def:resolve_name', 'import:ALIASES', 'import:normalize_name'},
    "pipelines/save_usatoday_references.py": {'import:ALIASES', 'import:normalize_name'},
    "pipelines/scrape_live_source_pages.py": {'import:norm_player_name'},
    "pipelines/translate_via_vorp.py": {'def:resolve_key'},
    "pipelines/vorp_translation/unified.py": {'import:norm_player_name'},
    "producers/build_staged_bundle_espn.py": {'def:_norm', 'file:player_identity_map.json'},
}

# Whole files that ARE identity infrastructure (allowed to name the retired
# things because they retire, export or guard them).
INFRA = {
    RESOLVER,
    "pipelines/export_player_registry.py",
    "pipelines/reconcile_player_identity.py",
    "pipelines/pull_sleeper_identity.py",   # writes sleeper_identity_base.json for the nightly job
    "pipelines/lib/nicknames.py",
}


def offences(path: str, text: str) -> set[str]:
    """Tokens describing every way this file matches names outside the resolver."""
    if path in INFRA:
        return set()
    out = set()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError:
        return {"unparseable"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and DEF_RE.match(node.name):
            out.add(f"def:{node.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[-1] in RETIRED_IMPORTS:
                out.add(f"import:{mod.split('.')[-1]}")
            for alias in node.names:
                if alias.name in RETIRED_IMPORTS:
                    out.add(f"import:{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] in RETIRED_IMPORTS:
                    out.add(f"import:{alias.name.split('.')[-1]}")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and ALIAS_ASSIGN_RE.match(t.id) and isinstance(node.value, ast.Dict):
                    out.add(f"aliases:{t.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for f in RETIRED_FILES:
                if f in node.value:
                    out.add(f"file:{f}")
    return out


def scan_repo() -> dict[str, set[str]]:
    found = {}
    for top in SCAN:
        for p in sorted((ROOT / top).rglob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            if "/_archived/" in rel or "__pycache__" in rel:
                continue
            hits = offences(rel, p.read_text(encoding="utf-8"))
            if hits:
                found[rel] = hits
    return found


class SingleResolverGuard(unittest.TestCase):
    def test_no_pipeline_matches_names_outside_the_resolver(self):
        found = scan_repo()
        new = {p: sorted(h - LEGACY.get(p, set())) for p, h in found.items() if h - LEGACY.get(p, set())}
        self.assertEqual(new, {}, "match player names through pipelines/lib/player_resolver.py "
                                  "(see docs/identity-model.md)")

    def test_legacy_list_only_shrinks(self):
        found = scan_repo()
        stale = {p: sorted(t - found.get(p, set())) for p, t in LEGACY.items() if t - found.get(p, set())}
        self.assertEqual(stale, {}, "these LEGACY entries no longer offend; delete them")


class GuardDiscriminationTest(unittest.TestCase):
    """Each detector fires on the broken state it names."""

    def test_private_normalizer_is_caught(self):
        src = "def normalize_name(v):\n    return v.lower()\n"
        self.assertIn("def:normalize_name", offences("pipelines/x.py", src))
        self.assertIn("def:_norm", offences("pipelines/x.py", "def _norm(n):\n    return n\n"))
        self.assertIn("def:norm_name", offences("pipelines/x.py", "def norm_name(n):\n    return n\n"))

    def test_retired_import_is_caught(self):
        self.assertIn("import:norm_plain",
                      offences("pipelines/x.py", "from lib.canonical_players import norm_plain\n"))
        self.assertIn("import:layered_identity",
                      offences("pipelines/x.py", "from lib import layered_identity\n"))
        self.assertIn("import:ALIASES",
                      offences("pipelines/x.py", "from build_ddf_two_tier_leg import ALIASES\n"))

    def test_hand_kept_alias_map_is_caught(self):
        src = "ALIASES = {'cameron ward': 'cam ward'}\n"
        self.assertIn("aliases:ALIASES", offences("pipelines/x.py", src))

    def test_retired_identity_file_is_caught(self):
        src = "P = 'data/inputs/player_identity_map.json'\n"
        self.assertIn("file:player_identity_map.json", offences("pipelines/x.py", src))

    def test_resolver_calls_are_clean(self):
        src = ("from lib.player_resolver import get_resolver, name_label\n"
               "r = get_resolver()\nk = r.key('Kenny Gainwell', source='x', pos='RB')\n")
        self.assertEqual(offences("pipelines/x.py", src), set())

    def test_new_offender_fails_the_guard(self):
        found = {"pipelines/new_saver.py": {"def:normalize_name"}}
        new = {p: h - LEGACY.get(p, set()) for p, h in found.items() if h - LEGACY.get(p, set())}
        self.assertEqual(new, {"pipelines/new_saver.py": {"def:normalize_name"}})


if __name__ == "__main__":
    unittest.main()
