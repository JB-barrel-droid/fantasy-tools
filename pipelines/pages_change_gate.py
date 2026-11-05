#!/usr/bin/env python3
"""Fail closed to full Pages validation; status-only runs never publish."""
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

# Exact generated operational records, not a directory or suffix exemption.
STATUS_FILES = frozenset({
    '.github/source-vintage-state.json',
    *('dist/modules/' + name + '.json' for name in (
        'fidelity-pulse', 'github-actions', 'monitoring-summary', 'ops-status',
        'player-trace',
        'comparison-chain-status')),
    'output/comparison-chain-status.json',
})
CONTROL = '.github/release-batches.json'
SHA = re.compile(r'[0-9a-f]{40}')


def api(path):
    req = urllib.request.Request('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def published_head(get=api):
    # A successful no-publication run has a skipped deploy job and cannot move
    # this anchor. Bounded lookup exhaustion/permissions failures mean full work.
    runs = get('actions/workflows/pages.yml/runs?branch=main&status=success&per_page=100')['workflow_runs']
    for run in runs:
        if str(run['id']) == os.environ.get('GITHUB_RUN_ID'):
            continue
        jobs = get(f"actions/runs/{run['id']}/jobs?per_page=100")['jobs']
        if any(j['name'] == 'deploy' and j['conclusion'] == 'success' for j in jobs):
            return run['head_sha']
    raise ValueError('no successful publication anchor')


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30)


def control_history(anchor, head, run_git=git):
    if __package__:
        from . import release_batch
    else:
        import release_batch
    previous = anchor
    commits = run_git('rev-list', '--first-parent', '--reverse', f'{anchor}..{head}').decode().splitlines()
    for commit in commits:
        parent = run_git('rev-parse', f'{commit}^1').decode().strip()
        if parent != previous:
            raise ValueError('publication anchor is not on main first-parent history')
        changed = run_git('diff', '--name-only', '-z', '--no-renames', previous, commit).decode().split('\0')
        changed = [p for p in changed if p]
        if CONTROL in changed:
            if changed != [CONTROL]:
                raise ValueError('control transition contains other changes')
            before = json.loads(run_git('show', f'{previous}:{CONTROL}'))
            after = json.loads(run_git('show', f'{commit}:{CONTROL}'))
            release_batch.transition(before, after)
        elif any(p not in STATUS_FILES for p in changed):
            raise ValueError('unverified unpublished intermediate changes')
        previous = commit
    if previous != head:
        raise ValueError('incomplete control history')


def classify(event_name, event, head, anchor, run_git=git, validate_control=control_history):
    if event_name != 'push' or event.get('ref') != 'refs/heads/main' or event.get('forced') is not False:
        return 'full', 'manual, non-main or unverified push'
    before = event.get('before', '')
    if not all(isinstance(s, str) and SHA.fullmatch(s) and s != '0' * 40 for s in (before, head, anchor)):
        return 'full', 'missing verified range'
    if event.get('after') != head:
        return 'full', 'event head mismatch'
    # Full history checkout; verify both push range and last actual publication.
    for base in (before, anchor):
        run_git('merge-base', '--is-ancestor', base, head)
    changed = run_git('diff', '--name-only', '-z', '--no-renames', anchor, head).decode().split('\0')
    changed = [p for p in changed if p]
    if not changed or any(p not in STATUS_FILES | {CONTROL} for p in changed):
        return 'full', 'application, data, workflow, unknown or empty range'
    # Malformed/deleted records cannot qualify as operational status.
    for path in changed:
        if path == CONTROL:
            continue
        doc = json.loads(run_git('show', f'{head}:{path}'))
        if not isinstance(doc, dict):
            return 'full', 'invalid status record'
    if CONTROL in changed:
        validate_control(anchor, head, run_git)
        return 'control-only', f'verified registry-only transitions since publication {anchor}'
    return 'status-only', f'{len(changed)} verified status records since publication {anchor}'


def main():
    anchor = None
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        if os.environ['GITHUB_EVENT_NAME'] == 'push':
            anchor = published_head()
        mode, reason = classify(os.environ['GITHUB_EVENT_NAME'], event, os.environ['GITHUB_SHA'], anchor)
    except Exception as exc:
        mode, reason = 'full', f'unverified range ({type(exc).__name__})'
    result = {'mode': mode, 'reason': reason, 'head': os.environ['GITHUB_SHA'], 'publication_anchor': anchor}
    Path('pages-change-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
        out.write(f'mode={mode}\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write(f"Pages classification: **{mode}** — {reason}.\n\n"
            'Status/control-only runs do not publish. Live status JSON remains at the last published build; '
            'current records are on main and in the producer artifacts. Manual/daily builds refresh the site.\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
