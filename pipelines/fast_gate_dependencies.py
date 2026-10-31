"""Conservative source dependency inventory for fast-gate coverage.

Literal paths/basenames include split Path expressions and Node harnesses.
Python imports are parsed without importing or executing project modules.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parents[1]
CODE = {".py", ".js", ".mjs", ".cjs", ".ts"}
TOKEN = re.compile(r"[A-Za-z0-9_.-]+\.[A-Za-z0-9_-]+")


def imported_paths(path, text, python_paths):
    """Resolve qualified, relative and sys.path-style imports conservatively."""
    if not path.endswith(".py"):
        return set()
    tree = ast.parse(text, filename=path)
    modules = {p[:-3].replace("/", "."): p for p in python_paths}
    by_stem = defaultdict(set)
    for p in python_paths:
        by_stem[Path(p).stem].add(p)
    found = set()
    def resolve(name):
        if name in modules:
            found.add(modules[name])
        elif "." not in name:
            found.update(by_stem[name])
        elif name:
            found.update(p for module, p in modules.items() if module.endswith("." + name))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolve(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ""
            if node.level:
                package = path[:-3].split("/")[:-node.level]
                prefix = ".".join(package + ([prefix] if prefix else []))
            resolve(prefix)
            for alias in node.names:
                resolve(".".join(filter(None, (prefix, alias.name))))
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name in ("import_module", "__import__") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    resolve(arg.value)
    found.discard(path)
    return found


@lru_cache(maxsize=1)
def inventory(root=ROOT):
    root = Path(root)
    # Only project source directories: never crawl environments or credentials.
    paths = set()
    for folder in ("tests", "app", "pipelines", "scripts", "tools", "lanes", "docs", "runbooks"):
        for parent, dirs, files in os.walk(root / folder, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", "__pycache__")]
            paths.update(str((Path(parent) / name).relative_to(root)) for name in files
                         if not (Path(parent) / name).is_symlink())
    paths.update(str(p.relative_to(root)) for p in root.glob("*.md") if not p.is_symlink())
    python_paths = {p for p in paths if p.endswith(".py")}
    names = defaultdict(set)
    for path in paths:
        names[Path(path).name].add(path)
    readers, shared_pipelines, test_helpers = defaultdict(set), set(), set()
    test_code = {p for p in paths if p.startswith("tests/") and Path(p).suffix in CODE}
    for path in sorted(test_code | python_paths):
        text = (root / path).read_text(encoding="utf-8")
        imports = imported_paths(path, text, python_paths)
        if "spec_from_file_location" in text:
            for token in TOKEN.findall(text):
                imports.update(p for p in names.get(token, ()) if p.endswith(".py") and p != path)
        shared_pipelines.update(p for p in imports if p.startswith("pipelines/"))
        if path in test_code:
            references = set(imports)
            for token in TOKEN.findall(text):
                references.update(names.get(token, ()))
            for dependency in references - {path}:
                readers[dependency].add(path)
            test_helpers.update(p for p in imports if p.startswith("tests/"))
            # ES imports and require() also make test files shared helpers.
            for value in re.findall(r'(?:require\(|from\s+|import\s*)[\s\(]*[\'"]([^\'"]+)[\'"]', text):
                test_helpers.update(p for p in names.get(Path(value).name, ()) if p.startswith("tests/"))
    documents = {p for p in paths if p.startswith(("docs/", "runbooks/")) or p.endswith(".md")}
    test_read_paths = sorted(documents & readers.keys())
    # Direct Node entry points already have a runnable argv recipe. Other Node
    # files are reached through their Python/Node callers in the reader graph.
    node_commands = {}
    for line in (root / "Makefile").read_text().splitlines():
        if re.match(r"\s*node tests/", line):
            argv = shlex.split(line.strip())
            node_commands[argv[1]] = argv
    for path in test_code:
        if re.fullmatch(r"tests/test_[^/]+\.(?:js|mjs|cjs)", path):
            node_commands.setdefault(path, ["node", "--test", path])
    entries = {p for p in test_code if Path(p).name.startswith("test_") and p.endswith(".py")}
    return {"paths": paths, "readers": readers, "shared_pipelines": shared_pipelines,
            "test_helpers": test_helpers, "test_read_paths": test_read_paths,
            "entries": entries, "node_commands": node_commands}


def readers_of(paths, data):
    pending = deque(paths)
    visited = set(pending)
    while pending:
        for reader in data["readers"].get(pending.popleft(), ()):
            if reader not in visited:
                visited.add(reader)
                pending.append(reader)
    return visited


def page_tests(patterns, data=None):
    from pipelines.fast_gate import matches
    data = inventory() if data is None else data
    visited = readers_of((p for p in data["paths"] if matches(p, patterns)), data)
    return sorted(visited & (data["entries"] | data["node_commands"].keys()))


def page_commands(tests, data=None):
    data = inventory() if data is None else data
    python = [p for p in tests if p.endswith(".py")]
    commands = ([["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", *python]] if python else [])
    commands.extend(data["node_commands"][p] for p in tests if p in data["node_commands"])
    return commands


def declared_tests(commands):
    found = set()
    for command in commands:
        if command[:3] == ["python3", "-m", "unittest"]:
            found.update("/".join(m.split(".")[:2]) + ".py" for m in command[3:])
        else:
            found.update(arg for arg in command if arg.startswith("tests/") and Path(arg).suffix in CODE)
    return found


def coverage_gaps(config, data=None):
    from pipelines.fast_gate import matches
    data = inventory() if data is None else data
    gaps = {}
    for rule in config["rules"]:
        for shard in rule["shards"]:
            if shard.startswith("fe-"):
                declared = declared_tests(config["shards"][shard]["commands"])
                missing = set(page_tests(rule["paths"], data)) - declared
                direct = set().union(*(data["readers"].get(p, set()) for p in data["paths"] if matches(p, rule["paths"])))
                missing.update(reader for reader in direct if not (readers_of([reader], data) & declared))
                if missing:
                    gaps[shard] = sorted(missing)
    return gaps


def refresh(config):
    data = inventory()
    config["test_read_paths"] = data["test_read_paths"]
    for rule in config["rules"]:
        for name in rule["shards"]:
            if name.startswith("fe-"):
                required = page_tests(rule["paths"], data)
                # Keep previous checks as well as all discovered readers.
                for command in config["shards"][name]["commands"]:
                    if command[:3] == ["python3", "-m", "unittest"]:
                        required.extend("/".join(m.split(".")[:2]) + ".py" for m in command[3:])
                    elif command[:3] == ["python3", "-m", "pytest"]:
                        required.extend(p for p in command[3:] if p.startswith("tests/") and p.endswith(".py"))
                config["shards"][name]["commands"] = page_commands(sorted(set(required)), data)
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", required=True)
    parser.parse_args()
    path = ROOT / "config/fast_gate.json"
    path.write_text(json.dumps(refresh(json.loads(path.read_text())), indent=2) + "\n")


if __name__ == "__main__":
    main()
