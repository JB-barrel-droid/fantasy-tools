"""Guard: the preview build must be the production build (JEG-31).

A preview that quietly stops running the same steps as .github/workflows/pages.yml
proves nothing about what production will publish. These tests compare the two
workflow files' build steps and fail when they drift, and they also pin the
deliberate differences (blocking validate, PR head SHA, no deploy).

Every rule is negative-tested against a mutated copy of the real preview.yml, so
the guard is shown to catch the defect it names. Parsing is plain text on purpose:
PyYAML is not installed on the CI runner's unit-test step.

JEG-1170: preview.yml runs pages' `make validate` split in two: `make validate-base` in the
preview-build job (compared step for step with pages.yml) and test-core as the parallel
preview-shard matrix. The `preview` job is the required check and passes only when both
succeeded. tests/test_validate_shards.py pins the Makefile side.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
PREVIEW = (ROOT / ".github/workflows/preview.yml").read_text(encoding="utf-8")
FULL_SUITE = (ROOT / ".github/workflows/full-suite.yml").read_text(encoding="utf-8")

FORBIDDEN_IN_PREVIEW = ("deploy-pages", "upload-pages-artifact", "configure-pages",
                        "pages: write", "id-token: write")


# preview-build runs this where pages.yml runs `make validate`; the shards run the rest.
SPLIT_VALIDATE = {"make validate-base": "make validate"}
SHARD_COMMANDS = ["make reference", "make sync", "make test-core-shard-${{ matrix.shard }}"]


def job(text, name):
    """The text of one job under `jobs:` (header line included), or None."""
    m = re.search(rf"^  {re.escape(name)}:\s*\n((?:(?:    .*)?\n)*)", text, re.M)
    return m.group(0) if m else None


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


def run_command(block):
    """The step's single-line `run:` command, or None (multi-line blocks are not
    build steps: they are the deploy gating in pages.yml and reporting here)."""
    m = re.search(r"run:\s*(\S.*)$", block, re.M)
    if not m:
        return None
    cmd = m.group(1).strip()
    return None if cmd in ("|", ">", "|-", ">-") else cmd


def build_steps(text):
    return [(run_command(b), "continue-on-error: true" in b)
            for b in steps(text) if run_command(b)]


def setting(text, key):
    m = re.search(rf"^\s*{re.escape(key)}:\s*\"?([^\"\n]+)\"?\s*$", text, re.M)
    return m.group(1).strip() if m else None


def check_preview(preview_text, pages_text):
    """Return a list of problems; empty means the preview matches production."""
    problems = []
    build = job(preview_text, "preview-build")
    if build is None:
        return ["preview.yml must have a preview-build job"]
    p_steps = build_steps(pages_text)
    v_steps = [(SPLIT_VALIDATE.get(c, c), off) for c, off in build_steps(build)]
    if any(c == "make validate" for c, _ in build_steps(build)):
        problems.append("preview-build must run make validate-base: the full make validate "
                        "would run test-core again on top of the shards")
    if [c for c, _ in p_steps] != [c for c, _ in v_steps]:
        problems.append(f"build commands differ: pages={[c for c, _ in p_steps]} "
                        f"preview={[c for c, _ in v_steps]}")
    p_flags, v_flags = dict(p_steps), dict(v_steps)
    if v_flags.get("make validate"):
        problems.append("make validate-base must be blocking in the preview "
                        "(no continue-on-error)")
    for command, blocking_off in p_flags.items():
        if command in v_flags and v_flags[command] != blocking_off:
            problems.append(f"{command}: continue-on-error differs from pages.yml")
    for name in ("preview-build", "preview-shard"):
        body = job(preview_text, name) or ""
        for key in ("python-version", "fetch-depth"):
            if setting(pages_text, key) != setting(body, key):
                problems.append(f"{name}: {key} differs: pages={setting(pages_text, key)!r} "
                                f"preview={setting(body, key)!r}")
        ref = setting(body, "ref")
        if not ref or "pull_request.head.sha" not in ref:
            problems.append(f"{name}: checkout must use the PR head SHA, not the merge ref")
    problems += shard_problems(preview_text) + aggregate_problems(preview_text)
    if not re.search(r"^  pull_request:\s*$", preview_text, re.M):
        problems.append("preview must trigger on pull_request")
    gate = [b for b in steps(build) if "tests/rendered_gate/gate.mjs" in b]
    if len(gate) != 1:
        problems.append("preview must run the rendered gate (tests/rendered_gate/gate.mjs) exactly once")
    elif "continue-on-error" in gate[0]:
        problems.append("the rendered gate must be blocking (no continue-on-error)")
    elif run_command(gate[0]):
        problems.append("the rendered gate must be a multi-line run block (JEG-47 scope)")
    for word in FORBIDDEN_IN_PREVIEW:
        if word in preview_text:
            problems.append(f"preview must not deploy or hold Pages permissions: {word!r}")
    # JEG-978 moved the full suite out of the preview job; JEG-1169 moved it off
    # pull requests entirely (it never finished inside 45 minutes and held a
    # runner). preview.yml must not run make test-unit in any job.
    runs_suite = re.compile(r"^\s+(- )?(run: )?make test-unit\s*$", re.M)  # the command, not comments
    if runs_suite.search(preview_text):
        problems.append("make test-unit must not run in preview.yml (nightly full-suite.yml owns it)")
    if re.search(r"^  full-suite:\s*$", preview_text, re.M):
        problems.append("the full-suite job must live in full-suite.yml, not preview.yml")
    return problems


def shard_problems(preview_text):
    """The preview-shard matrix runs test-core, blocking, with the browser required."""
    shard = job(preview_text, "preview-shard")
    if shard is None:
        return ["preview.yml must have a preview-shard job (test-core runs there)"]
    problems = []
    if "continue-on-error" in shard:
        problems.append("preview-shard must be blocking (no continue-on-error)")
    if re.search(r"^    if:", shard, re.M):
        problems.append("preview-shard must run unconditionally (no job-level if:)")
    if not re.search(r"^      fail-fast: false$", shard, re.M):
        problems.append("preview-shard must set fail-fast: false")
    if not re.search(r"^        shard: \[\d", shard, re.M):
        problems.append("preview-shard must have a shard matrix")
    if [c for c, _ in build_steps(shard)] != SHARD_COMMANDS:
        problems.append(f"preview-shard commands must be {SHARD_COMMANDS}, "
                        f"got {[c for c, _ in build_steps(shard)]}")
    if 'echo "RENDER_TESTS_REQUIRED=1" >> "$GITHUB_ENV"' not in shard:
        problems.append("preview-shard must set RENDER_TESTS_REQUIRED=1 (render tests may not skip)")
    return problems


def aggregate_problems(preview_text):
    """The `preview` check needs preview-build and every shard, and fails unless all succeeded."""
    agg = job(preview_text, "preview")
    if agg is None:
        return ["preview.yml must have the aggregate `preview` job (the required check)"]
    problems = []
    needs = re.search(r"^    needs:\s*\[([^\]]*)\]", agg, re.M)
    needs = {n.strip() for n in needs.group(1).split(",")} if needs else set()
    if needs != {"preview-build", "preview-shard"}:
        problems.append(f"the preview job must need exactly preview-build and preview-shard, got {sorted(needs)}")
    if not re.search(r"^    if: always\(\)$", agg, re.M):
        problems.append("the preview job must run if: always() so a failed or skipped job fails it")
    if "continue-on-error" in agg:
        problems.append("the preview job must be blocking (no continue-on-error)")
    for n in ("preview-build", "preview-shard"):
        if f"needs.{n}.result" not in agg:
            problems.append(f"the preview job must check needs.{n}.result")
    if not re.search(r'= "success" \] && \[ "\$\w+" = "success" \]\s*$', agg, re.M):
        problems.append("the preview job must fail unless every result is success")
    return problems


def check_full_suite(text):
    """JEG-1169: the full suite runs nightly and on demand, never on a PR, and
    stays informational (job-level continue-on-error)."""
    problems = []
    on = re.search(r"^on:\s*\n((?:[ \t]+.*\n|\s*\n)+)", text, re.M)
    on = on.group(1) if on else ""
    if re.search(r"^  (pull_request|pull_request_target|push):", on, re.M):
        problems.append("full-suite.yml must not run on pull requests or pushes")
    if not re.search(r"^  schedule:\s*$", on, re.M):
        problems.append("full-suite.yml must run on a nightly schedule")
    if not re.search(r"^  workflow_dispatch:", on, re.M):
        problems.append("full-suite.yml must accept workflow_dispatch")
    if not re.search(r"^\s+make test-unit\s*$", text, re.M):
        problems.append("full-suite.yml must run make test-unit")
    if not re.search(r"^    continue-on-error: true$", text, re.M):
        problems.append("the full-suite job must keep job-level continue-on-error")
    return problems


class PreviewMatchesPagesTest(unittest.TestCase):
    def assertCaught(self, mutated, fragment):
        problems = check_preview(mutated, PAGES)
        self.assertTrue(any(fragment in p for p in problems),
                        msg=f"expected a problem containing {fragment!r}, got {problems}")

    def test_real_preview_matches_production(self):
        self.assertEqual([], check_preview(PREVIEW, PAGES))

    def test_production_build_steps_are_the_expected_four(self):
        # If pages.yml changes its build steps this fails loudly, so the guard's
        # pinned list is updated deliberately instead of drifting unnoticed.
        # JEG-133: make validate is blocking on every run (no continue-on-error,
        # no path-conditional skip); the rendered gate is the next build step
        # but uses a multi-line run block and is excluded by run_command.
        self.assertEqual(
            [("make sync", False), ("make validate", False),
             # GAP-E2E-FIDELITY / GAP-031 (2026-10-08): monitor signals
             # produced on every deploy, never blocking it.
             ("python3 pipelines/build_e2e_fidelity.py", True),
             ("python3 pipelines/check_data_accuracy.py", True)],
            build_steps(PAGES))

    def test_pages_runs_the_rendered_gate(self):
        # JEG-133: the rendered gate runs in pages.yml (production deploy),
        # not only in preview.yml, so a direct push to main is gated too.
        gate = [b for b in steps(PAGES) if "tests/rendered_gate/gate.mjs" in b]
        self.assertEqual(len(gate), 1,
                         "pages.yml must run the rendered gate exactly once")
        self.assertNotIn("continue-on-error", gate[0],
                         "the rendered gate must be blocking in pages.yml")

    def test_pages_has_no_path_conditional_validate(self):
        # JEG-133: the deploy gate must not depend on which files the last
        # commit touched. A path-conditional skip is exactly the bypass
        # GAP-037 / PH-6 / BH-1 name.
        self.assertNotIn("dist/modules/", PAGES,
                         "pages.yml must not gate on dist/modules/ paths")
        self.assertNotIn("product_changed", PAGES,
                         "pages.yml must not have a path-conditional gate step")
        self.assertNotIn("HEAD~1", PAGES,
                         "pages.yml must not diff against the previous commit "
                         "to decide whether to validate")

    def test_pages_validate_is_blocking(self):
        # JEG-133: make validate must be blocking in pages.yml. The previous
        # shape used continue-on-error + a path-conditional re-fail step.
        flags = dict(build_steps(PAGES))
        self.assertIn("make validate", flags)
        self.assertFalse(flags["make validate"],
                         "make validate must block the deploy in pages.yml")

    def test_dropping_a_build_step_is_caught(self):
        mutated = PREVIEW.replace("      - run: make sync\n", "")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "build commands differ")

    def test_reordering_build_steps_is_caught(self):
        # JEG-139 inserted a multi-line step (the PR discrimination check)
        # between "make sync" and "make validate", so the old two-line swap
        # no longer matches any text. Swap two adjacent single-line build
        # steps instead: the e2e fidelity card and the data accuracy refresh
        # (the lineage rebuild used here before was retired 2026-10-08).
        e2e = ("      - name: Build end-to-end fidelity card\n"
               "        run: python3 pipelines/build_e2e_fidelity.py\n"
               "        continue-on-error: true\n")
        acc = ("      - name: Refresh data accuracy signals\n"
               "        run: python3 pipelines/check_data_accuracy.py\n"
               "        continue-on-error: true\n")
        mutated = PREVIEW.replace(e2e + acc, acc + e2e)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "build commands differ")

    def test_a_new_production_step_missing_from_preview_is_caught(self):
        pages = PAGES.replace("      - run: make sync\n",
                              "      - run: make sync\n      - run: make reference\n")
        self.assertNotEqual(PAGES, pages)
        problems = check_preview(PREVIEW, pages)
        self.assertTrue(any("build commands differ" in p for p in problems), problems)

    def test_non_blocking_validate_is_caught(self):
        mutated = PREVIEW.replace("      - run: make validate-base\n",
                                  "      - run: make validate-base\n        continue-on-error: true\n")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "must be blocking")

    def test_continue_on_error_drift_is_caught(self):
        # The first continue-on-error in preview.yml belongs to the e2e
        # fidelity step (non-blocking in pages.yml).
        mutated = PREVIEW.replace(
            "        run: python3 pipelines/build_e2e_fidelity.py\n        continue-on-error: true\n",
            "        run: python3 pipelines/build_e2e_fidelity.py\n", 1)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "build_e2e_fidelity.py: continue-on-error differs")

    def test_full_validate_in_preview_build_is_caught(self):
        # validate-base swapped back for validate would run test-core twice per PR.
        mutated = PREVIEW.replace("      - run: make validate-base\n", "      - run: make validate\n")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "must run make validate-base")

    def test_removing_the_shard_job_is_caught(self):
        mutated = PREVIEW.replace(job(PREVIEW, "preview-shard"), "")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "must have a preview-shard job")

    def test_non_blocking_shard_job_is_caught(self):
        mutated = PREVIEW.replace("  preview-shard:\n    runs-on: ubuntu-latest\n",
                                  "  preview-shard:\n    runs-on: ubuntu-latest\n    continue-on-error: true\n")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "preview-shard must be blocking")

    def test_non_blocking_shard_step_is_caught(self):
        mutated = PREVIEW.replace("      - run: make test-core-shard-${{ matrix.shard }}\n",
                                  "      - run: make test-core-shard-${{ matrix.shard }}\n        continue-on-error: true\n")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "preview-shard must be blocking")

    def test_shard_job_not_running_test_core_is_caught(self):
        mutated = PREVIEW.replace("make test-core-shard-${{ matrix.shard }}", "make test-core-shard-1")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "preview-shard commands")

    def test_shard_job_without_required_browser_is_caught(self):
        shard = job(PREVIEW, "preview-shard")
        mutated = PREVIEW.replace(shard, shard.replace('          echo "RENDER_TESTS_REQUIRED=1" >> "$GITHUB_ENV"\n', ""))
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "RENDER_TESTS_REQUIRED")

    def test_removing_the_aggregate_job_is_caught(self):
        mutated = PREVIEW.replace(job(PREVIEW, "preview"), "")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "aggregate `preview` job")

    def test_aggregate_not_needing_the_shards_is_caught(self):
        mutated = PREVIEW.replace("needs: [preview-build, preview-shard]", "needs: [preview-build]")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "must need exactly")

    def test_aggregate_without_always_is_caught(self):
        mutated = PREVIEW.replace("    if: always()\n", "")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "if: always()")

    def test_aggregate_that_ignores_results_is_caught(self):
        mutated = re.sub(r'\[ "\$BUILD_RESULT" = "success" \] && \[ "\$SHARD_RESULT" = "success" \]', "true", PREVIEW)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "unless every result is success")

    def test_non_blocking_aggregate_is_caught(self):
        mutated = PREVIEW.replace("    if: always()\n", "    if: always()\n    continue-on-error: true\n")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "the preview job must be blocking")

    def test_shard_fetch_depth_drift_is_caught(self):
        shard = job(PREVIEW, "preview-shard")
        mutated = PREVIEW.replace(shard, shard.replace("fetch-depth: 2", "fetch-depth: 1"))
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "preview-shard: fetch-depth differs")

    def test_python_version_drift_is_caught(self):
        mutated = PREVIEW.replace('python-version: "3.12"', 'python-version: "3.11"')
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "python-version differs")

    def test_fetch_depth_drift_is_caught(self):
        mutated = PREVIEW.replace("fetch-depth: 2", "fetch-depth: 1")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "fetch-depth differs")

    def test_merge_ref_checkout_is_caught(self):
        mutated = re.sub(r"          ref: .*\n", "", PREVIEW)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "PR head SHA")

    def test_missing_pull_request_trigger_is_caught(self):
        mutated = PREVIEW.replace("  pull_request:\n", "", 1)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "pull_request")

    def test_removing_the_rendered_gate_is_caught(self):
        mutated = PREVIEW.replace("node tests/rendered_gate/gate.mjs", "echo skipped")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "rendered gate")

    def test_non_blocking_rendered_gate_is_caught(self):
        mutated = PREVIEW.replace("        id: gate\n", "        id: gate\n        continue-on-error: true\n")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "must be blocking")

    def test_full_suite_back_in_the_preview_job_is_caught(self):
        # The pre-JEG-978 shape: the suite as the preview job's last step.
        mutated = PREVIEW.replace(
            "      - uses: actions/checkout@v4", "      - run: make test-unit\n      - uses: actions/checkout@v4", 1)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "must not run in preview.yml")

    def test_full_suite_job_back_in_preview_is_caught(self):
        # The JEG-978 shape: a separate full-suite job inside preview.yml.
        mutated = PREVIEW + "\n  full-suite:\n    runs-on: ubuntu-latest\n    steps:\n      - run: |\n          make test-unit\n"
        self.assertCaught(mutated, "must not run in preview.yml")
        self.assertCaught(mutated, "must live in full-suite.yml")

    def test_real_full_suite_is_nightly_and_informational(self):
        self.assertEqual([], check_full_suite(FULL_SUITE))

    def test_full_suite_on_pull_request_is_caught(self):
        mutated = FULL_SUITE.replace("on:\n", "on:\n  pull_request:\n", 1)
        self.assertNotEqual(FULL_SUITE, mutated)
        self.assertTrue(any("pull requests" in p for p in check_full_suite(mutated)))

    def test_full_suite_without_schedule_is_caught(self):
        mutated = re.sub(r"  schedule:\n    - cron: .*\n", "", FULL_SUITE)
        self.assertNotEqual(FULL_SUITE, mutated)
        self.assertTrue(any("nightly schedule" in p for p in check_full_suite(mutated)))

    def test_blocking_full_suite_job_is_caught(self):
        mutated = FULL_SUITE.replace("    continue-on-error: true\n    timeout-minutes", "    timeout-minutes", 1)
        self.assertNotEqual(FULL_SUITE, mutated)
        self.assertTrue(any("continue-on-error" in p for p in check_full_suite(mutated)))

    def test_any_deploy_or_pages_permission_is_caught(self):
        for word in FORBIDDEN_IN_PREVIEW:
            mutated = PREVIEW + f"\n# {word}\n"
            self.assertCaught(mutated, word)

    # JEG-133 negative tests: catch reintroduction of the bypass GAP-037 names.
    # The current pages.yml is intentionally clean (no path-conditional skip,
    # blocking validate, blocking rendered gate); these mutations re-introduce
    # each defect and must be flagged.

    def test_reintroducing_path_conditional_validate_is_caught(self):
        # Inject the old diff-based "only monitor files changed" step. The
        # test_pages_has_no_path_conditional_validate assertions must fail.
        mutated = PAGES + (
            "\n      - name: Path-conditional gating (the bug GAP-037 names)\n"
            "        id: bad\n"
            "        run: |\n"
            "          if git diff --name-only HEAD~1 HEAD | grep -qv '^dist/modules/'; then\n"
            "            echo 'product_changed=true'\n"
            "          else\n"
            "            echo 'product_changed=false'\n"
            "          fi\n"
        )
        self.assertNotEqual(PAGES, mutated)
        # Each of these is exactly one of the assertions in
        # test_pages_has_no_path_conditional_validate; a regression that
        # re-introduces the bypass re-introduces at least one of them.
        self.assertIn("dist/modules/", mutated,
                      "test_pages_has_no_path_conditional_validate must catch this")
        self.assertIn("HEAD~1", mutated,
                      "test_pages_has_no_path_conditional_validate must catch this")
        self.assertIn("product_changed", mutated,
                      "test_pages_has_no_path_conditional_validate must catch this")

    def test_reintroducing_non_blocking_rendered_gate_in_pages_is_caught(self):
        # Take the pages.yml gate block and add continue-on-error: true.
        mutated = PAGES.replace(
            "        id: gate\n",
            "        id: gate\n        continue-on-error: true\n", 1)
        self.assertNotEqual(PAGES, mutated)
        gate = [b for b in steps(mutated) if "tests/rendered_gate/gate.mjs" in b]
        self.assertEqual(len(gate), 1)
        self.assertIn("continue-on-error", gate[0],
                      "a non-blocking rendered gate in pages.yml must fail the test")

    def test_reintroducing_non_blocking_validate_in_pages_is_caught(self):
        # Add continue-on-error back to make validate in pages.yml.
        mutated = PAGES.replace(
            "      - run: make validate\n",
            "      - run: make validate\n        continue-on-error: true\n", 1)
        self.assertNotEqual(PAGES, mutated)
        flags = dict(build_steps(mutated))
        self.assertTrue(flags.get("make validate"),
                        "a non-blocking validate in pages.yml must fail the test")


if __name__ == "__main__":
    unittest.main()
