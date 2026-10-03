"""Cross-workflow contract: gh-dispatched inputs must be declared (JEG-271).

source-vintage-check.yml dispatches rebuild-chain.yml with
`gh workflow run rebuild-chain.yml -f source="source-vintage-check"`.
rebuild-chain.yml declared no `workflow_dispatch` inputs, so the dispatch
step exited 1 on every run (GitHub run 37111598432, 2026-10-03) and the chain
could never be dispatched — silently blocking the whole JEG-205 trigger.

These tests assert, by plain text (PyYAML is not on the CI unit-test step),
that every `-f/--field` key passed to `gh workflow run <file>` in
source-vintage-check.yml is a declared `workflow_dispatch` input of the
target workflow file. Mutation-proven: removing the input (or adding an
undeclared field) must be caught.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALLER = (ROOT / ".github/workflows/source-vintage-check.yml").read_text()


def dispatch_fields(caller_text):
    """All (target workflow file, input key) pairs passed via -f/--field."""
    pairs = []
    for m in re.finditer(r"gh\s+workflow\s+run\s+(\S+)([^\n]*)", caller_text):
        target = m.group(1).strip("'\"")
        for fm in re.finditer(r"(?:-f|--field)\s+([A-Za-z_][A-Za-z0-9_-]*)\s*=",
                              m.group(2)):
            pairs.append((target, fm.group(1)))
    return pairs


def declared_dispatch_inputs(workflow_text):
    """Keys declared under on: -> workflow_dispatch: -> inputs: (plain text)."""
    lines = workflow_text.splitlines()
    # find the `workflow_dispatch:` trigger line under `on:`
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^  workflow_dispatch:\s*(#.*)?$", line):
            start = i
            break
    if start is None:
        return None  # no workflow_dispatch trigger at all
    # find its `inputs:` block (deeper indent)
    inputs_at = None
    for line in lines[start + 1:]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^(\s*)inputs:\s*(#.*)?$", line)
        if m and len(m.group(1)) > 2:
            inputs_at = len(m.group(1))
            break
        if re.match(r"^  \S", line):
            break  # left the workflow_dispatch block (e.g. reached `permissions:`)
    if inputs_at is None:
        return set()
    keys = set()
    seen_inputs = False
    for line in lines[start + 1:]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if re.match(r"^\s*inputs:\s*(#.*)?$", line):
            seen_inputs = True
            continue
        if seen_inputs:
            if indent <= inputs_at:
                break
            m = re.match(r"^\s{4,}([A-Za-z_][A-Za-z0-9_-]*):", line)
            if m and indent == inputs_at + 2:
                keys.add(m.group(1))
    return keys


def contract_problems(caller_text, targets):
    problems = []
    for target, key in dispatch_fields(caller_text):
        declared = targets.get(target)
        if declared is None:
            problems.append(f"dispatch target {target!r} has no workflow_dispatch trigger")
        elif key not in declared:
            problems.append(
                f"gh workflow run {target} passes undeclared input {key!r} "
                f"(declared: {sorted(declared) or 'none'})")
    return problems


def real_targets():
    targets = {}
    for target, _ in dispatch_fields(CALLER):
        path = ROOT / ".github/workflows" / target
        targets[target] = declared_dispatch_inputs(path.read_text())
    return targets


class VintageDispatchContractTest(unittest.TestCase):
    def test_real_caller_is_clean(self):
        self.assertEqual([], contract_problems(CALLER, real_targets()))

    def test_dispatch_actually_passes_a_field(self):
        # The contract is only meaningful if the caller passes at least one
        # field; a caller with no -f flags would pass vacuously.
        self.assertTrue(dispatch_fields(CALLER),
                        "expected at least one gh workflow run -f/--field in the caller")

    def test_undeclared_input_is_caught(self):
        target, key = dispatch_fields(CALLER)[0]
        mutated = (ROOT / ".github/workflows" / target).read_text()
        # strip the JEG-271 input declaration back out
        mutated = re.sub(r"      source:\n(?:        .*\n)+", "", mutated, count=1)
        self.assertNotEqual((ROOT / ".github/workflows" / target).read_text(), mutated,
                            "mutation did not change the target workflow")
        self.assertNotIn(key, declared_dispatch_inputs(mutated))
        problems = contract_problems(CALLER, {target: declared_dispatch_inputs(mutated)})
        self.assertTrue(any(key in p for p in problems),
                        f"expected a problem naming {key!r}, got {problems}")

    def test_extra_undeclared_field_is_caught(self):
        mutated_caller = CALLER.replace(
            'gh workflow run rebuild-chain.yml -f source="source-vintage-check"',
            'gh workflow run rebuild-chain.yml -f source="source-vintage-check" -f bogus_flag=x',
            1)
        problems = contract_problems(mutated_caller, real_targets())
        self.assertTrue(any("bogus_flag" in p for p in problems),
                        f"expected a problem naming 'bogus_flag', got {problems}")


if __name__ == "__main__":
    unittest.main()
