"""Run every recipe line of a Makefile target, continuing past failures.

`make test-unit` used to stop at the first failing module: on 2026-10-08 one
playwright timeout in tests.test_espn_zero_badge_render meant the ~90 modules
after it (test_rebuild_chain_workflow, test_rebuild_chain_conflict_handoff ...)
never ran in preview CI. This runner reads the target's recipe lines from the
Makefile, runs each one, and exits 1 at the end listing every failed line.

Usage: python3 tests/run_suite.py [--makefile PATH] TARGET

Recipe lines must be plain shell commands (no make variables); comment lines
are skipped. A leading "python3 " runs with this interpreter, so the runner
also works where python3 is not on PATH (Windows).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def recipe_lines(makefile: Path, target: str) -> list[str]:
    """The target's recipe commands, in order, without comments or @/- prefixes."""
    lines = makefile.read_text(encoding="utf-8").splitlines()
    header = re.compile(rf"^{re.escape(target)}\s*:(?!=)")
    start = next((i for i, line in enumerate(lines) if header.match(line)), None)
    if start is None:
        raise SystemExit(f"run_suite: no target {target!r} in {makefile}")
    commands = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        command = line.strip().lstrip("@-").strip()
        if not command or command.startswith("#"):
            continue
        if "$" in command or command.endswith("\\"):
            raise SystemExit(f"run_suite: {target} line needs make to expand it: {command}")
        commands.append(command)
    if not commands:
        raise SystemExit(f"run_suite: target {target!r} has no commands")
    return commands


def run(commands: list[str], cwd: Path) -> list[str]:
    failed = []
    for command in commands:
        argv_command = command
        if command.startswith("python3 "):
            argv_command = f'"{sys.executable}" {command[len("python3 "):]}'
        print(command, flush=True)
        started = time.monotonic()
        rc = subprocess.run(argv_command, shell=True, cwd=str(cwd)).returncode
        if rc != 0:
            failed.append(command)
            print(f"run_suite: FAILED (rc={rc}, {time.monotonic() - started:.0f}s): {command}", flush=True)
    return failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target")
    parser.add_argument("--makefile", type=Path, default=ROOT / "Makefile")
    args = parser.parse_args(argv)
    commands = recipe_lines(args.makefile, args.target)
    failed = run(commands, args.makefile.resolve().parent)
    print(f"\nrun_suite: {args.target}: {len(commands) - len(failed)}/{len(commands)} passed", flush=True)
    for command in failed:
        print(f"run_suite: failed: {command}", flush=True)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::{args.target}: {command}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
