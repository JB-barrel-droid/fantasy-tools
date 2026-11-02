#!/usr/bin/env python3
"""Model-free rollup of retained Actions counter summaries (JEG-1458)."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

try:
    from .lib.timestamps import parse_iso_timestamp
except ImportError:  # Direct script invocation.
    from lib.timestamps import parse_iso_timestamp

COUNTER = re.compile(r'^\[supabase-bytes\] .*? (GET|HEAD|POST|PATCH|DELETE|PUT) (\S+) requests=(\d+) bytes=(\d+) wire=(\d+) context=(\{.*\})$')
NOTICE = ('Coverage: Python gh_sbclient response bodies only; headers and transport overhead excluded. '
          'get-values and site traffic are NOT COVERED and must not be read as zero. '
          'Missing days/workflows/scripts are unmeasured, not zero. Writes are included in totals; '
          'top reads are GET/HEAD only (RPC POST semantics are unknown).')


def parse_summaries(paths, since, until):
    """Parse structured lines, deduplicating summary/log/artifact copies by event."""
    rows, seen, legacy = [], set(), 0
    for path in sorted(paths):
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.startswith('[supabase-bytes]'):
                continue
            match = COUNTER.fullmatch(line)
            if not match:
                if ' context=' in line:
                    raise ValueError(f'{path}: malformed structured counter')
                legacy += 1
                continue
            method, table, requests, size, wire, context = match.groups()
            ctx = json.loads(context)
            required = ('at', 'event', 'workflow', 'script', 'caller')
            if not isinstance(ctx, dict) or any(
                    key not in ctx or not isinstance(ctx[key], str) for key in required):
                raise ValueError(f'{path}: counter needs string at/event/workflow/script/caller fields')
            at = parse_iso_timestamp(ctx['at'])
            if at.tzinfo is None:
                raise ValueError(f'{path}: counter timestamp needs timezone')
            key = (ctx['event'], method, table)
            if key in seen:
                continue
            seen.add(key)
            if not since <= at < until:
                continue
            rows.append(dict(ctx, day=at.astimezone(timezone.utc).date().isoformat(),
                             method=method, table=table, requests=int(requests),
                             bytes=int(size), wire=int(wire)))
    return rows, legacy


def aggregate(rows, reads_only=False):
    totals = defaultdict(lambda: [0, 0, 0])
    for row in rows:
        if reads_only and row['method'] not in ('GET', 'HEAD'):
            continue
        key = (row['day'], row['workflow'], row['script'], row['caller'], row['table'])
        for i, field in enumerate(('requests', 'bytes', 'wire')):
            totals[key][i] += row[field]
    return totals


def download(root, repo, since):
    """Read-only GitHub operations; any error (including quota) stops immediately."""
    # Run creation time excludes reruns and boundary-spanning runs. Discover
    # repository artifacts instead, then filter counter emission times at parse.
    endpoint = f'repos/{repo}/actions/artifacts?per_page=100'
    result = subprocess.run(['gh', 'api', '--paginate', '--slurp', endpoint],
                            check=True, capture_output=True, text=True)
    for batch in json.loads(result.stdout):
        for artifact in batch['artifacts']:
            if not artifact['name'].startswith('supabase-bytes-'):
                continue
            if parse_iso_timestamp(artifact['created_at']) < since:
                continue
            if artifact['expired']:
                print(f'WARNING: expired counter artifact {artifact["id"]}', file=sys.stderr)
                continue
            # Artifact IDs retain observations from previous run attempts too.
            archive = subprocess.run(['gh', 'api', f'repos/{repo}/actions/artifacts/{artifact["id"]}/zip'],
                                     check=True, capture_output=True)
            import io
            import zipfile
            target = root / str(artifact['id'])
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(archive.stdout)) as zf:
                for name in zf.namelist():
                    if name.endswith('.md'):
                        (target / Path(name).name).write_bytes(zf.read(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='exported summaries or extracted counter artifacts')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--until', help='exclusive ISO timestamp; default now (UTC)')
    parser.add_argument('--download', metavar='OWNER/REPO', help='download retained counter artifacts with gh (read only)')
    args = parser.parse_args()
    if args.days < 1:
        parser.error('--days must be positive')
    until = parse_iso_timestamp(args.until) if args.until else datetime.now(timezone.utc)
    if until.tzinfo is None:
        parser.error('--until needs a timezone')
    since = until - timedelta(days=args.days)
    try:
        if args.download:
            download(args.directory, args.download, since)
        rows, legacy = parse_summaries(args.directory.rglob('*.md'), since, until)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        # Do not print subprocess output: API errors can contain unexpected data.
        print(f'Rollup stopped: {type(exc).__name__}; no retries. Check gh access/quota or input format.', file=sys.stderr)
        return 1
    print(NOTICE)
    print(f'UTC window [{since.isoformat()}, {until.isoformat()}); boundary days may be partial.')
    print(f'Observed {len(rows)} counters; skipped {legacy} legacy lines lacking attribution/time.')
    print('day\tworkflow\tscript\tcaller\ttable\trequests\tbytes\twire_bytes')
    for key, values in sorted(aggregate(rows).items()):
        print('\t'.join(map(str, (*key, *values))))
    print('Top 5 reads by total wire bytes over the window (workflow / script / caller / table):')
    reads = defaultdict(lambda: [0, 0, 0])
    for key, values in aggregate(rows, reads_only=True).items():
        for i, value in enumerate(values):
            reads[key[1:]][i] += value
    for key, values in sorted(reads.items(), key=lambda item: (-item[1][2], item[0]))[:5]:
        print('\t'.join(map(str, (*key, *values))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
