"""Replay the last 30 merged PRs from main's first-parent git log (no API)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from pipelines.fast_gate import ROOT, load_mapping, plan


def git(*args, root=ROOT):
    return subprocess.check_output(["git", *args], cwd=root, text=True)


def capture(ref="origin/main", limit=30, root=ROOT):
    sha = git("rev-parse", "--verify", ref + "^{commit}", root=root).strip()
    prs = []
    for line in git("log", sha, "--first-parent", "--format=%H%x09%s", root=root).splitlines():
        commit, title = line.split("\t", 1)
        match = re.search(r"\(#(\d+)\)$", title) or re.match(r"Merge pull request #(\d+)\b", title)
        if not match:
            continue
        # First parent handles both squash and merge commits. Disable rename
        # detection so a move out of engine/CI cannot hide the old risky path.
        raw = subprocess.check_output(["git", "diff", "--no-renames", "--name-only", "-z",
                                       commit + "^1", commit, "--"], cwd=root)
        files = [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]
        prs.append({"number": int(match[1]), "sha": commit, "title": title, "files": files})
        if len(prs) == limit:
            break
    if len(prs) != limit:
        raise ValueError(f"wanted {limit} merged PRs; git history only supplied {len(prs)}")
    return {"main_sha": sha, "source": "git log --first-parent origin/main; git diff --no-renames PR^1 PR",
            "prs": prs}


def regression_audit(snapshot, regressions, planner=plan):
    """Check independently documented follow-ups against the original selection.

    required_shards name the broken area, not all paths in the fix (which often
    also edits Makefile or CI). Full runs cover every area by definition.
    """
    prs = {pr["number"]: pr for pr in snapshot["prs"]}
    rows = []
    for regression in regressions:
        selected = planner(prs[regression["original_pr"]]["files"])
        missed = [] if selected["full"] else sorted(set(regression["required_shards"]) - set(selected["shards"]))
        rows.append({**regression, "skipped_broken_area": missed})
    return rows


def report(snapshot, regressions):
    full_shards = load_mapping()["full_shards"]
    lines = [f"Main snapshot: `{snapshot['main_sha']}`. Source: git, no changed-files API.", "",
             "FULL = " + ", ".join(full_shards) + ". Any suffix lists additional touched shards.", "",
             "| PR | Commit | Selection (smoke always runs) |", "| --- | --- | --- |"]
    for pr in snapshot["prs"]:
        selected = plan(pr["files"])
        extra = [s for s in selected["shards"] if s not in full_shards]
        label = ("FULL" + (" + " + ", ".join(extra) if extra else "")) if selected["full"] else ", ".join(selected["shards"])
        lines.append(f"| #{pr['number']} | `{pr['sha'][:8]}` | {label} |")
    lines += ["", "Known follow-up audit (documented links; not proof that no other regression exists):", "",
              "| Original → follow-up | Broken area | Skipped? | Evidence |", "| --- | --- | --- | --- |"]
    for row in regression_audit(snapshot, regressions):
        lines.append(f"| #{row['original_pr']} → #{row['fix_pr']} | {', '.join(row['required_shards'])} | "
                     f"{', '.join(row['skipped_broken_area']) or 'No'} | {row['evidence']} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "tests/fast_gate_history.json")
    args = parser.parse_args()
    if args.capture:
        args.capture.write_text(json.dumps(capture(args.ref), indent=2) + "\n")
    else:
        snapshot = json.loads(args.snapshot.read_text())
        print(report(snapshot, snapshot.get("regressions", [])), end="")


if __name__ == "__main__":
    main()
