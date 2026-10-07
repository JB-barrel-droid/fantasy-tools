"""Workflows never interpolate attacker-controlled event text into run scripts.

`${{ github.event.pull_request.body }}` (or a title, comment, review or commit
message) pasted into a `run:` script is evaluated by the shell: backticks and
$(...) in a PR description execute on the runner (script injection). On
2026-10-07 preview.yml's discrimination step did exactly that and failed with
exit 2 on a PR body containing `code spans`. Such values must reach scripts
through `env:` only.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
UNSAFE = re.compile(
    r"\$\{\{\s*github\.event\.(pull_request\.(body|title|head\.ref|head\.label)|"
    r"issue\.(body|title)|comment\.body|review\.body|review_comment\.body|"
    r"head_commit\.message|commits)\b[^}]*\}\}")


def run_block_offenders(text):
    """Lines inside `run:` blocks that interpolate unsafe event fields."""
    offenders, in_run, run_indent = [], False, 0
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if in_run and stripped and indent <= run_indent:
            in_run = False
        m = re.match(r"^(\s*)(- )?run:\s*(.*)$", line)
        if m:
            run_indent = len(m.group(1))
            if UNSAFE.search(m.group(3)):
                offenders.append(n)
            in_run = m.group(3).strip() in ("|", ">", "|-", ">-")
            continue
        if in_run and UNSAFE.search(line):
            offenders.append(n)
    return offenders


class NoEventInterpolationTest(unittest.TestCase):
    def test_no_workflow_interpolates_event_text_into_run(self):
        bad = {p.name: run_block_offenders(p.read_text()) for p in WORKFLOWS}
        self.assertEqual({k: v for k, v in bad.items() if v}, {})

    def test_the_pre_fix_preview_step_is_caught(self):
        old = ("      - name: Check\n        run: |\n"
               "          echo \"${{ github.event.pull_request.body }}\" > /tmp/pr_body.md\n")
        self.assertEqual(run_block_offenders(old), [3])

    def test_env_passthrough_is_allowed(self):
        ok = ("      - name: Check\n        env:\n"
              "          PR_BODY: ${{ github.event.pull_request.body }}\n"
              "        run: |\n          printf '%s\\n' \"$PR_BODY\" > /tmp/b.md\n")
        self.assertEqual(run_block_offenders(ok), [])


if __name__ == "__main__":
    unittest.main()
