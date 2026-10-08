#!/usr/bin/env python3
"""JEG-205: the hourly vintage check triggers a rebuild on pipeline-code changes.

The code-version stamp is additive to the existing vintage logic and
fail-safe: any failure to compute the hash or read the state triggers a
rebuild rather than skipping one. All tests are hermetic (temp dirs, no
network, no git).
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import check_source_vintage as csv_mod


def _make_tree(files):
    """Build a fake repo root with a pipelines/ dir holding {relpath: text}."""
    d = Path(tempfile.mkdtemp())
    (d / "pipelines").mkdir()
    for rel, content in files.items():
        p = d / "pipelines" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


class PipelinesCodeHashTests(unittest.TestCase):
    def test_hash_is_deterministic(self):
        files = {"a.py": "x = 1\n", "sub/b.py": "y = 2\n"}
        self.assertEqual(
            csv_mod.compute_pipelines_code_hash(_make_tree(files)),
            csv_mod.compute_pipelines_code_hash(_make_tree(files)),
        )

    def test_hash_is_sensitive_to_content(self):
        self.assertNotEqual(
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 1\n"})),
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 2\n"})),
        )

    def test_hash_is_sensitive_to_filenames(self):
        self.assertNotEqual(
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 1\n"})),
            csv_mod.compute_pipelines_code_hash(_make_tree({"b.py": "x = 1\n"})),
        )

    def test_hash_ignores_bytecode_churn(self):
        """__pycache__ and .pyc files never count as a code change."""
        d = _make_tree({"a.py": "x = 1\n"})
        cache = d / "pipelines" / "__pycache__"
        cache.mkdir()
        (cache / "a.pyc").write_bytes(b"\x00\x01\x02")
        (d / "pipelines" / "stray.pyc").write_bytes(b"\x00\x01\x02")
        self.assertEqual(
            csv_mod.compute_pipelines_code_hash(d),
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 1\n"})),
        )

    def test_missing_pipelines_dir_raises(self):
        with self.assertRaises(FileNotFoundError):
            csv_mod.compute_pipelines_code_hash(Path(tempfile.mkdtemp()))


class CodeChangeTriggerTests(unittest.TestCase):
    def _state_with(self, root, payload):
        state = root / "state.json"
        state.write_text(json.dumps(payload), encoding="utf-8")
        return state

    def test_matching_hash_means_no_trigger(self):
        d = _make_tree({"a.py": "x = 1\n"})
        h = csv_mod.compute_pipelines_code_hash(d)
        r = csv_mod.check_code_change(
            state_path=self._state_with(d, {"last_code_hash": h}), repo_root=d
        )
        self.assertFalse(r["code_changed"])
        self.assertEqual(r["code_hash"], h)

    def test_differing_hash_triggers(self):
        """Simulated pipeline-code change with no vintage drift triggers."""
        d = _make_tree({"a.py": "x = 1\n"})
        r = csv_mod.check_code_change(
            state_path=self._state_with(d, {"last_code_hash": "deadbeef"}), repo_root=d
        )
        self.assertTrue(r["code_changed"])
        self.assertEqual(r["code_hash"], csv_mod.compute_pipelines_code_hash(d))

    def test_missing_state_file_triggers_fail_safe(self):
        d = _make_tree({"a.py": "x = 1\n"})
        r = csv_mod.check_code_change(state_path=d / "nope.json", repo_root=d)
        self.assertTrue(r["code_changed"])

    def test_corrupt_state_file_triggers_fail_safe(self):
        d = _make_tree({"a.py": "x = 1\n"})
        state = d / "state.json"
        state.write_text("not json{{{", encoding="utf-8")
        r = csv_mod.check_code_change(state_path=state, repo_root=d)
        self.assertTrue(r["code_changed"])

    def test_unhashable_tree_triggers_fail_safe(self):
        d = Path(tempfile.mkdtemp())  # no pipelines/ dir at all
        r = csv_mod.check_code_change(state_path=d / "s.json", repo_root=d)
        self.assertTrue(r["code_changed"])
        self.assertIsNone(r["code_hash"])

    def test_record_code_hash_round_trips(self):
        d = Path(tempfile.mkdtemp())
        state = d / "s.json"
        csv_mod.record_code_hash(state, "abc123")
        data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(data["last_code_hash"], "abc123")

    def test_record_preserves_other_state_fields(self):
        d = Path(tempfile.mkdtemp())
        state = self._state_with(d, {"other": 1})
        csv_mod.record_code_hash(state, "abc123")
        data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(data["last_code_hash"], "abc123")
        self.assertEqual(data["other"], 1)

    def test_recorded_hash_silences_next_check(self):
        """Record-then-check is the loop guard: exactly one dispatch per change."""
        d = _make_tree({"a.py": "x = 1\n"})
        state = d / "state.json"
        first = csv_mod.check_code_change(state_path=state, repo_root=d)
        self.assertTrue(first["code_changed"])
        csv_mod.record_code_hash(state, first["code_hash"])
        second = csv_mod.check_code_change(state_path=state, repo_root=d)
        self.assertFalse(second["code_changed"])


class VintageWorkflowContractTests(unittest.TestCase):
    """JEG-205 follow-up: the workflow must actually dispatch on code changes.

    Regression: the first shipped workflow recorded the pipelines code hash
    without dispatching the chain (the dispatch step fired only on vintage
    change), silently consuming the code-change trigger -- zero dispatches for
    the core case instead of exactly one. These tests pin the step conditions
    against .github/workflows/source-vintage-check.yml.
    """

    WORKFLOW = ROOT / ".github" / "workflows" / "source-vintage-check.yml"

    @classmethod
    def _step_block(cls, step_name):
        text = cls.WORKFLOW.read_text(encoding="utf-8")
        marker = "- name: " + step_name
        idx = text.index(marker)
        nxt = text.find("\n      - name: ", idx + 1)
        return text[idx:] if nxt == -1 else text[idx:nxt]

    @classmethod
    def _step_if(cls, step_name):
        block = cls._step_block(step_name)
        m = re.search(r"^\s*if:\s*(.+)$", block, re.M)
        assert m, "no if: condition on step %r" % step_name
        return m.group(1).strip()

    def test_dispatch_fires_on_code_change(self):
        cond = self._step_if("Dispatch rebuild-chain on changes")
        self.assertIn("code_changed", cond)

    def test_dispatch_fires_on_vintage_change(self):
        cond = self._step_if("Dispatch rebuild-chain on changes")
        self.assertIn("changed", cond)

    def test_dispatch_step_has_id(self):
        self.assertIn("id: dispatch", self._step_block("Dispatch rebuild-chain on changes"))

    def test_record_requires_successful_dispatch(self):
        # Negative regression: a bare `code_changed == 'True'` record step
        # consumes the trigger without a dispatch. The record must be gated
        # on the dispatch step's success so a failed dispatch retries next
        # hour instead of losing the code change.
        cond = self._step_if("Record pipelines code hash")
        self.assertIn("code_changed", cond)
        self.assertIn("steps.dispatch.outcome", cond)

    def test_report_only_when_nothing_triggered(self):
        cond = self._step_if("Report no changes")
        self.assertIn("changed", cond)
        self.assertIn("code_changed", cond)

    @classmethod
    def _run_check_step(cls, stub_exit, stub_json):
        """Run the check step's script under `bash -e` (the Actions default)
        with check_source_vintage.py replaced by a stub. Returns (rc, outputs)."""
        import subprocess
        import textwrap
        block = cls._step_block("Check source vintage")
        body = block.split("run: |", 1)[1]
        script = textwrap.dedent(body)
        target = "python3 pipelines/check_source_vintage.py --json"
        assert target in script, "script invocation not found in check step"
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "stub.sh"
            stub.write_text(f"#!/bin/bash\necho '{stub_json}'\nexit {stub_exit}\n")
            stub.chmod(0o755)
            script = script.replace(target, str(stub)).replace("/tmp/vintage-check.json",
                                                              str(Path(tmp) / "out.json"))
            out = Path(tmp) / "gh_output"
            env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                   "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(Path(tmp) / "summary")}
            proc = subprocess.run(["bash", "-e", "-c", script], env=env,
                                  capture_output=True, text=True, timeout=60)
            outputs = out.read_text() if out.exists() else ""
        return proc.returncode, outputs

    def test_check_step_survives_script_exit_1(self):
        # Regression (JEG-268): the script exits 1 on every change detection
        # (fail-closed). If bash -e fails the check step on that, outputs are
        # never parsed and the dispatch never fires -- the hourly trigger was
        # dead on its primary path. 2026-10-08: run the step instead of
        # pinning the `|| true` literal, which test_no_failopen_workflows
        # forbids on pull steps; the step now captures the exit code.
        rc, outputs = self._run_check_step(1, '{"changed": true, "code_changed": false, "code_hash": "abc"}')
        self.assertEqual(rc, 0)
        self.assertIn("changed=True", outputs)

    def test_check_step_fails_on_a_crash(self):
        # The other half: a crash (exit code other than 0/1) must fail the
        # step, not be swallowed.
        rc, _ = self._run_check_step(2, "{}")
        self.assertNotEqual(rc, 0)


class DispatchInputContractTests(unittest.TestCase):
    """JEG-269: `gh workflow run -f/--field` inputs must be declared.

    Regression: source-vintage-check.yml dispatched rebuild-chain.yml with
    `-f source="source-vintage-check"` while rebuild-chain.yml declared no
    inputs block. gh / the dispatches API rejects undeclared inputs
    (HTTP 422: workflow does not have the input), so the dispatch step failed
    even though the dispatch condition was satisfied. Production proof: run
    37111598432 (2026-10-03 ~09:02 UTC) -- check step success, dispatch step
    failure, record skipped, run failure.
    """

    WF_DIR = ROOT / ".github" / "workflows"

    @classmethod
    def _declared_inputs(cls, workflow_file):
        """Names under `on: workflow_dispatch: inputs:` (regex parse)."""
        lines = workflow_file.read_text(encoding="utf-8").splitlines()
        base = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*workflow_dispatch:\s*(#.*)?$", line):
                base = len(line) - len(line.lstrip())
                start = i
                break
        if base is None:
            return set()
        declared = set()
        in_inputs = False
        inputs_indent = None
        for line in lines[start + 1:]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base:
                break
            if re.match(r"^\s*inputs:\s*(#.*)?$", line):
                in_inputs = True
                inputs_indent = indent
                continue
            if in_inputs:
                if indent <= inputs_indent:
                    break
                m = re.match(r"^\s*([\w-]+):", line)
                if m and indent == inputs_indent + 2:
                    declared.add(m.group(1))
        return declared

    @classmethod
    def _dispatch_invocations(cls, workflow_file):
        """Yield (target workflow file, [input names]) per `gh workflow run`."""
        text = workflow_file.read_text(encoding="utf-8")
        for m in re.finditer(r"gh workflow run\s+(\S+)", text):
            target, rest_start = m.group(1), m.end()
            tail = text[rest_start:rest_start + 400].split("\n      - ")[0]
            inputs = re.findall(r"(?:^|\s)(?:-f|--field)\s+([\w-]+)=", tail)
            tgt = cls.WF_DIR / target
            if not tgt.exists() and not target.endswith(".yml"):
                alt = cls.WF_DIR / (target + ".yml")
                if alt.exists():
                    tgt = alt
            yield tgt, inputs

    def test_rebuild_chain_declares_source_input(self):
        declared = self._declared_inputs(self.WF_DIR / "rebuild-chain.yml")
        self.assertIn("source", declared)

    def test_all_dispatched_inputs_are_declared(self):
        failures = []
        for wf in sorted(self.WF_DIR.glob("*.yml")):
            for target, inputs in self._dispatch_invocations(wf):
                if not inputs or not target.exists():
                    continue
                declared = self._declared_inputs(target)
                for name in inputs:
                    if name not in declared:
                        failures.append(
                            "%s passes -f %s= to %s, which does not declare it"
                            % (wf.name, name, target.name))
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
