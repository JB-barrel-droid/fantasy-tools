"""Guard: the preview build must be the production build (JEG-31).

A preview that quietly stops running the same steps as .github/workflows/pages.yml
proves nothing about what production will publish. These tests compare the two
workflow files' build steps and fail when they drift, and they also pin the
deliberate differences (blocking validate, PR head SHA, no deploy).

Every rule is negative-tested against a mutated copy of the real preview.yml, so
the guard is shown to catch the defect it names. Parsing is plain text on purpose:
PyYAML is not installed on the CI runner's unit-test step.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
PREVIEW = (ROOT / ".github/workflows/preview.yml").read_text(encoding="utf-8")

FORBIDDEN_IN_PREVIEW = ("deploy-pages", "upload-pages-artifact", "configure-pages",
                        "pages: write", "id-token: write")


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
    p_steps, v_steps = build_steps(pages_text), build_steps(preview_text)
    if [c for c, _ in p_steps] != [c for c, _ in v_steps]:
        problems.append(f"build commands differ: pages={[c for c, _ in p_steps]} "
                        f"preview={[c for c, _ in v_steps]}")
    p_flags, v_flags = dict(p_steps), dict(v_steps)
    if v_flags.get("make validate"):
        problems.append("make validate must be blocking in the preview "
                        "(no continue-on-error)")
    for command, blocking_off in p_flags.items():
        if command in v_flags and v_flags[command] != blocking_off:
            problems.append(f"{command}: continue-on-error differs from pages.yml")
    for key in ("python-version", "fetch-depth"):
        if setting(pages_text, key) != setting(preview_text, key):
            problems.append(f"{key} differs: pages={setting(pages_text, key)!r} "
                            f"preview={setting(preview_text, key)!r}")
    ref = setting(preview_text, "ref")
    if not ref or "pull_request.head.sha" not in ref:
        problems.append("checkout must use the PR head SHA, not the merge ref")
    if not re.search(r"^  pull_request:\s*$", preview_text, re.M):
        problems.append("preview must trigger on pull_request")
    gate = [b for b in steps(preview_text) if "tests/rendered_gate/gate.mjs" in b]
    if len(gate) != 1:
        problems.append("preview must run the rendered gate (tests/rendered_gate/gate.mjs) exactly once")
    elif "continue-on-error" in gate[0]:
        problems.append("the rendered gate must be blocking (no continue-on-error)")
    elif run_command(gate[0]):
        problems.append("the rendered gate must be a multi-line run block (JEG-47 scope)")
    for word in FORBIDDEN_IN_PREVIEW:
        if word in preview_text:
            problems.append(f"preview must not deploy or hold Pages permissions: {word!r}")
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
        mutated = PREVIEW.replace("      - run: make validate\n",
                                  "      - run: make validate\n        continue-on-error: true\n")
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
