"""Read-only cloud inventory check. Exit 0=match, 1=drift, 2=unavailable.

Never print database exceptions: they can contain connection details.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import hashlib

ROOT = Path(__file__).resolve().parents[1]
TITLE = '[cron-migration-drift:JEG-1457] Cloud inventory differs from main'
# Shared patterns drive both the safe SQL projection and fixture extraction tests.
WORKFLOW_PATTERN = r"(?i)dispatch_gha_workflow\s*\(\s*'([A-Za-z0-9_.-]+)'"
FUNCTION_PATTERN = r"(?i)select\s+([A-Za-z_]+\.[A-Za-z_]+)\s*\("


def extract_target(command):
    for kind, pattern in [('workflow', WORKFLOW_PATTERN), ('function', FUNCTION_PATTERN)]:
        match = re.search(pattern, command)
        if match:
            return kind + ':' + match[1]
    return 'raw:' + hashlib.md5(command.encode()).hexdigest()


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


TARGET_SQL = ("coalesce('workflow:' || substring(command from " + sql_literal(WORKFLOW_PATTERN)
              + "), 'function:' || substring(command from " + sql_literal(FUNCTION_PATTERN)
              + "), 'raw:' || md5(command))")
# Raw commands stay in PostgreSQL; only safe identifiers or hashes leave it.
QUERY = """SELECT json_build_object(
 'cron', (SELECT coalesce(json_agg(json_build_object(
   'name', jobname, 'schedule', schedule, 'active', active,
   'target', """ + TARGET_SQL + """
 )), '[]'::json) FROM cron.job),
 'migrations', (SELECT coalesce(json_agg(json_build_object('version', version, 'name', name)), '[]'::json)
 FROM supabase_migrations.schema_migrations))"""


def normalize_migration(name):
    name = re.sub(r'^\d{14}_', '', name)
    # Legacy date_name and name_date represent the same MCP migration name.
    match = re.fullmatch(r'(\d{8})_(.+)', name)
    return match[2] + '_' + match[1] if match else name


def migration_rules():
    rules = json.loads((ROOT/'config/migration-drift-map.json').read_text())
    for entries in rules.values():
        for entry in entries.values():
            if not entry.get('reason'):
                raise ValueError('Migration mapping requires a reason')
    return rules


def canonical_migration(name, rules):
    name = normalize_migration(name)
    if name in rules['ignore']:
        return None
    return rules['aliases'].get(name, {}).get('canonical', name)


def migration_names(folder):
    return {normalize_migration(p.stem) for p in folder.glob('*.sql')}


def keyed(rows):
    result = {}
    for row in rows:
        if not row.get('name') or row['name'] in result:
            raise ValueError('Missing or duplicate inventory name')
        result[row['name']] = row
    return result


def compare(expected, repo_migrations, live, rules=None):
    rules = rules if rules is not None else migration_rules()
    if (not live["migrations"] or not live["cron"]
            or len(live["cron"]) * 2 < len(expected)
            or len(live["migrations"]) * 2 < len(repo_migrations)):
        raise ValueError("Incomplete cloud inventory")
    repo_migrations = {canonical_migration(n, rules) for n in repo_migrations} - {None}
    actual = keyed(live['cron'])
    expected = keyed(expected)
    applied = set()
    for row in live['migrations']:
        # Prefer recorded name; version identifies timestamp-only migrations.
        name = row.get('name') or row.get('version')
        if not name:
            raise ValueError('Missing migration identity')
        applied.add(canonical_migration(name, rules))
    applied.discard(None)
    changes = []
    for name in sorted(expected.keys() & actual.keys()):
        for field in ('schedule', 'target', 'active'):
            if actual[name].get(field) is None:
                raise ValueError('Unreadable command target or inventory field')
            want, got = expected[name][field], actual[name][field]
            if field == 'schedule':
                want, got = ' '.join(want.split()), ' '.join(got.split())
            if want != got:
                changes.append({'name': name, 'field': field, 'repo': want, 'live': got})
    return {'cron_in_supabase_not_repo': sorted(actual.keys() - expected.keys()),
            'cron_in_repo_not_supabase': sorted(expected.keys() - actual.keys()),
            'changed_schedules_targets_or_active': changes,
            'migrations_in_supabase_not_repo': sorted(applied - repo_migrations),
            'migrations_in_repo_not_applied': sorted(repo_migrations - applied)}


def read_live():
    if not os.environ.get('SUPABASE_DRIFT_READONLY_DSN'):
        raise RuntimeError('read-only access not configured')
    import psycopg
    # Connection startup enforces a read-only transaction; query is SELECT only.
    with psycopg.connect(os.environ['SUPABASE_DRIFT_READONLY_DSN'],
                         options='-c default_transaction_read_only=on -c statement_timeout=30000',
                         connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(QUERY)
            return cur.fetchone()[0]


def ticket(report, graphql=None):
    if graphql is None:
        from pipelines.open_divergence_issues import _graphql
        token = os.environ['LINEAR_API_KEY']
        graphql = lambda q, v: _graphql(token, q, v)
    parent = graphql('''query($id:String!){issue(id:$id){id team{id}
      children(first:250,includeArchived:true){nodes{id title description archivedAt url state{type}} pageInfo{hasNextPage}}}}''',
                     {'id': 'JEG-1457'})['issue']
    children = parent['children']
    if children['pageInfo']['hasNextPage']:
        raise RuntimeError('Incomplete Linear inventory')
    matches = [n for n in children['nodes'] if n['title'] == TITLE]
    active = [n for n in matches if not n.get('archivedAt') and
              n['state']['type'] not in ('completed', 'canceled')]
    if len(active) > 1:
        raise RuntimeError('Multiple active drift tickets require reconciliation')
    # Stable, canonical content means an unchanged diff makes no mutation.
    description = '<!-- cron-migration-drift:JEG-1457 -->\nLatest read-only diff\n```json\n' + json.dumps(report, indent=2, sort_keys=True) + '\n```'
    closed = [n for n in matches if n not in active]
    if closed:
        description += '\n\nPrevious drift tickets: ' + ', '.join(sorted(n['url'] for n in closed))
    if active:
        previous = re.search(r'```json\n(.*?)\n```', active[0].get('description') or '', re.S)
        if previous:
            try:
                if json.loads(previous[1]) == report:
                    return
            except (ValueError, TypeError):
                pass  # malformed prior report needs replacement
        response = graphql('''mutation($id:String!,$i:IssueUpdateInput!){issueUpdate(id:$id,input:$i){success}}''',
                           {'id': active[0]['id'], 'i': {'description': description}})
        ok = response['issueUpdate']['success']
    else:
        response = graphql('''mutation($i:IssueCreateInput!){issueCreate(input:$i){success}}''',
                           {'i': {'title': TITLE, 'description': description,
                                  'teamId': parent['team']['id'], 'parentId': parent['id']}})
        ok = response['issueCreate']['success']
    if not ok:
        raise RuntimeError('Linear mutation failed')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notify', action='store_true', help='Create/update one Linear child on drift')
    args = parser.parse_args(argv)
    try:
        report = compare(json.loads((ROOT/'config/expected-cron.json').read_text()),
                         migration_names(ROOT/'supabase/migrations'), read_live())
        print(json.dumps(report, indent=2))
        drift = any(report.values())
        if drift and args.notify:
            ticket(report)
        return int(drift)
    except Exception:
        print('Could not compare or notify (exit 2). Verify read-only access, inventory permissions and Linear configuration; no database error details logged.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    sys.exit(main())
