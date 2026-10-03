# JEG-285 Phase 2 — pg_cron Retention Policy

**Lane:** minimax (M3)
**Branch:** `minimax/jeg-285-retention-policy`
**Tracker item:** #9 in `01-migration-tracker.md`
**Status:** reviewed, ready for Jeremy's approval. This is a docs-only deliverable; nothing in this doc has been executed against a database.

## TL;DR

`cron.job_run_details` is the pg_cron execution log. pg_cron does **not**
auto-prune it; left alone, it grows unbounded and eventually blocks
`SELECT`s on the table. The draft in `02-pgcron-job-specs.md:18-23` is
correct in shape and idempotent; the **window is the only thing worth
rethinking**. At our cadence, 30 days writes ~1,080 rows (~1 MB) — 90
days is also cheap, and gives more debugging headroom for incident
post-mortems that surface weeks later. Recommendation: **keep 30 days
as drafted**, but make the schedule `0 3 * * *` UTC and add a parallel
**monitoring query** that surfaces the table growing past the window.

## Final SQL (paste-ready for the Supabase SQL editor)

```sql
-- Retention: cron.job_run_details is NEVER auto-cleaned by pg_cron.
-- Run daily, off-peak UTC, before any of the 7 shadow/cutover jobs go live.
select cron.schedule(
  'cron-retention-30d',
  '0 3 * * *',                                -- 03:00 UTC daily
  $$delete from cron.job_run_details
    where start_time < now() - interval '30 days'$$
);
```

Drop (idempotent re-run during hardening):

```sql
select cron.unschedule('cron-retention-30d');
```

The retention job itself appears in `cron.job_run_details` like every
other pg_cron job — its own row will be cleaned by the next day's run.
No interaction with `pipeline_cron_log` or any other pipeline table.

## Verification against pg_cron schema

### Table and columns — VERIFIED (upstream) / UNVERIFIED (live)

`cron.job_run_details` is the table pg_cron creates for execution
history. The column contract used by the filter is:

| Column             | Type         | Used by filter? | Notes                                                  |
|-------------------|--------------|-----------------|--------------------------------------------------------|
| `start_time`      | `timestamptz`| yes             | `DEFAULT now()` at job start. Index exists upstream.   |
| `end_time`        | `timestamptz`| no              | NULL while the job is in flight.          |
| `status`          | `text`       | no              | `succeeded` / `failed` / `running` / `starting`.       |
| `jobid`           | `bigint`     | no              | FK to `cron.job.jobid`.            |
| `runid`           | `bigint`     | no              | Unique-per-execution id.            |
| `return_message`  | `text`       | no              | Output of the cron body; truncated upstream.          |

- **VERIFIED-upstream**: `start_time` is the right column to filter on.
  It is `timestamptz` (timezone-aware) so `now() - interval '30 days'`
  is a sane, comparable expression; no cast needed.
- **VERIFIED-upstream**: pg_cron does **not** auto-prune
  `job_run_details`. This is the well-known footgun that motivates
  retention jobs; the upstream README and Supabase docs both call it
  out.
- **UNVERIFIED-live**: whether the Supabase project ships any
  default cron jobs of its own that also write rows. We have no
  visibility into the project's `cron.job` from this checkout
  (`docs/audits/jeg285-phase1/03-supabase-current-state.md:69`,
  `docs/architecture-current.md:120` both explicitly flag this).
  This affects the row-count estimate below only as a constant
  multiplier; the retention window decision does not change.
- **UNVERIFIED-live**: whether the project's pg_cron version has an
  index on `start_time` we can rely on. Modern pg_cron (≥1.4, which
  Supabase uses) does. The `DELETE` is on a column that is monotonic
  per-row and filters the oldest segment first, so even a seq-scan
  would degrade gracefully on the table sizes we project.

### Idempotency and lock behavior

- **Idempotent.** `DELETE WHERE start_time < …` re-running on the
  same day just deletes zero extra rows; nothing in the body is
  stateful.
