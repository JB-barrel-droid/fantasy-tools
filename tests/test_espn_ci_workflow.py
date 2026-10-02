"""JEG-102: the ESPN daily CI scrape must run, and must fail closed.

Before this fix the scheduled run crashed with `ModuleNotFoundError: No module named
'identity'`, the crash was swallowed by `|| echo "Scraper failed, using existing data"`,
the save was skipped by an `else echo "No fresh ESPN data"` branch, and the job was
green while `espn_season_projections` stopped updating.

These tests execute the real `run:` scripts from the workflow in a throwaway directory
with a stub scraper, and every rule is negative-tested against the OLD scrape step
(kept below as text) so a guard that cannot fail is caught. Parsing is plain text
(PyYAML is not on the CI unit-test step).
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/espn-supabase-sync.yml").read_text()
SCRAPER = ROOT / "pipelines" / "pull_espn_projections.py"

# The scrape step as it was on main before JEG-102 (verified in the 2026-10-02 run log).
OLD_SCRAPE_RUN = """\
# Run the ESPN scraper (outputs to /tmp/espn_projections.csv)
# The scraper is idempotent: only writes if data changed
python3 pipelines/pull_espn_projections.py --out /tmp/espn_projections.csv --meta /tmp/espn_meta.json || echo "Scraper failed, using existing data"
"""
OLD_SAVE_RUN = """\
# Save the scraped CSV to Supabase
# Uses --espn-csv to specify the fresh scrape output
if [ -f /tmp/espn_projections.csv ]; then
  python3 pipelines/save_espn_cbs_references.py --source espn \\
    --espn-csv /tmp/espn_projections.csv \\
    --espn-meta /tmp/espn_meta.json
else
  echo "No fresh ESPN data, skipping Supabase save"
fi
"""


def step_run(text, name):
    """The `run: |` script of the step called `name`, dedented."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == f"- name: {name}")
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for i in range(start + 1, len(lines)):
        l = lines[i]
        if l.strip() and (len(l) - len(l.lstrip())) <= indent and l.lstrip().startswith("- "):
            end = i
            break
    block = lines[start:end]
    run_at = next(i for i, l in enumerate(block) if l.strip().startswith("run: |"))
    body = []
    run_indent = len(block[run_at]) - len(block[run_at].lstrip())
    for l in block[run_at + 1:]:
        if l.strip() and (len(l) - len(l.lstrip())) <= run_indent:
            break
        body.append(l)
    return textwrap.dedent("\n".join(body)) + "\n"


def step_text(text, name):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == f"- name: {name}")
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for l in lines[start + 1:]:
        if l.strip() and (len(l) - len(l.lstrip())) <= indent and l.lstrip().startswith("- "):
            break
        out.append(l)
    return "\n".join(out)


def swallows_failure(run_text, step_block=""):
    """Reasons the scrape step could report success after a scraper failure."""
    reasons = []
    if "set -e" not in run_text:
        reasons.append("no `set -e`")
    for line in run_text.splitlines():
        code = line.split("#", 1)[0]
        if "||" in code and "exit 1" not in code and "{" not in code:
            reasons.append(f"swallowing `||` on: {code.strip()}")
    if "continue-on-error" in step_block:
        reasons.append("continue-on-error")
    return reasons


def run_script(script, cwd, env=None):
    return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def localize(script, tmp):
    return script.replace("/tmp/espn_", f"{tmp}/espn_").replace('"$GITHUB_STEP_SUMMARY"', f'"{tmp}/summary.md"')


def stub_repo(tmp, behavior):
    """A directory with a stub scraper whose behaviour is `behavior`."""
    pipelines = Path(tmp) / "pipelines"
    pipelines.mkdir()
    body = {
        "crash": "import sys; sys.exit(1)",
        "silent_zero_no_csv": "import sys; sys.exit(0)",
        "few_rows": "import sys; open(sys.argv[sys.argv.index('--out')+1],'w').write('h\\n' + 'r\\n'*3)",
        "good": "import sys; open(sys.argv[sys.argv.index('--out')+1],'w').write('h\\n' + 'r\\n'*500)",
    }[behavior]
    (pipelines / "pull_espn_projections.py").write_text(body + "\n")


