#!/usr/bin/env python3
"""JEG-1160: every script a workflow runs must exist in the repo.

Read-only guard over `.github/workflows/*.yml`. It collects the body of every
`run:` step and extracts the repo-relative script paths they invoke via
python/python3/node/bash/sh (e.g. `python3 pipelines/nfl_week.py`,
`node tests/rendered_gate/gate.mjs`) plus `python -m pkg.mod` module targets
that map to repo files. Every extracted path must exist; any that is genuinely
absent from main goes in ALLOWLIST below with a one-line reason.

Parser: PyYAML is not on the CI unit-test step (see
`tests/test_v2_render_runs_on_data_push.py`), so the text parser is the one CI
runs. PyYAML is used when importable; both feed the same extractor.

Mutation check (JEG-1160): renaming a referenced path
(`pipelines/nfl_week.py` -> `pipelines/nfl_week_missing.py`) in a workflow
makes `test_every_referenced_path_exists` fail with that path named. Reverted
after observing the failure.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# Interpreters whose next argument is a repo-relative script path.
INTERPRETERS = ("python3", "python", "node", "bash", "sh")
# Extensions we treat as repo-local scripts.
SCRIPT_EXT = r"(?:py|mjs|cjs|js|sh)"

SCRIPT_RE = re.compile(
    r"(?:^|[\s|&;()])(" + "|".join(INTERPRETERS) + r")\s+"
    r"((?:[A-Za-z0-9_][A-Za-z0-9_./-]*)\." + SCRIPT_EXT + r")\b"
)
# `python -m pkg.mod`: the module token immediately after -m.
MODULE_RE = re.compile(
    r"(?:^|[\s|&;()])python3?\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)"
)
# `python -m unittest tests.test_foo`: the test module follows `unittest`.
UNITTEST_RE = re.compile(
    r"(?:^|[\s|&;()])python3?\s+-m\s+unittest\s+(?:-v\s+)?"
    r"([A-Za-z_][A-Za-z0-9_.]*)"
)

# Paths genuinely absent from main that a workflow still references. Keep this
# empty unless a reference is provably broken; each entry needs a reason.
ALLOWLIST = {
    # (none at the time of writing, 2026-10-27)
}

# A broken extractor must not pass vacuously.
MIN_PATHS = 10


def _run_bodies_text(text):
    """Yield the body of every `run:` step from raw workflow text.

    Handles `run: cmd` inline and `run: |` / `run: >` block scalars. Block
    scalars are collected until the indentation drops back to the `run:` key.
    """
    lines = text.splitlines()
    bodies = []
    i = 0
    n = len(lines)
    while i < n:
        m = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        rest = m.group(2)
        if rest.strip() in ("", "|", ">", "|-", ">-", "|+", ">+"):
            j = i + 1
            block = []
            while j < n:
                line = lines[j]
                if line.strip() == "":
                    block.append("")
                    j += 1
                    continue
                if len(line) - len(line.lstrip()) <= indent:
                    break
                block.append(line)
                j += 1
            bodies.append("\n".join(block))
            i = j
        else:
            bodies.append(rest)
            i += 1
    return bodies


def _run_bodies_yaml(text):
    """Same as `_run_bodies_text` but via PyYAML when it is importable."""
    import yaml  # noqa: PLC0415 - optional dependency

    data = yaml.safe_load(text) or {}
    bodies = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "run" and isinstance(value, str):
                    bodies.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return bodies


def _run_bodies(text):
    try:
        import yaml  # noqa: F401,PLC0415 - optional dependency
    except ImportError:
        return _run_bodies_text(text)
    try:
        return _run_bodies_yaml(text)
    except Exception:  # pragma: no cover - malformed YAML falls back to text
        return _run_bodies_text(text)


def _extract_paths(script):
    """Repo-relative paths a single run-script body invokes.

    Ignores inline `-c`/heredoc bodies, quoted content (where `${{ }}` and
    shell variables live), absolute paths and `$`-bearing paths.
    """
    paths = set()
    heredoc = None
    for raw in script.splitlines():
        if heredoc is not None:
            if raw.strip() == heredoc:
                heredoc = None
            continue
        hm = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", raw)
        if hm:
            heredoc = hm.group(1)
        if raw.lstrip().startswith("#"):
            continue
        line = re.sub(r"'[^']*'", "", raw)
        line = re.sub(r'"[^"]*"', "", line)
        for match in SCRIPT_RE.finditer(line):
            paths.add(match.group(2))
        for match in MODULE_RE.finditer(line):
            p = _module_to_path(match.group(1))
            if p:
                paths.add(p)
        for match in UNITTEST_RE.finditer(line):
            p = _module_to_path(match.group(1))
            if p:
                paths.add(p)
    return {p for p in paths if _is_repo_path(p)}


def _module_to_path(module):
    """Map `pkg.mod` to `pkg/mod.py` when `pkg` is a repo top-level package."""
    top = module.split(".")[0]
    if not (ROOT / top).is_dir():
        return None
    return module.replace(".", "/") + ".py"


def _is_repo_path(path):
    """Skip absolute paths and anything carrying a shell/GitHub variable."""
    if "$" in path or "{{" in path:
        return False
    if path.startswith("/") or path.startswith("~"):
        return False
    return True


def _workflow_paths():
    """{workflow filename: sorted set of referenced repo paths}."""
    found = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        paths = set()
        for body in _run_bodies(wf.read_text(encoding="utf-8")):
            paths |= _extract_paths(body)
        found[wf.name] = paths
    return found


class ExtractorTest(unittest.TestCase):
    """Pin the extractor's rules on synthetic run bodies."""

    def test_extracts_interpreter_script_paths(self):
        self.assertEqual(
            _extract_paths("python3 pipelines/nfl_week.py"),
            {"pipelines/nfl_week.py"},
        )
        self.assertEqual(
            _extract_paths("node tests/rendered_gate/gate.mjs --flag"),
            {"tests/rendered_gate/gate.mjs"},
        )
        self.assertEqual(
            _extract_paths("bash scripts/check_weekly_freshness.sh"),
            {"scripts/check_weekly_freshness.sh"},
        )

    def test_extracts_module_targets(self):
        self.assertEqual(
            _extract_paths("python3 -m unittest tests.test_workflow_script_paths"),
            {"tests/test_workflow_script_paths.py"},
        )
        self.assertEqual(
            _extract_paths("python -m pipelines.lib.record_workflow_run"),
            {"pipelines/lib/record_workflow_run.py"},
        )

    def test_ignores_non_repo_invocations(self):
        ignored = [
            "python3 -m pip install --quiet playwright==1.49.1",
            'python3 -c "import json; print(json.load(open(\'x.json\')))"',
            "python3 << 'EOF'\nsubprocess.run(['pipelines/x.py'])\nEOF",
            "python3 pipelines/ingest_${{ matrix.source }}.py",
            "python3 /usr/local/bin/tool.py",
            "curl -s https://example.com/x.py",
            'grep -c "python3 -m unittest " "$RUNNER_TEMP/shard.log"',
        ]
        for body in ignored:
            self.assertEqual(_extract_paths(body), set(), body)


class WorkflowScriptPathsTest(unittest.TestCase):
    def test_found_a_sane_number_of_paths(self):
        """A broken extractor must not make the existence check vacuous."""
        found = _workflow_paths()
        all_paths = set().union(*found.values()) if found else set()
        self.assertGreater(
            len(all_paths),
            MIN_PATHS,
            f"extractor found only {len(all_paths)} script paths; "
            f"expected more than {MIN_PATHS}",
        )
        self.assertGreater(len(found), 0, "no workflows parsed")

    def test_every_referenced_path_exists(self):
        """Braces placeholder paths are ignored, so present maps to real files."""
        missing = {}
        for wf, paths in _workflow_paths().items():
            for path in sorted(paths):
                if path in ALLOWLIST:
                    continue
                if not (ROOT / path).exists():
                    missing.setdefault(path, []).append(wf)
        self.assertEqual(
            missing,
            {},
            "workflows reference paths that do not exist in the repo: "
            + "; ".join(
                f"{p} (in {', '.join(sorted(wfs))})"
                for p, wfs in sorted(missing.items())
            ),
        )


if __name__ == "__main__":
    unittest.main()