- **Lock surface.** A single bulk `DELETE` on this table takes a
  `RowExclusiveLock`. The query joins to `cron.job` only for the
  monitoring view; the retention body does not join. Reads of
  `cron.job_run_details` (the monitoring query in `02-pgcron-job-specs.md:149-154`)
  do not block under `RowExclusiveLock`, so shadow/cutover jobs are
  unaffected. The projection below keeps the table small enough that
  even a full seq-scan during the daily delete is sub-millisecond.
- **Ordering vs. shadow/cutover jobs.** 03:00 UTC sits between the
  Actions cron's last sync window (midnight UTC) and the daily
  sync kicks at 11:30–11:45 UTC. No overlap with the planned
  schedules in `01-migration-tracker.md:12-20`.

### Supabase-managed retention — UNVERIFIED

Supabase does not, in current public documentation, auto-prune
`cron.job_run_details` for you. Marking this **UNVERIFIED-live**
because the only way to confirm is to query `cron.job` on the
project, which this checkout cannot do. If Jeremy later confirms
Supabase already runs a cleanup, this retention job is still safe
to keep (it will just delete fewer rows per day); nothing about the
shape changes.

## Volume math (rows/day, rows/window, storage)

Counted from `01-migration-tracker.md:12-20`. Each scheduled job
writes one row to `cron.job_run_details` per execution. The
retention job itself contributes one row per day.

| Cadence        | Jobs | Runs/day |
|----------------|------|----------|
| Hourly         | 1    | 24       |
| 6-hourly       | 2    | 8        |
| Daily          | 3    | 3        |
| Weekly         | 1    | ≈0.14    |
| Retention job  | 1    | 1        |
| **Total**      | **8**| **≈36**  |

Plus any pre-existing project-level cron (UNVERIFIED); even at 100
extra runs/day the math below moves by ~3x, which still does not
change the recommendation.

| Window | Rows    | Bytes (≈1 KB / row) |
|--------|---------|---------------------|
| 14 d   | ≈504    | ≈0.5 MB             |
| **30 d** | **≈1,080** | **≈1.1 MB**       |
| 90 d   | ≈3,240  | ≈3.2 MB             |
| 365 d  | ≈13,140 | ≈13 MB              |

Even at the upper end (90 d, ×3 for unknown project-level jobs)
the table stays in the single-digit MB range. Storage cost is not
the constraint — **debuggability is**.

### Window recommendation

- **30 days** (matches draft): fits the shadow-mode duration across
  the seven migrations (longest shadow gate in
  `01-migration-tracker.md:14-20` is 7d for the synthetic-check, but
  the full pipeline cutover is weeks long — a 30-day window covers a
  full month of cross-job history).
- **90 days**: ~3× the storage, but covers a quarter. Useful if an
  incident post-mortem surfaces 60+ days later; the workspace
  post-mortems in `docs/claude-log.md` regularly reference jobs
  weeks old.

**Recommendation: keep 30 days.** The draft is right; do not change
the window without a reason. The math is below any cost threshold
either way; the choice is operational taste, not storage. If
Jeremy wants the longer debug window, 90 days is a single token
change in the cron body (`'30 days'` → `'90 days'`).

## Failure modes

| What fails                           | What's observed                                              | Detection latency                              |
|--------------------------------------|--------------------------------------------------------------|------------------------------------------------|
| Retention job body errors            | `cron.job_run_details` grows by ~36 rows/day; unbounded over months. | Months — until the next manual inspection of the table. |
| Retention job is dropped (`cron.unschedule` run by mistake) | Same as above.                                              | Same.                                          |
| Retention job runs but `start_time` index missing / corrupted | `DELETE` slows but eventually completes; no data loss. | Days — only visible via a slow query log or a SELECT runtime. |
| `cron.job_run_details` itself becomes slow / bloats storage to multi-GB | SELECT latency on the monitoring query degrades.       | Weeks.                                         |

The current detection story is **inspection only**. No automated
alert surfaces "retention has not run in N days". That is the gap
this section fixes.

## Monitoring proposal (query-only)

Add to the running monitoring section in
`02-pgcron-job-specs.md:147-158`. Query-only — no implementation in
this ticket.

