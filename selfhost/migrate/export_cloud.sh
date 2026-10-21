#!/usr/bin/env bash
# Export the fantasy-tools data store from the cloud Supabase project to a
# pg_dump archive for the Mac mini (JEG-792, lane B).
#
# What it dumps (one custom-format archive, cloud.dump):
#   - Structure of every object in schemas public, api, monitoring, ops:
#     tables, the 12 api views and all other views, functions, triggers,
#     enum types, sequences (with their current values), RLS policies, grants.
#     Other-app and skip tables are created too, empty, because api/public
#     views and foreign keys reference them (see docs/selfhost-tables.md).
#   - Data only for tables classed 'chain' or 'dashboard-other' in
#     tables.json. value_check_values (~500 MB) keeps its empty structure.
#   - Schemas ross and archive are not dumped.
#
# Also writes, next to the dump:
#   inventory.txt     relations the cloud reports (checked against tables.json)
#   data_tables.txt   tables whose rows are in the dump
#   counts.tsv        exact row counts per data table, taken before and after
#                     the dump (the export fails if they differ)
#   roles.txt         roles named by grants/policies, for import_local.sh
#   pg_dump.version   the pg_dump version used
#
# Usage (on the Mac):
#   export DATABASE_URL='postgresql://postgres.<ref>:<password>@<host>:5432/postgres?sslmode=require'
#   selfhost/migrate/export_cloud.sh [OUT_DIR]
# Options (environment):
#   INCLUDE_OTHER_APP=1   also dump data of other-app tables (Jeremy's call;
#                         adds roughly 75 MB of egress)
#
# Egress: the data part is roughly 150-200 MB (table data without indexes).
# The project is over its egress quota; if the connection is refused or
# returns a quota error, see export_via_rest.py (and its warning).
#
# The script only reads: pg_dump and SELECT count(*). It never writes to the
# cloud. The connection string is read from the environment and never echoed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TABLES_JSON="$HERE/tables.json"
OUT_DIR="${1:-$HERE/out/$(date -u +%Y%m%dT%H%M%SZ)}"
INCLUDE_OTHER_APP="${INCLUDE_OTHER_APP:-0}"
SCHEMAS=(public api monitoring ops)

die() { echo "export_cloud: FAIL: $*" >&2; exit 1; }

[ -n "${DATABASE_URL:-}" ] || die "DATABASE_URL is not set (cloud Postgres connection string)"
command -v pg_dump >/dev/null || die "pg_dump not found (brew install postgresql@17)"
command -v psql >/dev/null || die "psql not found"
command -v python3 >/dev/null || die "python3 not found"
[ -f "$TABLES_JSON" ] || die "missing $TABLES_JSON"

mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
echo "export_cloud: writing to $OUT_DIR"

q() { psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "$1"; }

# 1. Versions. pg_dump must be at least the server's major version (cloud is 17).
server_major="$(q "select current_setting('server_version_num')::int / 10000")" \
  || die "could not connect with DATABASE_URL (refused? quota? see export_via_rest.py)"
dump_major="$(pg_dump --version | sed -E 's/.* ([0-9]+)(\.[0-9]+)?.*/\1/')"
pg_dump --version > "$OUT_DIR/pg_dump.version"
[ "$dump_major" -ge "$server_major" ] \
  || die "pg_dump $dump_major is older than server $server_major; install postgresql@$server_major client tools"
echo "export_cloud: server major $server_major, pg_dump $(cat "$OUT_DIR/pg_dump.version")"

# 2. Every relation must be classified before anything is dumped.
q "select table_schema||'.'||table_name from information_schema.tables
   where table_schema in ('public','api','monitoring','ops','ross','archive') order by 1" \
  > "$OUT_DIR/inventory.txt"
python3 "$HERE/check_classification.py" "$TABLES_JSON" "$OUT_DIR/inventory.txt" \
  || die "unclassified relations; nothing was dumped"

extra=()
[ "$INCLUDE_OTHER_APP" = "1" ] && extra=(--include-other-app)
python3 "$HERE/check_classification.py" "$TABLES_JSON" --print-data-tables ${extra[@]+"${extra[@]}"} \
  > "$OUT_DIR/data_tables.txt"
python3 "$HERE/check_classification.py" "$TABLES_JSON" --print-no-data-tables ${extra[@]+"${extra[@]}"} \
  > "$OUT_DIR/no_data_tables.txt"
