"""Trusted, read-only incident observer. Never import App credentials into routine jobs.

Install requirements-incident.txt in the coordinator environment only.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp  # noqa: E402


class Unknown(Exception):
    """Incomplete evidence; messages must never contain remote response bodies."""


def transport(method, path, token, payload=None):
    request = urllib.request.Request(
        'https://api.github.com' + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
    # Refuse redirects: credentials must never follow a remote Location.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            return response.status, dict(response.headers), json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), {}


def sign_jwt(app_id, key, now):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b'=')
    message = b'.'.join(encode(json.dumps(value).encode()) for value in (
        {'alg': 'RS256', 'typ': 'JWT'}, {'iat': int(now)-60, 'exp': int(now)+540, 'iss': app_id}))
    private = serialization.load_pem_private_key(key.encode(), password=None)
    return (message + b'.' + encode(private.sign(message, padding.PKCS1v15(), hashes.SHA256()))).decode()


class RoutineClient:
    """Routine routing has no App credential selector or environment fallback."""
    def __init__(self, token, send=transport):
        self.token, self.send = token, send

    def read(self, path):
        status, headers, data = self.send('GET', path, self.token, None)
        if status != 200:
            raise Unknown('routine read unavailable')
        return data


class IncidentClient:
    def __init__(self, purpose, repo, *, env=None, send=transport, clock=time.time,
                 telemetry=lambda event: None, signer=sign_jwt):
        if purpose != 'incident':
            raise Unknown('routine callers cannot select incident credentials')
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
            raise Unknown('invalid repository')
        self.repo, self.env = repo, os.environ if env is None else env
        self.send, self.clock, self.telemetry, self.signer = send, clock, telemetry, signer
        self.token, self.expires, self.backoff_until, self.requests = '', 0, 0, 0

    def request(self, method, path, token, payload=None):
        if self.clock() < self.backoff_until:
            raise Unknown('rate backoff active')
        self.requests += 1
        try:
            status, headers, data = self.send(method, path, token, payload)
            headers = {k.lower(): v for k, v in headers.items()}
            event = {'caller': 'incident-observer', 'identity': 'incident-app-installation',
                     'repo': self.repo, 'timestamp': self.clock(), 'request_count': self.requests,
                     'category': 'mint' if method == 'POST' else path.split('?')[0].split('/')[-1],
                     'head': getattr(self, 'head', None), 'status': status}
            for field in ('resource', 'limit', 'remaining', 'used', 'reset'):
                event[field] = headers.get('x-ratelimit-' + field)
            event['retry_after'] = headers.get('retry-after')
            event['reserve_alert'] = event['remaining'] is not None and int(event['remaining']) < 1000
            self.telemetry(event)
            if status in (403, 429) or event['remaining'] == '0':
                self.backoff_until = max(self.clock()+60, float(headers.get('x-ratelimit-reset', 0)),
                                         self.clock()+float(headers.get('retry-after', 0)))
            if status != 200 and not (method == 'POST' and status == 201):
                raise Unknown('GitHub read or mint failed')
            return data, headers
        except Unknown:
            raise
        except Exception:
            raise Unknown('transport, telemetry or response failure') from None

    def credential(self):
        if self.expires > self.clock()+60:
            return self.token
        try:
            app, installation, key = (self.env['INCIDENT_GITHUB_APP_ID'],
                self.env['INCIDENT_GITHUB_INSTALLATION_ID'], self.env['INCIDENT_GITHUB_PRIVATE_KEY'])
            if not app.isdigit() or not installation.isdigit():
                raise ValueError()
            jwt = self.signer(app, key, self.clock())
            data, _ = self.request('POST', '/app/installations/'+installation+'/access_tokens', jwt,
                {'repositories': [self.repo.split('/')[1]], 'permissions': {
                    'actions': 'read', 'checks': 'read', 'statuses': 'read', 'pull_requests': 'read'}})
            expiry = parse_iso_timestamp(data['expires_at']).timestamp()
            if expiry <= self.clock()+60 or not data['token']:
                raise ValueError()
            self.token, self.expires = data['token'], expiry
            return self.token
        except Exception:
            raise Unknown('incident credentials unavailable or expired') from None

    def read(self, suffix):
        return self.request('GET', '/repos/'+self.repo+suffix, self.credential())


class Observer:
    def __init__(self, client, pr, required):
        if not required:
            raise ValueError('explicit required check names are mandatory')
        self.client, self.pr, self.required = client, int(pr), set(required)
        self.head, self.run_ids, self.workflow_ids = None, {}, set()
        self.started = time.monotonic()

    def sample(self):
        start = self.client.requests
        def read(path):
            if time.monotonic()-self.started >= 1800:
                raise Unknown('observer deadline')
            # Reserve a call for minting when needed; mint counts in the sample cap.
            needed = 1 + int(self.client.expires <= self.client.clock()+60)
            if self.client.requests-start+needed > 10:
                raise Unknown('sample read budget exhausted')
            return self.client.read(path)
        def pages(path, key):
            rows, page = [], 1
            while True:
                data, headers = read(path+('&' if '?' in path else '?')+f'per_page=100&page={page}')
                chunk = data[key] if key else data
                if not isinstance(chunk, list):
                    raise Unknown('malformed page')
                rows.extend(chunk)
                if 'rel="next"' not in headers.get('link', ''):
                    if isinstance(data, dict) and data.get('total_count', len(rows)) > len(rows):
                        raise Unknown('incomplete pagination')
                    return rows
                page += 1
        try:
            if time.monotonic()-self.started >= 1800:
                raise Unknown('observer deadline')
            pr, _ = read(f'/pulls/{self.pr}')
            head = pr['head']['sha']
            if not re.fullmatch('[0-9a-f]{40}', head):
                raise Unknown('invalid head')
            if head != self.head:
                self.head, self.run_ids, self.workflow_ids = head, {}, set()
            self.client.head = head
            checks = pages(f'/commits/{head}/check-runs?filter=latest', 'check_runs')
            statuses = pages(f'/commits/{head}/statuses', None)
            runs = pages(f'/actions/runs?head_sha={head}&event=pull_request', 'workflow_runs')
            latest = {}
            for run in runs:
                if run['head_sha'] != head:
                    raise Unknown('run head mismatch')
                workflow = run['workflow_id']
                if workflow not in latest or run['id'] > latest[workflow]['id']:
                    latest[workflow] = run
            self.workflow_ids = set(latest)
            self.run_ids = {k: v['id'] for k, v in latest.items()}
            jobs = []
            for run in latest.values():
                run_jobs = pages(f"/actions/runs/{self.run_ids[run['workflow_id']]}/jobs?filter=latest", 'jobs')
                if not run_jobs:
                    raise Unknown('run jobs missing')
                jobs.extend(run_jobs)
            current, _ = read(f'/pulls/{self.pr}')
            if current['head']['sha'] != head:
                self.head, self.run_ids, self.workflow_ids = None, {}, set()
                raise Unknown('head changed during sample')
            latest_statuses = {}
            for item in statuses:  # API newest first; never let old success hide new failure.
                latest_statuses.setdefault(item['context'], item['state'])
            # Status history has one current result per context. Checks are
            # separate evidence, including checks from different apps with the
            # same name; none may overwrite another result or a commit status.
            states = {name: [state] for name, state in latest_statuses.items()}
            for item in checks:
                states.setdefault(item['name'], []).append(
                    item['conclusion'] if item['status'] == 'completed' else 'pending')
            if not self.required <= states.keys():
                raise Unknown('required checks missing')
            complete = all(state == 'success' for name in self.required for state in states[name])
            complete &= all(r['status'] == 'completed' and r['conclusion'] == 'success' for r in latest.values())
            complete &= all(j['status'] == 'completed' and j['conclusion'] in ('success', 'skipped', 'neutral') for j in jobs)
            return {'state': 'GREEN' if complete else 'PENDING', 'head': head,
                    'run_ids': self.run_ids, 'checks': states, 'reads': self.client.requests-start}
        except Exception:
            return {'state': 'UNKNOWN', 'head': self.head, 'reads': self.client.requests-start}

    def observe(self, emit=print):
        while time.monotonic()-self.started < 1800:
            result = self.sample()
            emit(json.dumps(result))
            if result['state'] == 'GREEN':
                return result
            delay = max(60+random.uniform(0, 5), self.client.backoff_until-self.client.clock())
            left = 1800-(time.monotonic()-self.started)
            if delay >= left:
                break
            time.sleep(delay)
        return {'state': 'UNKNOWN', 'head': self.head, 'reason': 'deadline'}


# A coordinator process shares this registry; separate processes use a POSIX lock in main.
_registry = {}
_registry_lock = threading.Lock()


def observer_for(client, pr, required):
    with _registry_lock:
        key = (client.repo, int(pr))
        if key not in _registry:
            _registry[key] = Observer(client, pr, required)
        elif _registry[key].required != set(required):
            raise Unknown('observer required-check contract differs')
        return _registry[key]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo')
    parser.add_argument('pr', type=int)
    parser.add_argument('--required', action='append', required=True)
    args = parser.parse_args()
    import fcntl
    from pathlib import Path
    # Worktree-local lock, no secret material. Whole PR lock is stricter than per-head.
    lock_dir = Path(__file__).resolve().parents[1] / '.incident-reader-locks'
    lock_dir.mkdir(exist_ok=True, mode=0o700)
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repo):
        parser.error('invalid repository')
    with (lock_dir / (args.repo.replace('/', '_')+'_'+str(args.pr))).open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"state":"UNKNOWN","reason":"observer already active"}')
            return 2
        client = IncidentClient('incident', args.repo, telemetry=lambda e: print(json.dumps({'telemetry': e})))
        result = observer_for(client, args.pr, args.required).observe()
        print(json.dumps(result))
        return 0 if result['state'] == 'GREEN' else 2


if __name__ == '__main__':
    raise SystemExit(main())
