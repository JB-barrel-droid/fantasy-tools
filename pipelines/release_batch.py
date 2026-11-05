#!/usr/bin/env python3
"""JEG-1484: read-only, fail-closed preflight for the existing merge runbook.

The registry on fetched main owns membership. This is not a merge controller or
branch protection. Every merge operator must invoke it immediately before merge.
"""
import argparse
import ast
from datetime import datetime, timezone
import io
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

REGISTRY = '.github/release-batches.json'
MANIFEST = '.github/release-batch.json'
REPO = 'datadrivenfootball/fantasy-tools'
SHA = re.compile(r'[0-9a-f]{40}')
RISKS = {'review-light', 'review-standard', 'review-high-risk'}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30).decode().strip()


def api(path, raw=False):
    # --paginate is deliberately not used for objects. Lists below paginate
    # explicitly and reject partial responses where the API reports a total.
    data = subprocess.check_output(['gh', 'api', f'repos/{REPO}/{path}'], stderr=subprocess.PIPE, timeout=60)
    return data if raw else json.loads(data)


def items(path, key=None, get=api):
    result = []
    for page in range(1, 101):
        doc = get(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
        chunk = doc[key] if key else doc
        require(isinstance(chunk, list), 'invalid API list')
        result.extend(chunk)
        if len(chunk) < 100:
            if key and 'total_count' in doc:
                require(len(result) == doc['total_count'], 'incomplete API evidence')
            return result
    raise ValueError('API evidence pagination exhausted')


def registry(doc):
    require(doc.get('version') == 1 and isinstance(doc.get('batches'), list), 'invalid registry')
    ids, members, integrations = set(), set(), set()
    active = []
    for batch in doc['batches']:
        ident = batch['id']
        require(isinstance(ident, str) and re.fullmatch(r'[a-zA-Z0-9_-]+', ident), 'invalid batch id')
        require(ident not in ids, 'duplicate batch id')
        ids.add(ident)
        require(batch['state'] in ('active', 'accepted', 'withdrawn'), 'unknown batch state')
        require(isinstance(batch.get('owner'), str) and batch['owner'].strip(), 'missing owner session')
        number = batch['integration_pr']
        require(type(number) is int and number > 0 and number not in integrations, 'duplicate/invalid integration PR')
        integrations.add(number)
        rows = batch['members']
        require(isinstance(rows, list) and 1 <= len(rows) <= 7, 'batch must contain 1..7 members')
        risks, local_members = set(), set()
        for member in rows:
            pr = member['pr']
            require(type(pr) is int and pr > 0 and pr not in local_members, 'duplicate/invalid membership')
            local_members.add(pr)
            if batch['state'] != 'withdrawn':
                require(pr not in members, 'duplicate/invalid membership')
                members.add(pr)
            require(isinstance(member['head'], str) and SHA.fullmatch(member['head']), 'invalid member head')
            require(member['risk'] in RISKS, 'invalid risk')
            require(isinstance(member.get('owner'), str) and member['owner'].strip(), 'missing member owner')
            risks.add(member['risk'])
        require(len(risks) == 1, 'mixed-risk batch')
        require('review-high-risk' not in risks or len(rows) == 1, 'high-risk/value work must ship isolated')
        if batch['state'] == 'active':
            active.append(batch)
        elif batch['state'] == 'withdrawn':
            require(isinstance(batch.get('recovery', {}).get('reason'), str)
                    and batch['recovery']['reason'].strip(), 'withdrawal needs a recovery reason')
        else:
            receipt = batch['acceptance']
            require(SHA.fullmatch(receipt['published_sha']) and type(receipt['publication_run']) is int
                    and type(receipt['live_run']) is int, 'missing publication/live acceptance receipt')
    require(not members.intersection(integrations), 'integration PR cannot also be a member')
    require(len(active) <= 1, 'previous batch lacks publication/live acceptance')
    if active:
        require(doc['batches'][-1] == active[0], 'active batch must be last')
    return active[0] if active else None


def ordinary(doc, pr):
    active = registry(doc)
    require(active is None, f"individual merge blocked by active batch {active['id']}" if active else '')
    require(all(pr not in [m['pr'] for m in b['members']] for b in doc['batches'] if b['state'] == 'accepted'),
            'batch member is an integration record; do not merge it separately')



def risk_floor(pr, declared, get=api):
    labels = {label['name'] for label in pr['labels']} & RISKS
    require(labels == {declared}, 'registry risk must match the coordinator PR label')
    changed = items(f"pulls/{pr['number']}/files", get=get)
    require(len(changed) == pr['changed_files'], 'incomplete changed-file evidence')
    # Read the existing logic inventory without importing the build pipeline.
    tree = ast.parse((Path(__file__).resolve().parent / 'build_values_explainer.py').read_text())
    logic = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'LOGIC_FILES' for t in n.targets))
    hot = {'app/v2/v2.js', 'config/roster.json', 'config/lineup_parameters.json', 'pipelines/bake_players.py', *logic}
    high = False
    for file in changed:
        name, patch = file['filename'], file.get('patch')
        if name in hot or name.startswith(('tests/fixtures/', 'config/', 'supabase/', 'sql/')):
            high = True
        if name.startswith('tests/'):
            # Missing/truncated test diffs cannot establish a lower risk floor.
            if patch is None or any((line.startswith('-') and not line.startswith('---')
                                    and re.search(r'assert|expect|should|check', line, re.I))
                                   or (line.startswith('+') and re.search(r'skip|continue.on.error', line, re.I))
                                   for line in (patch or '').splitlines()):
                high = True
    require(not high or declared == 'review-high-risk', 'deterministic high-risk work must ship isolated')


