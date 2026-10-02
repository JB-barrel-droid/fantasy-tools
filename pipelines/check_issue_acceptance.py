#!/usr/bin/env python3
"""Machine-checkable acceptance validator for lane issue bodies.

A lane issue must carry an ``Acceptance (runnable)`` section that names the
exact commands a reviewer can paste and re-execute to prove "done". This
script parses a single Linear issue body (passed as a file path or via
``--stdin``) and rejects the issue when one of five pieces is missing:

    1. an ``Acceptance (runnable)`` heading exists,
    2. real ``python3 -m unittest tests.test_<x>`` modules are named,
    3. verify scripts (``pipelines/verify_<x>.py`` or ``verify_live.py``)
       are named where the issue implies one,
    4. a rendered/output check is named when the body mentions
       ``dashboard``, ``render``, ``chart`` or ``publish``,
    5. a negative-test note names a simulated broken state.

Exit code 0 on pass, exit code 1 with the rejection language naming the
exact missing piece. The rejection strings are the copy-paste contract
from ``docs/delegation-workflow.md`` -> "Acceptance (Runnable) Convention"
so a reviewer can paste the rejection straight back to the lane.

This script is intentionally CLI-only and assumes the issue body is
plaintext markdown. It does NOT call the Linear API and does NOT touch
the network; it reads a local file or stdin. That keeps the validator
safe to run inside a sandboxed lane branch.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Regex patterns --------------------------------------------------------------

# A heading like "## Acceptance (runnable)" / "### Acceptance (runnable)"
# (case-insensitive, any leading level of "#").
ACCEPTANCE_HEADING_RE = re.compile(
    r"""(?m)^[ \t]*#{1,6}[ \t]+Acceptance[ \t]*\(runnable\)[ \t]*$""",
    re.IGNORECASE,
)

# Body of the acceptance section: from the heading up to the next
# markdown heading at the same or higher level.
ACCEPTANCE_BODY_RE = re.compile(
    r"""(?ms)^(?P<level>\#{1,6})[ \t]+Acceptance[ \t]*\(runnable\)[ \t]*\n
        (?P<body>.*?)
        (?=^[ \t]*\#[1-6][ \t]+\S|^[ \t]*$|$)""",
    re.IGNORECASE,
)

# ``python3 -m unittest tests.test_<x>`` with module name made of letters,
# digits and underscores. ``-v`` or other unittest flags are tolerated.
TEST_COMMAND_RE = re.compile(
    r"""python3\s+-m\s+unittest\b[^\n`"]*tests\.test_[A-Za-z0-9_]+""",
    re.IGNORECASE,
)

# ``python3 pipelines/verify_<x>.py`` or ``python3 verify_live.py``.
# Flags after the script name are tolerated.
VERIFY_COMMAND_RE = re.compile(
    r"""python3\s+(?:pipelines/)?verify_[A-Za-z0-9_]+\.py\b""",
    re.IGNORECASE,
)

# Heuristic for UI-affecting changes. The body (anywhere) mentions any of
# these tokens. ``publish`` is included because a publish path almost
# always affects rendered output.
UI_HEURISTIC_RE = re.compile(
    r"\b(dashboard|render|chart|publish)\w*\b",
    re.IGNORECASE,
)

# Rendered/output commands we accept as evidence for check 4.
#   - ``node tests/rendered_gate/gate.mjs``
#   - ``python3 verify_live.py tv-<build>`` with a build tag
#   - generic ``playwright`` invocations under tests/
#   - a rendered HTML/JSON output capture (e.g. ``output/rendered-gate.json``)
RENDERED_RE = re.compile(
    r"""(?x)
        (?:
            node[ \t]+tests/rendered_gate/gate\.mjs
          | python3[ \t]+verify_live\.py[ \t]+tv-[A-Za-z0-9_\-\.]+
          | playwright[ \t]+[^\n`]*
          | output/rendered-gate\.json
        )
    """,
    re.IGNORECASE,
)

# A negative-test note names a simulated broken state. Accept either the
# naming ``negative test``/``negative-test`` or ``simulated broken state``,
# or a sentence that ties a regression guard to the state it must catch.
NEGATIVE_TEST_RE = re.compile(
    r"""(?ix)
    (?:
        negative[ \t-]*test
      | simulated[ \t]+broken[ \t]+state
      | regression[ \t]+guard
      | simulated[ \t]+broken
      | broken[ \t]+fixture
      | simulate[ \t]+a[ \t]+broken
    )
    """
)


# Rejection language ------------------------------------------------------
#
# These strings are the copy-paste contract from
# ``docs/delegation-workflow.md`` -> "Acceptance (Runnable) Convention".
# A reviewer should be able to paste the exact line, twice back to the
# lane without rewriting.

