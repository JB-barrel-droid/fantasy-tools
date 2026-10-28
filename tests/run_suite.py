"""Run every recipe line of a Makefile target, continuing past failures.

`make test-unit` used to stop at the first failing module: on 2026-10-08 one
playwright timeout in tests.test_espn_zero_badge_render meant the ~90 modules
after it (test_rebuild_chain_workflow, test_rebuild_chain_conflict_handoff ...)
never ran in preview CI. This runner reads the target's recipe lines from the
Makefile, runs each one, and exits 1 at the end listing every failed line.

Usage: python3 tests/run_suite.py [--makefile PATH] TARGET

Recipe lines may use make variables ($(NODE_CHROMIUM) in the node harness
lines): when any line contains "$", the runner asks `make -n` for the expanded
recipe instead of running it. Comment lines are skipped. A leading "python3 " runs with this interpreter, so the runner
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


def clean_command(line: str) -> str:
    return line.strip().lstrip("@-").strip()


def expanded_recipe_lines(makefile: Path, target: str) -> list[str]:
    """The recipe as make expands it (`make -n` prints, never runs, the commands)."""
    try:
        proc = subprocess.run(["make", "-n", "-s", "-f", str(makefile), target],
                              cwd=str(makefile.resolve().parent), capture_output=True,
                              text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"run_suite: {target} needs make to expand variables but make failed: {exc}")
    if proc.returncode != 0:
        raise SystemExit(f"run_suite: make -n {target} failed (rc={proc.returncode}): {proc.stderr.strip()}")
    commands = [clean_command(line) for line in proc.stdout.splitlines()]
    return [c for c in commands if c and not c.startswith("#")]


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
        command = clean_command(line)
        if not command or command.startswith("#"):
            continue
        if command.endswith("\\"):
            raise SystemExit(f"run_suite: {target} has a continued line the runner cannot split: {command}")
        commands.append(command)
    if any("$" in command for command in commands):
        commands = expanded_recipe_lines(makefile, target)
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


def suite_guards(target: str) -> list[str]:
    """Cheap CI guards registered here without changing the Makefile recipes."""
    return (["python3 -m unittest tests.test_no_real_clock"]
            if target == "test-unit-modules" else [])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target")
    parser.add_argument("--makefile", type=Path, default=ROOT / "Makefile")
    args = parser.parse_args(argv)
    commands = suite_guards(args.target) + recipe_lines(args.makefile, args.target)
    failed = run(commands, args.makefile.resolve().parent)
    print(f"\nrun_suite: {args.target}: {len(commands) - len(failed)}/{len(commands)} passed", flush=True)
    for command in failed:
        print(f"run_suite: failed: {command}", flush=True)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::{args.target}: {command}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
