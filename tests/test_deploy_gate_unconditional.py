"""Guard: Pages runs exhaustive validation and rendered gates on every push.

A deploy gate that no unrelated commit can bypass must run on EVERY push to main,
regardless of which files the last commit touched. This test verifies:
  (a) the validate step has no `if:` clause
  (b) the rendered-gate step exists and has no `if:` clause
  (c) no step reintroduces `paths-ignore` or `steps.*.outputs.*` gating

This test FAILS on the base commit (5df093c9b199) where path-dependent gating
was still present and the rendered gate was missing, and PASSES after the fix.
"""
import os
import re
import subprocess
import unittest
from pathlib import Path

from tests.test_preview_workflow_matches_pages import (
    WORKFLOW_GUARDS, build_steps, job, setting, shard_problems,
)
from tests.test_validate_shards import matrix_problems

ROOT = Path(__file__).resolve().parent.parent
PAGES = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")


def steps(text):
    """Split the job's steps; each step is the text of one '      - ' block."""
    blocks, current = [], None
    for line in text.splitlines():
        if re.match(r"^      - ", line):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None and (line.startswith("        ") or not line.strip()):
            current.append(line)
        elif current is not None:
            blocks.append("\n".join(current))
            current = None
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def get_step(step_blocks, keyword):
    """Find a step block containing the keyword."""
    for block in step_blocks:
        if keyword in block:
            return block
    return None


def has_if_clause(step_block):
    """Check if a step block has an `if:` clause at step level (not inside run:)."""
    # Both YAML spellings place if at step level, outside the run block.
    for line in step_block.splitlines():
        if re.match(r"^(?:      -|       ) if:", line):
            return True
    return False


ARTIFACT_NAME = "github-pages-${{ github.sha }}-${{ github.run_attempt }}"
SUCCESS_GUARD = '[ "$BUILD_RESULT" = "success" ] && [ "$SHARD_RESULT" = "success" ]'


