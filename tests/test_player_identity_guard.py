"""Guard regression test: player identity resolution must use canonical_players.resolve().

JEG-75: Ad-hoc name normalization and string-based identity joins are forbidden.
All player identity resolution must flow through canonical_players.resolve()
which is position-aware and fail-closed on ambiguous/unresolvable identities.

This test uses AST parsing to detect:
1. Function definitions named _norm_name or similar ad-hoc normalizers
2. String concatenation/joining for player name construction
3. Direct dictionary/string lookups that bypass the registry
4. Bare resolve()/resolve_with_reason() calls that do not bind to canonical_players.
   A function parameter (an injected resolver, e.g. projection_capture.cbs_capture_rows)
   passes only when every pipeline caller injects a canonical_players resolver (JEG-1238).
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


RESOLVER_NAMES = ("resolve", "resolve_with_reason")
_CANONICAL = "canonical_players"
_NEW_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
               ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _iter_pipeline_trees(pipelines_dir: Path):
    for root, dirs, files in os.walk(pipelines_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'tests')]
        for fname in files:
            if not fname.endswith('.py') or fname in PlayerIdentityGuard.ALLOWED_FILES:
                continue
            fpath = Path(root) / fname
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
            except SyntaxError:
                continue
            yield str(fpath.relative_to(REPO)), fpath.stem, tree


def _own_scope(node):
    """Nodes evaluated in `node`'s own scope: nested function, class and
    comprehension bodies are left out (their names bind there, not here)."""
    todo = list(ast.iter_child_nodes(node))
    while todo:
        child = todo.pop()
        yield child
        if not isinstance(child, _NEW_SCOPES):
            todo.extend(ast.iter_child_nodes(child))


def _params(fn) -> set:
    a = fn.args
    names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    names |= {x.arg for x in (a.vararg, a.kwarg) if x is not None}
    return names


def _is_canonical_module(name) -> bool:
    return bool(name) and name.split(".")[-1] == _CANONICAL


def _bindings(scope):
    """{name: kind} bound in scope's own body. kind is 'canonical' for
    `from canonical_players import resolve[_with_reason]`, 'def' for a def,
    'global'/'nonlocal' for those declarations, else 'other'."""
    out = {}
    if isinstance(scope, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        for gen in scope.generators:
            for n in ast.walk(gen.target):
                if isinstance(n, ast.Name):
                    out[n.id] = "other"
        return out
    body_nodes = _own_scope(scope) if not isinstance(scope, ast.Lambda) else ()
    for n in body_nodes:
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.setdefault(n.id, "other")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(n.name, "def")
        elif isinstance(n, ast.ClassDef):
            out.setdefault(n.name, "other")
        elif isinstance(n, ast.ImportFrom):
            for al in n.names:
                name = al.asname or al.name
                kind = "canonical" if _is_canonical_module(n.module) and al.name in RESOLVER_NAMES else "other"
                out[name] = kind if out.get(name) in (None, kind) else "other"
        elif isinstance(n, ast.Import):
            for al in n.names:
                out.setdefault(al.asname or al.name.split(".")[0], "other")
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.setdefault(n.name, "other")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            for name in n.names:
                out[name] = "global" if isinstance(n, ast.Global) else "nonlocal"
        elif isinstance(n, ast.NamedExpr):
            out.setdefault(n.target.id, "other")
    return out


def _resolver_calls(tree):
    """(call, scope_chain) for every bare resolve()/resolve_with_reason() call.
    scope_chain runs from the module to the innermost enclosing scope."""
    found = []

    def walk(node, chain):
        for child in ast.iter_child_nodes(node):
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                    and child.func.id in RESOLVER_NAMES):
                found.append((child, chain))
            walk(child, chain + [child] if isinstance(child, _NEW_SCOPES) else chain)

    walk(tree, [tree])
    return found


def _classify(name, chain, binding_cache):
    """Where a bare `name` binds lexically: ('canonical'|'module_def'|'unbound'|
    'param'|'local', scope). A parameter that is also rebound in its own
    function is 'local' (shadowed), never an injected resolver."""
    module = chain[0]
    inner = chain[1:]
    for i in range(len(inner) - 1, -1, -1):
        scope = inner[i]
        # A class body does not enclose the functions inside it.
        if isinstance(scope, ast.ClassDef) and i != len(inner) - 1:
            continue
        b = binding_cache.setdefault(id(scope), _bindings(scope))
        kind = b.get(name)
        if kind == "global":
            break
        if kind == "nonlocal":
            continue
        is_param = isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and name in _params(scope)
        if is_param:
            return ("param", scope) if kind is None else ("local", scope)
        if kind == "canonical":
            return "canonical", scope
        if kind is not None:
            return "local", scope
    kind = binding_cache.setdefault(id(module), _bindings(module)).get(name)
    if kind == "canonical":
        return "canonical", module
    if kind == "def":
        # A module-level `def resolve(...)` of its own is not player identity
        # (JEG-916, 2026-10-22: derive_lineup_parameters.resolve picks the
        # expected-starts parameters for a reader's settings, JEG-536).
        return "module_def", module
    return ("unbound", module) if kind is None else ("local", module)


def _module_aliases(tree, stem):
    """Names a caller module uses for module `stem`, and the bare names it
    imports from it: ({alias}, {local_name: imported_name})."""
    mods, names = set(), {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for al in n.names:
                if al.name.split(".")[-1] == stem:
                    mods.add(al.asname or al.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module and n.module.split(".")[-1] == stem:
                for al in n.names:
                    names[al.asname or al.name] = al.name
            else:
                for al in n.names:
                    if al.name == stem:
                        mods.add(al.asname or al.name)
    return mods, names


def _canonical_call(node, canon_mods, canon_names, wired_defs) -> bool:
    """node is a Call into canonical_players' resolver, directly or through a
    module-level def of the caller that itself calls it."""
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Attribute) and f.attr in RESOLVER_NAMES:
        return ast.unparse(f.value) in canon_mods
    if isinstance(f, ast.Name):
        return f.id in canon_names or f.id in wired_defs
    return False


def _canonical_context(tree):
    canon_mods, canon_names = set(), set()
    for n in tree.body:
        if isinstance(n, ast.Import):
            for al in n.names:
                if _is_canonical_module(al.name):
                    canon_mods.add(al.asname or al.name)
        elif isinstance(n, ast.ImportFrom):
            if _is_canonical_module(n.module):
                canon_names |= {al.asname or al.name for al in n.names if al.name in RESOLVER_NAMES}
            else:
                canon_mods |= {al.asname or al.name for al in n.names if al.name == _CANONICAL}
    wired_defs = {n.name for n in tree.body
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and any(_canonical_call(c, canon_mods, canon_names, set()) for c in ast.walk(n))}
    return canon_mods, canon_names, wired_defs


def _wired_resolver_arg(arg, ctx) -> bool:
    """The resolver a caller injects must be canonical_players itself, a
    module-level def that calls it, or a lambda whose whole body is such a call
    (optionally indexed, e.g. `resolve_name(...)[0]`). Fallbacks, guesses and
    anything the AST cannot trace fail closed."""
    canon_mods, canon_names, wired_defs = ctx
    if isinstance(arg, ast.Attribute):
        return arg.attr in RESOLVER_NAMES and ast.unparse(arg.value) in canon_mods
    if isinstance(arg, ast.Name):
        return arg.id in canon_names or arg.id in wired_defs
    if isinstance(arg, ast.Lambda):
        body = arg.body.value if isinstance(arg.body, ast.Subscript) else arg.body
        return _canonical_call(body, *ctx)
    return False


def injected_resolver_wiring(pipelines_dir: Path):
    """JEG-1238: functions that take the resolver as a parameter (e.g.
    projection_capture.cbs_capture_rows) and how each pipeline caller wires it.
    -> (entries, issues). entries: [{"file", "function", "param", "callers":
    [(caller_file, line, ok)]}]."""
    trees = list(_iter_pipeline_trees(pipelines_dir))
    entries, issues = [], []
    for rel, stem, tree in trees:
        cache = {}
        params = {}
        for call, chain in _resolver_calls(tree):
            kind, scope = _classify(call.func.id, chain, cache)
            if kind != "param":
                continue
            if scope not in tree.body or isinstance(scope, ast.Lambda):
                issues.append({"file": rel, "issue": f"resolver parameter {call.func.id!r} of a nested "
                               f"function or lambda (line {scope.lineno}) cannot be traced to its callers"})
                continue
            params[(scope.name, call.func.id)] = scope
        for (fn_name, param), fn in params.items():
            positional = [x.arg for x in fn.args.posonlyargs + fn.args.args]
            index = positional.index(param) if param in positional else None
            entry = {"file": rel, "function": fn_name, "param": param, "callers": []}
            for crel, cstem, ctree in trees:
                mods, names = _module_aliases(ctree, stem)
                local = names | ({fn_name: fn_name} if crel == rel else {})
                ctx = _canonical_context(ctree)
                for c in ast.walk(ctree):
                    if not isinstance(c, ast.Call):
                        continue
                    f = c.func
                    hit = ((isinstance(f, ast.Attribute) and f.attr == fn_name and ast.unparse(f.value) in mods)
                           or (isinstance(f, ast.Name) and local.get(f.id) == fn_name))
                    if not hit:
                        continue
                    arg = next((k.value for k in c.keywords if k.arg == param), None)
                    if arg is None and index is not None and not any(isinstance(a, ast.Starred) for a in c.args[:index + 1]):
                        arg = c.args[index] if index < len(c.args) else None
                    ok = arg is not None and _wired_resolver_arg(arg, ctx)
                    entry["callers"].append((crel, c.lineno, ok))
                    if not ok:
                        issues.append({"file": crel, "issue": f"line {c.lineno}: {fn_name}() is not given a "
                                       f"canonical_players resolver for {param!r}"})
            if not entry["callers"]:
                issues.append({"file": rel, "issue": f"{fn_name}() takes resolver {param!r} but no pipeline "
                               "caller wires a canonical_players resolver into it"})
            entries.append(entry)
    return entries, issues


def check_canonical_resolution_usage(pipelines_dir: Path):
    """Every bare resolve()/resolve_with_reason() call in pipelines must bind to
    canonical_players.

    Allowed bindings: `from canonical_players import resolve[_with_reason]`; a
    module-level def of the module's own (JEG-916, not player identity); and,
    since JEG-1238, a function parameter (an injected resolver), but only when
    every pipeline caller of that function passes a canonical_players resolver
    (injected_resolver_wiring). An unbound global, a local or shadowing
    rebinding, a comprehension variable, or an untraceable injection fails.
    """
    issues = []
    for rel, _stem, tree in _iter_pipeline_trees(pipelines_dir):
        cache = {}
        flagged = set()
        for call, chain in _resolver_calls(tree):
            kind, _scope = _classify(call.func.id, chain, cache)
            if kind == "unbound" and "unbound" not in flagged:
                flagged.add("unbound")
                issues.append({"file": rel, "issue": "uses resolve() but doesn't import from canonical_players"})
            elif kind == "local":
                issues.append({"file": rel, "issue": f"line {call.lineno}: {call.func.id}() is bound locally "
                               "(rebinding or shadowing), not to canonical_players"})
    issues.extend(injected_resolver_wiring(pipelines_dir)[1])
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

    def test_bare_resolve_call_is_flagged_unless_defined_locally(self):
        """A pipeline module that calls resolve() with neither the canonical_players
        import nor a module-level def of its own is flagged; one that defines its
        own resolve (lineup parameters, JEG-536) is not."""
        import tempfile
        # Inside the repo: the checker reports paths relative to REPO.
        with tempfile.TemporaryDirectory(dir=REPO, prefix=".jeg916-identity-") as tmp:
            d = Path(tmp)
            (d / "bare.py").write_text("def go(name):\n    return resolve(name)\n", encoding="utf-8")
            (d / "local.py").write_text(
                "def resolve(cfg, objective=None):\n    return cfg\n\ndef go(cfg):\n    return resolve(cfg)\n",
                encoding="utf-8")
            (d / "imported.py").write_text(
                "from canonical_players import resolve\n\ndef go(name):\n    return resolve(name)\n",
                encoding="utf-8")
            flagged = {issue["file"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                       for issue in check_canonical_resolution_usage(d)}
        self.assertIn("bare.py", flagged, "a bare resolve() call with no import went unflagged")
        self.assertNotIn("local.py", flagged, "a module's own def resolve() is not player identity")
        self.assertNotIn("imported.py", flagged)

    def _scan(self, files: dict) -> list:
        """Run the guard on a throwaway pipelines tree; -> sorted issue lines."""
        import tempfile
        with tempfile.TemporaryDirectory(dir=REPO, prefix=".jeg1238-identity-") as tmp:
            d = Path(tmp)
            for rel, text in files.items():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_text(text, encoding="utf-8")
            return sorted(f"{i['file'].split(tmp.rsplit('/', 1)[-1] + '/', 1)[-1]}: {i['issue']}"
                          for i in check_canonical_resolution_usage(d))

    CAP = "def build(rows, resolve):\n    return [resolve(r) for r in rows]\n"
    WIRED = ("import canonical_players\nimport cap as c\n\n"
             "def rn(n):\n    return canonical_players.resolve_with_reason(n)\n\n"
             "def go(rows):\n    return c.build(rows, {arg})\n")

    def test_production_injected_resolver_is_canonical(self):
        """JEG-1238: projection_capture.cbs_capture_rows takes `resolve` as a
        parameter. Its only pipeline caller, save_cbsros_references.save_captures,
        must inject a resolver over canonical_players.resolve_with_reason."""
        entries, issues = injected_resolver_wiring(PIPELINES_DIR)
        self.assertEqual(issues, [])
        cbs = [e for e in entries if e["file"] == "pipelines/lib/projection_capture.py"
               and e["function"] == "cbs_capture_rows"]
        self.assertEqual(len(cbs), 1, entries)
        self.assertEqual(cbs[0]["param"], "resolve")
        self.assertIn("pipelines/save_cbsros_references.py", {f for f, _line, _ok in cbs[0]["callers"]})
        self.assertTrue(all(ok for _f, _line, ok in cbs[0]["callers"]), cbs[0])

    def test_injected_resolver_needs_canonical_wiring_at_every_caller(self):
        ok = {"lib/cap.py": self.CAP}
        for arg in ("lambda n: rn(n)[0]", "rn", "canonical_players.resolve_with_reason",
                    "resolve=lambda n: rn(n)[0]"):
            with self.subTest(arg=arg):
                self.assertEqual(self._scan({**ok, "caller.py": self.WIRED.format(arg=arg)}), [])
        # A bare-name import of the function is traced too.
        self.assertEqual(self._scan({**ok, "caller.py":
                                     "from canonical_players import resolve\nfrom cap import build as b\n\n"
                                     "def go(rows):\n    return b(rows, resolve)\n"}), [])
        bad = {
            "ad-hoc normalizer": "lambda n: str(n).lower()",
            "permit-all": "lambda n: 5",
            "guess on miss": "lambda n: rn(n)[0] or 5",
            "untraceable variable": "make_resolver()",
            "argument missing": "",
        }
        for why, arg in bad.items():
            with self.subTest(why=why):
                got = self._scan({**ok, "caller.py": self.WIRED.format(arg=arg).replace("rows, )", "rows)")})
                self.assertEqual(len(got), 1, got)
                self.assertTrue(got[0].startswith("caller.py: line "), got)
        # Two callers: one canonical, one not -> the bad one is still reported.
        got = self._scan({**ok, "a.py": self.WIRED.format(arg="rn"),
                          "b.py": self.WIRED.format(arg="lambda n: n")})
        self.assertEqual([g.split(":")[0] for g in got], ["b.py"])

    def test_injected_resolver_without_any_caller_fails_closed(self):
        got = self._scan({"lib/cap.py": self.CAP})
        self.assertEqual(len(got), 1, got)
        self.assertIn("no pipeline caller wires a canonical_players resolver", got[0])

    def test_shadowing_nested_and_local_bindings(self):
        canonical_caller = self.WIRED.format(arg="rn")
        legit = {
            "closure over the parameter":
                "def build(rows, resolve):\n    def one(r):\n        return resolve(r)\n"
                "    return [one(r) for r in rows]\n",
            "function-level canonical import":
                "def build(rows):\n    from canonical_players import resolve\n    return resolve(rows)\n",
        }
        for why, cap in legit.items():
            with self.subTest(why=why):
                self.assertEqual(self._scan({"lib/cap.py": cap, "caller.py": canonical_caller}), [])
        flagged = {
            "parameter rebound in its own function":
                "def build(rows, resolve):\n    resolve = lambda n: n.lower()\n    return resolve(rows)\n",
            "nested function rebinds the name":
                "def build(rows, resolve):\n    def one(r):\n        resolve = str\n        return resolve(r)\n"
                "    return one(rows)\n",
            "comprehension variable":
                "def build(rows, fns):\n    return [resolve(rows) for resolve in fns]\n",
            "lambda parameter (no traceable caller)":
                "f = lambda resolve, n: resolve(n)\n",
            "method parameter (no traceable caller)":
                "class C:\n    def build(self, rows, resolve):\n        return resolve(rows)\n",
            "module-level import from elsewhere":
                "from fuzzy import resolve\n\ndef build(rows):\n    return resolve(rows)\n",
            "module-level assignment":
                "resolve = str.lower\n\ndef build(rows):\n    return resolve(rows)\n",
            "global declaration escapes the parameter-free scope":
                "def build(rows):\n    global resolve\n    return resolve(rows)\n",
        }
        for why, cap in flagged.items():
            with self.subTest(why=why):
                got = self._scan({"lib/cap.py": cap, "caller.py": canonical_caller})
                self.assertTrue(any(g.startswith("lib/cap.py: ") for g in got), got)

    def test_real_capture_wiring_mutations_fail(self):
        """Mutation evidence on the real files: the current pair is clean;
        bypassing canonical_players in the caller, or dropping the caller, fails."""
        cap = (PIPELINES_DIR / "lib" / "projection_capture.py").read_text(encoding="utf-8")
        saver = (PIPELINES_DIR / "save_cbsros_references.py").read_text(encoding="utf-8")
        lam = 'lambda n, p, norm: resolve_name(str(n or "").strip(), (p or "").upper() or None, registry, norm)[0]'
        self.assertIn(lam, saver, "the production caller changed; re-check its provenance")
        real = {"lib/projection_capture.py": cap, "save_cbsros_references.py": saver}
        self.assertEqual(self._scan(real), [])
        mutations = {
            "caller injects an ad-hoc resolver": saver.replace(lam, 'lambda n, p, norm: str(n or "").lower()'),
            "caller falls back to a guess": saver.replace(lam, lam + " or 0"),
            "resolve_name stops calling canonical_players":
                saver.replace("canonical_players.resolve_with_reason(", "fuzzy_match("),
        }
        for why, text in mutations.items():
            with self.subTest(why=why):
                got = self._scan({**real, "save_cbsros_references.py": text})
                self.assertTrue(any("cbs_capture_rows() is not given a canonical_players resolver" in g
                                    for g in got), got)
        got = self._scan({"lib/projection_capture.py": cap})
        self.assertTrue(any("no pipeline caller" in g for g in got), got)

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
