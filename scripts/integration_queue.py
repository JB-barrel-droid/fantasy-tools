"""Offline, fail-closed integration queue preparation. No remote or trunk writes.

Receipts are trusted coordinator input, not independently fetched GitHub evidence.
See runbooks/integration-queue.md before use. Git >= 2.38 required.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


SHA = re.compile(r"[0-9a-f]{40}")


def git(repo, *args, **kwargs):
    return subprocess.run(['git', '-C', str(repo), *args], text=True,
                          capture_output=True, check=True, **kwargs).stdout.strip()


def admission(pr, required):
    head = pr['head']
    if not SHA.fullmatch(head):
        return 'invalid head'
    if pr.get('held') or pr.get('closed'):
        return 'removed by owner'
    review = pr.get('review', {})
    if (review.get('head') != head or review.get('result') != 'pass'
            or not pr.get('author_session')
            or not review.get('url') or not review.get('session')
            or review['session'] == pr.get('author_session')):
        return 'independent current-head review required'
    checks = pr.get('checks', {})
    if not required or any(checks.get(name) != {'head': head, 'result': 'success'}
                           for name in required):
        return 'current-head required CI must pass'
    return None


def prepare(repo, snapshot, *, dry_run=False, validator=None):
    """Prepare at most one eligible PR; input list order is FIFO.

    Always rebuild and revalidate, even for a previously prepared head. No cached
    candidate can survive a base change. Returned JSON is a receipt, not approval
    to publish. validator injection is for local fixture tests only.
    """
    repo = Path(repo).resolve()
    base = git(repo, 'rev-parse', '--verify', snapshot['base_ref'] + '^{commit}')
    result = {'base': base, 'events': []}
    for pr in snapshot['prs']:
        reason = admission(pr, snapshot['required_checks'])
        if reason:
            result['events'].append({'pr': pr['number'], 'owner': pr['owner'],
                                     'state': 'removed' if pr.get('held') or pr.get('closed') else 'held',
                                     'reason': reason})
            continue
        number = pr['number']
        if type(number) is not int or number < 1:
            raise ValueError('PR number must be a positive integer')
        head = git(repo, 'rev-parse', '--verify', pr['head'] + '^{commit}')
        ref = f'refs/heads/queue/pr-{number}'
        if dry_run:
            result['events'].append({'pr': number, 'state': 'would_prepare',
                                     'head': head, 'ref': ref})
            break
        try:
            tree = git(repo, 'merge-tree', '--write-tree', base, head).splitlines()[0]
        except subprocess.CalledProcessError as exc:
            if exc.returncode != 1:
                raise
            result['events'].append({'pr': number, 'owner': pr['owner'],
                                     'state': 'returned_to_owner',
                                     'reason': 'merge conflict; owner must repair and renew review/CI',
                                     'detail': exc.stdout})
            continue
        if tree == git(repo, 'rev-parse', base + '^{tree}'):
            result['events'].append({'pr': number, 'state': 'held', 'reason': 'empty candidate'})
            continue
        # Keep the PR tip author; retain every other original author as a trailer.
        author = git(repo, 'show', '-s', '--format=%an <%ae>', head)
        authors = sorted(set(git(repo, 'log', '--format=%an <%ae>', f'{base}..{head}').splitlines()))
        message = (f"{pr['title']} (#{number})\n\nPR: {pr['url']}\n"
                   f"Reviewed-head: {head}\nReview: {pr['review']['url']}\n"
                   + ''.join(f'Co-authored-by: {a}\n' for a in authors if a != author))
        env = dict(os.environ, GIT_AUTHOR_NAME=author.rsplit(' <', 1)[0],
                   GIT_AUTHOR_EMAIL=author.rsplit(' <', 1)[1][:-1])
        commit = git(repo, 'commit-tree', tree, '-p', base, input=message, env=env)
        symbolic = subprocess.run(['git', '-C', str(repo), 'symbolic-ref', '--quiet', ref],
                                  text=True, capture_output=True)
        if symbolic.returncode == 0:
            raise ValueError(f'symbolic queue ref is forbidden: {ref}')
        if symbolic.returncode != 1:
            symbolic.check_returncode()
        old = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', ref],
                             text=True, capture_output=True)
        # Never follow a symbolic ref, including one installed after the check.
        git(repo, 'update-ref', '--no-deref', ref, commit,
            old.stdout.strip() if old.returncode == 0 else '0' * 40)
        event = {'pr': number, 'owner': pr['owner'], 'head': head,
                 'base': base, 'candidate': commit, 'ref': ref}
        # Validate the exact candidate, never the lane checkout.
        with tempfile.TemporaryDirectory(prefix='.queue-validation-', dir=repo) as directory:
            # A clone preserves exact commit identity for build-tag/git consumers.
            subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(repo), directory],
                           capture_output=True, check=True)
            git(directory, 'checkout', '--detach', commit)
            valid = (validator(Path(directory)) if validator else
                     subprocess.run(['make', 'validate'], cwd=directory,
                                    stdout=sys.stderr, stderr=sys.stderr).returncode == 0)
        current = git(repo, 'rev-parse', snapshot['base_ref'] + '^{commit}')
        event['state'] = ('invalidated' if current != base else
                          'validated' if valid else 'validation_failed')
        result['events'].append(event)
        break  # A validation failure stops this run; never silently retry.
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    # Lock only the queue's local state; production needs a single remote owner.
    if args.dry_run:
        receipt = prepare(args.repo, snapshot, dry_run=True)
    else:
        with (args.repo / '.integration-queue.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            receipt = prepare(args.repo, snapshot)
    print(json.dumps(receipt, indent=2))
    return 1 if any(e['state'] in {'invalidated', 'validation_failed'}
                    for e in receipt['events']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