def pages_problems(text):
    """Fail closed across the build, exhaustive matrix, and publication boundary."""
    problems = []
    build, shard, deploy = (job(text, n) for n in ("build", "validate-shard", "deploy"))
    if not all((build, shard, deploy)):
        return ["Pages requires build, validate-shard and deploy jobs"]
    for name, body in (("build", build), ("validate-shard", shard)):
        if re.search(r"^    (if|needs|continue-on-error):", body, re.M):
            problems.append(f"{name} must start unconditionally and block on failure")
        if setting(body, "ref") != "${{ github.sha }}":
            problems.append(f"{name} must check out the exact run SHA")
        if 'echo "RENDER_TESTS_REQUIRED=1" >> "$GITHUB_ENV"' not in body:
            problems.append(f"{name} must require the browser")
        for block in steps(body):
            if has_if_clause(block):
                problems.append(f"{name} steps must have no if clause")
            if "continue-on-error" in block and not any(
                build_steps(block) == [(command, True)] for command in (
                    "python3 pipelines/build_e2e_fidelity.py",
                    "python3 pipelines/check_data_accuracy.py")):
                problems.append(f"{name} checks must block on failure")
    problems += shard_problems(text, "validate-shard")
    problems += matrix_problems((ROOT / "Makefile").read_text(encoding="utf-8"), text, "pages.yml")
    for command in (WORKFLOW_GUARDS, "make validate-base"):
        if (command, False) not in build_steps(build):
            problems.append(f"build must run blocking {command}")
    gate = get_step(steps(build), "tests/rendered_gate/gate.mjs")
    if gate is None:
        problems.append("rendered gate must keep blocking harnesses in build")
    else:
        for command in ("node tests/rendered_gate/gate.mjs dist --out rendered-gate.json",
                        "node tests/rendered_gate/bench_share_readout_harness.mjs dist",
                        "node tests/rendered_gate/gate_flexibility.mjs dist",
                        'if [ $rc -ne 0 ] || [ $rc2 -ne 0 ] || [ $rc3 -ne 0 ]; then exit 1; fi'):
            if command not in gate:
                problems.append(f"rendered gate must keep blocking harness: {command}")
    build_blocks = steps(build)
    uploads = [b for b in build_blocks if "uses: actions/upload-pages-artifact@" in b]
    if len(uploads) != 1 or uploads[0] != build_blocks[-1]:
        problems.append("build must upload exactly once, after all checks, as its last step")
    elif (setting(uploads[0], "path") != "dist" or setting(uploads[0], "name") != ARTIFACT_NAME):
        problems.append("upload must contain the build dist under its exact artifact name")
    if not re.search(r"^    outputs:\n      artifact-name: " + re.escape(ARTIFACT_NAME) + "$", build, re.M):
        problems.append("build must expose its uploaded artifact name for partial reruns")
    if text.count("uses: actions/upload-pages-artifact@") != 1:
        problems.append("only build may upload the publication artifact")
    if text.count("uses: actions/deploy-pages@") != 1:
        problems.append("only deploy may publish")
    if setting(deploy, "needs") != "[build, validate-shard]":
        problems.append("deploy must need build and the full shard matrix")
    if setting(deploy, "if") != "always()":
        problems.append("deploy must check failed, cancelled and skipped dependencies")
    if "continue-on-error" in deploy:
        problems.append("deploy must block on any failed check")
    deploy_blocks = steps(deploy)
    if len(deploy_blocks) != 2 or SUCCESS_GUARD not in deploy_blocks[0]:
        problems.append("deploy must check success first and then publish without rebuilding")
    else:
        guard, publish = deploy_blocks
        for binding in ("BUILD_RESULT: ${{ needs.build.result }}",
                        "SHARD_RESULT: ${{ needs.validate-shard.result }}"):
            if binding not in guard:
                problems.append("deploy must check the actual build and matrix results")
        if "uses: actions/deploy-pages@v4" not in publish:
            problems.append("deploy must publish after its success guard")
        if setting(publish, "artifact_name") != "${{ needs.build.outputs.artifact-name }}":
            problems.append("deploy must consume the successful build's exact artifact name")
        for block in deploy_blocks:
            if has_if_clause(block):
                problems.append("deploy steps must not bypass the success guard")
    if re.search(r"^\s+paths(?:-ignore)?:", text, re.M):
        problems.append("Pages must validate every push without path filters")
    return problems


