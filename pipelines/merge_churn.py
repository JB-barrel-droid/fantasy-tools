"""Offline-first merge telemetry. See docs/merge-churn-telemetry.md."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import statistics
from typing import Protocol

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp  # noqa: E402


KINDS = {'ready', 'enqueue', 'head', 'base', 'refresh', 'merge', 'ci'}


def instant(value):
    dt = parse_iso_timestamp(value)
    if dt.tzinfo is None:
        raise ValueError('timestamps must include a timezone')
    return dt.astimezone(timezone.utc)


class EventSource(Protocol):
    def events(self):
        """Yield normalized events with stable source IDs (no network in store)."""
        ...


class FixtureSource:
    def __init__(self, path):
        self.path = Path(path)

    def events(self):
        data = json.loads(self.path.read_text())
        if data['schema_version'] != 1:
            raise ValueError('unsupported input schema')
        return iter(data['events'])


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, 1):
        db.close()
        raise ValueError('unsupported database schema')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS events (
            repository TEXT NOT NULL, source_id TEXT NOT NULL,
            pr INTEGER NOT NULL CHECK(pr > 0), kind TEXT NOT NULL,
            occurred_at TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(repository, source_id)
        );
        CREATE INDEX IF NOT EXISTS events_pr_time
            ON events(repository, pr, occurred_at);
        PRAGMA user_version = 1;
    ''')
    return db


def normalized(event):
    repo, source_id = event['repository'], event['source_id']
    if not isinstance(repo, str) or len(repo.split('/')) != 2 or not all(repo.split('/')):
        raise ValueError('repository must be owner/repo')
    if not isinstance(source_id, str) or not source_id:
        raise ValueError('source_id required')
    if type(event['pr']) is not int or event['pr'] <= 0:
        raise ValueError('positive integer PR required')
    kind = event['kind']
    if kind not in KINDS:
        raise ValueError('unknown event kind')
    stamp = instant(event['occurred_at']).isoformat()
    p = dict(event.get('payload', {}))
    if kind in {'head', 'base', 'refresh', 'ci'} and not p.get('head_sha'):
        raise ValueError('head_sha required')
    if kind == 'base':
        if not p.get('base_sha') or type(p.get('behind')) is not int or p['behind'] < 0:
            raise ValueError('base requires base_sha and nonnegative behind')
    if kind == 'ci':
        if not p.get('run_id') or type(p.get('attempt')) is not int or p['attempt'] < 1:
            raise ValueError('CI run_id and positive attempt required')
        start = instant(p['started_at'])
        if start > instant(stamp):
            raise ValueError('CI observation precedes start')
        p['started_at'] = start.isoformat()
        if p.get('completed_at'):
            end = instant(p['completed_at'])
            if end < start or end > instant(stamp):
                raise ValueError('invalid CI completion interval')
            p['completed_at'] = end.isoformat()
    return (repo, source_id, event['pr'], kind, stamp,
            json.dumps(p, sort_keys=True, separators=(',', ':')))


def collect(db, source: EventSource):
    """Atomic, idempotent ingest; conflicting source IDs fail rather than overwrite."""
    inserted = 0
    with db:
        for event in source.events():
            row = normalized(event)
            old = db.execute('SELECT * FROM events WHERE repository=? AND source_id=?', row[:2]).fetchone()
            if old is not None:
                if tuple(old) != row:
                    raise ValueError('source ID reused with changed content')
                continue
            db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)', row)
            inserted += 1
    return inserted


def weekly_report(db, repository, start):
    """Seven UTC days [start,end); PR cohort has any event in that interval."""
    start = instant(start)
    end = start + timedelta(days=7)
    groups = {}
    for row in db.execute('SELECT * FROM events WHERE repository=? AND occurred_at < ? '
                          'ORDER BY occurred_at, source_id', (repository, end.isoformat())):
        event = dict(row)
        event['time'] = instant(row['occurred_at'])
        event['data'] = json.loads(row['payload'])
        groups.setdefault(row['pr'], []).append(event)
    # Resolve attempt lifecycle globally before associating shared runs to PRs.
    snapshots = {}
    for history in groups.values():
        for e in history:
            if e['kind'] == 'ci':
                p = e['data']
                key = (str(p['run_id']), p['attempt'])
                old = snapshots.get(key)
                # Completion is established evidence, even if a later shared-PR
                # observation is incomplete. Prefer a completed snapshot in either
                # traversal order, retaining its coherent start/head/end facts.
                if (old is None
                        or (p.get('completed_at') and not old.get('completed_at'))
                        or (bool(p.get('completed_at')) == bool(old.get('completed_at'))
                            and old['observed_at'] <= e['time'])):
                    snapshots[key] = dict(p, observed_at=e['time'], superseded=False)
    prs = []
    attempts = {}
    for number, history in groups.items():
        if not any(start <= e['time'] < end for e in history):
            continue
        window = [e for e in history if e['time'] >= start]
        heads = [e for e in history if e['kind'] == 'head']
        transitions = sum(a['data']['head_sha'] != b['data']['head_sha']
                          for a, b in zip(heads, heads[1:]) if b['time'] >= start)
        bases = [e for e in window if e['kind'] == 'base']
        ready = next((e['time'] for e in history if e['kind'] == 'ready'), None)
        merge = next((e['time'] for e in history if e['kind'] == 'merge'), None)
        enqueue = next((e['time'] for e in history if e['kind'] == 'enqueue'), None)
        latency = ((merge - ready).total_seconds() / 60
                   if ready and merge and start <= merge < end and merge >= ready else None)
        prs.append(dict(pr=number, ready_at=ready.isoformat() if ready else None,
                        enqueue_at=enqueue.isoformat() if enqueue else None,
                        merged_at=merge.isoformat() if merge else None,
                        head_transitions=transitions,
                        refreshes=sum(e['kind'] == 'refresh' for e in window),
                        base_samples=len(bases),
                        stale=any(e['data']['behind'] > 0 for e in bases) if bases else None,
                        ready_to_merge_minutes=latency))
        # Latest completed (otherwise latest) observation; reruns remain separate. Runs shared
        # by multiple PRs count once in the repository-wide CI denominator.
        pr_attempts = {}
        for e in history:
            if e['kind'] == 'ci':
                p = e['data']
                key = (str(p['run_id']), p['attempt'])
                pr_attempts[key] = dict(snapshots[key])
        for key, candidate in pr_attempts.items():
            finish = instant(candidate['completed_at']) if candidate.get('completed_at') else end
            candidate['superseded'] = any(
                instant(candidate['started_at']) < h['time'] < finish
                and h['data']['head_sha'] != candidate['head_sha'] for h in heads)
            old = attempts.get(key)
            if old is None:
                attempts[key] = dict(candidate)
            else:
                old['superseded'] |= candidate['superseded']
        local_ci = [a for a in pr_attempts.values() if start <= instant(a['started_at']) < end]
        prs[-1].update(ci_attempts=len(local_ci),
                       ci_minutes=sum((instant(a['completed_at']) - instant(a['started_at'])).total_seconds() / 60
                                      for a in local_ci if a.get('completed_at')),
                       superseded_ci_attempts=sum(a['superseded'] for a in local_ci))
    ci = [a for a in attempts.values() if start <= instant(a['started_at']) < end]
    completed = [a for a in ci if a.get('completed_at')]
    minutes = lambda a: (instant(a['completed_at']) - instant(a['started_at'])).total_seconds() / 60
    total_minutes = sum(map(minutes, completed))
    superseded = [a for a in ci if a['superseded']]
    stale = [p for p in prs if p['stale'] is not None]
    latency = [p['ready_to_merge_minutes'] for p in prs if p['ready_to_merge_minutes'] is not None]
    return dict(repository=repository, start=start.isoformat(), end=end.isoformat(),
                prs=prs, pr_count=len(prs),
                refreshes_per_pr=sum(p['refreshes'] for p in prs) / len(prs) if prs else None,
                stale_prs=sum(p['stale'] for p in stale), sampled_prs=len(stale),
                stale_rate=sum(p['stale'] for p in stale) / len(stale) if stale else None,
                latency_samples=len(latency), median_ready_to_merge_minutes=statistics.median(latency) if latency else None,
                ci_attempts=len(ci), completed_ci_attempts=len(completed), ci_minutes=total_minutes,
                superseded_ci_attempts=len(superseded),
                superseded_ci_share=len(superseded) / len(ci) if ci else None,
                superseded_ci_minutes_share=sum(minutes(a) for a in completed if a['superseded']) / total_minutes if total_minutes else None)


def render(report):
    def value(v):
        return 'N/A' if v is None else f'{v:.3f}' if isinstance(v, float) else str(v)
    lines = [f"# Merge churn: {report['repository']}",
             f"UTC window [{report['start']}, {report['end']})", '',
             '| Metric | Value |', '| --- | --- |']
    for key in ('pr_count', 'refreshes_per_pr', 'stale_prs', 'sampled_prs', 'stale_rate',
                'latency_samples', 'median_ready_to_merge_minutes', 'ci_attempts',
                'completed_ci_attempts', 'ci_minutes', 'superseded_ci_attempts',
                'superseded_ci_share', 'superseded_ci_minutes_share'):
        lines.append(f'| {key} | {value(report[key])} |')
    lines += ['', '| PR | Ready | Enqueued | Merged | Refreshes | Head transitions | Base samples | Stale | Latency minutes | CI attempts | CI minutes | Superseded attempts |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for p in report['prs']:
        lines.append('| ' + ' | '.join(value(p[k]) for k in ('pr', 'ready_at', 'enqueue_at', 'merged_at', 'refreshes', 'head_transitions', 'base_samples', 'stale', 'ready_to_merge_minutes', 'ci_attempts', 'ci_minutes', 'superseded_ci_attempts')) + ' |')
    lines += ['', 'Observed data only. Ready means an explicit ready event, not inferred approval or green CI.',
              'Refresh counts require explicit refresh events; head changes alone are not refreshes.',
              'Stale = any behind>0 sample in window; missing samples are excluded, not fresh.',
              'Latency = first observed ready to merge, for merges in window; open PRs excluded.',
              'CI attempts are grouped by start time; minutes are completed attempt wall time, not billed runner time.',
              'Superseded = different head observed strictly during execution; missing head history can undercount.',
              'Live data requires a read-only GitHub adapter producing this event contract, paginated PR timelines,',
              'run-attempt history, persisted head/base observations and explicit queue ready/enqueue/refresh events.',
              'Configure repository, read access for PRs/Actions/contents, durable DB location and an approved collection schedule.',
              'Fixture mode performs no GitHub requests. See docs/merge-churn-telemetry.md.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    ingest = sub.add_parser('collect')
    ingest.add_argument('--fixture', required=True)
    report = sub.add_parser('report')
    report.add_argument('--repository', required=True)
    report.add_argument('--start', required=True)
    report.add_argument('--json', action='store_true')
    args = parser.parse_args()
    db = connect(args.db)
    try:
        if args.command == 'collect':
            print(json.dumps({'inserted': collect(db, FixtureSource(args.fixture))}))
        else:
            result = weekly_report(db, args.repository, args.start)
            print(json.dumps(result, indent=2) if args.json else render(result), end='\n')
    finally:
        db.close()


if __name__ == '__main__':
    main()
