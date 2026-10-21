#!/usr/bin/env bash
# Load the cloud export (export_cloud.sh) into the local self-hosted Postgres
# on the Mac mini, then verify row counts (JEG-792, lane B).
#
# Usage:
#   export LOCAL_DATABASE_URL='postgresql://postgres:<password>@127.0.0.1:5432/postgres'
#   selfhost/migrate/import_local.sh selfhost/migrate/out/<stamp>
#
# Steps:
#   1. Refuse a cloud URL (this script writes) and a non-empty target.
#   2. Create schema extensions + pgcrypto, uuid-ossp; pg_net and pg_cron
#      when the local image ships them (warn loudly when not).
#   3. Create the roles the grants and RLS policies name, as NOLOGIN
#      (service_role gets BYPASSRLS, as on Supabase). No passwords.
#   4. pg_restore --no-owner in one transaction, exit on first error.
#      Without pg_net, monitoring.v_dispatch_outcomes is left out (it is a
#      view over net._http_response) and the script says so.
#   5. ANALYZE, tell PostgREST to reload its schema cache.
#   6. verify_counts.py: exact counts per table against counts.tsv; any
#      mismatch fails the import.
# Then run cron_and_functions.sql by hand (it needs the GitHub token step).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP_DIR="${1:-}"
die() { echo "import_local: FAIL: $*" >&2; exit 1; }

[ -n "$DUMP_DIR" ] || die "usage: import_local.sh <export dir from export_cloud.sh>"
[ -f "$DUMP_DIR/cloud.dump" ] || die "no cloud.dump in $DUMP_DIR"
[ -f "$DUMP_DIR/counts.tsv" ] || die "no counts.tsv in $DUMP_DIR (export did not finish)"
[ -n "${LOCAL_DATABASE_URL:-}" ] || die "LOCAL_DATABASE_URL is not set"
case "$LOCAL_DATABASE_URL" in
  *supabase.co*|*supabase.com*|*iskiybsimubiujwuchsl*)
    die "LOCAL_DATABASE_URL points at Supabase cloud; this script writes and must only target the Mac" ;;
esac
command -v pg_restore >/dev/null || die "pg_restore not found"
command -v psql >/dev/null || die "psql not found"

q() { psql "$LOCAL_DATABASE_URL" -X -v ON_ERROR_STOP=1 -At -c "$1"; }

# 1. Versions and an empty target.
local_major="$(q "select current_setting('server_version_num')::int / 10000")" \
  || die "cannot connect to LOCAL_DATABASE_URL"
restore_major="$(pg_restore --version | sed -E 's/.* ([0-9]+)(\.[0-9]+)?.*/\1/')"
dump_major="$(pg_restore --list "$DUMP_DIR/cloud.dump" | sed -nE 's/^;[[:space:]]+Dumped by pg_dump version: ([0-9]+).*/\1/p' | head -1)"
[ -n "$dump_major" ] || die "cannot read the pg_dump version from the archive header"
[ "$restore_major" -ge "$dump_major" ] \
  || die "pg_restore $restore_major cannot read a pg_dump $dump_major archive; use postgresql@$dump_major client tools"
[ "$local_major" -ge "$dump_major" ] \
  || echo "import_local: WARNING: local server is $local_major, the dump came from pg_dump $dump_major; restore may fail on newer syntax" >&2
existing="$(q "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
               where n.nspname in ('public','api','monitoring','ops') and c.relkind in ('r','v','p')")"
[ "$existing" = "0" ] || die "target already has $existing tables/views in public/api/monitoring/ops; restore into an empty database"

# 2. Extensions.
avail() { q "select count(*) from pg_available_extensions where name = '$1'"; }
q "create schema if not exists extensions"
q 'create extension if not exists pgcrypto with schema extensions'
q 'create extension if not exists "uuid-ossp" with schema extensions'
have_net=0; have_cron=0
if [ "$(avail pg_net)" = "1" ]; then q 'create extension if not exists pg_net'; have_net=1; fi
if [ "$(avail pg_cron)" = "1" ]; then
  q 'create extension if not exists pg_cron' && have_cron=1 \
    || echo "import_local: WARNING: pg_cron is available but needs shared_preload_libraries=pg_cron and cron.database_name" >&2
