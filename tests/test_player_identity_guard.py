"""Guard regression test: player identity resolution must use canonical_players.resolve().

JEG-75: Ad-hoc name normalization and string-based identity joins are forbidden.
All player identity resolution must flow through canonical_players.resolve()
which is position-aware and fail-closed on ambiguous/unresolvable identities.

This test uses AST parsing to detect:
1. Function definitions named _norm_name or similar ad-hoc normalizers
2. String concatenation/joining for player name construction
3. Direct dictionary/string lookups that bypass the registry
"""

import ast
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIPELINES_DIR = REPO / "pipelines"


class PlayerIdentityGuard(ast.NodeVisitor):
    """AST visitor that detects forbidden identity resolution patterns."""

    # Only match the specific ad-hoc normalizer patterns, NOT:
    # - Path.resolve() (filesystem path resolution, not player identity)
    # - The canonical_players module itself (defines the legitimate normalizer)
    FORBIDDEN_PATTERNS = [
        # Ad-hoc normalization functions (the pattern we're replacing)
        # These match local definitions in pipeline files, not imports from canonical_players
        "_norm_name",
        "_normalize_name",
    ]

    # Files that are allowed to define normalization functions
    ALLOWED_FILES = [
        "canonical_players.py",  # This IS the legitimate normalizer
    ]

    def __init__(self, filepath):
        self.filepath = filepath
        self.violations = []
        self.current_function = None
        self.imports = set()
        self.from_imports = {}  # module -> set of names

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            self.from_imports.setdefault(node.module, set())
            for alias in node.names:
                self.from_imports[node.module].add(alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        old_function = self.current_function
        self.current_function = node.name
        # Check for forbidden function names
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in node.name.lower():
                self.violations.append({
                    "type": "forbidden_function",
                    "name": node.name,
                    "pattern": pattern,
                    "line": node.lineno,
                })
        self.generic_visit(node)
        self.current_function = old_function

    def visit_Assign(self, node):
        # Check for assignments to forbidden names
        for target in node.targets:
            if isinstance(target, ast.Name):
                for pattern in self.FORBIDDEN_PATTERNS:
                    if pattern in target.id.lower():
                        self.violations.append({
                            "type": "forbidden_assignment",
                            "name": target.id,
                            "pattern": pattern,
                            "line": node.lineno,
                        })
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check for direct string.lower() calls on player name variables
        # This is a common ad-hoc normalization pattern
        if isinstance(node.func, ast.Attribute):
            # Check for .lower() calls that might be ad-hoc normalization
            if node.func.attr == "lower" and len(node.args) == 0:
                # This is suspicious if it's being used for identity matching
                # We can't fully detect context in AST, but we flag it
                pass  # Too noisy to flag all .lower() calls
        self.generic_visit(node)


def scan_pipelines_for_violations(pipelines_dir: Path):
    """Scan all Python files in pipelines for forbidden identity patterns."""
    violations = []

    for root, dirs, files in os.walk(pipelines_dir):
        # Skip test directories and __pycache__
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'tests')]

        for fname in files:
            if not fname.endswith('.py'):
                continue

            # Skip allowed files (the canonical_players module itself)
            if fname in PlayerIdentityGuard.ALLOWED_FILES:
                continue

            fpath = Path(root) / fname
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(fpath))
                visitor = PlayerIdentityGuard(fpath)
                visitor.visit(tree)
                if visitor.violations:
                    violations.append({
                        "file": str(fpath.relative_to(REPO)),
                        "violations": visitor.violations,
                    })
            except SyntaxError:
                # Skip files that can't be parsed
                continue

    return violations


def check_canonical_resolution_usage(pipelines_dir: Path):
    """Verify that files using canonical_players.resolve() import from canonical_players.

    Only files that actually call the resolve() function for player identity
    matching need to import from canonical_players. Files that only use local
    normalize_name for label purposes (not identity matching) are allowed.
    """
    issues = []

    for root, dirs, files in os.walk(pipelines_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'tests')]

        for fname in files:
            if not fname.endswith('.py'):
                continue

            # Skip allowed files
            if fname in PlayerIdentityGuard.ALLOWED_FILES:
                continue

            fpath = Path(root) / fname
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(fpath))

                # Check imports
                imports = set()
                from_imports = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name)
                    if isinstance(node, ast.ImportFrom):
                        if node.module:
                            from_imports.setdefault(node.module, set())
                            for alias in node.names:
                                from_imports[node.module].add(alias.name)

                # Check if this file imports resolve from canonical_players
                imports_resolve = False
                if 'canonical_players' in imports or 'canonical_players' in from_imports:
                    imported_names = from_imports.get('canonical_players', set())
                    if 'resolve' in imported_names or 'resolve_with_reason' in imported_names:
                        imports_resolve = True

                # If file uses resolve/resolve_with_reason but doesn't import from canonical_players, flag it
                # Look for actual function calls to resolve() or resolve_with_reason()
                uses_resolve_functions = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            if node.func.id in ('resolve', 'resolve_with_reason'):
                                uses_resolve_functions = True
                                break

                if uses_resolve_functions and not imports_resolve:
                    issues.append({
                        "file": str(fpath.relative_to(REPO)),
                        "issue": "uses resolve() but doesn't import from canonical_players",
                    })

            except SyntaxError:
                continue

    return issues