def check_ci(pr, head, get=api):
    runs = items(f'actions/runs?head_sha={head}', 'workflow_runs', get)
    for path in ('.github/workflows/preview.yml', '.github/workflows/v2-render-test.yml'):
        candidates = [r for r in runs if r['path'] == path and r['head_sha'] == head
                      and any(p['number'] == pr for p in r.get('pull_requests', []))]
        require(candidates, f'missing combined-head CI: {path}')
        run = max(candidates, key=lambda r: (r['run_number'], r.get('run_attempt', 1)))
        require(run['status'] == 'completed' and run['conclusion'] == 'success', f'failed/pending CI: {path}')
        jobs = items(f"actions/runs/{run['id']}/jobs", 'jobs', get)
        required = ({'preview', 'preview-build', *(f'preview-shard ({i})' for i in range(1, 6))}
                    if 'preview.yml' in path else {'v2-render', *(f'render-tests ({lane})' for lane in ('contract', 'league', 'journey'))})
        passed = {j['name'] for j in jobs if j['conclusion'] == 'success'}
        require(required <= passed, 'missing/failed exhaustive CI jobs')
        if 'preview.yml' in path:
            artifacts = items(f"actions/runs/{run['id']}/artifacts", 'artifacts', get)
            require(any(a['name'] == f'preview-dist-{head}' and not a['expired'] and a['size_in_bytes'] > 0
                        for a in artifacts), 'missing/expired combined build artifact')
    checks = items(f'commits/{head}/check-runs', 'check_runs', get)
    require(all(c['status'] == 'completed' and c['conclusion'] in ('success', 'neutral', 'skipped')
                for c in checks), 'failed/pending current-head check')


def review(pr, head, owners, risk, get=api):
    # Explicit attestation supports independent sessions sharing one GitHub login.
    # It does not establish independence beyond that durable reviewer receipt.
    reviews = items(f'pulls/{pr}/reviews', get=get)
    for receipt in reversed(reviews):
        if receipt['commit_id'] != head or receipt['state'] not in ('APPROVED', 'COMMENTED'):
            continue
        match = re.search(r'<!-- release-review (\{[^\n]+\}) -->', receipt.get('body') or '')
        if not match:
            continue
        att = json.loads(match[1])
        if (att.get('head') == head and att.get('result') == 'pass'
                and att.get('reviewer_session') and att['reviewer_session'] not in owners
                and att.get('provider') and att.get('model')
                and (risk != 'review-high-risk' or att.get('capability') == 'high-risk')):
            require(not any(r['commit_id'] == head and r['state'] == 'CHANGES_REQUESTED'
                            and r['submitted_at'] > receipt['submitted_at'] for r in reviews), 'unresolved review findings')
            return
    raise ValueError(f'missing independent current-head review for PR {pr}')


