#!/usr/bin/env python3
"""Record a failed post-rebuild validation in the chain status (GAP-MAIN-STATIC-PIN).

rebuild-chain.yml runs `make validate` on the freshly rebuilt fixture before
anything is committed. On 2026-10-07 the chain pushed a fixture (0b0ddee) that
failed tests.test_static_export, which turned main red and blocked every PR
check and Pages deploy. The validation now runs inside the chain step, so a red
validate fails the step and the workflow's existing failure path publishes only
the status, never the fixture.

This script makes that failure legible: it reads the captured validate log and
marks output/comparison-chain-status.json (and the dist/modules monitor copy)
as failed, with the failing test ids and assertion lines, so the monitor names
the pin that broke instead of showing a green chain.

Usage:
    python3 pipelines/record_post_rebuild_validation.py --log output/post-rebuild-validate.log
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

STATUS_PATHS = ("output/comparison-chain-status.json",
                "dist/modules/comparison-chain-status.json")
TEST_LINE = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)]+)\)")
ASSERT_LINE = re.compile(r"^\w*(Error|Exception)\b.*")
MAKE_LINE = re.compile(r"^make: \*\*\* \[([^\]]+)\]")


def summarize(log_text: str) -> dict:
    failed_tests, assertions, make_targets = [], [], []
    for line in log_text.splitlines():
        m = TEST_LINE.match(line)
        if m:
            failed_tests.append(f"{m.group(1)} {m.group(3)}")
            continue
        if ASSERT_LINE.match(line) and line not in assertions:
            assertions.append(line.strip())
            continue
        m = MAKE_LINE.match(line)
        if m:
            make_targets.append(m.group(1))
    detail = "; ".join(failed_tests + assertions) or (
        f"make validate failed at {', '.join(make_targets)}" if make_targets
        else "make validate failed (see the workflow log)")
    return {
        "status": "failed",
        "command": "make validate",
        "failed_tests": failed_tests,
        "assertions": assertions[:20],
        "make_targets": make_targets,
        "detail": detail,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def record(repo: Path, log_text: str) -> dict:
    block = summarize(log_text)
    status = {}
    src = repo / STATUS_PATHS[0]
    if src.exists():
        try:
            status = json.loads(src.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
    status["post_rebuild_validation"] = block
    status["failed"] = sorted(set(status.get("failed") or []) | {"post_rebuild_validation"})
    status["success"] = False
    for rel in STATUS_PATHS:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path("."))
    args = ap.parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace") if args.log.exists() else ""
    block = record(args.repo, text)
    print(f"::error::Post-rebuild validation failed; fixture not published: {block['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
