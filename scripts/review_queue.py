#!/usr/bin/env python3
"""Read-only review queue from complete Linear export and gh pr list JSON.

No credentials, network calls, model calls, or board writes. See AGENTS.md.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

FAMILIES = ('engine/value math', 'pipelines', 'front end', 'connector/get-values', 'docs and rules', 'bridge')
TIERS = {'review-light', 'review-standard', 'review-high-risk'}
OWNER = 'Claude (Duet coordinator)'


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamps must include timezone')
    return result


def issues_from_export(data):
    if not isinstance(data, dict) or data.get('hasNextPage') is not False:
        raise ValueError('export must contain issues and hasNextPage: false after all pages are combined')
    return data['issues']


def note(text, field):
    # Exact field lines avoid treating incidental tier mentions as routing.
    values = re.findall(r'^\s*(?:[-*]\s*)?(?:\*\*)?' + field + r':(?:\*\*)?\s*([^\n]+)', text, re.I | re.M)
    return values[0].strip().strip('`') if len(values) == 1 else ''


def rows(issues, prs, now):
    by_id = {i['id']: i for i in issues}
    pairs = []
    linked = set()
    for pr in prs:
        if pr.get('isDraft'):
            continue
        # Title/branch identify the work; body may also mention dependencies.
        ids = set(re.findall(r'\bJEG-\d+\b', pr.get('title', '') + ' ' + pr.get('headRefName', ''), re.I))
        if not ids:
            ids = set(re.findall(r'\bJEG-\d+\b', pr.get('body', ''), re.I))
        for key in sorted(ids):
            key = key.upper()
            pairs.append((by_id.get(key, {'id': key}), pr))
            linked.add(key)
        if not ids:
            pairs.append(({}, pr))
    for issue in issues:
        if issue.get('status') == 'In Review' and issue['id'] not in linked:
            pairs.append((issue, {}))
    result = []
    for issue, pr in pairs:
        flags = []
        desc = issue.get('description') or ''
        family = note(desc, 'Review family')
        tier = note(desc, 'Review tier')
        labels = issue.get('labels', [])
        tiers = {x if isinstance(x, str) else x['name'] for x in labels} & TIERS
        if issue.get('id') not in by_id:
            flags.append('missing Linear ticket')
        if family not in FAMILIES:
            flags.append('missing/unknown family')
        if tier not in TIERS:
            flags.append('missing/ambiguous routing tier')
        if len(tiers) != 1:
            flags.append('missing/multiple tier labels')
        elif tier in TIERS and tiers != {tier}:
            flags.append('tier mismatch')
        if pr and issue.get('status') != 'In Review':
            flags.append('PR ready but Linear not In Review')
        if '…' in desc or '(truncated' in desc:
            flags.append('truncated description: fetch full issue')
        created = pr.get('createdAt') or issue.get('createdAt')
        age = str(max(0, (now - timestamp(created)).days)) + 'd (created)' if created else 'unknown'
        result.append(dict(ticket=issue.get('id', 'unknown'), pr='#' + str(pr['number']) if pr else '-',
                           owner=OWNER, family=family or 'unknown', age=age,
                           label=','.join(sorted(tiers)) or 'unknown', routing=tier or 'unknown', flags=flags))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--issues', type=Path, required=True)
    parser.add_argument('--prs', type=Path, required=True)
    parser.add_argument('--now', help='ISO timestamp for replay (default UTC now)')
    args = parser.parse_args()
    try:
        issues = issues_from_export(json.loads(args.issues.read_text()))
        prs = json.loads(args.prs.read_text())
        now = timestamp(args.now) if args.now else datetime.now(timezone.utc)
        report = rows(issues, prs, now)
    except (ValueError, KeyError, TypeError, OSError):
        parser.exit(2, 'Invalid/incomplete input; see AGENTS.md export contract.\n')
    print('Review queue as of ' + now.isoformat() + ' (age since creation, not time in review)')
    print('ticket | PR | owner | family | age | label | routing | flags')
    for row in report:
        values = [row[k] for k in ('ticket', 'pr', 'owner', 'family', 'age', 'label', 'routing')]
        print(' | '.join(values + [', '.join(row['flags']) or 'OK']))
    print(f'{len(report)} rows; {sum(bool(r["flags"]) for r in report)} flagged. Read-only; no approval implied.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