grep -qx 'public.value_check_values' "$OUT_DIR/no_data_tables.txt" \
  || die "public.value_check_values must be in the no-data list"
echo "export_cloud: $(wc -l < "$OUT_DIR/data_tables.txt") tables with data," \
     "$(wc -l < "$OUT_DIR/no_data_tables.txt") structure only"

# 3. Roles named by grants, policies and default privileges (import creates
#    the missing ones as NOLOGIN; no passwords are exported).
q "select distinct r from (
     select grantee::text r from information_schema.role_table_grants
       where table_schema in ('public','api','monitoring','ops')
     union select grantee from information_schema.role_routine_grants
       where routine_schema in ('public','api','monitoring','ops')
     union select unnest(roles)::text from pg_policies
       where schemaname in ('public','api','monitoring','ops')
     union select pg_get_userbyid(defaclrole) from pg_default_acl d
       join pg_namespace n on n.oid = d.defaclnamespace
       where n.nspname in ('public','api','monitoring','ops')
     union select pg_get_userbyid(nspowner) from pg_namespace
       where nspname in ('public','api','monitoring','ops')
   ) x where r not in ('PUBLIC','public') order by 1" > "$OUT_DIR/roles.txt"

# 4. Exact row counts (one statement, a few hundred bytes of egress).
count_sql() {
  local sql="" t
  while read -r t; do
    [ -n "$t" ] || continue
    local s="${t%%.*}" n="${t#*.}"
    sql+="${sql:+ union all }select '$t', count(*) from \"$s\".\"$n\""
  done < "$OUT_DIR/data_tables.txt"
  printf '%s order by 1' "$sql"
}
q "$(count_sql)" | tr '|' '\t' > "$OUT_DIR/counts.before.tsv"

# 5. The dump.
args=(--format=custom --compress=6 --verbose)
for s in "${SCHEMAS[@]}"; do args+=(--schema="$s"); done
while read -r t; do
  [ -n "$t" ] || continue
  s="${t%%.*}"; n="${t#*.}"
  args+=(--exclude-table-data="\"$s\".\"$n\"")
done < "$OUT_DIR/no_data_tables.txt"

echo "export_cloud: running pg_dump (this is the egress-heavy step)"
pg_dump "${args[@]}" --file="$OUT_DIR/cloud.dump" "$DATABASE_URL" 2> "$OUT_DIR/pg_dump.log" \
  || { tail -20 "$OUT_DIR/pg_dump.log" >&2; die "pg_dump failed (log: $OUT_DIR/pg_dump.log)"; }

# 6. Counts again. A writer that ran during the dump (a pg_cron-dispatched
#    workflow) makes the dump and counts disagree, so fail rather than guess.
q "$(count_sql)" | tr '|' '\t' > "$OUT_DIR/counts.after.tsv"
if ! cmp -s "$OUT_DIR/counts.before.tsv" "$OUT_DIR/counts.after.tsv"; then
  diff "$OUT_DIR/counts.before.tsv" "$OUT_DIR/counts.after.tsv" >&2 || true
  die "row counts changed while dumping (a scheduled writer ran). Re-run in a quiet window."
fi
cp "$OUT_DIR/counts.after.tsv" "$OUT_DIR/counts.tsv"

# 7. Sanity: the archive must list data for every data table and none for value_check_values.
pg_restore --list "$OUT_DIR/cloud.dump" > "$OUT_DIR/toc.list"
missing=0
while read -r t; do
  s="${t%%.*}"; n="${t#*.}"
  grep -Eq "TABLE DATA ${s} ${n} " "$OUT_DIR/toc.list" || { echo "  no TABLE DATA for $t" >&2; missing=1; }
done < "$OUT_DIR/data_tables.txt"
[ "$missing" = 0 ] || die "dump is missing table data (see above)"
if grep -Eq "TABLE DATA public value_check_values " "$OUT_DIR/toc.list"; then
  die "value_check_values data is in the dump; it must not be"
fi
grep -Eq "TABLE public value_check_values " "$OUT_DIR/toc.list" \
  || die "value_check_values structure is missing from the dump"
api_views="$(grep -Ec ' VIEW api ' "$OUT_DIR/toc.list" || true)"
echo "export_cloud: api views in dump: $api_views (expected 12)"
[ "$api_views" -ge 12 ] || die "expected the 12 api views in the dump"

ls -l "$OUT_DIR/cloud.dump"
echo "export_cloud: OK. Next: selfhost/migrate/import_local.sh $OUT_DIR"
