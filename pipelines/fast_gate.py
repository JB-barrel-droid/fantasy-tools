"""Choose PR tests from git paths; unknown or shared-risk paths run the full gate.

No GitHub API calls. The PR diff is merge-base..head, with renames disabled so
both the old and new path participate. Commands are argv lists, never shell text.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time

from pipelines.fast_gate_dependencies import inventory

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / "config/fast_gate.json"


def load_mapping(path=MAPPING):
    config = json.loads(Path(path).read_text())
    if config["version"] != 1:
        raise ValueError("unsupported fast-gate mapping version")
    if "smoke" not in config["full_shards"]:
        raise ValueError("full coverage must include smoke")
    for name, shard in config["shards"].items():
        commands = shard["commands"]
        if not isinstance(shard["build"], bool) or not isinstance(commands, list) or not commands:
            raise ValueError(f"invalid or empty shard: {name}")
        if any(not isinstance(cmd, list) or not cmd
               or any(not isinstance(arg, str) or not arg for arg in cmd) for cmd in commands):
            raise ValueError(f"shard commands must be nonempty argv lists: {name}")
    for name in config["full_shards"]:
        if name not in config["shards"]:
            raise ValueError(f"unknown full-suite shard: {name}")
    for rule in config["rules"] + config["dependencies"]:
        if not rule["paths"] or not rule["shards"]:
            raise ValueError("empty mapping rule")
        for name in rule["shards"]:
            if name not in config["shards"]:
                raise ValueError(f"unknown shard: {name}")
    return config


def matches(path, patterns):
    # fnmatch's * spans slash: the checked-in patterns deliberately use that
    # for all Markdown and recursive prefixes. Rules are first-match per path.
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def test_owners(config):
    owners = {}
    for name, shard in config["shards"].items():
        for command in shard["commands"]:
            if command[:3] == ["python3", "-m", "unittest"]:
                for module in command[3:]:
                    if len(module.split(".")) != 2:
                        # A fast shard running only a module's offline classes
                        # cannot claim coverage of edits to its render classes.
                        continue
                    path = "/".join(module.split(".")[:2]) + ".py"
                    owners.setdefault(path, []).append(name)
            elif command[:3] == ["python3", "-m", "pytest"]:
                for path in command[3:]:
                    if path.startswith("tests/") and path.endswith(".py"):
                        owners.setdefault(path, []).append(name)
    return owners


def plan(paths, config=None, force_full=False):
    config = load_mapping() if config is None else config
    paths = sorted(set(paths))
    chosen, reasons, paired_tests = {"smoke"}, {}, set()
    owners = test_owners(config)
    dependencies = inventory()
    full = force_full or not paths
    for path in paths:
        if (not path or PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts or "\\" in path):
            raise ValueError(f"invalid repository path: {path!r}")
        if (matches(path, config["full_paths"])
                or path in dependencies["shared_pipelines"]
                or path in dependencies["test_helpers"]
                or path in config.get("test_read_paths", ())
                or path in dependencies["test_read_paths"]):
            reasons[path] = ["full"]
            full = True
            # Shared test helpers still own page checks outside full-unit.
            # Promoting a test to full coverage must retain those consumers.
            chosen.update(owners.get(path, ()))
        elif path in owners:
            reasons[path] = owners[path]
            chosen.update(owners[path])
        elif matches(path, config["docs_paths"]) and not any(matches(path, r["paths"]) for r in config["rules"]):
            reasons[path] = ["docs-only"]
        else:
            rule = next((r for r in config["rules"] if matches(path, r["paths"])), None)
            if rule is None:
                reasons[path] = ["full (unmapped)"]
                full = True
            else:
                reasons[path] = rule["shards"]
                chosen.update(rule["shards"])
                full |= rule.get("full", False)
                if rule["shards"] == ["pipelines"]:
                    test = ROOT / "tests" / ("test_" + PurePosixPath(path).stem + ".py")
                    if test.is_file():
                        paired_tests.add("tests." + test.stem)
                    else:
                        # A broad pipeline prefix is not enough evidence of
                        # test coverage for an unfamiliar producer.
                        reasons[path] = ["full (no paired pipeline test)"]
                        full = True
        # The hosted connector loads some of the page's modules from the
        # published site. Those edits touch both consumers even on a narrow PR.
        for dependency in config["dependencies"]:
            if matches(path, dependency["paths"]):
                chosen.update(dependency["shards"])
                reasons[path] = sorted(set(reasons[path] + dependency["shards"]))
    touched = [s for s in config["shards"] if s in chosen]
    # Full coverage must be a superset of the touched fast shards: some page
    # renders live in the daily list rather than the nightly test-unit list.
    shards = list(dict.fromkeys(config["full_shards"] + touched)) if full else touched
    return {"full": full, "docs_only": bool(paths) and all(r == ["docs-only"] for r in reasons.values()),
            "shards": shards, "reasons": reasons, "paired_tests": sorted(paired_tests)}


def changed_paths(base, head="HEAD", root=ROOT):
    # Resolve hashes first: no revisions supplied by an event become git options.
    revisions = []
    for revision in (base, head):
        if not revision or revision.startswith("-"):
            raise ValueError("base and head revisions are required")
        revisions.append(subprocess.check_output(
            ["git", "rev-parse", "--verify", revision + "^{commit}"], cwd=root, text=True).strip())
    data = subprocess.check_output(["git", "diff", "--no-renames", "--name-only", "-z",
                                    "...".join(revisions), "--"], cwd=root)
    return [os.fsdecode(p) for p in data.split(b"\0") if p]


def run_shard(name, config=None, extra_tests=()):
    config = load_mapping() if config is None else config
    shard = config["shards"][name]
    commands = list(shard["commands"])
    if extra_tests:
        if name != "pipelines" or any(not re.fullmatch(r"tests\.test_[A-Za-z0-9_]+", t)
                                      or not (ROOT / (t.replace(".", "/") + ".py")).is_file()
                                      for t in extra_tests):
            raise ValueError("invalid paired pipeline tests")
        # Some puller tests are pytest functions; unittest would report zero
        # tests and succeed. Pytest runs both styles and fails on no collection.
        commands.append(["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         *[t.replace(".", "/") + ".py" for t in extra_tests]])
    failed = False
    for command in commands:
        argv = [sys.executable if part == "python3" and i == 0 else part
                for i, part in enumerate(command)]
        print(f"fast-gate {name}: {command}", flush=True)
        started = time.monotonic()
        # Attribute baseline reds without excusing them (JEG-1450). Keep each
        # command's real exit code and run subsequent commands after a red.
        rc = subprocess.run([sys.executable, "-m", "pipelines.baseline_reds", "--context",
                             os.environ.get("BASELINE_RED_CONTEXT", "CI"), "--", *argv], cwd=ROOT).returncode
        print(f"fast-gate {name}: rc={rc}, seconds={time.monotonic() - started:.1f}", flush=True)
        failed |= rc != 0
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    choose = sub.add_parser("plan")
    choose.add_argument("--base")
    choose.add_argument("--head", default="HEAD")
    choose.add_argument("--full", action="store_true")
    choose.add_argument("--paths-file", type=Path, help="JSON array of repository paths")
    choose.add_argument("--github-output", type=Path)
    choose.add_argument("--summary", type=Path)
    run = sub.add_parser("run")
    run.add_argument("--shard", required=True)
    run.add_argument("--extra-tests", default="[]", help="JSON array of paired pipeline test modules")
    args = parser.parse_args(argv)
    config = load_mapping()
    if args.action == "run":
        return run_shard(args.shard, config, json.loads(args.extra_tests))
    paths = json.loads(args.paths_file.read_text()) if args.paths_file else (
        changed_paths(args.base, args.head) if not args.full else [])
    result = plan(paths, config, args.full)
    print(json.dumps(result, indent=2))
    if args.github_output:
        matrix = {"include": [{"shard": s, "build": config["shards"][s]["build"],
                               "extra_tests": result["paired_tests"] if s == "pipelines" else [],
                               "timeout": 120 if s == "full-unit" else 30 if result["full"] else 15}
                              for s in result["shards"] if s != "smoke"]}
        with args.github_output.open("a") as output:
            output.write(f"matrix={json.dumps(matrix, separators=(',', ':'))}\n")
            output.write(f"has_shards={'true' if matrix['include'] else 'false'}\n")
    if args.summary:
        with args.summary.open("a") as summary:
            summary.write("### Fast gate (informational; not required)\n\n")
            summary.write(f"Full suite: **{result['full']}**; docs-only: **{result['docs_only']}**.\n\n")
            summary.write("Selected: " + ", ".join(result["shards"]) + ".\n\n")
            for path, reason in result["reasons"].items():
                # JSON quoting keeps newlines/backticks in filenames out of Markdown markup.
                safe = json.dumps(path).replace("`", "&#96;").replace("<", "&lt;")
                summary.write(f"- {safe}: {', '.join(reason)}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"fast-gate: {error}", file=sys.stderr)
        sys.exit(1)
