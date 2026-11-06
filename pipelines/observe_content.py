#!/usr/bin/env python3
"""Record one complete parsed native dataset, or a failed attempt, locally.

Example: python3 pipelines/observe_content.py --ledger data/content-observations.sqlite3
 --scope scope.json --rows native-rows.json --expected 500 --attempted-at <UTC ISO>
Scope JSON contains all six Scope fields; rows JSON is a list, before pricing.
Does not acquire vendors, import, publish, or activate schedules.
"""
import argparse
import json
import sys as _sys
from pathlib import Path as _Path

# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from lib.content_observations import Ledger, Scope, verdict  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger', required=True)
    p.add_argument('--scope', required=True)
    p.add_argument('--rows')
    p.add_argument('--expected', type=int, required=True)
    p.add_argument('--attempted-at', required=True)
    p.add_argument('--result', default='success', choices=['success', 'failed', 'skipped'])
    args = p.parse_args()
    with open(args.scope) as f:
        scope = Scope(**json.load(f))
    rows = None
    if args.rows:
        with open(args.rows) as f:
            rows = json.load(f)
    observation = Ledger(args.ledger).observe(scope, rows, expected=args.expected,
        attempted_at=args.attempted_at, result=args.result,
        raw_snapshot_reference=args.rows)
    print(json.dumps(verdict(observation, args.attempted_at), indent=2))


if __name__ == '__main__':
    main()
