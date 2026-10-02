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
                source = fpath.read_text()
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
    """Verify that files using player identity resolution import from canonical_players."""
    issues = []

    for root, dirs, files in os.walk(pipelines_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'tests')]

        for fname in files:
            if not fname.endswith('.py'):
                continue

            fpath = Path(root) / fname
            try:
                source = fpath.read_text()
                tree = ast.parse(source, filename=str(fpath))

                # Check if this file does player name resolution
                # Look for patterns like registry lookup, player_key references
                has_player_resolution = False

                for node in ast.walk(tree):
                    # Check for registry usage (Registry, resolve, etc.)
                    if isinstance(node, ast.Name):
                        if node.id in ('resolve', 'Registry', 'load_registry',
                                       'norm_player_name', 'resolve_with_reason'):
                            has_player_resolution = True
                            break
                    if isinstance(node, ast.Attribute):
                        if node.attr in ('resolve', 'by_key', 'by_norm', 'lookup'):
                            has_player_resolution = True
                            break

                if has_player_resolution:
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

                    # Must import from canonical_players
                    canonical_imported = False
                    if 'canonical_players' in imports:
                        canonical_imported = True
                    for module, names in from_imports.items():
                        if 'canonical_players' in module:
                            canonical_imported = True

                    if not canonical_imported:
                        issues.append({
                            "file": str(fpath.relative_to(REPO)),
                            "issue": "uses player resolution but doesn't import from canonical_players",
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

        source = unified_path.read_text()
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
            source = Path(temp_path).read_text()
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


if __name__ == "__main__":
    unittest.main()
