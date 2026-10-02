"""Tests for ``pipelines/check_issue_acceptance.py``.

Public-API + CLI coverage. Five failing fixtures, one per check, each
asserting the rejection names only the missing piece. Rejection
language is the copy-paste contract from
``docs/delegation-workflow.md`` -> "Acceptance (Runnable) Convention".
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "pipelines" / "check_issue_acceptance.py"


PASSING_BODY = """\
# JEG-92: machine-checkable acceptance validator

## Acceptance (runnable)

- `python3 -m unittest tests.test_check_issue_acceptance -v` (exit 0).
- `python3 pipelines/verify_xxx.py --source foo` (exit 0).
- `node tests/rendered_gate/gate.mjs dist --out output/rendered-gate.json`
  (exit 0).
- Negative test: simulate a broken acceptance body and confirm the
  validator catches the missing unittest command.
"""

MISSING_SECTION_BODY = """\
# JEG-92: machine-checkable acceptance validator
"""

MISSING_TESTS_BODY = """\
# JEG-92: machine-checkable acceptance validator

## Acceptance (runnable)

- `python3 pipelines/verify_xxx.py --source foo` (exit 0).
- `node tests/rendered_gate/gate.mjs dist --out output/rendered-gate.json`
  (exit 0).
- Negative test: simulate a broken acceptance body and confirm the
  validator catches the missing unittest command.
"""

MISSING_VERIFY_BODY = """\
# JEG-92: machine-checkable acceptance validator

## Acceptance (runnable)

- `python3 -m unittest tests.test_check_issue_acceptance -v` (exit 0).
- `node tests/rendered_gate/gate.mjs dist --out output/rendered-gate.json`
  (exit 0).
- Negative test: simulate a broken acceptance body missing the verify
  script and confirm the validator catches it.
"""

MISSING_RENDERED_BODY = """\
# JEG-92: dashboard chart render regression

## Acceptance (runnable)

- `python3 -m unittest tests.test_dashboard_chart -v` (exit 0).
- `python3 pipelines/verify_xxx.py --source foo` (exit 0).
- Negative test: simulate a broken render where the chart axis labels
  disappear and confirm the dashboard test fails on the mutated fixture.
"""

MISSING_NEGATIVE_TEST_BODY = """\
# JEG-92: machine-checkable acceptance validator

## Acceptance (runnable)

- `python3 -m unittest tests.test_check_issue_acceptance -v` (exit 0).
- `python3 pipelines/verify_xxx.py --source foo` (exit 0).
- `node tests/rendered_gate/gate.mjs dist --out output/rendered-gate.json`
  (exit 0).
