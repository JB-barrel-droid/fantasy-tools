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
PAGES = (ROOT / ".github/workflows/pages.yml").read_text()
PREVIEW = (ROOT / ".github/workflows/preview.yml").read_text()

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
    lineage = "python3 pipelines/build_source_value_lineage.py"
    if lineage in p_flags and p_flags[lineage] != v_flags.get(lineage):
        problems.append("lineage step continue-on-error differs from pages.yml")
    for key in ("python-version", "fetch-depth"):
        if setting(pages_text, key) != setting(preview_text, key):
            problems.append(f"{key} differs: pages={setting(pages_text, key)!r} "
                            f"preview={setting(preview_text, key)!r}")
    ref = setting(preview_text, "ref")
    if not ref or "pull_request.head.sha" not in ref:
        problems.append("checkout must use the PR head SHA, not the merge ref")
    if not re.search(r"^  pull_request:\s*$", preview_text, re.M):
        problems.append("preview must trigger on pull_request")
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

    def test_production_build_steps_are_the_expected_three(self):
        # If pages.yml changes its build steps this fails loudly, so the guard's
        # pinned list is updated deliberately instead of drifting unnoticed.
        self.assertEqual(
            [("make sync", False), ("make validate", True),
             ("python3 pipelines/build_source_value_lineage.py", True)],
            build_steps(PAGES))

    def test_dropping_a_build_step_is_caught(self):
        mutated = PREVIEW.replace("      - run: make sync\n", "")
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "build commands differ")

    def test_reordering_build_steps_is_caught(self):
        mutated = PREVIEW.replace(
            "      - run: make sync\n      - run: make validate\n",
            "      - run: make validate\n      - run: make sync\n")
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

    def test_lineage_flag_drift_is_caught(self):
        mutated = PREVIEW.replace("        continue-on-error: true\n", "", 1)
        self.assertNotEqual(PREVIEW, mutated)
        self.assertCaught(mutated, "lineage step continue-on-error differs")

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

    def test_any_deploy_or_pages_permission_is_caught(self):
        for word in FORBIDDEN_IN_PREVIEW:
            mutated = PREVIEW + f"\n# {word}\n"
            self.assertCaught(mutated, word)


if __name__ == "__main__":
    unittest.main()
