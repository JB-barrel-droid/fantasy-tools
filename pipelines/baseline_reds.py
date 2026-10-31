"""Attribute gate failures without changing the gate's exit status."""
import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/baseline-reds/registry.json"


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


def report(entries, observed, context, history, night=None):
    lines = ['### Baseline red attribution', '']
    for test, outcome in sorted(observed.items()):
        entry = next((e for e in entries if e['test_id'] == test and context in e['where']), None)
        if outcome == 'red':
            label = f"known baseline red ({entry['ticket']})" if entry else 'new red'
            lines.append(f'- `{test}`: {label}')
    if not any(v == 'red' for v in observed.values()):
        lines.append('No identifiable failing unittest tests; inspect the gate output for non-test failures.')
    if night:
        today = date.fromisoformat(night)
        for entry in entries:
            test = entry['test_id']
            days = history.setdefault(test, {})
            days[night] = observed.get(test, 'missing')
            if all(days.get((today - timedelta(days=i)).isoformat()) == 'green' for i in range(3)):
                lines.append(f"- `{test}`: can remove after three green nights; close {entry['ticket']} before removal.")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--context', choices=['local', 'CI', 'nightly', 'daily sweep'], default='local')
    parser.add_argument('--history', type=Path)
    parser.add_argument('--night', help='UTC YYYY-MM-DD; nightly main runs only')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('provide a gate command after --')
    entries = json.loads(args.registry.read_text())
    env = dict(os.environ, BASELINE_RED_VERBOSE='1')
    env['PYTHONPATH'] = str(ROOT / 'pipelines/baseline_runtime') + os.pathsep + env.get('PYTHONPATH', '')
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    log = []
    for line in proc.stdout:
        print(line, end='', flush=True)
        log.append(line)
    rc = proc.wait()
    history = json.loads(args.history.read_text()) if args.history and args.history.exists() else {}
    summary = report(entries, results(''.join(log)), args.context, history, args.night)
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write(summary)
    if args.history and args.night:
        args.history.parent.mkdir(parents=True, exist_ok=True)
        args.history.write_text(json.dumps(history, indent=2) + '\n')
    return rc if rc >= 0 else 128 - rc


if __name__ == '__main__':
    sys.exit(main())