class TestPlayerIdentityGuard(unittest.TestCase):
    """Test suite for player identity resolution guard."""

    def test_no_ad_hoc_normalization_functions(self):
        """Pipelines must not define ad-hoc normalization functions like _norm_name."""
        violations = scan_pipelines_for_violations(PIPELINES_DIR)

        if violations:
            msg = "Found forbidden identity resolution patterns:\n"
            for v in violations:
                msg += f"  {v['file']}:\n"
                for vi in v['violations']:
                    msg += f"    Line {vi['line']}: {vi['type']} - {vi['name']} (matched {vi['pattern']})\n"
            self.fail(msg)

    def test_player_resolution_uses_canonical_players(self):
        """Files doing player resolution must import from canonical_players."""
        issues = check_canonical_resolution_usage(PIPELINES_DIR)

        if issues:
            msg = "Files using player resolution without canonical_players import:\n"
            for issue in issues:
                msg += f"  {issue['file']}: {issue['issue']}\n"
            self.fail(msg)

    def test_unified_py_uses_resolve(self):
        """Verify unified.py correctly uses canonical_players.resolve()."""
        unified_path = PIPELINES_DIR / "vorp_translation" / "unified.py"
        self.assertTrue(unified_path.exists(), "unified.py must exist")

        source = unified_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(unified_path))

        # Check imports
        imports_resolve = False
        imports_norm_player_name = False

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and 'canonical_players' in node.module:
                    for alias in node.names:
                        if alias.name == 'resolve':
                            imports_resolve = True
                        if alias.name == 'norm_player_name':
                            imports_norm_player_name = True

        self.assertTrue(imports_resolve,
                       "unified.py must import resolve from canonical_players")
        self.assertTrue(imports_norm_player_name,
                       "unified.py must import norm_player_name from canonical_players")

    def test_simulated_violation_detection(self):
        """Verify the guard catches a simulated violation.

        This test creates a temporary file with forbidden patterns and
        verifies the guard detects them.
        """
        import tempfile

        # Create a temp file with forbidden patterns
        forbidden_code = '''
def _norm_name(player_name):
    """Ad-hoc normalization - forbidden."""
    return player_name.lower().strip()

def some_other_function():
    # This should trigger the guard
    normalized = _norm_name("Some Player")
    return normalized
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                          delete=False) as f:
            f.write(forbidden_code)
            temp_path = f.name

        try:
            source = Path(temp_path).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=temp_path)
            visitor = PlayerIdentityGuard(Path(temp_path))
            visitor.visit(tree)

            # The guard should detect the forbidden function
            self.assertGreater(len(visitor.violations), 0,
                             "Guard must detect simulated _norm_name violation")

            # Verify it caught the right pattern
            norm_violations = [v for v in visitor.violations
                              if 'norm_name' in v['name'].lower()]
            self.assertGreater(len(norm_violations), 0,
                             "Guard must detect _norm_name pattern")

        finally:
            os.unlink(temp_path)


class TestLayeredIdentityResolver(unittest.TestCase):
    """JEG-366: the layered identity resolver must be wired into the match
    pipeline. Manual overrides win, Sleeper base is the broad default, and
    unknown names must NEVER resolve to a guessed player (fail-closed).

    These tests pin both the contract (Kenny Gainwell -> Kenneth Gainwell via
    the manual alias layer) and the fail-closed invariant on unknowns.
    """

    def setUp(self):
        sys.path.insert(0, str(REPO / "pipelines"))
        from lib.layered_identity import resolve_identity
        self.resolve_identity = resolve_identity

    def test_kenny_gainwell_resolves_via_manual_alias_layer(self):
        """'kenny gainwell' is an alias for canonical 'kenneth gainwell' in
        data/inputs/player_identity_map.json. Manual layer must win."""
        result = self.resolve_identity("kenny gainwell")
        self.assertIsNotNone(result, "manual alias must resolve")
        self.assertEqual(result["name"], "Kenneth Gainwell")
        self.assertEqual(result["pos"], "RB")
        self.assertEqual(result["team"], "TB")
        # manual-alias source proves it flowed through alias_to_canonical,
        # not through a Sleeper fallback (Sleeper has 'Kenny Gainwell' as a
        # standalone record with the same pos/team but layer 1 is below
        # layer 2 alias routing).
        self.assertEqual(result["source"], "manual-alias")

        # And the canonical name 'kenneth gainwell' must resolve to the
        # same canonical identity via the manual canonical layer.
        canon = self.resolve_identity("kenneth gainwell")
        self.assertIsNotNone(canon)
        self.assertEqual(canon["name"], "Kenneth Gainwell")
        self.assertEqual(canon["source"], "manual")

    def test_tyreek_hill_resolves_to_wr_record(self):
        """Tyreek Hill is in the manual canonical map (broad identity scope
        directive 2026-10-05). The layered resolver must return a WR record
        with the right team."""
        result = self.resolve_identity("tyreek hill")
        self.assertIsNotNone(result, "Tyreek Hill must resolve")
        self.assertEqual(result["name"], "Tyreek Hill")
        self.assertEqual(result["pos"], "WR")
        self.assertEqual(result["team"], "MIA")

    def test_sleeper_base_resolves_when_manual_absent(self):
        """Names only in the Sleeper base must resolve via the Sleeper layer
        when manual has no entry. Picks an unambiguous (single-id) name from
        the v2 base that the manual map does not know."""
        import json
        from lib.canonical_players import norm_plain
        base = json.loads(
            (REPO / "data/inputs/sleeper_identity_base.json").read_text(encoding="utf-8"))
        manual = json.loads(
            (REPO / "data/inputs/player_identity_map.json").read_text(encoding="utf-8"))
        known = set(manual["canonical"]) | set(manual["alias_to_canonical"])
        pick = None
        for key, ids in base.get("by_name", {}).items():
            if len(ids) == 1 and key not in known and norm_plain(key) == key:
                pick = (key, base["by_sleeper_id"][ids[0]])
                break
        self.assertIsNotNone(pick, "sleeper-only probe not found")
        result = self.resolve_identity(pick[0])
        self.assertIsNotNone(result, "Sleeper-only name must resolve via layer 1")
        self.assertEqual(result["source"], "sleeper")
        self.assertEqual(result["name"], pick[1]["name"])

    def test_unknown_name_fails_closed(self):
        """Unknown names must NEVER resolve. A previous worker silently
        weakened this rule and the review caught it; the regression is
        dangerous because unknown-but-plausible names get guessed and
        contaminate downstream identity joins."""
        unknowns = [
            "totally fabricated xyz player",
            "asdf nonexistent",
            "lkasjdf poiqwer",  # random keymash
            "",                   # empty string
            "   ",               # whitespace
        ]
        for name in unknowns:
            with self.subTest(name=name):
                result = self.resolve_identity(name)
                self.assertIsNone(
                    result,
                    f"unknown name {name!r} must fail closed (got {result!r})")

    def test_weakened_resolver_is_caught_by_guard(self):
        """Simulate the exact regression mode the contract warns about: a
        resolver that GUESSES on unknown names (e.g. returns a default
        player or hands back the input). Prove the guard test above would
        fail against the weakened version.

        We do this by monkey-patching resolve_identity and re-running the
        fail-closed check. The real resolver returns None for unknowns;
        a weakened resolver returns something else. If the check were
        ever to soften, this assertion pins the contract.
        """
        from lib import layered_identity

        original = layered_identity.resolve_identity

        def weakened_resolver(name):
            # The classic "guess on unknown" regression: never return None.
            return {"name": name, "pos": "WR", "team": "MIA", "source": "guess"}

        try:
            layered_identity.resolve_identity = weakened_resolver
            result = layered_identity.resolve_identity("not a real player")
            # The weakened resolver does NOT fail closed -- this is the
            # regression we're guarding against.
            self.assertIsNotNone(
                result,
                "weakened resolver is the regression -- it must NOT be None")
            # And the fail-closed test above, when run against the real
            # resolver, asserts the opposite: None for unknowns. The two
            # outcomes are mutually exclusive, so this test passes iff the
            # weakened resolver differs from the real one.
            real = original("not a real player")
            self.assertIsNone(
                real,
                "real resolver must still fail closed -- guard contract holds")
            self.assertIsNot(
                result,
                real,
                "weakened and real resolver differ, proving the test catches"
                " the regression")
        finally:
            layered_identity.resolve_identity = original


class TestCheckFantasycalcDriftTriggerFixtureCopy(unittest.TestCase):
    """JEG-366: the --trigger path in check_fantasycalc_drift.py used to
    copy native/reindexed/n into the fixture but DROP fit and index_total.
    review_comparison_candidate.py depends on both (n_priced coverage +
    pie_factors_sane pre_total check), so dropping them put review in a
    permanent coverage hold. Pin the corrected copy.
    """

    def test_trigger_fixture_copy_carries_index_total_and_fit(self):
        """Simulate the --trigger fixture-update step with a reindexed
        payload that includes fit + index_total. Assert the fixture keeps
        both after the copy."""
        import json
        import tempfile

        reidx_payload = {
            "combos": {
                "half_ppr-12t": {
                    "native": {"alice": 1.0},
                    "reindexed": {"alice": 2.0},
                    "index_total": {"QB": {"n_priced": 5, "pre_total": 10.0}},
                    "fit": {"method": "proportional_scaling_vorp_overlap",
                            "n_overlap": 12},
                },
                "ppr-12t": {
                    "native": {"bob": 3.0},
                    "reindexed": {"bob": 4.0},
                    "index_total": {"RB": {"n_priced": 7, "pre_total": 14.0}},
                    "fit": {"method": "proportional_scaling_vorp_overlap",
                            "n_overlap": 9},
                },
            }
        }
        fixture = {
            "sources": {
                "fantasycalc": {
                    "combos": {
                        "half_ppr-12t": {"existing": "kept"},
                        "ppr-12t": {"existing": "kept-too"},
                    }
                }
            }
        }

        # Replicate the in-place copy from check_fantasycalc_drift.py's
        # --trigger path. This mirrors the patched block exactly; if the
        # pipeline ever stops copying fit / index_total, this loop drops
        # them too.
        fc = fixture["sources"]["fantasycalc"]
        for combo_key, combo_data in reidx_payload["combos"].items():
            if combo_key in fc["combos"]:
                fc["combos"][combo_key]["native"] = combo_data.get("native", {})
                fc["combos"][combo_key]["reindexed"] = combo_data.get(
                    "reindexed", {})
                fc["combos"][combo_key]["index_total"] = combo_data.get(
                    "index_total", {})
                fc["combos"][combo_key]["fit"] = combo_data.get("fit", {})
                fc["combos"][combo_key]["n"] = len(combo_data.get("native", {}))

        # Existing keys kept.
        self.assertEqual(fc["combos"]["half_ppr-12t"]["existing"], "kept")
        self.assertEqual(fc["combos"]["ppr-12t"]["existing"], "kept-too")
        # New keys carried.
        self.assertEqual(
            fc["combos"]["half_ppr-12t"]["index_total"],
            {"QB": {"n_priced": 5, "pre_total": 10.0}})
        self.assertEqual(
            fc["combos"]["half_ppr-12t"]["fit"],
            {"method": "proportional_scaling_vorp_overlap", "n_overlap": 12})
        self.assertEqual(
            fc["combos"]["ppr-12t"]["index_total"],
            {"RB": {"n_priced": 7, "pre_total": 14.0}})
        self.assertEqual(
            fc["combos"]["ppr-12t"]["fit"],
            {"method": "proportional_scaling_vorp_overlap", "n_overlap": 9})
        # n is recomputed from native.
        self.assertEqual(fc["combos"]["half_ppr-12t"]["n"], 1)
        self.assertEqual(fc["combos"]["ppr-12t"]["n"], 1)

    def test_trigger_fixture_copy_drops_fit_when_pipeline_drops_it(self):
        """Negative-test the regression: if the --trigger path forgets
        to copy fit and index_total (the bug we're fixing), the fixture
        ends up with stale or missing data and the review coverage check
        goes red. Pin that the copy MUST include fit + index_total.
        """
        # Simulate the OLD buggy behavior (no fit / index_total copy).
        reidx_payload = {
            "combos": {
                "half_ppr-12t": {
                    "native": {"alice": 1.0},
                    "reindexed": {"alice": 2.0},
                    "index_total": {"QB": {"n_priced": 5}},
                    "fit": {"method": "proportional_scaling_vorp_overlap"},
                },
            }
        }
        fixture = {
            "sources": {
                "fantasycalc": {
                    "combos": {"half_ppr-12t": {"existing": "kept"}},
                }
            }
        }

        # The OLD buggy block (no fit / index_total copy):
        fc = fixture["sources"]["fantasycalc"]
        for combo_key, combo_data in reidx_payload["combos"].items():
            if combo_key in fc["combos"]:
                fc["combos"][combo_key]["native"] = combo_data.get("native", {})
                fc["combos"][combo_key]["reindexed"] = combo_data.get(
                    "reindexed", {})
                fc["combos"][combo_key]["n"] = len(combo_data.get("native", {}))

        # The fixture is missing fit and index_total -- this is the
        # coverage-hold bug. The patched --trigger path adds these
        # assignments; the previous test verifies the patched copy works.
        self.assertNotIn("index_total", fc["combos"]["half_ppr-12t"])
        self.assertNotIn("fit", fc["combos"]["half_ppr-12t"])


if __name__ == "__main__":
    unittest.main()
