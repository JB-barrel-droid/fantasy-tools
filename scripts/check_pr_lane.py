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
    return config['warn_only'] and now < datetime.fromisoformat(config['enforce_after'])


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--event', required=True, type=Path)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / '.github/lane-check.json')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    pr = json.loads(args.event.read_text())['pull_request']
    warn_only = is_warn_only(config, datetime.now(timezone.utc))
    try:
        check_prefix(parse_lane(pr.get('body') or ''), pr['head']['ref'])
    except ValueError as exc:
        # Only fixed diagnostics are printed; PR text is never a command or annotation.
        level = 'warning' if warn_only else 'error'
        print(f'::{level}::Lane attribution invalid: {exc}')
        print(f"Warn-only expires {config['enforce_after']}.")
        return 0 if warn_only else 1
    print('Lane attribution and branch prefix match.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
