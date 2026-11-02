"""Attribute gate failures without changing the gate's exit status."""
import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTEXTS = {"local", "CI", "nightly", "daily sweep"}
REGISTRY = ROOT / "docs/baseline-reds/registry.json"


def observe_targets(entries):
    """Fixture error IDs are result labels; load their owning test scope."""
    targets = []
    for entry in entries:
        test = entry['test_id']
        owner, _, method = test.rpartition('.')
        target = owner if method in ('setUpModule', 'tearDownModule', 'setUpClass', 'tearDownClass') else test
        if target not in targets:
            targets.append(target)
    return targets


def results(log):
    found = {}
    for line in log.splitlines():
        match = re.match(r"(?:FAIL|ERROR): (\w+) \(([^)]+)\)", line)
        if match:
            method, owner = match.groups()
            # Python 3.12 includes the method in the qualified parenthesis.
            test = owner if owner.endswith('.' + method) else owner + '.' + method
            found[test] = 'red'
        match = re.match(r"(\w+) \(([^)]+)\).* \.\.\. (ok|FAIL|ERROR|skipped.*)$", line)
        if match:
            method, owner, outcome = match.groups()
            test = owner if owner.endswith('.' + method) else owner + '.' + method
            found[test] = 'green' if outcome == 'ok' else 'red' if outcome in ('FAIL', 'ERROR') else 'skip'
    return found


def load_registry(path):
    entries = json.loads(path.read_text())
    if not isinstance(entries, list):
        raise ValueError("registry must be a list")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"entry {i} must be an object")
        for key in ('test_id', 'first_seen_main_sha', 'reason'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f"entry {i}: {key} must be non-empty")
        if not re.fullmatch(r'JEG-\d+', str(entry.get('ticket', ''))):
            raise ValueError(f"entry {i}: invalid ticket")
        where = entry.get('where')
        if not isinstance(where, list) or not where or any(not isinstance(c, str) or c not in CONTEXTS for c in where):
            raise ValueError(f"entry {i}: invalid where contexts")
        if 'signature' in entry and (not isinstance(entry['signature'], str) or not entry['signature'].strip()):
            raise ValueError(f"entry {i}: signature must be non-empty")
        if 'expires' in entry:
            value = entry['expires']
            if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError(f"entry {i}: invalid expires date")
            date.fromisoformat(value)
    return entries


def failure_details(log):
    """Keep exception text scoped to its unittest traceback, never a neighbour."""
    details = {}
    headers = list(re.finditer(r'^(?:FAIL|ERROR): (\w+) \(([^)]+)\).*$', log, re.M))
    for i, match in enumerate(headers):
        method, owner = match.groups()
        test = owner if owner.endswith('.' + method) else owner + '.' + method
        end = headers[i + 1].start() if i + 1 < len(headers) else len(log)
        block = re.sub(r'^\s*-{10,}\n', '', log[match.end():end])
        block = re.split(r'\n[-=]{10,}', block)[0]
        details.setdefault(test, []).append(block)
    return details


