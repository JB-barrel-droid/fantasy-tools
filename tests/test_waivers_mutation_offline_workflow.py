"""Guard: the Waivers mutation offline classes run on every PR without blocking a merge (JEG-1373).

Jeremy (2026-10-29, option A on the JEG-1279 question): the three offline classes of
tests/test_waivers_mutation_specificity.py run on every PR as a separate check that flags a failure
but does not block merges, and they stay out of test-core, the deploy gate for data math.

  - .github/workflows/waivers-mutation-offline.yml fires on every pull request (no paths or branches
    filter) and runs exactly the three offline classes, never the Chromium class and never a browser install;
  - a failure turns that check red: no continue-on-error, no `|| true` / `|| echo` / `exit 0`, and the
    test step that pipes through tee sets pipefail;
  - it stays out of the required path: preview.yml and pages.yml never name it, and no test-core target
    in the Makefile runs the mutation module.

Plain-text parsing on purpose (PyYAML is not on the CI runner). Each rule is negative-tested against a
mutated copy of the real file.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
NAME = "waivers-mutation-offline.yml"
MODULE = "tests.test_waivers_mutation_specificity"
OFFLINE = ("ClassifierOfflineTests", "AnchorOfflineTests", "FixtureOfflineTests")
BROWSER_CLASS = "MutationSpecificityRenderTests"
SWALLOWS = (re.compile(r"continue-on-error\s*:\s*true", re.I), re.compile(r"\|\|\s*(true|echo|:)"),
            re.compile(r"^\s*exit 0\s*$", re.M))


def read(path):
    return path.read_text(encoding="utf-8")


def workflow_problems(text):
    out = []
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#")) + "\n"
    m = re.search(r"^  pull_request:\n((?:    .*\n)*)", text, re.M)
    if not m:
        return ["no pull_request trigger"]
    if re.search(r"^    (paths|paths-ignore|branches|branches-ignore):", m.group(1), re.M):
        out.append("the pull_request trigger is filtered: it must run on every PR")
    for cls in OFFLINE:
        if f"{MODULE}.{cls}" not in text:
            out.append(f"does not run {cls}")
    if BROWSER_CLASS in text or re.search(rf"{re.escape(MODULE)}(?!\.)", text):
        out.append("runs the Chromium class or the whole module (needs a browser and a build)")
    if re.search(r"playwright install", text):
        out.append("installs a browser: the offline classes need none")
    for pattern in SWALLOWS:
        if pattern.search(text):
            out.append(f"swallows a failure ({pattern.pattern})")
    if "| tee" in text and "set -o pipefail" not in text:
        out.append("pipes the tests through tee without pipefail, so a failure would exit 0")
    if not re.search(r"^    timeout-minutes: \d+$", text, re.M):
        out.append("job has no timeout")
    return out


def make_targets(text, prefix):
    """Recipe lines of every Makefile target whose name starts with prefix."""
    out, current = {}, None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+):", line)
        if m:
            current = m.group(1) if m.group(1).startswith(prefix) else None
            if current:
                out[current] = [line]
        elif current and (line.startswith("\t") or not line.strip()):
            out[current].append(line)
        else:
            current = None
    return out


def gate_problems(preview, pages, makefile):
    out = []
    for name, text in (("preview.yml", preview), ("pages.yml", pages)):
        if "waivers-mutation" in text or "test_waivers_mutation" in text:
            out.append(f"{name} names the Waivers mutation check: it must stay out of the required path")
    targets = make_targets(makefile, "test-core")
    if "test-core" not in targets:
        out.append("no test-core target found in the Makefile")
    for target, lines in targets.items():
        if any("test_waivers_mutation" in line for line in lines):
            out.append(f"Makefile {target} runs the Waivers mutation module: keep it out of test-core")
    return out


class RealFiles(unittest.TestCase):
    def test_workflow(self):
        self.assertEqual([], workflow_problems(read(WF / NAME)))

    def test_stays_out_of_the_gate(self):
        self.assertEqual([], gate_problems(read(WF / "preview.yml"), read(WF / "pages.yml"), read(ROOT / "Makefile")))

    def test_the_named_classes_exist(self):
        source = read(ROOT / "tests" / "test_waivers_mutation_specificity.py")
        for cls in OFFLINE + (BROWSER_CLASS,):
            self.assertIsNotNone(re.search(rf"^class {cls}\(unittest\.TestCase\):", source, re.M), cls)


class Mutations(unittest.TestCase):
    """Each rule catches a broken copy of the real file."""

    def setUp(self):
        self.wf = read(WF / NAME)

    def assertCaught(self, text, needle):
        problems = workflow_problems(text)
        self.assertTrue(any(needle in p for p in problems), problems)

    def test_paths_filter_is_caught(self):
        text = self.wf.replace("converted_to_draft]\n", 'converted_to_draft]\n    paths:\n      - "app/v2/waivers.*"\n', 1)
        self.assertCaught(text, "filtered")

    def test_dropped_class_is_caught(self):
        text = self.wf.replace(f"            {MODULE}.AnchorOfflineTests \\\n", "", 1)
        self.assertCaught(text, "AnchorOfflineTests")

    def test_whole_module_is_caught(self):
        text = self.wf.replace(f"{MODULE}.FixtureOfflineTests", MODULE, 1)
        self.assertCaught(text, "Chromium class or the whole module")

    def test_browser_install_is_caught(self):
        text = self.wf.replace("playwright==1.49.1\n", "playwright==1.49.1\n          python3 -m playwright install chromium\n", 1)
        self.assertCaught(text, "installs a browser")

    def test_continue_on_error_is_caught(self):
        text = self.wf.replace("    timeout-minutes: 10\n", "    timeout-minutes: 10\n    continue-on-error: true\n", 1)
        self.assertCaught(text, "swallows")

    def test_or_true_is_caught(self):
        text = self.wf.replace('"$RUNNER_TEMP/waivers-mutation.log"\n', '"$RUNNER_TEMP/waivers-mutation.log" || true\n', 1)
        self.assertCaught(text, "swallows")

    def test_missing_pipefail_is_caught(self):
        self.assertCaught(self.wf.replace("set -o pipefail\n", "", 1), "pipefail")

    def test_missing_timeout_is_caught(self):
        self.assertCaught(re.sub(r"    timeout-minutes: \d+\n", "", self.wf), "timeout")

    def test_required_check_dependency_is_caught(self):
        preview = read(WF / "preview.yml").replace("needs: [pr-state, preview-build, preview-shard]",
                                                    "needs: [pr-state, preview-build, preview-shard, waivers-mutation-offline]", 1)
        problems = gate_problems(preview, read(WF / "pages.yml"), read(ROOT / "Makefile"))
        self.assertTrue(any("preview.yml" in p for p in problems), problems)

    def test_module_in_test_core_is_caught(self):
        makefile = read(ROOT / "Makefile").replace("test-core:\n", f"test-core:\n\tpython3 -m unittest {MODULE}.AnchorOfflineTests\n", 1)
        problems = gate_problems(read(WF / "preview.yml"), read(WF / "pages.yml"), makefile)
        self.assertTrue(any("Makefile test-core " in p for p in problems), problems)

    def test_module_in_a_shard_is_caught(self):
        makefile = read(ROOT / "Makefile").replace("test-core-shard-2:\n", f"test-core-shard-2:\n\tpython3 -m unittest {MODULE}\n", 1)
        problems = gate_problems(read(WF / "preview.yml"), read(WF / "pages.yml"), makefile)
        self.assertTrue(any("test-core-shard-2" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
