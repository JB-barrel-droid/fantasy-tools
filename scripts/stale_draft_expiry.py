#!/usr/bin/env python3
"""Model-free draft expiry. Dry-run is the committed default; never deletes branches."""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WARNING = '<!-- jeg-1452:stale-draft-warning -->'
CLOSED = '<!-- jeg-1452:stale-draft-closed -->'
PROTECTED = {'needs-jeremy', 'blocked-dependency'}


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def gh(*args):
    return json.loads(subprocess.check_output(['gh', *args], text=True))


def pages(path):
    return [item for page in gh('api', '--paginate', '--slurp', path) for item in page]


def tickets(pr):
    # Check every referenced ticket: ambiguity must never bypass a protected label.
    return sorted(set(re.findall(r'\bJEG-\d+\b', ' '.join(
        str(pr.get(k) or '') for k in ('title', 'body', 'headRefName')))))


def normalize_label(name):
    return re.sub(r'[\s_-]+', '-', name.strip().lower())


def select(pr, comments, reviews, review_comments, commits, labels, now, days, events=()):
    if pr.get('state') != 'OPEN' or not pr['isDraft']:
        return None
    protected = {normalize_label(name) for name in PROTECTED}
    pr_labels = {normalize_label(x['name']) for x in pr['labels']}
    if pr_labels & (protected | {'keep-open'}):
        return None
    ids = tickets(pr)
    if not ids or any(t not in labels or protected & {normalize_label(name) for name in labels[t]} for t in ids):
        return None  # Missing ticket information fails closed.
    warnings = [c for c in comments if WARNING in c['body'] and c['user']['login'] == 'github-actions[bot]']
    # Local gh authors can also run apply: only accept a marker authored by the current actor.
    warnings += [c for c in comments if WARNING in c['body'] and c['user']['login'] == pr.get('_actor') and c not in warnings]
    activity = [stamp(pr['createdAt'])]
    for c in comments:
        if c not in warnings:
            activity.append(stamp(c.get('updated_at') or c['created_at']))
    for c in review_comments:
        activity.append(stamp(c.get('updated_at') or c['created_at']))
    activity += [stamp(e['created_at']) for e in events if e.get('event') == 'reopened']
    activity += [stamp(r['submitted_at']) for r in reviews if r.get('submitted_at')]
    activity += [stamp(c['commit']['committer']['date']) for c in commits]
    # updatedAt conservatively covers pushes of old commits and metadata changes.
    # Our warning counts toward the second quiet window, never an immediate close.
    activity.append(stamp(pr['updatedAt']))
    last = max(activity)
    quiet = (now - last).total_seconds() / 86400
    if quiet < days:
        return None
    if not warnings and any(WARNING in c['body'] for c in comments):
        return None  # Other actors' markers suppress reposting, never authorize closing.
    if not warnings:
        return {'action': 'warn', 'days_quiet': quiet, 'tickets': ids}
    warned = max(stamp(c['created_at']) for c in warnings)
    # Any later activity (including closure/reopen) starts a new warning cycle.
    if last > warned + timedelta(seconds=5):
        return {'action': 'warn', 'days_quiet': quiet, 'tickets': ids}
    cutoff = warned + timedelta(days=days)
    if now >= cutoff:
        return {'action': 'close', 'days_quiet': quiet, 'tickets': ids}
    return None


def linear(query, variables):
    request = urllib.request.Request('https://api.linear.app/graphql',
        data=json.dumps({'query': query, 'variables': variables}).encode(),
        headers={'Authorization': os.environ['LINEAR_API_KEY'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError('Linear operation failed')
    return result['data']


def load_labels(ids, snapshot):
    if snapshot:
        return json.loads(Path(snapshot).read_text())
    result = {}
    for ticket in ids:
        data = linear('query($id:String!){issue(id:$id){labels{nodes{name}}}}', {'id': ticket})
        if data.get('issue'):
            result[ticket] = [x['name'] for x in data['issue']['labels']['nodes']]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='JB-barrel-droid/fantasy-tools')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/stale_draft_expiry.json')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--linear-labels', help='Local connector snapshot of ticket -> label names; missing tickets are skipped')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    days = config['window_days']
    if type(days) is not int or days <= 0 or type(config['dry_run']) is not bool:
        parser.error('window_days must be a positive integer and dry_run a boolean')
    dry = args.dry_run or config['dry_run']
    if args.linear_labels and not dry:
        parser.error('label snapshots are only allowed in dry-run mode')
    prs = gh('pr', 'list', '--repo', args.repo, '--state', 'open', '--draft', '--limit', '1000',
             '--json', 'number,title,body,headRefName,isDraft,state,labels,createdAt,updatedAt')
    labels = load_labels(sorted({t for p in prs for t in tickets(p)}), args.linear_labels)
    actor = gh('api', 'user')['login'] if not os.environ.get('GITHUB_ACTIONS') else 'github-actions[bot]'
    now = datetime.now(timezone.utc)
    print('| PR | Title | Days quiet | Action |')
    print('| --- | --- | ---: | --- |')
    for pr in prs:
        number = pr['number']
        path = f'repos/{args.repo}'
        def inspect(p, ticket_labels):
            p['_actor'] = actor
            return select(p, pages(f'{path}/issues/{number}/comments'),
                          pages(f'{path}/pulls/{number}/reviews'), pages(f'{path}/pulls/{number}/comments'),
                          pages(f'{path}/pulls/{number}/commits'), ticket_labels, now, days,
                          events=pages(f'{path}/issues/{number}/events'))
        action = inspect(pr, labels)
        if not action:
            continue
        print(f"| #{number} | {pr['title'].replace('|', '/')} | {action['days_quiet']:.1f} | {action['action']} |", flush=True)
        if dry:
            continue
        # Recheck draft, exemptions and activity immediately before mutation.
        pr = gh('pr', 'view', str(number), '--repo', args.repo, '--json',
                'number,title,body,headRefName,isDraft,state,labels,createdAt,updatedAt')
        recheck_labels = load_labels(tickets(pr), args.linear_labels)
        fresh = inspect(pr, recheck_labels)
        if not fresh or fresh['action'] != action['action']:
            continue
        if action['action'] == 'warn':
            body = f'{WARNING}\nThis draft closes in {days} days unless updated. Push a commit, comment, review, mark ready, or add keep-open to retain it.'
            subprocess.run(['gh', 'pr', 'comment', str(number), '--repo', args.repo, '--body', body], check=True)
        else:
            ids = ', '.join(action['tickets'])
            body = f'{CLOSED}\nClosing stale draft for {ids}. Reopen with `gh pr reopen {number} --repo {args.repo}` or the Reopen button. The branch is retained.'
            subprocess.run(['gh', 'pr', 'close', str(number), '--repo', args.repo, '--comment', body], check=True)
            for ticket in action['tickets']:
                issue = linear('query($id:String!){issue(id:$id){id}}', {'id': ticket})['issue']['id']
                linear('mutation($input:CommentCreateInput!){commentCreate(input:$input){success}}',
                       {'input': {'issueId': issue, 'body': f'Closed stale draft https://github.com/{args.repo}/pull/{number}; branch retained; reopen with `gh pr reopen {number}`.'}})


if __name__ == '__main__':
    main()
