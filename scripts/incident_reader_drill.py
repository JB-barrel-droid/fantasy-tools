#!/usr/bin/env python3
"""Live protected-reader drill; injects routine exhaustion without spending its quota.

Run only after human approval of App scope and drill targets. See --help.
Outputs JSONL evidence; redirect stdout to a private, retained evidence file.
"""
import argparse
import json
from pathlib import Path
import random
import fcntl
import re
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.incident_reader import IncidentClient, RoutineClient, Observer, Unknown


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo')
    parser.add_argument('pr', type=int)
    parser.add_argument('--required', action='append', required=True)
    parser.add_argument('--minutes', type=int, default=65, help='>=65: crosses an hourly reset boundary')
    args = parser.parse_args()
    if args.minutes < 65:
        parser.error('at least 65 minutes required')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repo):
        parser.error('invalid repository')
    lock_dir = Path(__file__).resolve().parents[1] / '.incident-reader-locks'
    lock_dir.mkdir(exist_ok=True, mode=0o700)
    lock = (lock_dir / (args.repo.replace('/', '_')+'_'+str(args.pr))).open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('{"state":"UNKNOWN","reason":"observer already active"}')
        return 2
    events, results = [], []
    def emit(event):
        print(json.dumps(event), flush=True)
    def telemetry(event):
        events.append(event)
        emit({'telemetry': event})
    client = IncidentClient('incident', args.repo, telemetry=telemetry)
    # This is a boundary injection, never a live quota-exhaustion request.
    routine = RoutineClient('', send=lambda *a: (403, {
        'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int(time.time()+900))}, {}))
    start = time.monotonic()
    observer = Observer(client, args.pr, args.required)
    while time.monotonic()-start < args.minutes*60:
        if time.monotonic()-observer.started >= 1800:
            observer = Observer(client, args.pr, args.required)
        elapsed = time.monotonic()-start
        if elapsed < 900:
            try:
                routine.read('/repos/'+args.repo+'/pulls/'+str(args.pr))
                raise RuntimeError('routine exhaustion injection failed')
            except Unknown:
                emit({'routine_injection': '403', 'elapsed': elapsed})
        result = observer.sample()
        result['timestamp'] = time.time()
        results.append(result)
        emit({'sample': result})
        delay = max(60+random.uniform(0, 5), client.backoff_until-time.time())
        # Keep wait chunks bounded for responsive coordinator cancellation.
        until = min(start+args.minutes*60, time.monotonic()+delay)
        while time.monotonic() < until:
            time.sleep(min(60, until-time.monotonic()))
    now = time.time()
    peak = max((sum(e['timestamp'] <= x['timestamp'] < e['timestamp']+1800 for x in events)
                for e in events), default=0)
    remaining = [int(e['remaining']) for e in events if e['remaining'] is not None]
    resets = {e['reset'] for e in events if e['reset'] is not None}
    summary = {'ended': now, 'requests': len(events), 'peak_30min_requests': peak,
        'min_remaining': min(remaining) if remaining else None,
        'reset_values': sorted(resets), 'rate_failures': sum(e['status'] in (403, 429) for e in events),
        'unknown_samples': sum(r['state'] == 'UNKNOWN' for r in results),
        'automatic_thresholds_pass': bool(remaining) and len(resets) >= 2 and peak <= 300
            and min(remaining) >= 1000 and not any(e['status'] in (403, 429) for e in events),
        'acceptance': 'HUMAN_EVIDENCE_REQUIRED: identity separation, baseline counters, completion trigger latency, publication verification'}
    emit({'summary': summary})
    return 0 if summary['automatic_thresholds_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
