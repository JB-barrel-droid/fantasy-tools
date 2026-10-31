# Cron and migration drift (JEG-1457)

The daily/manual workflow is checked in **disabled** (`if: ${{ false }}`).
JEG-1049 uses public edge endpoints and has no database role or database secret
to reuse. The local attempt on 2026-10-31 exited 2: read-only access was not
configured. Today's cloud diff is **unavailable**, not empty or in sync.
No SQL was sent and no real mismatch could be confirmed or ticketed.

## Jeremy's enablement step

1. Provision a dedicated login restricted to SELECT on `cron.job` and
   `supabase_migrations.schema_migrations`, with schema USAGE and connection
   permission, no write privileges or inherited privileged role, and
   `default_transaction_read_only=on`. Verify it sees **all** cron jobs:
   pg_cron's row security can otherwise hide jobs owned by other users. Have
   the database owner authorize a SELECT-only policy for this role if needed;
   do not give it the postgres role. Verify the two inventories against the
   owner's counts before enabling. These are Jeremy's database administration
   steps; this PR applies no grants, policies, migrations or cron changes.
2. Store its TLS connection configuration as the GitHub Actions secret
   `SUPABASE_DRIFT_READONLY_DSN` (require TLS verification), outside the repo.
   Supply the existing `LINEAR_API_KEY` secret with child-issue create/update
   access to JEG-1457. Never paste either secret into a command, PR or log.
3. Run `python tools/cron_migration_drift.py` with the read-only connection
   injected securely. Inspect the diff, then run with `--notify` to create or
   update one child ticket. Exit 0 means match, 1 confirmed drift, 2 means
   incomplete comparison or notification failure. No retries are automatic.
4. After verifying visibility and the expected baseline, remove the job's
   `if: ${{ false }}` in a reviewed PR. Workflow concurrency serializes ticket
   creation; avoid simultaneous manual local notification runs.

## Baseline and identity

`config/expected-cron.json` records repo intent, not an observed cloud snapshot.
Its 23 entries come from the cited migration files; retired producer and
monitoring jobs are excluded. `health-artifacts-live` uses the later
`20261008_monitoring_6h_and_posture.sql` override. Update this file alongside
future schedule changes. Targets identify workflow filenames or SQL function
names; dispatch payload changes are outside this check. Active state is checked.
Unrecognized commands use a `raw:` MD5 fingerprint, including the retention
DELETE job. This is a change detector, not a security checksum; raw commands
are never returned from the query or logged. Whitespace changes to raw commands
are reported. An empty migration inventory or fewer than half the expected cron
jobs (currently fewer than 12) exits 2 before notifying Linear. This floor is a
visibility guard, not a substitute for the owner-count verification above.

Applied migrations match by recorded name (or version when name is absent).
Timestamp-prefixed CLI filenames strip their 14-digit version. Legacy
`20261008_name` and `name_20261008` normalize to the latter, on both sides.
`config/migration-drift-map.json` holds explicit `aliases` (canonical name plus
reason) and `ignore` entries (reason). Both are initially empty: no additional
historical identity exception has been verified, and inventing exceptions would
hide real drift. Add only verified exceptions using normalized names, with a
reason per entry. Unknown names still appear in the diff. This checks inventory,
not SQL content/checksums, and never executes migration files.

The notifier follows `pipelines/open_divergence_issues.py`'s Linear transport.
A stable child title/key creates once and updates an active ticket only when
the parsed diff changes. A recurrence after completion, cancellation or archival
creates a new ticket linking prior tickets; it never rewrites a closed ticket.
It does not auto-close tickets.
No ticket is created for unavailable evidence. Authentication errors are
reported without exception details to avoid exposing connection configuration.

Verification: `python -m unittest tests.test_cron_migration_drift`.
F1 is not applicable: this changes an operational checker, no product workflow.

Baseline review: the four additional jobs are retained/altered by
`source_probe_schedules_20261008.sql`, `monitoring_coverage_20261007.sql`,
`20261008_monitoring_6h_and_posture.sql`, `producers_schedule_tidy_20261008.sql`
and `20261008_live_page_synthetic_schedule.sql`. The exact vintage-check slot
is corroborated by `docs/architecture-current.md`; the retention command and
03:00 slot by `docs/audits/jeg285-phase2/02-pgcron-job-specs.md`.
