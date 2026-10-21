#!/usr/bin/env bash
# Restore a backup made by backup.sh (JEG-792).
#
#   ./restore.sh ~/ddf-supabase-backups/ddf-2026-10-21T0315Z.dump
#
# Restores into the running `db` service. Meant for a FRESH database (the
# runbook's restore steps recreate the volume first); on a database that
# already holds the app schemas it stops unless you pass --clean, which drops
# and recreates the objects in the dump. Replays the matching .cron.sql if it
# is next to the dump, then asks PostgREST to reload its schema cache.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

clean=""
if [ "${1:-}" = "--clean" ]; then clean=1; shift; fi
dump="${1:?usage: restore.sh [--clean] <file.dump>}"
[ -f "$dump" ] || { echo "restore: $dump not found" >&2; exit 1; }
cron="${dump%.dump}.cron.sql"

dc() { docker compose --env-file .env "$@"; }
psql_admin() { dc exec -T db psql -h localhost -U supabase_admin -d postgres -v ON_ERROR_STOP=1 "$@"; }

existing="$(psql_admin -At -c "select count(*) from pg_tables where schemaname = 'public'")"
if [ "$existing" != 0 ] && [ -z "$clean" ]; then
  echo "restore: public already has $existing tables. Restore into a fresh volume" >&2
  echo "         (docs/selfhost-supabase.md, Restore) or re-run with --clean." >&2
  exit 1
fi

echo "restore: pg_restore $dump"
args=(-h localhost -U supabase_admin -d postgres --no-password)
[ -n "$clean" ] && args+=(--clean --if-exists)
# Not --exit-on-error: "schema already exists" for public/api is expected.
# Every other error is printed; read them.
dc exec -T db pg_restore "${args[@]}" < "$dump" || echo "restore: pg_restore reported errors (see above)" >&2

if [ -f "$cron" ]; then
  echo "restore: replaying $(grep -c 'cron.schedule' "$cron") cron jobs from $cron"
  psql_admin -c "select cron.unschedule(jobid) from cron.job" > /dev/null
  psql_admin -q < "$cron" > /dev/null
fi

psql_admin -c "notify pgrst, 'reload schema'" > /dev/null
echo "restore: done. Re-enter Vault secrets (github_dispatch_token), then run ./healthcheck.sh"