class ScrapeStepFailsClosedTest(unittest.TestCase):
    def setUp(self):
        self.run_text = step_run(WORKFLOW, "Scrape ESPN projections")
        self.step = step_text(WORKFLOW, "Scrape ESPN projections")

    def run_step(self, run_text, behavior):
        with tempfile.TemporaryDirectory() as tmp:
            stub_repo(tmp, behavior)
            r = run_script(localize(run_text, tmp), cwd=tmp)
            return r.returncode, r.stdout + r.stderr

    def test_text_guard_fires_on_the_old_step_and_passes_the_new_one(self):
        self.assertTrue(swallows_failure(OLD_SCRAPE_RUN), "the guard must flag the old step")
        self.assertEqual(swallows_failure(self.run_text, self.step), [])

    def test_scraper_crash_fails_the_job(self):
        code, _ = self.run_step(self.run_text, "crash")
        self.assertNotEqual(code, 0)

    def test_negative_old_step_reports_success_after_a_crash(self):
        code, _ = self.run_step(OLD_SCRAPE_RUN, "crash")
        self.assertEqual(code, 0, "premise: the old step really did swallow the crash")

    def test_zero_exit_with_no_csv_fails(self):
        code, out = self.run_step(self.run_text, "silent_zero_no_csv")
        self.assertNotEqual(code, 0)
        self.assertIn("no CSV", out)

    def test_tiny_csv_fails(self):
        code, out = self.run_step(self.run_text, "few_rows")
        self.assertNotEqual(code, 0)
        self.assertIn("floor", out)

    def test_good_csv_passes_and_reports_the_row_count(self):
        code, out = self.run_step(self.run_text, "good")
        self.assertEqual(code, 0, out)
        self.assertIn("acquired 500 rows", out)


class SaveStepTest(unittest.TestCase):
    def setUp(self):
        self.run_text = step_run(WORKFLOW, "Save to Supabase")

    def test_no_skip_branch_remains(self):
        self.assertNotIn("skipping Supabase save", self.run_text)
        self.assertIn("skipping Supabase save", OLD_SAVE_RUN, "premise: the old step skipped")

    def test_dry_run_flag_is_wired_and_default_is_a_live_write(self):
        self.assertIn("--dry-run", self.run_text)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pipelines").mkdir()
            Path(tmp, "pipelines", "save_espn_cbs_references.py").write_text(
                "import sys; print('ARGS ' + ' '.join(sys.argv[1:]))\n")
            for dry, expect in (("true", True), ("", False), ("false", False)):
                r = run_script(localize(self.run_text, tmp), cwd=tmp, env={"DRY_RUN": dry})
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual("--dry-run" in r.stdout, expect, f"DRY_RUN={dry!r}: {r.stdout}")

    def test_save_failure_fails_the_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "pipelines").mkdir()
            Path(tmp, "pipelines", "save_espn_cbs_references.py").write_text("import sys; sys.exit(3)\n")
            r = run_script(localize(self.run_text, tmp), cwd=tmp)
            self.assertNotEqual(r.returncode, 0)


class ScraperRunsOutsideTheGoalWorkspaceTest(unittest.TestCase):
    """The CI failure itself: `import identity` could not be resolved from pipelines/."""

    def test_the_module_imports_in_the_repo_layout_and_finds_a_snapshot(self):
        code = (
            "import importlib.util, sys\n"
            "sys.argv = ['x', '--out', '/tmp/_e.csv', '--meta', '/tmp/_m.json']\n"
            f"spec = importlib.util.spec_from_file_location('pe', {str(SCRAPER)!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "print('SNAPSHOT', m.IDENTITY_SNAPSHOT, m.IDENTITY_SNAPSHOT.exists())\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            r = subprocess.run([sys.executable, "-c", code], cwd=tmp, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("True", r.stdout.split("SNAPSHOT", 1)[1])

    def test_negative_the_old_import_fails_exactly_as_ci_did(self):
        old = f"import sys; sys.path.insert(0, {str(ROOT / 'pipelines')!r}); import identity"
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, "-c", old], cwd=tmp, capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No module named 'identity'", r.stderr)

    def test_output_directories_are_created_inside_the_repo_output_dir(self):
        code = (
            "import importlib.util, sys, tempfile, pathlib\n"
            "sys.argv = ['x', '--out', '/tmp/_e.csv', '--meta', '/tmp/_m.json']\n"
            f"spec = importlib.util.spec_from_file_location('pe', {str(SCRAPER)!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "tmp = pathlib.Path(tempfile.mkdtemp())\n"
            "m.FILES, m.HIDDEN = tmp / 'files', tmp / 'hidden_files'\n"
            "assert not m.FILES.exists() and not m.HIDDEN.exists()\n"
            "m.ensure_output_dirs()\n"
            "assert m.FILES.is_dir() and m.HIDDEN.is_dir()\n"
            "print('GOAL', m.GOAL)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
            r = subprocess.run([sys.executable, "-c", code], cwd=tmp, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        goal = r.stdout.split("GOAL", 1)[1].strip()
        self.assertTrue(goal.startswith(str(ROOT)), f"working files must stay inside the repo, got {goal}")


if __name__ == "__main__":
    unittest.main()
