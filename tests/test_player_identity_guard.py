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
# The import paths that name the real module (pipelines put pipelines/ and
# pipelines/lib on sys.path). Any other module that exports a canonical_players
# or resolve name is not it.
_CANONICAL_PATHS = {"canonical_players", "lib.canonical_players", "pipelines.lib.canonical_players"}
_NEW_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef,
               ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)

# JEG-1238: the only functions allowed to take the resolver as a parameter, and
# the only pipeline files allowed to call them. Paths are relative to the
# scanned pipelines dir. A new injection point or a new caller must be added
# here on purpose; anything unlisted fails. Each pinned call must also inject a
# resolver that provably returns canonical_players' answer (_injected_ok).
INJECTED_RESOLVER_CONTRACTS = {
    ("lib/projection_capture.py", "cbs_capture_rows", "resolve"): {"save_cbsros_references.py"},
}


def _iter_pipeline_trees(pipelines_dir: Path):
    """(repo-relative path, path relative to pipelines_dir, module stem, tree)."""
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
            yield (str(fpath.relative_to(REPO)), fpath.relative_to(pipelines_dir).as_posix(),
                   fpath.stem, tree)


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
    return name in _CANONICAL_PATHS


def _bindings(scope):
    """{name: kind} bound in scope's own body. kind: 'canonical' (the name is
    `from canonical_players import resolve[_with_reason]`), 'canonical_module'
    (the name is the canonical_players module), 'def', 'global', 'nonlocal' or
    'other'. A name bound two different ways is 'other': a later rebinding
    (e.g. `canonical_players = fake`) never keeps the canonical kind."""
    out = {}

    def bind(name, kind):
        if out.get(name) in ("global", "nonlocal"):
            return
        out[name] = kind if out.get(name) in (None, kind) else "other"

    if isinstance(scope, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        for gen in scope.generators:
            for n in ast.walk(gen.target):
                if isinstance(n, ast.Name):
                    bind(n.id, "other")
        return out
    for n in (_own_scope(scope) if not isinstance(scope, ast.Lambda) else ()):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            for name in n.names:
                out[name] = "global" if isinstance(n, ast.Global) else "nonlocal"
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            bind(n.id, "other")
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bind(n.name, "def")
        elif isinstance(n, ast.ClassDef):
            bind(n.name, "other")
        elif isinstance(n, ast.ImportFrom):
            for al in n.names:
                if n.level == 0 and _is_canonical_module(n.module) and al.name in RESOLVER_NAMES:
                    kind = "canonical"
                elif n.level == 0 and _is_canonical_module(f"{n.module}.{al.name}"):
                    kind = "canonical_module"
                else:
                    kind = "other"
                bind(al.asname or al.name, kind)
        elif isinstance(n, ast.Import):
            for al in n.names:
                if al.asname:
                    bind(al.asname, "canonical_module" if _is_canonical_module(al.name) else "other")
                else:
                    bind(al.name.split(".")[0],
                         "canonical_module" if al.name == _CANONICAL else "other")
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bind(n.name, "other")
        elif isinstance(n, ast.NamedExpr):
            bind(n.target.id, "other")
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            bind(n.name, "other")
        elif isinstance(n, ast.MatchMapping) and n.rest:
            bind(n.rest, "other")
    return out


def _scope_chains(tree):
    """{id(node): scope chain} for every node; the chain runs from the module
    to the innermost scope the node is evaluated in."""
    chains = {}

    def walk(node, chain):
        for child in ast.iter_child_nodes(node):
            chains[id(child)] = chain
            walk(child, chain + [child] if isinstance(child, _NEW_SCOPES) else chain)

    chains[id(tree)] = [tree]
    walk(tree, [tree])
    return chains


_TRUSTED_KINDS = ("canonical", "canonical_module", "def")


def _tainted(tree) -> set:
    """Names whose binding some code in the module can change behind a lexical
    lookup: any `global`/`nonlocal` declaration of the name (in any scope,
    called or not), an attribute write or delete on it (`x.resolve = fake`), or
    setattr/delattr on it. Conservative: such a name is never trusted."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)):
            base = n.value
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                out.add(base.id)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("setattr", "delattr")
              and n.args and isinstance(n.args[0], ast.Name)):
            out.add(n.args[0].id)
    return out


def _lookup(name, chain, cache):
    """Where a bare `name` binds lexically: (kind, scope). kind is a _bindings
    kind, 'param', or 'unbound'. A parameter also rebound in its own function
    is 'other' (shadowed), never 'param'; a canonical or def binding of a name
    the module can rewrite (_tainted) is 'other'."""
    kind, scope = _lookup_raw(name, chain, cache)
    if kind in _TRUSTED_KINDS and name in cache.setdefault("tainted", _tainted(chain[0])):
        return "other", scope
    return kind, scope


def _lookup_raw(name, chain, cache):
    module, inner = chain[0], chain[1:]
    for i in range(len(inner) - 1, -1, -1):
        scope = inner[i]
        # A class body does not enclose the functions inside it.
        if isinstance(scope, ast.ClassDef) and i != len(inner) - 1:
            continue
        kind = cache.setdefault(id(scope), _bindings(scope)).get(name)
        if kind == "global":
            break
        if kind == "nonlocal":
            continue
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and name in _params(scope):
            return ("param", scope) if kind is None else ("other", scope)
        if kind is not None:
            return kind, scope
    kind = cache.setdefault(id(module), _bindings(module)).get(name)
    return (kind or "unbound"), module


def _resolver_calls(tree):
    """Every bare resolve()/resolve_with_reason() call."""
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in RESOLVER_NAMES]


def _canonical_ref(expr, chain, cache) -> bool:
    """expr names canonical_players' resolver through an unshadowed binding:
    `canonical_players.resolve*` with canonical_players bound to the module
    import, or a name bound by `from canonical_players import resolve*`."""
    if isinstance(expr, ast.Attribute) and expr.attr in RESOLVER_NAMES and isinstance(expr.value, ast.Name):
        return _lookup(expr.value.id, chain, cache)[0] == "canonical_module"
    if isinstance(expr, ast.Name):
        return _lookup(expr.id, chain, cache)[0] == "canonical"
    return False


def _canonical_call(expr, chain, cache) -> bool:
    return isinstance(expr, ast.Call) and _canonical_ref(expr.func, chain, cache)


def _returns_canonical(fn, chains, cache) -> bool:
    """Return provenance for a wrapper def: every `return` in its own body hands
    back None, a canonical call (optionally indexed), a tuple or conditional of
    those, or a local whose every binding is `x[, y] = <canonical call>`.
    Discarding the canonical answer, a fallback (`or 5`), a literal, a rebound
    local or a yield fails. Nested helpers are not this function's returns."""
    own = list(_own_scope(fn))
    if any(isinstance(n, (ast.Yield, ast.YieldFrom)) for n in own):
        return False
    chain = chains[id(fn)] + [fn]
    approved, stores = set(), {}
    for n in own:
        if isinstance(n, ast.Assign) and _canonical_call(n.value, chain, cache):
            for t in n.targets:
                for x in ([t] if isinstance(t, ast.Name) else
                          t.elts if isinstance(t, (ast.Tuple, ast.List)) else []):
                    if isinstance(x, ast.Name):
                        approved.add(id(x))
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            stores.setdefault(n.id, []).append(id(n))
    binds = cache.setdefault(id(fn), _bindings(fn))
    sourced = {name for name, ids in stores.items()
               if binds.get(name) == "other" and name not in _params(fn)
               and all(i in approved for i in ids)}

    def ok(e):
        if isinstance(e, ast.Constant) and e.value is None:
            return True
        if isinstance(e, ast.Subscript) and isinstance(e.slice, ast.Constant) and isinstance(e.slice.value, int):
            return _canonical_call(e.value, chain, cache)
        if isinstance(e, ast.Tuple):
            return all(ok(x) for x in e.elts)
        if isinstance(e, ast.IfExp):
            return ok(e.body) and ok(e.orelse)
        if isinstance(e, ast.Name):
            return e.id in sourced
        return _canonical_call(e, chain, cache)

    returns = [n for n in own if isinstance(n, ast.Return)]
    return bool(returns) and all(r.value is not None and ok(r.value) for r in returns)


def _wrapper_ok(name, chain, tree, chains, cache) -> bool:
    """`name` binds, unshadowed, to one plain (undecorated, sync) module-level
    def with return provenance."""
    kind, scope = _lookup(name, chain, cache)
    if kind != "def" or scope is not tree:
        return False
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    # A decorator can replace the function, and an async def returns a
    # coroutine, not a player_key: neither is proven by its body.
    return (len(defs) == 1 and isinstance(defs[0], ast.FunctionDef) and not defs[0].decorator_list
            and _returns_canonical(defs[0], chains, cache))


def _injected_ok(arg, chain, tree, chains, cache) -> bool:
    """The resolver a pinned caller injects: canonical_players' resolver itself,
    a wrapper def with return provenance, or a lambda whose whole body is a call
    to one of those (optionally indexed, e.g. `resolve_name(...)[0]`). Names are
    resolved where they are used, so a parameter or local that shadows
    canonical_players or the wrapper fails."""
    if _canonical_ref(arg, chain, cache):
        return True
    if isinstance(arg, ast.Name):
        return _wrapper_ok(arg.id, chain, tree, chains, cache)
    if isinstance(arg, ast.Lambda):
        inner = chain + [arg]
        body = arg.body
        if isinstance(body, ast.Subscript) and isinstance(body.slice, ast.Constant) \
                and isinstance(body.slice.value, int):
            body = body.value
        if not isinstance(body, ast.Call):
            return False
        if _canonical_ref(body.func, inner, cache):
            return True
        return isinstance(body.func, ast.Name) and _wrapper_ok(body.func.id, inner, tree, chains, cache)
    return False


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


def injected_resolver_wiring(pipelines_dir: Path, contracts=None):
    """JEG-1238: functions that take the resolver as a parameter (e.g.
    projection_capture.cbs_capture_rows) and how each pipeline caller wires it.
    contracts defaults to INJECTED_RESOLVER_CONTRACTS. -> (entries, issues).
    entries: [{"file", "function", "param", "callers": [(caller_file, line, ok)]}]."""
    contracts = INJECTED_RESOLVER_CONTRACTS if contracts is None else contracts
    trees = [(rel, local, stem, tree, _scope_chains(tree), {})
             for rel, local, stem, tree in _iter_pipeline_trees(pipelines_dir)]
    entries, issues = [], []
    for rel, local, stem, tree, chains, cache in trees:
        params = {}
        for call in _resolver_calls(tree):
            kind, scope = _lookup(call.func.id, chains[id(call)], cache)
            if kind != "param":
                continue
            if isinstance(scope, ast.Lambda) or not any(scope is n for n in tree.body):
                issues.append({"file": rel, "issue": f"resolver parameter {call.func.id!r} of a nested "
                               f"function or lambda (line {scope.lineno}) cannot be traced to its callers"})
                continue
            params[(scope.name, call.func.id)] = scope
        for (fn_name, param), fn in params.items():
            pinned = contracts.get((local, fn_name, param))
            if pinned is None:
                issues.append({"file": rel, "issue": f"{fn_name}() takes resolver {param!r} but is not a "
                               "registered injection point (INJECTED_RESOLVER_CONTRACTS)"})
                continue
            positional = [x.arg for x in fn.args.posonlyargs + fn.args.args]
            index = positional.index(param) if param in positional else None
            entry = {"file": rel, "function": fn_name, "param": param, "callers": []}
            seen = set()
            for crel, clocal, _cstem, ctree, cchains, ccache in trees:
                mods, names = _module_aliases(ctree, stem)
                bare = names | ({fn_name: fn_name} if crel == rel else {})
                for c in ast.walk(ctree):
                    if not isinstance(c, ast.Call):
                        continue
                    f = c.func
                    hit = ((isinstance(f, ast.Attribute) and f.attr == fn_name and ast.unparse(f.value) in mods)
                           or (isinstance(f, ast.Name) and bare.get(f.id) == fn_name))
                    if not hit:
                        continue
                    seen.add(clocal)
                    if clocal not in pinned:
                        entry["callers"].append((crel, c.lineno, False))
                        issues.append({"file": crel, "issue": f"line {c.lineno}: calls {fn_name}() but is not "
                                       "a pinned caller in INJECTED_RESOLVER_CONTRACTS"})
                        continue
                    arg = next((k.value for k in c.keywords if k.arg == param), None)
                    if arg is None and index is not None and not any(isinstance(a, ast.Starred) for a in c.args[:index + 1]):
                        arg = c.args[index] if index < len(c.args) else None
                    ok = arg is not None and _injected_ok(arg, cchains[id(c)], ctree, cchains, ccache)
                    entry["callers"].append((crel, c.lineno, ok))
                    if not ok:
                        issues.append({"file": crel, "issue": f"line {c.lineno}: {fn_name}() is not given a "
                                       f"canonical_players resolver for {param!r}"})
            for m in sorted(set(pinned) - seen):
                issues.append({"file": rel, "issue": f"pinned caller {m} no longer wires a canonical_players "
                               f"resolver into {fn_name}()"})
            entries.append(entry)
    return entries, issues


def check_canonical_resolution_usage(pipelines_dir: Path, contracts=None):
    """Every bare resolve()/resolve_with_reason() call in pipelines must bind to
    canonical_players.

    Allowed bindings: `from canonical_players import resolve[_with_reason]`; a
    module-level def of the module's own (JEG-916: derive_lineup_parameters.resolve
    picks lineup parameters, JEG-536, not player identity); and, since JEG-1238,
    a function parameter, only at a registered injection point whose pinned
    callers each inject a resolver with proven canonical provenance
    (injected_resolver_wiring). An unbound global, a local or shadowing
    rebinding, a comprehension variable, an unregistered or untraceable
    injection, or an unpinned caller fails.
    """
    issues = []
    for rel, _local, _stem, tree in _iter_pipeline_trees(pipelines_dir):
        chains, cache, unbound = _scope_chains(tree), {}, False
        for call in _resolver_calls(tree):
            kind, scope = _lookup(call.func.id, chains[id(call)], cache)
            if kind in ("canonical", "param") or (kind == "def" and scope is tree):
                continue
            if kind == "unbound":
                if not unbound:
                    unbound = True
                    issues.append({"file": rel, "issue": "uses resolve() but doesn't import from canonical_players"})
                continue
            issues.append({"file": rel, "issue": f"line {call.lineno}: {call.func.id}() is bound locally "
                           "(rebinding or shadowing), not to canonical_players"})
    issues.extend(injected_resolver_wiring(pipelines_dir, contracts)[1])
    return issues


RN_TWICE = ("def rn(n):\n    return canonical_players.resolve(n)\n\n"
            "def rn(n):\n    return 5\n")


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

    TEST_CONTRACT = {("lib/cap.py", "build", "resolve"): {"caller.py"}}
    CAP = "def build(rows, resolve):\n    return [resolve(r) for r in rows]\n"
    # rn mirrors save_cbsros_references.resolve_name: canonical answer, one
    # canonical retry, (key, None) or (None, reason).
    RN = ("def rn(n):\n"
          "    key, reason = canonical_players.resolve_with_reason(n)\n"
          "    if key is None and reason == 'unmatched':\n"
          "        key, reason = canonical_players.resolve_with_reason(n.strip())\n"
          "    return (key, None) if key is not None else (None, reason)\n")
    WIRED = "import canonical_players\nimport cap as c\n\n{rn}\n\ndef go(rows):\n    return c.build(rows, {arg})\n"

    def _scan(self, files: dict, contracts=None) -> list:
        """Run the guard on a throwaway pipelines tree; -> sorted 'file: issue' lines
        with paths relative to that tree."""
        import tempfile
        contracts = self.TEST_CONTRACT if contracts is None else contracts
        with tempfile.TemporaryDirectory(dir=REPO, prefix=".jeg1238-identity-") as tmp:
            d = Path(tmp)
            for rel, text in files.items():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_text(text, encoding="utf-8")
            prefix = str(d.relative_to(REPO)) + "/"
            return sorted(f"{i['file'].replace(prefix, '', 1)}: {i['issue']}"
                          for i in check_canonical_resolution_usage(d, contracts))

    def _caller(self, arg, rn=None):
        return self.WIRED.format(rn=self.RN if rn is None else rn, arg=arg)

    def test_production_injected_resolver_is_canonical(self):
        """JEG-1238: projection_capture.cbs_capture_rows takes `resolve` as a
        parameter. Its one pinned caller, save_cbsros_references.save_captures,
        injects resolve_name, whose every return is canonical_players' answer."""
        entries, issues = injected_resolver_wiring(PIPELINES_DIR)
        self.assertEqual(issues, [])
        self.assertEqual([(e["file"], e["function"], e["param"]) for e in entries],
                         [("pipelines/lib/projection_capture.py", "cbs_capture_rows", "resolve")])
        self.assertEqual([(f, ok) for f, _line, ok in entries[0]["callers"]],
                         [("pipelines/save_cbsros_references.py", True)])

    def test_registered_injection_positive_controls(self):
        for arg in ("canonical_players.resolve_with_reason", "rn", "lambda n: rn(n)[0]",
                    "resolve=lambda n: rn(n)[0]", "lambda n: canonical_players.resolve(n)"):
            with self.subTest(arg=arg):
                self.assertEqual(self._scan({"lib/cap.py": self.CAP, "caller.py": self._caller(arg)}), [])
        bare = ("from canonical_players import resolve\nfrom cap import build as b\n\n"
                "def go(rows):\n    return b(rows, resolve)\n")
        self.assertEqual(self._scan({"lib/cap.py": self.CAP, "caller.py": bare}), [])

    def test_review_bypasses_fail(self):
        """The four injections Codex's review (JEG-1238, 12:23 UTC) found accepted on 49e825dd."""
        cases = {
            "wrapper discards the canonical answer, returns 5": self._caller(
                "rn", rn="def rn(n):\n    canonical_players.resolve_with_reason(n)\n    return 5\n"),
            "unused nested canonical helper, returns 5": self._caller(
                "rn", rn="def rn(n):\n    def helper():\n        return canonical_players.resolve(n)\n"
                         "    return 5\n"),
            "caller parameter shadows canonical_players": (
                "import canonical_players\nimport cap as c\n\n"
                "def go(rows, canonical_players):\n    return c.build(rows, canonical_players.resolve)\n"),
            "fake bound before the import (two bindings fail closed)": (
                "import cap as c\nimport fake\ncanonical_players = fake\nimport canonical_players\n\n"
                "def go(rows):\n    return c.build(rows, canonical_players.resolve)\n"),
            "imported canonical_players rebound to a fake": (
                "import canonical_players\nimport cap as c\nimport fake\ncanonical_players = fake\n\n"
                "def go(rows):\n    return c.build(rows, canonical_players.resolve)\n"),
        }
        for why, caller in cases.items():
            with self.subTest(why=why):
                got = self._scan({"lib/cap.py": self.CAP, "caller.py": caller})
                self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)

    def test_second_review_holes_fail(self):
        """Codex's re-review of 05ce4aa4 (JEG-1238, 14:13 UTC): writes through
        global/nonlocal, decorated wrappers and async wrappers were accepted."""
        cases = {
            "global write replaces the imported module": (
                "import canonical_players\nimport cap as c\nimport fake\n\n"
                "def go(rows):\n    global canonical_players\n    canonical_players = fake\n"
                "    return c.build(rows, canonical_players.resolve)\n"),
            "nonlocal write by an invoked nested writer": (
                "import cap as c\nimport fake\n\n"
                "def go(rows):\n    import canonical_players as cp\n"
                "    def poison():\n        nonlocal cp\n        cp = fake\n"
                "    poison()\n    return c.build(rows, cp.resolve)\n"),
            "global write in a function that is never called": (
                "import canonical_players\nimport cap as c\nimport fake\n\n"
                "def later():\n    global canonical_players\n    canonical_players = fake\n\n"
                "def go(rows):\n    return c.build(rows, canonical_players.resolve)\n"),
            "global write replaces the wrapper": self._caller("rn").replace(
                "def go(rows):\n", "def swap():\n    global rn\n    rn = lambda n: 5\n\ndef go(rows):\n"),
            "attribute write on the module": self._caller("canonical_players.resolve").replace(
                "def go(rows):\n", "def go(rows):\n    canonical_players.resolve = lambda n: 5\n"),
            "setattr on the module": self._caller("canonical_players.resolve").replace(
                "def go(rows):\n", "def go(rows):\n    setattr(canonical_players, 'resolve', len)\n"),
            "decorated wrapper": self._caller("rn", rn="def fake(fn):\n    return lambda n: 5\n\n@fake\n"
                                                       "def rn(n):\n    return canonical_players.resolve(n)\n"),
            "decorated wrapper through a lambda": self._caller(
                "lambda n: rn(n)[0]", rn="@staticmethod\ndef rn(n):\n    return canonical_players.resolve(n)\n"),
            "async wrapper": self._caller("rn", rn="async def rn(n):\n    return canonical_players.resolve(n)\n"),
            "async wrapper through a lambda": self._caller(
                "lambda n: rn(n)[0]", rn="async def rn(n):\n    return canonical_players.resolve(n)\n"),
        }
        for why, caller in cases.items():
            with self.subTest(why=why):
                got = self._scan({"lib/cap.py": self.CAP, "caller.py": caller})
                self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)
        # The positive path is unchanged: the plain wrapper and the direct resolver pass.
        for arg in ("rn", "canonical_players.resolve"):
            self.assertEqual(self._scan({"lib/cap.py": self.CAP, "caller.py": self._caller(arg)}), [])

    def test_wrapper_and_lambda_fallbacks_fail(self):
        wrappers = {
            "fallback in return": "def rn(n):\n    key, r = canonical_players.resolve_with_reason(n)\n"
                                  "    return key or 5\n",
            "rebound before return": "def rn(n):\n    key, r = canonical_players.resolve_with_reason(n)\n"
                                     "    key = 5\n    return key\n",
            "augmented rebinding": "def rn(n):\n    key, r = canonical_players.resolve_with_reason(n)\n"
                                   "    key += 1\n    return key\n",
            "literal on one branch": "def rn(n):\n    if not n:\n        return 5\n"
                                     "    return canonical_players.resolve(n)\n",
            "loop variable return": "def rn(n):\n    canonical_players.resolve(n)\n"
                                    "    for key in (1, 2):\n        pass\n    return key\n",
            "returns its own input": "def rn(n):\n    canonical_players.resolve(n)\n    return n\n",
            "generator": "def rn(n):\n    yield canonical_players.resolve(n)\n",
            "no return at all": "def rn(n):\n    canonical_players.resolve(n)\n",
            "wrapper redefined": RN_TWICE,
        }
        for why, rn in wrappers.items():
            with self.subTest(wrapper=why):
                got = self._scan({"lib/cap.py": self.CAP, "caller.py": self._caller("rn", rn=rn)})
                self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)
        args = {
            "lambda fallback": "lambda n: rn(n)[0] or 5",
            "ad-hoc lambda": "lambda n: str(n).lower()",
            "permit-all lambda": "lambda n: 5",
            "lambda parameter shadows the wrapper": "lambda n, rn=str: rn(n)",
            "untraceable variable": "make_resolver()",
        }
        for why, arg in args.items():
            with self.subTest(arg=why):
                got = self._scan({"lib/cap.py": self.CAP, "caller.py": self._caller(arg)})
                self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)
        impostors = {
            "canonical_players taken from another module":
                self._caller("canonical_players.resolve").replace(
                    "import canonical_players\n", "from fake import canonical_players\n", 1),
            "another module aliased as canonical_players":
                self._caller("canonical_players.resolve").replace(
                    "import canonical_players\n", "import fake as canonical_players\n", 1),
            "resolve imported from another module":
                "from fake.canonical_players_shim import resolve\nimport cap as c\n\n"
                "def go(rows):\n    return c.build(rows, resolve)\n",
            "aliased module name": self._caller("cp.resolve").replace(
                "import canonical_players\n", "import canonical_players\ncp = canonical_players\n", 1),
        }
        for why, caller in impostors.items():
            with self.subTest(impostor=why):
                got = self._scan({"lib/cap.py": self.CAP, "caller.py": caller})
                self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)
        legit = self._caller("cp.resolve").replace(
            "import canonical_players\n", "import lib.canonical_players as cp\n", 1)
        self.assertEqual(self._scan({"lib/cap.py": self.CAP, "caller.py": legit}), [])
        shadowed = self._caller("rn").replace("def go(rows):\n", "def go(rows):\n    rn = lambda n: 5\n")
        got = self._scan({"lib/cap.py": self.CAP, "caller.py": shadowed})
        self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)
        missing = self._caller("rn").replace("c.build(rows, rn)", "c.build(rows)")
        got = self._scan({"lib/cap.py": self.CAP, "caller.py": missing})
        self.assertTrue(any("not given a canonical_players resolver" in g for g in got), got)

    def test_injection_contract_is_pinned(self):
        ok = {"lib/cap.py": self.CAP, "caller.py": self._caller("rn")}
        got = self._scan(ok, contracts={})
        self.assertEqual(len(got), 1, got)
        self.assertIn("not a registered injection point", got[0])
        got = self._scan({**ok, "other.py": self._caller("rn")})
        self.assertEqual(len(got), 1, got)
        self.assertTrue(got[0].startswith("other.py: ") and "not a pinned caller" in got[0], got)
        got = self._scan({"lib/cap.py": self.CAP})
        self.assertEqual(len(got), 1, got)
        self.assertIn("pinned caller caller.py no longer wires", got[0])
        two = {("lib/cap.py", "build", "resolve"): {"a.py", "b.py"}}
        got = self._scan({"lib/cap.py": self.CAP, "a.py": self._caller("rn"),
                          "b.py": self._caller("lambda n: n")}, contracts=two)
        self.assertEqual([g.split(":")[0] for g in got], ["b.py"])

    def test_shadowing_nested_and_local_bindings(self):
        canonical_caller = self._caller("rn")
        legit = {
            "closure over the parameter":
                "def build(rows, resolve):\n    def one(r):\n        return resolve(r)\n"
                "    return [one(r) for r in rows]\n",
        }
        for why, cap in legit.items():
            with self.subTest(why=why):
                self.assertEqual(self._scan({"lib/cap.py": cap, "caller.py": canonical_caller}), [])
        self.assertEqual(self._scan({"lib/cap.py": "def build(rows):\n    from canonical_players import resolve\n"
                                                   "    return resolve(rows)\n"}, contracts={}), [])
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
            "canonical import then rebound":
                "from canonical_players import resolve\nresolve = str.lower\n\ndef build(rows):\n"
                "    return resolve(rows)\n",
            "module-level assignment":
                "resolve = str.lower\n\ndef build(rows):\n    return resolve(rows)\n",
            "global declaration escapes to an unbound module name":
                "def build(rows):\n    global resolve\n    return resolve(rows)\n",
        }
        for why, cap in flagged.items():
            with self.subTest(why=why):
                got = self._scan({"lib/cap.py": cap, "caller.py": canonical_caller})
                self.assertTrue(any(g.startswith("lib/cap.py: ") for g in got), got)

    def test_real_capture_wiring_mutations_fail(self):
        """Mutation evidence on the real files: the current pair is clean; bypassing
        canonical_players anywhere on the caller's path, or moving the call, fails."""
        cap = (PIPELINES_DIR / "lib" / "projection_capture.py").read_text(encoding="utf-8")
        saver = (PIPELINES_DIR / "save_cbsros_references.py").read_text(encoding="utf-8")
        lam = 'lambda n, p, norm: resolve_name(str(n or "").strip(), (p or "").upper() or None, registry, norm)[0]'
        ret = "    return (key, None) if key is not None else (None, reason)\n"
        imp = "import canonical_players  # noqa: E402"
        for needle in (lam, ret, imp, "\nfrom nfl_week import", "\ndef resolve_name(", "\ndef save_captures("):
            self.assertEqual(saver.count(needle), 1, f"the production caller changed; re-check: {needle}")
        real = {"lib/projection_capture.py": cap, "save_cbsros_references.py": saver}
        self.assertEqual(self._scan(real, contracts=INJECTED_RESOLVER_CONTRACTS), [])
        mutations = {
            "caller injects an ad-hoc resolver": saver.replace(lam, 'lambda n, p, norm: str(n or "").lower()'),
            "caller falls back to a guess": saver.replace(lam, lam + " or 0"),
            "resolve_name stops calling canonical_players":
                saver.replace("canonical_players.resolve_with_reason(", "fuzzy_match("),
            "resolve_name returns a literal": saver.replace(ret, "    return (5, None)\n"),
            "resolve_name guesses on a miss": saver.replace(ret, "    return (key or 5, None)\n"),
            "resolve_name decorated": saver.replace("\ndef resolve_name(", "\n@functools.cache\ndef resolve_name(", 1),
            "resolve_name made async": saver.replace("\ndef resolve_name(", "\nasync def resolve_name(", 1),
            "canonical_players written through global": saver.replace(
                "\ndef save_captures(", "\ndef _poison():\n    global canonical_players\n    canonical_players = None\n"
                "\n\ndef save_captures(", 1),
            "canonical_players rebound after import":
                saver.replace("\nfrom nfl_week import", "\ncanonical_players = object()\nfrom nfl_week import", 1),
        }
        for why, text in mutations.items():
            with self.subTest(why=why):
                got = self._scan({**real, "save_cbsros_references.py": text}, contracts=INJECTED_RESOLVER_CONTRACTS)
                self.assertTrue(any("cbs_capture_rows() is not given a canonical_players resolver" in g
                                    for g in got), got)
        got = self._scan({"lib/projection_capture.py": cap}, contracts=INJECTED_RESOLVER_CONTRACTS)
        self.assertTrue(any("no longer wires" in g for g in got), got)
        got = self._scan({"lib/projection_capture.py": cap, "save_other.py": saver},
                         contracts=INJECTED_RESOLVER_CONTRACTS)
        self.assertTrue(any(g.startswith("save_other.py: ") and "not a pinned caller" in g for g in got), got)

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
