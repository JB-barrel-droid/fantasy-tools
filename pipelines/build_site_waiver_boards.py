#!/usr/bin/env python3
"""Publish versioned offline waiver boards (JEG-1419); no network or engine edits.

The commit timestamp is the default clock, matching sync's reproducible build
identity. --as-of explicitly selects a different capture cutoff for replays.
"""
from __future__ import annotations

import argparse
import hashlib
import gzip
import json
import shutil
import subprocess
from pathlib import Path

import build_weekly_inputs as weekly
import build_waiver_board as board
from lib import waiver_board as schema
from lib.timestamps import parse_iso_timestamp
import nfl_week

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = tuple((s, t, sf) for s in schema.SCORINGS for t in (8, 10, 12, 14) for sf in (0, 1))


def publish(root: Path, dist: Path, tag: str, as_of: str) -> dict:
    moment = parse_iso_timestamp(as_of)
    day = nfl_week.today_ny(moment)
    week = nfl_week.content_week(day)
    target = dist / 'data' / 'weekly'
    target.mkdir(parents=True, exist_ok=True)
    # Keep prior committed boards across clean builds as well as local reruns.
    source = root / 'data' / 'weekly'
    for old in sorted(list(source.glob('waiver-board-*.json')) + list(source.glob('waiver-boards-wk*.json'))):
        shutil.copy2(old, target / old.name)
    for archive in sorted(source.glob('waiver-boards-wk*.json.gz')):
        for name, text in json.loads(gzip.decompress(archive.read_bytes())).items():
            if Path(name).name != name or not name.endswith('.json'):
                raise ValueError('invalid archived board filename')
            (target / name).write_text(text, encoding='utf-8')
    inputs_path = target / f'inputs-wk{week}.json'
    args = ['--season', str(nfl_week.SEASON), '--week', str(week), '--as-of', as_of,
            '--players', str(root / 'data/inputs/players_identity_snapshot.json'),
            '--aliases', str(root / 'data/inputs/player_aliases.json'), '--out', str(inputs_path)]
    for flag, name in [('espn-weekly', f'espn_weekly_projections_{nfl_week.SEASON}.csv'),
                       ('byes', f'nfl_byes_{nfl_week.SEASON}.json'),
                       ('sleeper-base', 'sleeper_identity_base.json')]:
        path = root / 'data/inputs' / name
        if path.exists():
            args.extend(['--' + flag, str(path)])
    if weekly.main(args):
        raise RuntimeError('weekly-input producer failed')
    wbytes = inputs_path.read_bytes()
    wdoc = board.load_weekly(wbytes.decode('utf-8'))
    entries = []
    for scoring, teams, sf in SETTINGS:
        setting = dict(scoring=scoring, teams=teams, superflex=sf)
        values = board.values_from_reference(setting, day,
            root / 'app/trade-value-chart/assets/comparison-sources-data.json',
            root / 'data/fixtures/current/players.json', dist / 'assets/history')
        vbytes = board.dumps(values).encode('utf-8')
        doc = board.build_board(wdoc, values, setting, as_of, inputs={
            'weekly_inputs': {'name': inputs_path.name, 'sha256': hashlib.sha256(wbytes).hexdigest()},
            'values': {'name': 'value_reference', 'sha256': hashlib.sha256(vbytes).hexdigest()}})
        name = f'waiver-board-wk{week}-{scoring}-{teams}-sf{sf}.json'
        payload = board.dumps(doc).encode('utf-8')
        (target / name).write_bytes(payload)
        entries.append(dict(file=name, setting=setting, sha256=hashlib.sha256(payload).hexdigest()))
    manifest = dict(schema='site-waiver-boards', schema_version='1.0.0', build_tag=tag,
                    built_at=as_of, season=nfl_week.SEASON, board_week=week, boards=entries)
    (target / f'waiver-boards-wk{week}.json').write_text(board.dumps(manifest), encoding='utf-8')
    (target / 'waiver-boards.json').write_text(board.dumps(manifest), encoding='utf-8')
    # Compact, versioned source archive preserves the built board on clean builds.
    source.mkdir(parents=True, exist_ok=True)
    names = [e['file'] for e in entries] + [f'waiver-boards-wk{week}.json']
    archive = {name: (target / name).read_text(encoding='utf-8') for name in names}
    (source / f'waiver-boards-wk{week}.json.gz').write_bytes(
        gzip.compress(board.dumps(archive).encode('utf-8'), mtime=0))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of')
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist')
    args = parser.parse_args(argv)
    from sync_dashboard_artifacts import build_tag
    as_of = args.as_of or subprocess.check_output(
        ['git', '-C', str(ROOT), 'show', '-s', '--format=%cI', 'HEAD'], text=True).strip()
    publish(ROOT, args.dist, build_tag(), as_of)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