"""


def _run_cli(body: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"],
        input=body,
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=30,
    )


class ExtractAcceptanceBodyTest(unittest.TestCase):
    def test_heading_extracts_section_body(self):
        from pipelines.check_issue_acceptance import extract_acceptance_body

        body = extract_acceptance_body(PASSING_BODY)
        self.assertIsNotNone(body)
        self.assertIn("python3 -m unittest", body)
        self.assertIn("verify_xxx.py", body)

    def test_no_heading_returns_none(self):
        from pipelines.check_issue_acceptance import extract_acceptance_body

        self.assertIsNone(extract_acceptance_body(MISSING_SECTION_BODY))

    def test_case_insensitive_heading(self):
        from pipelines.check_issue_acceptance import extract_acceptance_body

        body = extract_acceptance_body(
            PASSING_BODY.replace("Acceptance (runnable)", "ACCEPTANCE (RUNNABLE)")
        )
        self.assertIsNotNone(body)
        self.assertIn("python3 -m unittest", body)

    def test_deeper_heading_levels(self):
        from pipelines.check_issue_acceptance import extract_acceptance_body

        body = extract_acceptance_body(
            PASSING_BODY.replace("## Acceptance", "##### Acceptance")
        )
        self.assertIsNotNone(body)
        self.assertIn("python3 -m unittest", body)


class UiHeuristicTest(unittest.TestCase):
    def test_dashboard_keyword(self):
        from pipelines.check_issue_acceptance import issue_is_ui_affecting

        self.assertTrue(issue_is_ui_affecting("We touched the dashboard render."))

    def test_publish_keyword(self):
        from pipelines.check_issue_acceptance import issue_is_ui_affecting

        self.assertTrue(issue_is_ui_affecting("Ready to publish tonight."))

    def test_no_ui_keyword(self):
        from pipelines.check_issue_acceptance import issue_is_ui_affecting

        self.assertFalse(issue_is_ui_affecting("Refactor a pure-Python helper."))


class ValidateIssueBodyTest(unittest.TestCase):
    def test_passing_body_returns_no_rejections(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        self.assertEqual([], validate_issue_body(PASSING_BODY))

    def test_missing_section_rejected(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        rejections = validate_issue_body(MISSING_SECTION_BODY)
        self.assertEqual(1, len(rejections))
        self.assertIn("Acceptance (runnable) section is missing", rejections[0])

    def test_missing_tests_rejected(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        rejections = validate_issue_body(MISSING_TESTS_BODY)
        self.assertEqual(1, len(rejections))
        self.assertIn("does not name which", rejections[0])
        self.assertIn("python3 -m unittest", rejections[0])

    def test_missing_verify_rejected(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        rejections = validate_issue_body(MISSING_VERIFY_BODY)
        self.assertEqual(1, len(rejections))
        self.assertIn("does not name the", rejections[0])
        self.assertIn("pipelines/verify", rejections[0])

    def test_missing_rendered_rejected_when_ui_affecting(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        rejections = validate_issue_body(MISSING_RENDERED_BODY)
        self.assertEqual(1, len(rejections))
        self.assertIn("does not name the rendered/output command", rejections[0])

    def test_missing_negative_test_rejected(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        rejections = validate_issue_body(MISSING_NEGATIVE_TEST_BODY)
        self.assertEqual(1, len(rejections))
        self.assertIn("regression guard catches the bug", rejections[0])

    def test_rendered_check_not_required_for_non_ui_body(self):
        from pipelines.check_issue_acceptance import validate_issue_body

        body = """\
# JEG-99: helper refactor

## Acceptance (runnable)

- `python3 -m unittest tests.test_helper -v` (exit 0).
- `python3 pipelines/verify_helper.py --flag foo` (exit 0).
- Negative test: simulate a broken helper and confirm the unittest
  fails on the mutated fixture.
"""
        self.assertEqual([], validate_issue_body(body))


class CliTest(unittest.TestCase):
    def test_passing_body_exits_zero(self):
        result = _run_cli(PASSING_BODY)
        self.assertEqual(0, result.returncode, msg=result.stderr)

    def test_missing_section_exits_one(self):
        result = _run_cli(MISSING_SECTION_BODY)
        self.assertEqual(1, result.returncode)
        self.assertIn("Acceptance (runnable) section is missing", result.stderr)

    def test_missing_tests_exits_one(self):
        result = _run_cli(MISSING_TESTS_BODY)
        self.assertEqual(1, result.returncode)
        self.assertIn("does not name which", result.stderr)

    def test_missing_verify_exits_one(self):
        result = _run_cli(MISSING_VERIFY_BODY)
        self.assertEqual(1, result.returncode)
        self.assertIn("does not name the", result.stderr)

    def test_missing_rendered_exits_one(self):
        result = _run_cli(MISSING_RENDERED_BODY)
        self.assertEqual(1, result.returncode)
        self.assertIn("does not name the rendered/output command", result.stderr)

    def test_missing_negative_test_exits_one(self):
        result = _run_cli(MISSING_NEGATIVE_TEST_BODY)
        self.assertEqual(1, result.returncode)
        self.assertIn("regression guard catches the bug", result.stderr)

    def test_rejection_named_exactly_once(self):
        result = _run_cli(MISSING_TESTS_BODY)
        self.assertEqual(1, result.returncode)
        self.assertEqual(1, result.stderr.count("REJECT:"))

    def test_rejection_language_uses_copy_paste_phrases(self):
        result = _run_cli(MISSING_TESTS_BODY)
        self.assertRegex(
            result.stderr,
            re.compile(
                r"Paste the module list \(`python3 -m unittest tests\.test_<x>`\)"
                r" and the exit codes"
            ),
        )


if __name__ == "__main__":
    unittest.main()