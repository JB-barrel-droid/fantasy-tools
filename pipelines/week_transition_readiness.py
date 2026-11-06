"""Offline, fail-closed week-transition capture and rehearsal (JEG-1526).

No live DB adapter is installed. DB-dependent stages deliberately remain BLOCKED.
Only fixed diagnostic commands may execute, inside a networkless container.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import fcntl
import json
import re
import shutil
import subprocess
from pathlib import Path

SOURCES = ('fantasycalc', 'usatoday', 'fantasypros', 'espn', 'cbs', 'cbsros', 'razzball')
SCORINGS = {'standard', 'half_ppr', 'ppr'}
DB_STAGES = {
    'import': 'captured-source replay/import adapter',
    'health': 'target-week staging import health adapter',
    'chain_first': 'isolated staging DB and audited target-week consumers',
    'translation_refresh': 'staging writing refresh plus verification of all 21 grains',
    'chain_second': 'staging second chain plus consumed-translation provenance verifier',
    'consolidation_export': 'staging consolidation write/export round-trip adapter',
    'lineage': 'captured-input lineage verifier',
    'weekly_loader': 'explicit season/week bundle and disposable DB loader/freshness adapter',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inside(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'path escapes capture root: {name}')
    return path


def capture(root, policy, arrivals, season, week):
    """Hash actual bytes; do not trust advertised hashes, mtimes or fetch dates.

    Both policy and arrivals are versioned caller-owned JSON. Date feeds need
    explicit content date windows; weekly feeds must match season/week exactly.
    """
    errors, rows = [], []
    expected = policy.get('sources', {})
    if policy.get('version') != 1 or set(expected) != set(SOURCES):
        errors.append('version 1 policy must explicitly cover all seven sources')
    for source in SOURCES:
        rule, item = expected.get(source, {}), arrivals.get(source)
        if not item:
            errors.append(f'{source}: missing arrival')
            continue
        row = dict(item, source=source)
        try:
            path = inside(root, item['path'])
            row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            if item.get('season') != season:
                raise ValueError('wrong season')
            if rule.get('kind') == 'week':
                if item.get('week') != week:
                    raise ValueError('wrong content week (carry-forward is not implicit)')
            elif rule.get('kind') == 'date':
                date = dt.date.fromisoformat(item['content_date'])
                if not (dt.date.fromisoformat(rule['earliest']) <= date <= dt.date.fromisoformat(rule['latest'])):
                    raise ValueError('content date outside expected window')
            else:
                raise ValueError('missing week/date expectation')
            required = set(rule['scorings'])
            if not required or not required <= SCORINGS or not required <= set(item['scorings']):
                raise ValueError('missing scoring coverage')
            for grain, minimum in rule['grains'].items():
                if not isinstance(minimum, int) or minimum < 1 or item['grains'].get(grain, 0) < minimum:
                    raise ValueError(f'missing grain {grain}')
            if not rule['grains']:
                raise ValueError('empty grain expectations')
        except (OSError, KeyError, TypeError, ValueError) as exc:
            errors.append(f'{source}: {exc}')
        rows.append(row)
    manifest = {'version': 1, 'season': season, 'week': week, 'policy': policy, 'sources': rows}
    return dict(manifest, input_hash=digest(manifest), complete=not errors, errors=errors)


def reconcile(state, manifest, code_hash, event):
    """Landing hook and hourly reconciliation share one content-addressed queue.

    A claimed/failed operation is never automatically retried. Corrected content
    or code creates a new operation; retry policy remains an operator decision.
    """
    key = digest([manifest['season'], manifest['week'], code_hash, manifest['input_hash']])
    old = state.get('current_key')
    state['current_key'] = key
    jobs = state.setdefault('jobs', {})
    queued = key not in jobs
    if queued:
        jobs[key] = {'status': 'QUEUED', 'event': event, 'complete': manifest['complete']}
    return {'key': key, 'queued': queued, 'invalidated': old is not None and old != key}


def receipt_valid(receipt, manifest, code_hash):
    return (receipt.get('ready') is True and manifest['complete']
            and receipt.get('input_hash') == manifest['input_hash']
            and receipt.get('code_hash') == code_hash)


def commands(today):
    return {
        'week9_regression': ['python3', '-m', 'unittest', 'tests.test_waiver_band_line.OnePlayerPerturbationTest'],
        'sync': ['make', 'sync'],
        'validate': ['make', 'validate', f'TODAY={today}'],
        'integration': ['make', 'test-integration'],
        'browser_render': ['node', 'tests/rendered_gate/gate.mjs', 'dist', '--out', 'rendered-gate.json'],
        'browser_bench': ['node', 'tests/rendered_gate/bench_share_readout_harness.mjs', 'dist'],
        'browser_flex': ['node', 'tests/rendered_gate/gate_flexibility.mjs', 'dist'],
    }


def code_digest(root):
    # Track bytes rather than HEAD alone, including dirty/untracked implementation.
    files = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard'], cwd=root,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    return digest([(name, hashlib.sha256((root / name).read_bytes()).hexdigest())
                   for name in sorted(set(files))
                   if name not in ('IMPL-REPORT.md',) and not name.startswith('ticket-work/') and not name.startswith('SOURCE')
                   and (root / name).is_file() and not (root / name).is_symlink()])


def scratch_copy(root, dest):
    """Select version-controlled, nonignored diagnostic inputs, never a tree copy.

    Read current working bytes so tracked fixes are rehearsed. Untracked inputs
    require explicit review/addition before they can enter diagnostics. Private
    paths are rejected even if accidentally force-added to the index.
    """
    def tracked(*options):
        result = subprocess.run(['git', 'ls-files', '-z', '--cached', *options],
                                cwd=root, capture_output=True, check=True)
        return {Path(name.decode('utf-8')) for name in result.stdout.split(b'\0') if name}

    selected = tracked() - tracked('--ignored', '--exclude-standard')
    forbidden = {'.git', '.aws', '.codex', '.agents', 'secrets', 'node_modules',
                 'dist', '__pycache__', '.venv', 'venv', 'ticket-work'}
    dest.mkdir(parents=True, exist_ok=False)
    for relative in sorted(selected):
        if (relative.is_absolute() or '..' in relative.parts
                or any(part in forbidden or part.startswith(('.env', 'SOURCE'))
                       for part in relative.parts)
                or relative.suffix.lower() in {'.key', '.pem'}
                or relative.name == 'IMPL-REPORT.md'
                or relative.parts[:2] in {('data', 'private'), ('data', 'raw')}):
            continue
        source = root / relative
        # Reject directory symlinks as well as leaf symlinks before reading.
        if any((root / Path(*relative.parts[:i])).is_symlink()
               for i in range(1, len(relative.parts) + 1)):
            continue
        if not source.is_file() or source.resolve().is_relative_to(dest.parent.resolve()):
            continue
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def run(root, output, manifest, code_hash, today, image=None):
    stages = [{'name': 'source_completeness', 'status': 'PASS' if manifest['complete'] else 'BLOCKED',
               'detail': manifest['errors']}]
    stages += [{'name': name, 'status': 'BLOCKED', 'detail': f'Missing {adapter}'}
               for name, adapter in DB_STAGES.items()]
    output.mkdir(parents=True, exist_ok=False)
    scratch = output / 'scratch'
    captures = output / 'captures'
    captures.mkdir()
    for row in manifest['sources']:
        if 'sha256' in row:
            payload = inside(root, row['path']).read_bytes()
            if hashlib.sha256(payload).hexdigest() != row['sha256']:
                raise ValueError('source changed during immutable capture')
            (captures / row['sha256']).write_bytes(payload)
    if image:
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('image must be a preloaded immutable sha256 image ID')
        scratch_copy(root, scratch)
    for name, command in commands(today).items():
        stage = {'name': name, 'command': command, 'status': 'BLOCKED',
                 'detail': 'Supply prebuilt local image; diagnostic only until staging adapters exist'}
        if image:
            # No host env forwarding, network, Docker socket, Git directory, or production credentials.
            argv = ['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=256',
                    '--tmpfs', '/tmp', '--mount', f'type=bind,src={scratch},dst=/work',
                    '--workdir', '/work', '--entrypoint', '/usr/bin/env', image,
                    '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/tmp', *command]
            try:
                proc = subprocess.run(argv, capture_output=True, timeout=1800)
                log = name + '.log'
                (output / log).write_bytes(proc.stdout + proc.stderr)
                stage.update(status='PASS' if proc.returncode == 0 else 'FAIL',
                             exit_code=proc.returncode, log=log, detail='isolated diagnostic')
            except (OSError, subprocess.TimeoutExpired) as exc:
                stage.update(detail=type(exc).__name__ + ': container unavailable or timed out')
        stages.append(stage)
    # No skipped adapter can yield READY, even when all executable diagnostics pass.
    status = 'FAIL' if any(s['status'] == 'FAIL' for s in stages) else 'BLOCKED'
    result = {'schema_version': 1, 'season': manifest['season'], 'week': manifest['week'],
              'code_hash': code_hash, 'input_hash': manifest['input_hash'], 'status': status,
              'ready': False, 'stages': stages,
              'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'first_failed_stage': next(s['name'] for s in stages if s['status'] != 'PASS')}
    (output / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'readiness.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'summary.md').write_text(f"# Week {manifest['week']} readiness: {status}\n\n" +
        '\n'.join(f"- {s['name']}: {s['status']} — {s.get('detail', '')}" for s in stages) + '\n')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--season', type=int, required=True)
    ap.add_argument('--week', type=int, choices=range(1, 19), required=True)
    ap.add_argument('--today', type=dt.date.fromisoformat, required=True)
    ap.add_argument('--policy', required=True)
    ap.add_argument('--arrivals', required=True)
    ap.add_argument('--output', required=True, help='new directory inside this checkout')
    ap.add_argument('--event', choices=('landing', 'hourly'), help='enqueue only, no execution')
    ap.add_argument('--state', help='persistent queue JSON inside checkout; required with --event')
    ap.add_argument('--image', help='optional preloaded immutable diagnostic image ID')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not inside(root, args.output).is_relative_to(root / 'ticket-work'):
        ap.error('--output must be under ticket-work/')
    if args.state and not inside(root, args.state).is_relative_to(root / 'ticket-work'):
        ap.error('--state must be under ticket-work/')
    policy = json.loads(inside(root, args.policy).read_text())
    arrivals = json.loads(inside(root, args.arrivals).read_text())
    manifest = capture(root, policy, arrivals, args.season, args.week)
    code_hash = code_digest(root)
    if args.event:
        if not args.state:
            ap.error('--event requires --state')
        state_path = inside(root, args.state)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # Serialize simultaneous landing/reconciliation deliveries. Atomic rename
        # prevents a crash while writing from corrupting the persistent queue.
        with state_path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            event = reconcile(state, manifest, code_hash, args.event)
            pending = state_path.with_suffix('.pending')
            pending.write_text(json.dumps(state, indent=2) + '\n')
            pending.replace(state_path)
        print(json.dumps(event))
        return 0
    result = run(root, inside(root, args.output), manifest, code_hash, str(args.today), args.image)
    print(json.dumps({'status': result['status'], 'ready': result['ready']}))
    return 1 if result['status'] == 'FAIL' else 2


if __name__ == '__main__':
    raise SystemExit(main())