def explained_command(command, log, known):
    """Only a plain unittest invocation with complete failure accounting is proof."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if len(argv) < 4 or Path(argv[0]).name not in ('python', 'python3') or argv[1:3] != ['-m', 'unittest']:
        return False
    targets = [arg for arg in argv[3:] if arg not in ('-v', '--verbose')]
    if not targets or any(not re.fullmatch(r'[A-Za-z_][\w.]*', arg) for arg in targets):
        return False
    red = {t for t, outcome in results(log).items() if outcome == 'red'}
    counts = re.findall(r'^FAILED \(([^)]+)\)', log, re.M)
    if len(counts) != 1:
        return False
    total = sum(int(n) for n in re.findall(r'(?:failures|errors)=(\d+)', counts[0]))
    return bool(red) and total == len(red) and red <= known and all(any(t == a or t.startswith(a + '.') for a in targets) for t in red)


def report(entries, observed, context, history, night=None, rc=0, log='', command=None, today=None):
    today = today or date.today()
    lines = ['### Baseline red attribution', '']
    known = set()
    details = failure_details(log)
    for test, outcome in sorted(observed.items()):
        entry = next((e for e in entries if e['test_id'] == test), None)
        if outcome == 'red':
            notes = []
            matched = entry is not None
            if entry and context not in entry['where']:
                matched = False
                notes.append('registered for ' + ', '.join(entry['where']) + ' only')
            if entry and entry.get('expires') and date.fromisoformat(entry['expires']) < today:
                matched = False
                notes.append('expired registry entry')
            if entry and entry.get('signature') and (not details.get(test) or not all(entry['signature'] in block for block in details[test])):
                matched = False
                notes.append('failure signature mismatch')
            label = f"known baseline red ({entry['ticket']})" if matched else 'new red'
            if matched:
                known.add(test)
            lines.append(f'- `{test}`: {label}' + ('; ' + '; '.join(notes) if notes else ''))
    if rc != 0:
        failed_commands = re.findall(r'^run_suite: failed: (.+)$', log, re.M)
        for failed in failed_commands:
            # run_suite prints the command immediately before executing it.
            start = log.find(failed + '\n')
            end = log.find('run_suite: FAILED (', start)
            block = log[start:end] if start >= 0 and end >= 0 else ''
            if not explained_command(failed, block, known):
                lines.append(f'- `{failed}`: unattributed failure')
        if command and explained_command(shlex.join(command), log, known):
            lines.append('All failures are known baseline reds.')
        else:
            # Runner summaries cannot prove the enclosing shell/make did not also fail.
            lines.append(f'Not every failure is explained: unattributed failure (gate exit {rc}); inspect original output, including shell, pytest and node commands.')
    if night:
        night_date = date.fromisoformat(night)
        for entry in entries:
            if context not in entry['where']:
                continue
            test = entry['test_id']
            days = history.setdefault(test, {}).setdefault(context, {})
            days[night] = observed.get(test, 'missing')
            if all(days.get((night_date - timedelta(days=i)).isoformat()) == 'green' for i in range(3)):
                lines.append(f"- `{test}`: can remove after three green nights; close {entry['ticket']} before removal.")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--context', choices=['local', 'CI', 'nightly', 'daily sweep'], default='local')
    parser.add_argument('--history', type=Path)
    parser.add_argument('--list-observe-targets', action='store_true')
    parser.add_argument('--night', help='UTC YYYY-MM-DD; nightly main runs only')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if args.list_observe_targets:
        print('\n'.join(observe_targets(load_registry(args.registry))))
        return 0
    if not command:
        parser.error('provide a gate command after --')
    registry_error = None
    try:
        entries = load_registry(args.registry)
    except (OSError, ValueError, TypeError) as exc:
        entries = []
        registry_error = f"Malformed registry: {exc}"
    env = dict(os.environ, BASELINE_RED_VERBOSE='1')
    env['PYTHONPATH'] = str(ROOT / 'pipelines/baseline_runtime') + os.pathsep + env.get('PYTHONPATH', '')
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    log = []
    for line in proc.stdout:
        print(line, end='', flush=True)
        log.append(line)
    rc = proc.wait()
    history = json.loads(args.history.read_text()) if args.history and args.history.exists() else {}
    summary = report(entries, results(''.join(log)), args.context, history, args.night, rc=rc, log=''.join(log), command=command)
    if registry_error:
        summary += registry_error + '\n'
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write(summary)
    if args.history and args.night:
        args.history.parent.mkdir(parents=True, exist_ok=True)
        args.history.write_text(json.dumps(history, indent=2) + '\n')
    return (rc if rc >= 0 else 128 - rc) if rc else (2 if registry_error else 0)


if __name__ == '__main__':
    sys.exit(main())