fi
[ "$have_net" = 1 ] || cat >&2 <<'EOF'
import_local: WARNING ************************************************************
  pg_net is not installed locally. public.dispatch_gha_workflow (all 20 pg_cron
  jobs) calls net.http_post and will fail at run time; monitoring.v_dispatch_outcomes
  is left out of this restore. Either add pg_net to the local image (lane A) or
  dispatch the workflows another way (see cron_and_functions.sql).
**********************************************************************************
EOF
[ "$have_cron" = 1 ] || echo "import_local: WARNING: pg_cron not installed; cron_and_functions.sql cannot schedule the jobs until it is." >&2

# 3. Roles.
if [ -f "$DUMP_DIR/roles.txt" ]; then
  while read -r r; do
    [ -n "$r" ] || continue
    case "$r" in pg_*) continue ;; esac
    exists="$(q "select count(*) from pg_roles where rolname = '$r'")"
    if [ "$exists" = "0" ]; then
      attrs="NOLOGIN NOINHERIT"
      [ "$r" = "service_role" ] && attrs="NOLOGIN NOINHERIT BYPASSRLS"
      q "create role \"$r\" $attrs"
      echo "import_local: created role $r ($attrs)"
    fi
  done < "$DUMP_DIR/roles.txt"
fi
if [ "$(q "select count(*) from pg_roles where rolname='service_role' and not rolbypassrls")" = "1" ]; then
  echo "import_local: WARNING: role service_role exists without BYPASSRLS; RLS policies will block service-key reads/writes through PostgREST" >&2
fi

# 4. Restore.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pg_restore --list "$DUMP_DIR/cloud.dump" > "$work/toc.list"
# The image already creates `public`, so the dump's CREATE SCHEMA public would
# abort the restore; its ACL and COMMENT entries stay in. The stack's init SQL
# also creates an empty `api` schema (a USAGE grant only): drop that one so the
# dump can create it (the existing-tables check above guarantees it is empty).
sed -E -i.bak '/ SCHEMA - public /s/^/;/' "$work/toc.list"
q "drop schema if exists api restrict" >/dev/null
if [ "$have_net" = 0 ]; then
  # Comment out the one view that depends on pg_net, plus its ACL and comment
  # entries (TOC lines: "VIEW monitoring v_dispatch_outcomes", "ACL monitoring
  # TABLE v_dispatch_outcomes", "COMMENT monitoring VIEW v_dispatch_outcomes").
  sed -E -i.bak '/ (VIEW|ACL|COMMENT) monitoring ((TABLE|VIEW) )?v_dispatch_outcomes /s/^/;/' "$work/toc.list"
  grep -q '^;.*v_dispatch_outcomes' "$work/toc.list" \
    && echo "import_local: left out monitoring.v_dispatch_outcomes (needs pg_net)" >&2
fi
echo "import_local: restoring (single transaction)"
pg_restore --no-owner --exit-on-error --single-transaction \
  --use-list="$work/toc.list" --dbname="$LOCAL_DATABASE_URL" "$DUMP_DIR/cloud.dump" \
  || die "pg_restore failed; nothing was committed"

# 5. Planner stats and the PostgREST schema cache.
q "analyze"
q "notify pgrst, 'reload schema'" || true

# 6. Counts.
python3 "$HERE/verify_counts.py" --counts "$DUMP_DIR/counts.tsv" \
  --tables-json "$HERE/tables.json" --database-url-env LOCAL_DATABASE_URL \
  || die "row counts do not match the cloud export"

echo "import_local: OK. Next: store the GitHub token and run cron_and_functions.sql (see its header)."