class PagesParallelValidationTest(unittest.TestCase):
    def assertCaught(self, text, fragment):
        self.assertNotEqual(PAGES, text)
        problems = pages_problems(text)
        self.assertTrue(any(fragment in p for p in problems), problems)

    def test_real_pages_parallel_validation(self):
        self.assertEqual([], pages_problems(PAGES))

    def test_serial_pages_does_not_satisfy_parallel_contract(self):
        # This fails on the prior layout: no independent matrix or checked artifact handoff.
        self.assertCaught(PAGES.replace("  validate-shard:\n", "  old-shards:\n", 1),
                          "requires build, validate-shard and deploy")

    def test_conditional_or_allowed_failure_jobs_are_caught(self):
        for name in ("build", "validate-shard"):
            for field in ("if: false", "continue-on-error: true", "needs: [deploy]"):
                with self.subTest(name=name, field=field):
                    self.assertCaught(PAGES.replace(f"  {name}:\n", f"  {name}:\n    {field}\n", 1),
                                      "unconditionally and block")

    def test_conditional_or_allowed_failure_checks_are_caught(self):
        for command in (WORKFLOW_GUARDS, "make validate-base", "make test-core-shard-${{ matrix.shard }}"):
            for field in ("if: false", "continue-on-error: true"):
                with self.subTest(command=command, field=field):
                    self.assertCaught(PAGES.replace(f"run: {command}\n", f"run: {command}\n        {field}\n", 1),
                                      "no if clause" if field.startswith("if") else "block on failure")

    def test_build_and_shards_must_use_same_commit_and_require_browser(self):
        for name in ("build", "validate-shard"):
            body = job(PAGES, name)
            for old, new, fragment in (("ref: ${{ github.sha }}", "ref: main", "exact run SHA"),
                                       ('echo "RENDER_TESTS_REQUIRED=1"', 'echo "RENDER_TESTS_REQUIRED=0"', "require the browser")):
                with self.subTest(name=name, fragment=fragment):
                    self.assertCaught(PAGES.replace(body, body.replace(old, new, 1)), fragment)

    def test_each_rendered_harness_must_remain_blocking(self):
        for command in ("node tests/rendered_gate/gate.mjs dist --out rendered-gate.json",
                        "node tests/rendered_gate/bench_share_readout_harness.mjs dist",
                        "node tests/rendered_gate/gate_flexibility.mjs dist",
                        'if [ $rc -ne 0 ] || [ $rc2 -ne 0 ] || [ $rc3 -ne 0 ]; then exit 1; fi'):
            with self.subTest(command=command):
                self.assertCaught(PAGES.replace(command, "true", 1), "blocking harness")

    def test_shards_cannot_fail_fast_or_skip_commands(self):
        self.assertCaught(PAGES.replace("fail-fast: false", "fail-fast: true"), "fail-fast: false")
        self.assertCaught(PAGES.replace("      - run: make reference\n", ""), "commands must be")

    def test_dependency_and_success_guard_bypasses_are_caught(self):
        for old, new, fragment in (("needs: [build, validate-shard]", "needs: [build]", "full shard matrix"),
                                   ("if: always()", "if: success()", "skipped dependencies"),
                                   (SUCCESS_GUARD, "true", "check success first"),
                                   ("SHARD_RESULT: ${{ needs.validate-shard.result }}", "SHARD_RESULT: success", "actual build and matrix"),
                                   ("        uses: actions/deploy-pages@v4", "        if: always()\n        uses: actions/deploy-pages@v4", "bypass the success guard")):
            with self.subTest(fragment=fragment):
                self.assertCaught(PAGES.replace(old, new, 1), fragment)

    def test_actual_deploy_guard_rejects_every_non_success_result(self):
        guard = steps(job(PAGES, "deploy"))[0].split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in guard.splitlines())
        for build in ("success", "failure", "cancelled", "skipped"):
            for shard in ("success", "failure", "cancelled", "skipped"):
                with self.subTest(build=build, shard=shard):
                    result = subprocess.run(["bash", "-e", "-c", script], capture_output=True,
                                            env={**os.environ, "BUILD_RESULT": build, "SHARD_RESULT": shard})
                    self.assertEqual(result.returncode == 0, build == shard == "success")

    def test_artifact_must_come_from_the_rendered_build(self):
        upload = get_step(steps(job(PAGES, "build")), "uses: actions/upload-pages-artifact@")
        gate = get_step(steps(job(PAGES, "build")), "tests/rendered_gate/gate.mjs")
        # Move the upload before the rendered gate: the published bytes were never gated.
        mutated = PAGES.replace(upload, "", 1).replace(gate, upload + "\n" + gate, 1)
        self.assertCaught(mutated, "after all checks")
        for old, new, fragment in (("          path: dist", "          path: output", "build dist"),
                                   ("          name: " + ARTIFACT_NAME, "          name: other", "exact artifact name"),
                                   ("      artifact-name: " + ARTIFACT_NAME, "      artifact-name: other", "partial reruns"),
                                   ("artifact_name: ${{ needs.build.outputs.artifact-name }}", "artifact_name: github-pages", "successful build's exact artifact name")):
            with self.subTest(fragment=fragment):
                self.assertCaught(PAGES.replace(old, new, 1), fragment)
        self.assertCaught(PAGES.replace("      - id: deployment\n", "      - run: make sync\n      - id: deployment\n", 1), "without rebuilding")
        self.assertCaught(PAGES.replace("      - run: make reference\n", upload + "\n      - run: make reference\n", 1), "only build may upload")

    def test_path_filter_and_old_step_if_syntax_are_caught(self):
        self.assertCaught(PAGES.replace("    branches: [main]", "    branches: [main]\n    paths: [app/**]", 1), "without path filters")
        self.assertTrue(has_if_clause("      - if: false\n        run: make validate-base"))
        self.assertTrue(has_if_clause("      - run: make validate-base\n        if: false"))


