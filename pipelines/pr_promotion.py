"""Gated entry points for ready-for-review and the final merge gate.

This never merges. The merge session still needs Jeremy's yes in his window.
"""

import argparse
import subprocess
import sys

from pipelines.pr_freshness_gate import REPO, main as freshness


def main(argv=None, gate=freshness, execute=subprocess.run):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ready-for-review", "merge-gate"))
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args(argv)
    result = gate([str(args.number), "--repo", args.repo])
    if result:
        return result
    if args.action == "ready-for-review":
        return execute(["gh", "pr", "ready", str(args.number), "--repo", args.repo],
                       check=False).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