def acceptance(batch, get=api):
    receipt = batch['acceptance']
    sha = receipt['published_sha']
    publication = get(f"actions/runs/{receipt['publication_run']}")
    require(publication['path'] == '.github/workflows/pages.yml' and publication['head_branch'] == 'main'
            and publication['head_sha'] == sha
            and publication['conclusion'] == 'success', 'missing/failed publication')
    jobs = items(f"actions/runs/{publication['id']}/jobs", 'jobs', get)
    require({'build', 'deploy', *(f'validate-shard ({i})' for i in range(1, 6))}
            <= {j['name'] for j in jobs if j['conclusion'] == 'success'}, 'publication gates missing')
    integration = get(f"pulls/{batch['integration_pr']}")
    require(integration['merged'] and integration['merge_commit_sha'] == sha, 'publication is not the batch merge')
    live = get(f"actions/runs/{receipt['live_run']}")
    require(live['path'] == '.github/workflows/live-page-synthetic.yml' and live['head_branch'] == 'main'
            and live['conclusion'] == 'success'
            and live['run_started_at'] > publication['updated_at'], 'missing/failed post-publication live gate')
    artifacts = items(f"actions/runs/{live['id']}/artifacts", 'artifacts', get)
    found = [a for a in artifacts if a['name'] == 'live-page-synthetic-results' and not a['expired'] and a['size_in_bytes'] > 0]
    require(len(found) == 1, 'missing/expired live acceptance artifact')
    with zipfile.ZipFile(io.BytesIO(get(f"actions/artifacts/{found[0]['id']}/zip", raw=True))) as archive:
        result = json.loads(archive.read('live-page-synthetic.json'))
    require(not result.get('error') and result.get('problems') == []
            and result.get('passed') is True
            and result.get('httpStatus') == 200 and result.get('pageErrors') == []
            and result.get('pages') and all(p.get('passed') is True for p in result['pages'])
            and re.fullmatch(r'tv-\d{8}-\d{4}-' + sha[:7], result.get('liveTag', '')), 'live artifact does not accept published batch')


def preflight(doc, manifest, main, head, get=api, run_git=git):
    active = registry(doc)
    require(active is not None and manifest['batch_id'] == active['id'], 'no matching active reservation')
    require(SHA.fullmatch(main) and SHA.fullmatch(head) and manifest['main_sha'] == main, 'stale pinned main')
    require(manifest['members'] == active['members'], 'manifest does not match exclusive membership')
    previous = [b for b in doc['batches'] if b['state'] == 'accepted']
    if previous:
        acceptance(previous[-1], get)
    run_git('merge-base', '--is-ancestor', main, head)
    owners = {active['owner'], *(m['owner'] for m in active['members'])}
    for m in active['members']:
        pr = get(f"pulls/{m['pr']}")
        require(pr['state'] == 'open' and not pr['merged'] and pr['head']['sha'] == m['head'], 'stale/merged member head')
        require(pr['base']['ref'] == 'main', 'member base must be main')
        risk_floor(pr, m['risk'], get)
        run_git('merge-base', '--is-ancestor', m['head'], head)
        check_ci(m['pr'], m['head'], get)
        review(m['pr'], m['head'], {m['owner']}, m['risk'], get)
    pr = get(f"pulls/{active['integration_pr']}")
    require(pr['state'] == 'open' and not pr['draft'] and pr['head']['sha'] == head
            and pr['base']['ref'] == 'main' and pr['mergeable'] is True, 'stale/draft/conflicted integration head')
    check_ci(active['integration_pr'], head, get)
    review(active['integration_pr'], head, owners, active['members'][0]['risk'], get)


