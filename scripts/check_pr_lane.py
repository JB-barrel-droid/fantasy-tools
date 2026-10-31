#!/usr/bin/env python3
"""Check a GitHub event locally, with no API calls or dependencies."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lanes.pr_attribution import check_prefix, parse_lane


def is_warn_only(config, now):
    if not isinstance(config, dict) or type(config.get('warn_only')) is not bool:
        raise ValueError('warn_only must be a boolean.')
    try:
        timestamp = config['enforce_after']
        if not isinstance(timestamp, str):
            raise ValueError
        deadline = datetime.fromisoformat(timestamp.removesuffix('Z') + ('+00:00' if timestamp.endswith('Z') else ''))
    except (KeyError, TypeError, ValueError):
        raise ValueError('enforce_after must be an ISO-8601 timestamp with a timezone offset.') from None
    if deadline.utcoffset() is None:
        raise ValueError('enforce_after must include a timezone offset.')
    return config['warn_only'] and now < deadline


def check_pr(pr, config, warn_only):
    try:
        check_prefix(parse_lane(pr.get('body') or ''), pr['head']['ref'])
    except ValueError as exc:
        level = 'warning' if warn_only else 'error'
        print(f'::{level}::Lane attribution invalid: {exc}')
        print(f"Warn-only expires {config['enforce_after']}.")
        return 0 if warn_only else 1
    print('Lane attribution and branch prefix match.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--event', type=Path)
    source.add_argument('--open-prs', type=Path, help='JSON array of open PRs from the GitHub API')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / '.github/lane-check.json')
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.config.read_text())
        warn_only = is_warn_only(config, datetime.now(timezone.utc))
    except (OSError, ValueError) as exc:
        print(f'Config error: {exc}', file=sys.stderr)
        return 2
    if args.event:
        prs = [json.loads(args.event.read_text())['pull_request']]
    else:
        prs = json.loads(args.open_prs.read_text())
    result = 0
    for pr in prs:
        # Never print untrusted titles, bodies or branch names.
        if args.open_prs:
            print(f"Checking PR #{int(pr['number'])}")
        result = max(result, check_pr(pr, config, warn_only))
    return result


if __name__ == '__main__':
    sys.exit(main())