```sql
-- A: retention job still scheduled (returns 0 rows if absent)
select jobname, schedule, active
from cron.job
where jobname = 'cron-retention-30d';

-- B: oldest row is within the retention window (pass if oldest is < 31d old)
select
  extract(epoch from (now() - min(start_time))) / 86400.0
    as oldest_row_age_days,
  count(*) as total_rows
from cron.job_run_details;

-- C: last 30 days of retention runs (proves the job itself is firing)
select start_time, end_time, status, return_message
from cron.job_run_details
where jobname = 'cron-retention-30d'
order by start_time desc
limit 30;
```

**Pass criteria:**
- A returns one row with `active = true`.
- B `oldest_row_age_days ≤ 31` (one day of slack against the
  30-day window).
- C has at least one row dated within the last 26 hours (one
  cycle of slack against the daily `0 3 * * *`).

**Fail actions (for Jeremy's call, not part of this ticket):**
- B crossing 35 → retention is not running; check whether A still
  exists, then check C for failures.
- A returning zero rows → the job was dropped; re-run the `select
  cron.schedule(...)` from the final SQL above.
- C returning `status = 'failed'` repeatedly → read it and decide
  whether to `unschedule` and reschedule with a corrected body.

No `NOTIFY` channel, no Slack hook, no new tables in this ticket.
Monitoring lives in the same `cron.job_run_details` view the draft
already uses; downstream alerting is JEG-285 #8 (chain failure
notification), out of scope here.

## What this ticket does NOT touch

- The 7 shadow/cutover jobs in `02-pgcron-job-specs.md`. Their
  bodies do not change.
- `pipeline_cron_log`, `pipeline_cron_state`, `live_page_checks`
  (none of which exist yet — created in the implementation phase
  per `02-pgcron-job-specs.md:160-164`). None of them interact
  with `cron.job_run_details`.
- The webhook for chain failure notification (#8 in the tracker).
- Any cron schedule itself — only this one retention job is being
  scheduled in this ticket's implementation phase.

## Open questions for Jeremy

1. **Window: 30 days (recommended) or 90?** A single token change
   in the cron body. 30 days matches the draft and the math; 90
   days costs ~3× the storage (still trivial) and gives a
   quarter of cross-job debug history.
2. **Is Supabase already running a `cron.job_run_details` cleanup
   on the project?** If yes, this retention job is harmless but
   redundant; if no, it is required. UNVERIFIED-live from this
   checkout.
3. **Are there pre-existing project-level cron jobs we should know
   about?** Affects the row-count constant but not the window
   decision. UNVERIFIED-live.
4. **Should the retention window auto-extend during incident
   response?** E.g., a one-shot `'90 days'` run before a
   cutover so pre-cutover history survives the 30-day cliff.
   Implementation would be one additional `select cron.schedule`
   with a different jobname and a self-`unschedule` body. Not in
   scope today; flagging for the cutover runbook.

## Citations

- `docs/audits/jeg285-phase2/01-migration-tracker.md:12-20` — the
  seven planned pg_cron jobs and cadences that drive the volume
  math.
- `docs/audits/jeg285-phase2/01-migration-tracker.md:42-46` — the
  prerequisite order (this is item #2; the only earlier item is the
  audit-table migration with Jeremy approval gated).
- `docs/audits/jeg285-phase2/02-pgcron-job-specs.md:18-23` — the
  draft retention job verified here.
- `docs/audits/jeg285-phase2/00-target-architecture-decision.md:52`
  — the architectural commitment that this retention is a prerequisite.
- `docs/audits/jeg285-phase1/03-supabase-current-state.md:69` —
  explicit "pg_cron state is unverified in this repo; Phase 2 must
  verify live", repeated for the project-level cron count.
- `docs/architecture-current.md:120` — same flag ("RLS and pg_cron
  state are unverified in the handoff and must not be assumed").
- `lanes/inbox/minimax/JEG-110-supabase-features.md:200-227` —
  the prior lane's UNVERIFIED list, which already flagged
  "`cron.job_run_details` exists in the Supabase project's pg_cron
  install" as needing a pre-migration `select * from
  cron.job_run_details limit 1`. That precheck still applies here
  before the SQL in this doc is executed.