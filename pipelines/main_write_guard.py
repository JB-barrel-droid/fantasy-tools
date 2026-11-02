#!/usr/bin/env python3
"""JEG-1215: defer only repository publication, retaining recoverable output.

Exit 0 permits publication; 75 means retained/deferred; other exits mean a
retention failure, which must be visible. No database or workflow settings API.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp

CONTROL = '.github/main-write-pause.json'
MAX_PAUSE = timedelta(hours=6)
# JEG-1472: a pause that names a `scope` covers only those writers, for at most
# two hours. Writer ids are the workflow names; the `-<n>` suffix a guarded
# block passes (`health-artifacts-3`) is stripped before matching.
MAX_SCOPED_PAUSE = timedelta(hours=2)
# The one allowlist of writers a scoped pause may name: they run several times
# a day, so a skipped run is regenerated within hours. Fidelity pulse; comparison
# rebuild and chain status; health artifacts with ops status and monitoring
# summary; the hourly source-vintage code hash.
FREQUENT_WRITERS = ('fidelity-pulse', 'rebuild-chain', 'health-artifacts', 'source-vintage-check')
# Daily and weekly snapshots: a skipped run is not replayed, so a scoped pause
# must never cover them. Listed for the switch's error message and the tests;
# anything outside FREQUENT_WRITERS is rejected from a scope either way.
DAILY_WRITERS = ('espn-weekly-store', 'player-trace-rebuild', 'player-status-history',
                 'espn-supabase-sync', 'sleeper-identity-refresh', 'espn-history-probe')


def writer_base(writer):
    return re.sub(r'-\d+$', '', writer)


def scope_of(doc):
    """None when the control has no scope (pause everything), else the scope set."""
    if 'scope' not in doc:
        return None
    scope = doc['scope']
    if not isinstance(scope, list) or not scope or any(type(item) is not str for item in scope):
        raise ValueError('scope must be a nonempty list of writer ids')
    if len(set(scope)) != len(scope):
        raise ValueError('scope must not repeat a writer')
    outside = [item for item in scope if item not in FREQUENT_WRITERS]
    if outside:
        raise ValueError('scope may name only frequent writers: ' + ', '.join(outside))
    return frozenset(scope)


def decision(raw, now, writer=None):
    doc = json.loads(raw)
    if type(doc.get('paused')) is not bool:
        raise ValueError('paused must be a boolean')
    if not doc['paused']:
        return False, 'unpaused'
    start = parse_iso_timestamp(doc['started_at'])
    end = parse_iso_timestamp(doc['expires_at'])
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError('pause times must include a timezone')
    scope = scope_of(doc)
    limit = MAX_PAUSE if scope is None else MAX_SCOPED_PAUSE
    if not timedelta(0) < end - start <= limit:
        raise ValueError('pause duration must be positive and at most '
                         + ('six hours' if scope is None else 'two hours for a scoped pause'))
    if start > now:
        raise ValueError('pause start is in the future')
    if not isinstance(doc.get('reason'), str) or not doc['reason'].strip():
        raise ValueError('active pause requires a reason')
    if now >= end:
        return False, f'pause expired at {end.isoformat()}; publication restored'
    if scope is None:
        return True, f"paused until {end.isoformat()}: {doc['reason']}"
    names = ', '.join(sorted(scope))
    if writer is not None and writer_base(writer) not in scope:
        return False, f'scoped pause ({names}) does not cover this writer; publication continues'
    return True, f"paused until {end.isoformat()} (scope {names}): {doc['reason']}"


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30)


def check(writer, phase, target, head='HEAD'):
    if target != 'main':
        return 0
    now = datetime.now(timezone.utc)
    remote = None
    try:
        git('fetch', '--no-tags', 'origin', 'main')
        remote = git('rev-parse', 'FETCH_HEAD').decode().strip()
        # Missing control is the unpaused default, including pre-install main.
        exists = git('ls-tree', '--name-only', remote, '--', CONTROL).strip()
        raw = git('show', f'{remote}:{CONTROL}').decode() if exists else '{"paused":false}'
        paused, reason = decision(raw, now, writer)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError) as exc:
        paused, reason = True, f'control unavailable/invalid ({type(exc).__name__}); publication deferred'
    reason = ' '.join(reason.splitlines())
    status = f'{writer}: {reason}'
    print(f'::{"warning" if paused else "notice"} title=Main publication::{status}')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            f.write(f'\n### Main publication — {writer}\n{reason}\n')
    if not paused:
        return 0
    # Stage phase captures only the explicit publication index (never partial
    # unstaged fixture changes). Push phase captures commits not on fetched main.
    base = git('rev-parse', 'HEAD').decode().strip()
    if phase == 'push':
        # JEG-1364: --head names the commit being published when it is not this
        # checkout's HEAD (rebuild-chain publishes a scratch-worktree commit).
        head = git('rev-parse', f'{head}^{{commit}}').decode().strip()
        if remote:
            base = git('merge-base', remote, head).decode().strip()
        else:
            base = git('merge-base', 'origin/main', head).decode().strip()
        patch = git('diff', '--binary', '--no-ext-diff', base, head)
        if remote and base == head:
            # A previously accepted push may have lost its acknowledgement.
            # Permit the no-op retry so its existing Pages dispatch still runs.
            print('::notice title=Main publication::No unpublished commits; permitting no-op push confirmation')
            return 0
    else:
        patch = git('diff', '--cached', '--binary', '--no-ext-diff')
    folder = Path('output/release-publications') / writer
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{phase}.patch').write_bytes(patch)
    (folder / f'{phase}.json').write_text(json.dumps({
        'writer': writer, 'phase': phase, 'base': base, 'remote': remote,
        'reason': reason, 'recorded_at': now.isoformat(),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'recovery': 'Review patch against its base; regenerate and validate before publication.'
    }, indent=2) + '\n')
    if phase == 'stage':
        # Keep bytes in the worktree, but prevent a later publication step from
        # accidentally committing this deferred index when the pause expires.
        git('restore', '--staged', '--', '.')
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a') as f:
            f.write('pushed=false\npublication_deferred=true\n')
    return 75


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--writer', required=True)
    parser.add_argument('--phase', choices=['stage', 'push'], required=True)
    parser.add_argument('--target', default='main')
    parser.add_argument('--head', default='HEAD', help='commit a push publishes (push phase)')
    args = parser.parse_args()
    if not args.writer.replace('-', '').isalnum():
        parser.error('writer must contain only letters, digits and hyphens')
    return check(args.writer, args.phase, args.target, args.head)


if __name__ == '__main__':
    raise SystemExit(main())
