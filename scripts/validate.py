"""Run `make validate` without make (Windows has no make binary).

Reads the Makefile, resolves the validate target's prerequisites in order
(reference, sync, guard-harness, test-core, test-integration), and runs each
recipe line the way make would: stop at the first failing line. --keep-going
runs every line and lists the failures at the end.

Only $(TODAY) is expanded (env TODAY, else today's date, like the Makefile's
`TODAY ?= $(shell date +%F)`); any other make variable is an error. A leading
"python3 " runs with this interpreter, since python3 on Windows is the Store stub.

Usage: python scripts/validate.py [--keep-going] [TARGET]
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"


def parse_rules(text: str) -> dict[str, tuple[list[str], list[str]]]:
    """target -> (prerequisites, recipe lines) for plain `target: deps` rules."""
    rules: dict[str, tuple[list[str], list[str]]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("\t"):
            if current is not None:
                command = line.strip().lstrip("@-").strip()
                if command and not command.startswith("#"):
                    rules[current][1].append(command)
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)(.*)$", line)
        current = match.group(1) if match else None
        if current is not None:
            rules[current] = (match.group(2).split("#")[0].split(), [])
    return rules


def commands_for(target: str, rules, seen=None) -> list[str]:
    seen = set() if seen is None else seen
    if target in seen:
        return []
    seen.add(target)
    if target not in rules:
        raise SystemExit(f"validate: no target {target!r} in {MAKEFILE}")
    prerequisites, recipe = rules[target]
    commands = [c for dep in prerequisites for c in commands_for(dep, rules, seen)]
    return commands + recipe


def expand(command: str, today: str) -> str:
    command = command.replace("$(TODAY)", today)
    if "$" in command or command.endswith("\\"):
        raise SystemExit(f"validate: line needs make to expand it: {command}")
    if command.startswith("python3 "):
        command = f'"{sys.executable}" {command[len("python3 "):]}'
    return command


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", default="validate")
    parser.add_argument("--keep-going", "-k", action="store_true")
    args = parser.parse_args(argv)

    today = os.environ.get("TODAY") or datetime.date.today().isoformat()
    rules = parse_rules(MAKEFILE.read_text(encoding="utf-8"))
    commands = [(c, expand(c, today)) for c in commands_for(args.target, rules)]

    failed = []
    ran = 0
    for shown, command in commands:
        ran += 1
        print(shown, flush=True)
        started = time.monotonic()
        rc = subprocess.run(command, shell=True, cwd=str(ROOT)).returncode
        if rc != 0:
            failed.append(shown)
            print(f"validate: FAILED (rc={rc}, {time.monotonic() - started:.0f}s): {shown}", flush=True)
            if not args.keep_going:
                break

    print(f"\nvalidate: {args.target}: {ran - len(failed)}/{len(commands)} lines passed", flush=True)
    for shown in failed:
        print(f"validate: failed: {shown}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
