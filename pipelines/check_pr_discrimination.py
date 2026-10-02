#!/usr/bin/env python3
"""
Check PR discrimination proof checklist.

Validates that new health guards include concrete failure discrimination evidence:
1. Guard ID
2. Concrete broken scenario
3. Broken-state test/command + observed result
4. Correct-state test/command + observed result

Usage:
    python3 pipelines/check_pr_discrimination.py --body-file <path> --diff-file <path>

Exit codes:
    0 - Pass: checklist complete OR explicit applicability reason provided
    1 - Fail: required checklist items missing/blank/placeholder
"""

import argparse
import re
import sys
from pathlib import Path


# Patterns that indicate placeholder/empty content
PLACEHOLDER_PATTERNS = [
    r'^TBD$',
    r'^TODO$',
    r'^describe here$',
    r'^<[^>]+>$',  # Markdown-style placeholders like <describe>
    r'^--*$',  # Just dashes
    r'^__*$',  # Just underscores
    r'^\s*$',  # Whitespace only
]


def is_placeholder(text: str) -> bool:
    """Check if text is empty or a placeholder."""
    if not text or not text.strip():
        return True

    text_lower = text.strip().lower()
    for pattern in PLACEHOLDER_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return True

    return False


def extract_section(content: str, section_name: str) -> str:
    """Extract content from a named section in the PR body."""
    # Match section headers (markdown ## or ###)
    pattern = rf'##?\s*{re.escape(section_name)}.*?\n(.*?)(?=\n##?\s|\Z)'
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def extract_checklist_item(content: str, item_name: str) -> str:
    """Extract a checklist item from the discrimination proof section."""
    # Look for the item header and capture until the next item or section
    pattern = rf'###\s*{re.escape(item_name)}.*?\n(.*?)(?=###|\Z)'
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def check_guard_applicability(diff_content: str) -> bool:
    """
    Determine if the diff adds a new production guard.

    Returns True if the diff touches guard-related files.
    """
    guard_file_patterns = [
        r'pipelines/check_.*\.py$',
        r'pipelines/.*_guard.*\.py$',
        r'opens/.*check.*\.py$',
        r'tools/guard.*\.mjs$',
        r'tools/guard.*\.js$',
        r'\.github/workflows/.*\.yml$',
    ]

    for line in diff_content.split('\n'):
        if line.startswith('+++') or line.startswith('---'):
            filepath = line.replace('+++ ', '').replace('--- ', '').strip()
            if filepath.startswith('a/') or filepath.startswith('b/'):
                filepath = filepath[2:]

            for pattern in guard_file_patterns:
                if re.search(pattern, filepath):
                    return True

    return False


def check_applicability_declaration(content: str) -> tuple[bool, str]:
    """
    Check if an applicability declaration is present.

    Returns (has_declaration, reason)
    """
    # Look for the applicability declaration section
    section = extract_section(content, 'Applicability Declaration')

    if not section:
        return False, "No applicability declaration found"

    # Check if any checkbox is marked
    checkboxes = [
        r'\[x\]\s*.*docs-only change',
        r'\[x\]\s*.*test-only change',
        r'\[x\]\s*.*refactor',
        r'\[x\]\s*.*Other:',
    ]

    for pattern in checkboxes:
        if re.search(pattern, section, re.IGNORECASE):
            # Extract the reason if "Other" is selected
            if 'Other:' in section:
                other_match = re.search(r'Other:\s*(.+?)(?:\n|$)', section, re.IGNORECASE | re.DOTALL)
                if other_match:
                    reason = other_match.group(1).strip()
                    if not is_placeholder(reason):
                        return True, reason
            return True, "Explicit applicability reason provided"

    return False, "No checkbox marked in applicability declaration"


def validate_checklist(content: str) -> tuple[bool, list[str]]:
    """
    Validate the discrimination proof checklist.

    Returns (is_valid, list of missing/empty items)
    """
    missing_items = []

    # Extract the checklist section
    checklist_section = extract_section(content, 'Discrimination Proof Checklist')

    if not checklist_section:
        return False, ["Discrimination Proof Checklist section not found"]

    # Check each required item
    required_items = [
        ("Guard ID", "1\.\s*Guard ID"),
        ("Concrete Broken Scenario", "2\.\s*Concrete Broken Scenario"),
        ("Broken-State Test/Command + Observed Result", "3\.\s*Broken-State Test"),
        ("Correct-State Test/Command + Observed Result", "4\.\s*Correct-State Test"),
    ]

    for item_name, pattern in required_items:
        # Find the item content
        match = re.search(rf'{pattern}.*?\n(.*?)(?=###|\Z)', checklist_section, re.IGNORECASE | re.DOTALL)
        if match:
            item_content = match.group(1).strip()
            if is_placeholder(item_content):
                missing_items.append(item_name)
        else:
            missing_items.append(item_name)

    return len(missing_items) == 0, missing_items


def main():
    parser = argparse.ArgumentParser(
        description='Check PR discrimination proof checklist for new health guards.'
    )
    parser.add_argument(
        '--body-file',
        required=True,
        help='Path to the PR body markdown file'
    )
    parser.add_argument(
        '--diff-file',
        required=True,
        help='Path to the git diff file'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Read the PR body
    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"ERROR: Body file not found: {body_path}", file=sys.stderr)
        sys.exit(1)

    pr_body = body_path.read_text()

    # Read the diff
    diff_path = Path(args.diff_file)
    if not diff_path.exists():
        print(f"ERROR: Diff file not found: {diff_path}", file=sys.stderr)
        sys.exit(1)

    diff_content = diff_path.read_text()

    # Check if this is a new guard applicability
    is_guard_applicable = check_guard_applicability(diff_content)

    if args.verbose:
        print(f"Guard applicability: {is_guard_applicable}")

    if not is_guard_applicable:
        # Check for applicability declaration
        has_declaration, reason = check_applicability_declaration(pr_body)
        if has_declaration:
            if args.verbose:
                print(f"Pass: Non-guard change with applicability declaration: {reason}")
            print("PASS: Non-guard change - applicability declared")
            sys.exit(0)
        else:
            print("FAIL: Non-guard change requires applicability declaration", file=sys.stderr)
            print(f"Reason: {reason}", file=sys.stderr)
            sys.exit(1)

    # This is a new guard - validate the checklist
    is_valid, missing_items = validate_checklist(pr_body)

    if is_valid:
        if args.verbose:
            print("Pass: All checklist items present and non-empty")
        print("PASS: Discrimination proof checklist complete")
        sys.exit(0)
    else:
        print("FAIL: Discrimination proof checklist incomplete", file=sys.stderr)
        print(f"Missing or empty items: {', '.join(missing_items)}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