def transition(old, new, get=api):
    """Preserve history; reserve, re-pin verified heads, accept, or withdraw unmerged work."""
    current = registry(old)
    following = registry(new)
    before, after = old['batches'], new['batches']
    if current is None:
        require(len(after) == len(before) + 1 and after[:-1] == before and following,
                'registry history must be preserved; append one active reservation')
        accepted = [b for b in before if b['state'] == 'accepted']
        if accepted:
            acceptance(accepted[-1], get)
        return
    require(len(after) == len(before) and after[:-1] == before[:-1], 'active membership/history is immutable')
    latest = after[-1]
    stable = lambda b: {k: v for k, v in b.items() if k not in ('state', 'acceptance', 'recovery', 'members')}
    require(stable(current) == stable(latest), 'active ownership changed')
    if latest['state'] == 'active':
        without_head = lambda rows: [{k: v for k, v in m.items() if k != 'head'} for m in rows]
        require(without_head(current['members']) == without_head(latest['members']), 'active membership changed')
        require(current['members'] != latest['members'], 'no head correction')
        for member in latest['members']:
            pr = get(f"pulls/{member['pr']}")
            require(pr['state'] == 'open' and not pr['merged'] and pr['head']['sha'] == member['head'], 'stale recovery head')
            risk_floor(pr, member['risk'], get)
            check_ci(member['pr'], member['head'], get)
            review(member['pr'], member['head'], {member['owner']}, member['risk'], get)
        return
    require(latest['members'] == current['members'], 'active ownership changed')
    if latest['state'] == 'withdrawn':
        pr = get(f"pulls/{current['integration_pr']}")
        require(pr['merged'] is False, 'merged batch cannot withdraw; publication/live acceptance still required')
        return
    require(latest['state'] == 'accepted', 'invalid completion state')
    acceptance(latest, get)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pr', type=int, help='ordinary merge preflight (no merge is performed)')
    group.add_argument('--batch', help='integration preflight; requires --head')
    group.add_argument('--check-ownership', type=int, help='cheap PR gate against main reservations')
    parser.add_argument('--main', required=True, help='pinned main SHA; ownership-only checks pin its registry blob')
    parser.add_argument('--head', help='exact expected integration head SHA')
    args = parser.parse_args()
    try:
        git('fetch', '--no-tags', 'origin', 'main')
        tip = git('rev-parse', 'FETCH_HEAD')
        registry_blob = None
        if args.check_ownership:
            # This lightweight check establishes membership, not merge readiness.
            # Pin the actual ownership data so bot/status commits cannot poison
            # source CI; every real --pr/--batch merge gate still pins main itself.
            require(SHA.fullmatch(args.main) and SHA.fullmatch(tip), 'invalid registry source head')
            registry_blob = git('rev-parse', f'{args.main}:{REGISTRY}')
            require(SHA.fullmatch(registry_blob), 'missing registry blob')
            require(git('rev-parse', f'{tip}:{REGISTRY}') == registry_blob,
                    'registry changed; refresh ownership evidence')
        else:
            require(tip == args.main, 'main advanced; regenerate evidence')
        doc = json.loads(git('show', f'{tip}:{REGISTRY}'))
        active = registry(doc)
        if args.check_ownership:
            # Combined CI must run before review, so this gate checks ownership
            # only. Full preflight below still requires CI/review before merge.
            claims = [b['id'] for b in doc['batches'] if b['state'] != 'withdrawn'
                      and any(m['pr'] == args.check_ownership for m in b['members'])]
            # A valid reservation is not a failed application check. Keep source
            # CI usable after synchronize; --pr still blocks every individual
            # merge during the reservation and --batch pins the actual heads.
            if claims:
                print('Reserved member of ' + claims[0] + '; individual merge preflight remains blocked.')
            changed = items(f'pulls/{args.check_ownership}/files')
            if any(f['filename'] == REGISTRY for f in changed):
                require([f['filename'] for f in changed] == [REGISTRY] and changed[0]['status'] == 'modified',
                        'reservation changes must be a registry-only PR')
                pr = api(f'pulls/{args.check_ownership}')
                candidate = api(f"contents/{REGISTRY}?ref={pr['head']['sha']}")
                transition(doc, json.loads(base64.b64decode(candidate['content'])))
        elif args.pr:
            changed = items(f'pulls/{args.pr}/files')
            if [f['filename'] for f in changed] == [REGISTRY] and changed[0]['status'] == 'modified':
                pr = api(f'pulls/{args.pr}')
                candidate = api(f"contents/{REGISTRY}?ref={pr['head']['sha']}")
                transition(doc, json.loads(base64.b64decode(candidate['content'])))
            else:
                ordinary(doc, args.pr)
                accepted = [b for b in doc['batches'] if b['state'] == 'accepted']
                if accepted:
                    acceptance(accepted[-1])
        else:
            require(active and active['id'] == args.batch and args.head and SHA.fullmatch(args.head), 'unknown batch/head')
            git('fetch', '--no-tags', 'origin', f"pull/{active['integration_pr']}/head")
            require(git('rev-parse', 'FETCH_HEAD') == args.head, 'integration head advanced')
            manifest = json.loads(git('show', f'{args.head}:{MANIFEST}'))
            preflight(doc, manifest, tip, args.head)
        latest_main = api('git/ref/heads/main')['object']['sha']
        if args.check_ownership:
            require(SHA.fullmatch(latest_main), 'invalid registry source head')
            if latest_main != tip:
                require(api(f'contents/{REGISTRY}?ref={latest_main}')['sha'] == registry_blob,
                        'registry changed during ownership check')
        else:
            require(latest_main == tip, 'main advanced during preflight')
        print(json.dumps({'passed': True, 'main': tip, 'head': args.head, 'batch': args.batch,
                          'ownership_only': bool(args.check_ownership), 'registry_blob': registry_blob,
                          'checked_at': datetime.now(timezone.utc).isoformat()}))
        return 0
    except Exception as exc:
        print(f'release preflight blocked: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
