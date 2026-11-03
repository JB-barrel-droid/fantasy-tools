#!/usr/bin/env python3
"""JEG-1472: build the scoped release-window pause control, validated first.

Used by `.github/workflows/main-write-pause-switch.yml`. It writes only
`.github/main-write-pause.json` (never a path the caller names). The new control
is checked with the guard's own `decision` before a byte is written, because an
invalid control fails closed and holds every writer with no end time.

`on` pauses only the frequent writers for 1..120 minutes (default 90);
`off` writes the default unpaused control.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from main_write_guard import CONTROL, FREQUENT_WRITERS, MAX_SCOPED_PAUSE, decision

DEFAULT_MINUTES = 90
MAX_MINUTES = int(MAX_SCOPED_PAUSE.total_seconds() // 60)
MAX_REASON = 200
ROOT = Path(__file__).resolve().parent.parent
OFF = {'paused': False, 'started_at': None, 'expires_at': None, 'reason': ''}


def stamp(moment):
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def build(action, minutes, reason, now, scope=FREQUENT_WRITERS):
    """Return the validated control dict, or raise ValueError (nothing written)."""
    if action not in ('on', 'off'):
        raise ValueError('action must be on or off')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('reason is required')
    if len(reason.strip()) > MAX_REASON or any(ord(ch) < 32 or ord(ch) == 127 for ch in reason):
        raise ValueError(f'reason must be one line of at most {MAX_REASON} characters')
    if action == 'off':
        doc = dict(OFF)
        decision(json.dumps(doc), now)
        return doc
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise ValueError('minutes must be a whole number')
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f'minutes must be between 1 and {MAX_MINUTES}')
    start = now.astimezone(timezone.utc).replace(microsecond=0)
    doc = {'paused': True, 'started_at': stamp(start),
           'expires_at': stamp(start + timedelta(minutes=minutes)),
           'reason': reason.strip(), 'scope': sorted(scope)}
    # The guard's own validator, at the moment of writing. It must read this
    # control as an active pause, not as unpaused or invalid.
    if not decision(json.dumps(doc), start)[0]:
        raise ValueError('control does not read as an active pause')
    return doc


def write_control(doc, root=ROOT):
    path = Path(root) / CONTROL
    path.write_text(json.dumps(doc, indent=2) + '\n')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', required=True, choices=['on', 'off'])
    parser.add_argument('--minutes', default=str(DEFAULT_MINUTES))
    parser.add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    try:
        minutes = int(args.minutes)
    except ValueError:
        print('::error title=Main write pause switch::minutes must be a whole number; nothing written')
        return 2
    try:
        doc = build(args.action, minutes, args.reason, datetime.now(timezone.utc))
    except ValueError as exc:
        print(f'::error title=Main write pause switch::{exc}; nothing written')
        return 2
    write_control(doc)
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