REJECTION_MISSING_SECTION = (
    "REJECT: Acceptance (runnable) section is missing. Add a section "
    "titled exactly `## Acceptance (runnable)` (or a deeper heading) that "
    "names the reviewer-pasteable commands and exit codes."
)

REJECTION_MISSING_TESTS = (
    "REJECT: Acceptance (runnable) does not name which "
    "`python3 -m unittest` modules run. Paste the module list "
    "(`python3 -m unittest tests.test_<x>`) and the exit codes."
)

REJECTION_MISSING_VERIFY = (
    "REJECT: Acceptance (runnable) does not name the "
    "`python3 pipelines/verify_<x>.py` command(s) and flags. "
    "Paste them (`python3 pipelines/verify_<x>.py --flag`) and their exit codes."
)

REJECTION_MISSING_RENDERED = (
    "REJECT: Acceptance (runnable) does not name the rendered/output "
    "command. Paste `node tests/rendered_gate/gate.mjs dist` (or "
    "`python3 verify_live.py tv-<build>`) and its exit code."
)

REJECTION_MISSING_NEGATIVE_TEST = (
    "REJECT: Acceptance (runnable) does not show the regression guard "
    "catches the bug it names. Add a sentence naming the simulated "
    "broken state and which test fails on it."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_acceptance_body(issue_body: str) -> str | None:
    """Return the ``Acceptance (runnable)`` section body, or ``None``.

    Looks for an ``## Acceptance (runnable)`` (or deeper) heading and
    returns everything under it until the next markdown heading. The
    match is case-insensitive.
    """

    if not ACCEPTANCE_HEADING_RE.search(issue_body):
        return None

    match = ACCEPTANCE_BODY_RE.search(issue_body)
    if match is None:
        # Heading exists but no body found (last section of the file).
        heading_match = ACCEPTANCE_HEADING_RE.search(issue_body)
        if heading_match is None:
            return None
        return issue_body[heading_match.end():]

    return match.group("body")


def check_acceptance_body(body: str, *, is_ui_affecting: bool | None = None) -> list[str]:
    """Run the five acceptance checks against the section ``body``.

    Returns an empty list when the body passes; otherwise each entry is a
    rejection string naming the exact missing piece. The caller is
    responsible for the heading-exists check (use
    :func:`extract_acceptance_body` first); when ``body`` is ``None`` the
    section-missing rejection is appended automatically.
    """

    if body is None:
        return [REJECTION_MISSING_SECTION]

    rejections: list[str] = []

    if not TEST_COMMAND_RE.search(body):
        rejections.append(REJECTION_MISSING_TESTS)

    if not VERIFY_COMMAND_RE.search(body):
        rejections.append(REJECTION_MISSING_VERIFY)

    # Check 4 is conditional: only when the issue body mentions a UI
    # keyword. We re-derive it here so a caller that passes a precomputed
    # ``is_ui_affecting`` flag does not have to duplicate the heuristic.
    ui_hits = UI_HEURISTIC_RE.search(body)
    if is_ui_affecting is None:
        ui_affecting = bool(ui_hits)
    else:
        ui_affecting = bool(is_ui_affecting)

    if ui_affecting and not RENDERED_RE.search(body):
        rejections.append(REJECTION_MISSING_RENDERED)

    if not NEGATIVE_TEST_RE.search(body):
        rejections.append(REJECTION_MISSING_NEGATIVE_TEST)

    return rejections


def issue_is_ui_affecting(issue_body: str) -> bool:
    """Return ``True`` if the issue body (any section) names a UI keyword."""

    return bool(UI_HEURISTIC_RE.search(issue_body))


def validate_issue_body(issue_body: str) -> list[str]:
    """Validate the full issue body and return the list of rejections."""

    body = extract_acceptance_body(issue_body)
    return check_acceptance_body(body, is_ui_affecting=issue_is_ui_affecting(issue_body))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "issue_body",
        nargs="?",
        type=Path,
        help="Path to a file containing the Linear issue body (plaintext markdown).",
    )
    group.add_argument(
        "--stdin",
        action="store_true",
        help="Read the issue body from stdin instead of a file path.",
    )
    args = parser.parse_args(argv)

    if args.stdin:
        issue_body = sys.stdin.read()
    else:
        if args.issue_body is None:
            parser.error("issue_body path or --stdin is required")
        issue_body = args.issue_body.read_text(encoding="utf-8")

    rejections = validate_issue_body(issue_body)
    if rejections:
        for rejection in rejections:
            print(rejection, file=sys.stderr)
        return 1

    if args.stdin:
        sys.stderr.write("Acceptance (runnable) section OK: 5/5 checks passed.\n")
    else:
        sys.stderr.write(
            f"Acceptance (runnable) section OK in {args.issue_body}: 5/5 checks passed.\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())