#!/usr/bin/env python3
"""Pin candidate evidence. Run/replay commands without replacing live inputs.

  python3 pipelines/candidate_evidence.py run --kind validation -- make validate
  python3 pipelines/candidate_evidence.py run --kind perturbation -- python3 -m unittest tests.test_waiver_band_line.OnePlayerPerturbationTest
  python3 pipelines/candidate_evidence.py replay RESULT_ID

Keep output/candidate-evidence (including archives) with CI artifacts. Exemption
JSON may be supplied with --exemptions; it is evidence, never approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone

INPUTS = ('data', 'config', 'tests/fixtures')
CODE = ('pipelines', 'scripts', 'app', 'tests', 'tools', 'producers',
        'modules', 'docs', 'runbooks', 'bin', 'lanes', 'sql', 'waiver_wire', 'weekly_vegas')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def files(repo):
    paths = set()
    for name in INPUTS + CODE:
        root = repo / name
        if root.exists():
            paths.update(p for p in root.rglob('*') if p.is_file())
    paths.update(p for p in repo.iterdir() if p.is_file() and
                 not p.name.startswith(('SOURCE', 'IMPL-REPORT', '.')))
    return sorted(p for p in paths if not p.is_symlink() and
                  '__pycache__' not in p.parts and 'node_modules' not in p.parts)


def describe(repo):
    hashes = {str(p.relative_to(repo)): sha(p.read_bytes()) for p in files(repo)}
    inputs = {k: v for k, v in hashes.items() if any(k.startswith(n + '/') for n in INPUTS)}
    fixture = repo / 'data/fixtures/current/comparison-sources-data.json'
    sources = {}
    if fixture.exists():
        try:
            sections = json.loads(fixture.read_text()).get('sources', {})
        except (ValueError, AttributeError):
            sections = {}  # Hash malformed inputs too; the gate diagnoses them.
        for name, section in sections.items():
            field = ('espn_snapshot' if name == 'espn' else
                     'vintage' if name in ('cbsros', 'razzball') else 'content_vintage')
            sources[name] = {'content_vintage': section.get(field),
                             'sha256': sha(json.dumps(section, sort_keys=True, separators=(',', ':')).encode())}
    return {'id': sha(json.dumps(hashes, sort_keys=True).encode()),
            'input_id': sha(json.dumps(inputs, sort_keys=True).encode()),
            'files': hashes, 'sources': sources}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def refresh(repo, store):
    current = describe(repo)
    index_path = store / 'index.json'
    index = json.loads(index_path.read_text()) if index_path.exists() else {'results': []}
    for result in index['results']:
        if result['candidate_id'] != current['id']:
            result['superseded'] = True
            result['superseded_by'] = current['id']
    index['current_candidate'] = current
    save(index_path, index)
    return current, index


def run(repo, store, kind, command, exemptions=None):
    candidate, index = refresh(repo, store)
    archive = store / (candidate['id'] + '.tar.gz')
    if not archive.exists():
        with tarfile.open(archive, 'w:gz') as tar:
            for rel in candidate['files']:
                tar.add(repo / rel, arcname=rel, recursive=False)
    result_id = uuid.uuid4().hex
    result = {'id': result_id, 'kind': kind, 'candidate_id': candidate['id'],
              'input_id': candidate['input_id'], 'sources': candidate['sources'],
              'command': command, 'today': os.environ.get('TODAY') or datetime.now().date().isoformat(),
              'exemptions': json.loads(exemptions.read_text()) if exemptions else [],
              'recorded_at': datetime.now(timezone.utc).isoformat(),
              'superseded': False, 'status': 'running'}
    index['results'].append(result)
    save(store / 'index.json', index)
    with (store / (result_id + '.log')).open('wb') as log:
        try:
            rc = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, 'TODAY': result['today']}).returncode
        except OSError as exc:
            log.write(str(exc).encode())
            rc = 127
    result.update(returncode=rc, status='passed' if rc == 0 else 'failed',
                  log_sha256=sha((store / (result_id + '.log')).read_bytes()))
    # Detect mutation during validation too; never attach a green result to B.
    after = describe(repo)
    if after['id'] != candidate['id']:
        result.update(superseded=True, superseded_by=after['id'])
    save(store / 'index.json', index)
    print((store / (result_id + '.log')).read_text(errors='replace'), end='')
    print(f"candidate-evidence: {result_id} {result['status']} candidate={candidate['id']} superseded={result['superseded']}")
    return rc


def replay(repo, store, result_id):
    _, index = refresh(repo, store)
    result = next(r for r in index['results'] if r['id'] == result_id)
    candidate_id = result['candidate_id']
    replay_id = uuid.uuid4().hex
    evidence = {**result, 'id': replay_id, 'kind': 'replay',
                'parent_result_id': result_id,
                'recorded_at': datetime.now(timezone.utc).isoformat(),
                'status': 'running'}
    for key in ('returncode', 'log_sha256', 'completed_at'):
        evidence.pop(key, None)
    index['results'].append(evidence)
    save(store / 'index.json', index)
    log_path = store / (replay_id + '.log')
    rc = 127
    try:
        with log_path.open('wb') as log:
            with tempfile.TemporaryDirectory(prefix='candidate-replay-', dir=store) as tmp:
                target = Path(tmp)
                with tarfile.open(store / (candidate_id + '.tar.gz')) as tar:
                    for member in tar.getmembers():
                        if not member.isfile() or not (target / member.name).resolve().is_relative_to(target.resolve()):
                            raise ValueError('unsafe candidate archive')
                    tar.extractall(target, filter='data')
                if describe(target)['id'] != candidate_id:
                    raise ValueError('candidate archive hash mismatch')
                try:
                    rc = subprocess.run(result['command'], cwd=target, stdout=log,
                                        stderr=subprocess.STDOUT,
                                        env={**os.environ, 'TODAY': result['today']}).returncode
                except OSError as exc:
                    log.write(str(exc).encode())
    except Exception as exc:
        with log_path.open('ab') as log:
            log.write(str(exc).encode())
        raise
    finally:
        evidence.update(returncode=rc, status='passed' if rc == 0 else 'failed',
                        log_sha256=sha(log_path.read_bytes()),
                        completed_at=datetime.now(timezone.utc).isoformat())
        save(store / 'index.json', index)
        print(log_path.read_text(errors='replace'), end='')
        print(f"candidate-evidence: {replay_id} {evidence['status']} parent={result_id} candidate={candidate_id}")
    return rc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    sub = parser.add_subparsers(dest='action', required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--kind', choices=('validation', 'perturbation', 'exemption'), required=True)
    run_parser.add_argument('--exemptions', type=Path)
    run_parser.add_argument('command', nargs=argparse.REMAINDER)
    sub.add_parser('refresh')
    sub.add_parser('replay').add_argument('result_id')
    args = parser.parse_args()
    repo = args.repo.resolve()
    store = repo / 'output/candidate-evidence'
    store.mkdir(parents=True, exist_ok=True)
    if args.action == 'refresh':
        refresh(repo, store)
        return 0
    if args.action == 'replay':
        return replay(repo, store, args.result_id)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('a command is required')
    return run(repo, store, args.kind, command, args.exemptions)


if __name__ == '__main__':
    raise SystemExit(main())
