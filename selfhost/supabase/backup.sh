#!/usr/bin/env bash
# Nightly backup of the self-hosted data store (JEG-792).
#
#   ./backup.sh            dump now; delete dumps older than BACKUP_KEEP_DAYS
#
# Writes, per run, into BACKUP_DIR (default ~/ddf-supabase-backups):
#   ddf-<UTC stamp>.dump      pg_dump custom format of the app schemas
#   ddf-<UTC stamp>.cron.sql  the pg_cron jobs, as cron.schedule() calls
# Supabase-managed schemas (auth, storage, vault, cron internals...) come
# from the image and are not dumped. Vault secret VALUES are not backed up:
# re-enter them after a restore (docs/selfhost-supabase.md, "Restore").
# A dump is only kept if `pg_restore --list` can read it back.
set -euo pipefail

# launchd starts with a bare PATH; find docker from OrbStack or Docker Desktop.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
[ -f .env ] || { echo "backup: $HERE/.env not found" >&2; exit 1; }

env_get() { awk -v k="$1" 'index($0, k "=") == 1 { print substr($0, length(k) + 2); exit }' .env; }

BACKUP_DIR="$(env_get BACKUP_DIR)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/ddf-supabase-backups}"
KEEP_DAYS="$(env_get BACKUP_KEEP_DAYS)"
KEEP_DAYS="${KEEP_DAYS:-14}"
SCHEMAS="${BACKUP_SCHEMAS:-public api ops monitoring archive ross}"

case "$KEEP_DAYS" in ''|*[!0-9]*) echo "backup: BACKUP_KEEP_DAYS must be a number" >&2; exit 1;; esac

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
umask 077

stamp="$(date -u +%Y-%m-%dT%H%MZ)"
dump="$BACKUP_DIR/ddf-$stamp.dump"
cron="$BACKUP_DIR/ddf-$stamp.cron.sql"

dc() { docker compose --env-file .env "$@"; }

schema_args=()
for s in $SCHEMAS; do schema_args+=(-n "$s"); done

echo "backup: dumping schemas [$SCHEMAS] to $dump"
dc exec -T db pg_dump -h localhost -U supabase_admin -d postgres -Fc "${schema_args[@]}" > "$dump.partial"

# Integrity check: the archive's table of contents must be readable.
if ! dc exec -T db pg_restore --list < "$dump.partial" > /dev/null; then
  echo "backup: pg_restore --list could not read the dump; keeping nothing" >&2
  rm -f "$dump.partial"
  exit 1
fi
mv "$dump.partial" "$dump"

dc exec -T db psql -h localhost -U supabase_admin -d postgres -At -v ON_ERROR_STOP=1 -c "
  select format('select cron.schedule(%L, %L, %L);', coalesce(jobname, 'job_' || jobid), schedule, command)
         || case when active then '' else format(
              E'\nselect cron.alter_job((select jobid from cron.job where jobname = %L), active := false);',
              coalesce(jobname, 'job_' || jobid)) end
  from cron.job order by jobid" > "$cron.partial"
mv "$cron.partial" "$cron"

echo "backup: ok $(du -h "$dump" | cut -f1) $(grep -c 'cron.schedule' "$cron") cron jobs"

# Rotation: drop anything older than KEEP_DAYS days.
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'ddf-*' -mtime +"$KEEP_DAYS" -print -delete