class DeployGateUnconditionalTest(unittest.TestCase):
    """Verify deploy gates run unconditionally on every push to main."""

    def test_validate_step_has_no_if_clause(self):
        """(a) the validate step has no `if:` clause."""
        step = get_step(steps(PAGES), "make validate")
        self.assertIsNotNone(step, "pages.yml must have a 'make validate' step")
        self.assertFalse(
            has_if_clause(step),
            "make validate must run unconditionally (no `if:` clause)")

    def test_rendered_gate_step_exists_and_has_no_if_clause(self):
        """(b) the rendered-gate step exists and has no `if:` clause."""
        gate = get_step(steps(PAGES), "tests/rendered_gate/gate.mjs")
        self.assertIsNotNone(
            gate,
            "pages.yml must run the rendered gate (tests/rendered_gate/gate.mjs)")
        self.assertFalse(
            has_if_clause(gate),
            "rendered gate must run unconditionally (no `if:` clause)")

    def test_no_paths_ignore_gating(self):
        """(c) no step reintroduces paths-ignore gating."""
        self.assertNotIn(
            "paths-ignore", PAGES,
            "pages.yml must not use paths-ignore to skip validation")
        self.assertNotIn(
            "paths:", PAGES,
            "pages.yml must not use paths to conditionally run steps")

    def test_no_step_output_gating(self):
        """(c) no step uses steps.*.outputs.* to gate validate or rendered gate."""
        # Check for any conditional that references step outputs
        output_gating_patterns = [
            r"if:.*steps\.[a-z]+\.outputs\.",
            r"if:.*needs\.",
        ]
        for pattern in output_gating_patterns:
            matches = re.findall(pattern, PAGES)
            self.assertEqual(
                [], matches,
                f"pages.yml must not gate on step outputs (found: {matches})")

    def test_validate_step_is_not_continue_on_error(self):
        """make validate must be blocking (not continue-on-error)."""
        step = get_step(steps(PAGES), "make validate")
        self.assertIsNotNone(step, "pages.yml must have a 'make validate' step")
        self.assertNotIn(
            "continue-on-error: true", step,
            "make validate must block the deploy (not continue-on-error)")

    def test_rendered_gate_is_not_continue_on_error(self):
        """rendered gate must be blocking (not continue-on-error)."""
        gate = get_step(steps(PAGES), "tests/rendered_gate/gate.mjs")
        self.assertIsNotNone(
            gate,
            "pages.yml must run the rendered gate (tests/rendered_gate/gate.mjs)")
        self.assertNotIn(
            "continue-on-error: true", gate,
            "rendered gate must block the deploy (not continue-on-error)")



class DeployNeverStarves(unittest.TestCase):
    """2026-10-09: with cancel-in-progress: true, commits landing faster than a
    deploy cancelled every run and nothing went live for hours. A running deploy
    must finish; the newest pending run deploys next."""

    def test_running_deploy_is_not_cancelled(self):
        block = re.search(r"^concurrency:\n((?:  .*\n?)+)", PAGES, re.M)
        self.assertIsNotNone(block, "pages.yml has no concurrency block")
        self.assertRegex(block.group(1), r"cancel-in-progress:\s*false")

if __name__ == "__main__":
    unittest.main()
