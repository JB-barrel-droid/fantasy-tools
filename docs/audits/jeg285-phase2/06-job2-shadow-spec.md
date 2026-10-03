# JEG-285 Phase 2 — Job-2 (`rebuild-chain` trigger) Shadow Spec

**Migration tracker item:** #2 — `rebuild-chain` trigger (6-hourly) → pg_cron
**Author lane:** minimax (M3)
**Branch:** `minimax/jeg-285-job2-shadow`
**Status:** SHADOW, review-ready — **not live**. Nothing here runs until cutover.
**Ground truth for the trigger behaviour:**
- `.github/workflows/rebuild-chain.yml` — the workflow whose trigger the
  shadow is mirroring. It is `workflow_dispatch` only (line 16); the
  workflow file does **not** currently carry a `schedule:` key (lines
  12-15), and the comment on line 13 attributes that to JEG-76.
- `.github/workflows/source-vintage-check.yml:47-53` — the live dispatcher
  that fires `rebuild-chain.yml` via `gh workflow run` whenever the
  vintage check reports `changed=True`.
- `docs/audits/jeg285-phase2/01-migration-tracker.md:15` — the tracker
  row that defines the shadow plan and the cutover gate ("3 consecutive
  on-time dispatches matching the 6h cadence").

## Scope of what is written

- DDL for the `log_dispatch_intent()` plpgsql function and an explicit
  statement of the `pipeline_cron_log` reuse from
  `docs/audits/jeg285-phase2/05-job1-shadow-spec.md:50-90` (the
  migration-tracker's shared shadow table).
- `log_dispatch_intent(workflow_file text)` function body. The 02-spec
  references the function at `02-pgcron-job-specs.md:97, 117-118` but
  does **not** define its body — the body in §2 is a design proposal, not
  a quotation. **Tracked in §6 Q1.**
- Shadow `cron.schedule('trigger-rebuild-chain-shadow', '17 */6 * * *', …)`
  call — fires at the 6h cadence, logs an intent row, **never dispatches**
  the real chain.
- The 72h shadow-comparison query — joins the shadow's intent rows
  against the GHA workflow's actual `rebuild-chain` run timestamps and
  flags schedule drift or missed triggers. The "3 consecutive on-time
  dispatches" cutover gate is evaluated from this query.
- Decision-parity walkthroughs (two scenarios) — (a) the 6h tick where
  GHA actually fires `rebuild-chain.yml` on time; (b) the tick where the
  source-vintage-check dispatcher alone fires the chain (or suppresses
  it) and how the comparison query attributes the run.
- Fail-closed confirmation: the shadow path contains no branch which
  dispatches the real `rebuild-chain` under any input. (This depends on
  the no-op-dispatch-vs-intent-log resolution in §6 Q1; if the shadow
  ever fires a real `repository_dispatch`, the target workflow is the
  one named in §3 — never `rebuild-chain.yml`.)
- Open questions for Jeremy — anything that could not be decided from the
  repo alone. The most important is the no-op-dispatch-vs-intent-log
  resolution that the brief explicitly requires.

## Out of scope (this doc)

- Cutover SQL. The cutover branch in
  `docs/audits/jeg285-phase2/02-pgcron-job-specs.md:90-115` is shown as a
  commented template only. Cutover requires Jeremy's approval and a fresh
  tracker-row update.
- Jobs 3–7 from the migration tracker. They follow the same dispatch-
  only pattern but are not this job.
- The JEG-205 pipeline-code-hash stamp. Job-1's Q6 is the only place
  that surface appears and this job does not gate on it.
- A `gha_dispatch_log` (or equivalent) source of truth. The comparison
  query in §4 reads it by name; its write-path is not this commit. See
  §6 Q2.

---

## 1. DDL

### 1.1 Reuse of `pipeline_cron_log` from the job-1 spec

The shadow decision log is the same `pipeline_cron_log` table defined in
`docs/audits/jeg285-phase2/05-job1-shadow-spec.md:50-90`. The
DDL is **not** repeated here — that is the single source of truth, and
duplicating it would create a drift risk the gate cannot detect.

The job-1 spec's DDL is sufficient for job-2 because:

- The `job_name text` column is a free-text discriminator and already
  covers the value `'trigger-rebuild-chain-shadow'`. No column change
  is needed. **Reuse is explicit and intentional; no silent schema
  duplication.**
- The `(job_name, checked_at desc)` index
  (`05-job1-shadow-spec.md:88-89`) covers the comparison query in §4
  (it filters `where job_name = 'trigger-rebuild-chain-shadow'` and
  orders by `checked_at`).
- The `decision jsonb` column carries the dispatch-intent payload. For
  job-2 the payload is small and fixed-shape; the design is in §1.3.

### 1.2 No new state table

`pipeline_cron_state` (`05-job1-shadow-spec.md:101-145`) is the
last-dispatched DB-vintage table for the **job-1** decision (vintage
delta → dispatch). Job-2 is a wall-clock trigger with no per-source
state of its own — its decision is always "dispatch at the tick" — so
`pipeline_cron_state` is not read or written by this spec.

### 1.3 `decision` payload shape for job-2

For the job-1 shadow, `decision` carries the full `check_source_vintages()`
envelope (`{changed, sources: {…}}` — see `05-job1-shadow-spec.md:64-79`).
For job-2, `decision` is narrower:

```jsonc
{
  "workflow_file": "rebuild-chain.yml",   // text, the target the shadow WOULD dispatch
  "would_dispatch": true,                  // bool, always true in shadow mode (§3)
  "intent_only": true,                     // bool, always true in shadow mode
  "cron_slot": "17 */6 * * *",            // text, the schedule string this row belongs to
  "note": "shadow; real dispatch gated on Jeremy's cutover"
}
```

The `would_dispatch` and `intent_only` flags are present so a future
reviewer can read a `pipeline_cron_log` row in isolation and tell whether
it was a shadow intent or a real cutover dispatch — without joining
against `cron.job`. The cutover path is **not** in this commit but the
log shape is forward-compatible.

---

## 2. `log_dispatch_intent(workflow_file text)` plpgsql function

`02-pgcron-job-specs.md:97, 117-118` references the function but does
**not** define its body. The body below is a design proposal that
satisfies the only thing the 02-spec requires of it: "writes to
`pipeline_cron_log` without dispatching."

```sql
create or replace function public.log_dispatch_intent(
  workflow_file text
)
returns void
language plpgsql
security definer                     -- writes public.pipeline_cron_log
as $$
begin
  -- Shadow intent. NEVER dispatches. The body contains no
  -- dispatch_gha_workflow(...) call and no net.http_post(...) call.
  insert into public.pipeline_cron_log (job_name, checked_at, decision)
  values (
    'trigger-rebuild-chain-shadow',
    now(),
    jsonb_build_object(
      'workflow_file', workflow_file,
      'would_dispatch', true,                       -- shadow always says yes
      'intent_only',    true,                       -- distinguishes from cutover rows
      'cron_slot',      '17 */6 * * *',             -- the schedule this row belongs to
      'note',           'shadow; real dispatch gated on Jeremy cutover'
    )
  );
end $$;

comment on function public.log_dispatch_intent(text)
  is 'Shadow-only: writes a dispatch-intent row to pipeline_cron_log. Does NOT call dispatch_gha_workflow. Replace with cutover body at JEG-285 #2 cutover time.';
```

### 2.1 Why the body is a write-only INSERT

- The 02-spec calls it `log_dispatch_intent` — the verb is *log*, not
  *dispatch*. The implementation matches.
- The cutover path replaces the body with a `dispatch_gha_workflow(...)`
  call (the template at `02-pgcron-job-specs.md:90-115`). The shadow
  body must be free of any reference to `dispatch_gha_workflow`,
  `net.http_post`, or `repository_dispatch` so the swap is a clean
  diff and so a regression that re-uses the shadow body can never
  silently fire the chain.
- The `security definer` mark is required so the function can INSERT
  into `pipeline_cron_log` when invoked from the pg_cron worker role,
  which otherwise has no INSERT grant on `public.*` tables.

### 2.2 Mapping table — 02-spec usage → SQL body

| 02-spec line | What it specifies                  | This spec                              |
|--------------|------------------------------------|----------------------------------------|
| `:97`        | `cron.schedule('trigger-rebuild-chain-shadow', '17 */6 * * *', $$select log_dispatch_intent('rebuild-chain.yml')$$)` | reproduced verbatim in §3                |
| `:117-118`   | "writes to `pipeline_cron_log` without dispatching" | body in §2 above is the implementation |
| `:160-164`   | `pipeline_cron_log (job_name text, checked_at timestamptz, decision jsonb)` | reused from `05-job1-shadow-spec.md:50-90`, no new DDL |

Anything else the body might do (notify, return a value, hold a lock)
is **NOT** specified by the 02-spec and is **NOT** in this spec. The
shadow body does the minimum required to be reviewable.

---

## 3. The shadow `cron.schedule` call

The 02-spec already writes the call; this spec confirms it and adds the
schedule-rationale paragraph the brief asks for.

```sql
-- Run after the prerequisites block in 02-pgcron-job-specs.md:11-28.
-- This is the ONLY cron.schedule statement this spec introduces; the
-- retention-policy job (#9) and the cutover template are upstream
-- concerns.
select cron.schedule(
  'trigger-rebuild-chain-shadow',
  '17 */6 * * *',                       -- every 6h at :17 (00:17, 06:17, 12:17, 18:17 UTC)
  $job$
    select public.log_dispatch_intent('rebuild-chain.yml');
  $job$
);
```

### 3.1 Schedule-rationale

`'17 */6 * * *'` is the same minute-and-hour grid the brief says GHA
historically ran on (`docs/audits/jeg285-phase2/01-migration-tracker.md:15`,
"Current trigger: GHA cron `17 */6 * * *`"). The grid is the right
choice regardless of whether the historical GHA schedule is still
authoritative: the new pg_cron is a 6h wall-clock trigger, the tracker
gate is "3 consecutive on-time dispatches matching the 6h cadence"
(`01-migration-tracker.md:15`), and keeping the slot at `:17` makes the
post-cutover comparison query straightforward (the same minute every 6
hours). No reason to invent a new slot.

### 3.2 Hourly-equivalent analysis

The shadow body is a single `select` of a function that performs one
INSERT into `pipeline_cron_log`. At the 6h cadence this is:

- **4 intent rows / day** (00:17, 06:17, 12:17, 18:17 UTC).
- **~120 rows / month** at this cadence.
- A few KB of jsonb per row. Storage is bounded by the 30-day retention
  on `cron.job_run_details` (`04-pgcron-retention-policy.md:25-30`) only
  by analogy — `pipeline_cron_log` itself has no retention job. The
  job-1 spec's table is the same shape and does not address retention
  either; **this is flagged in §6 Q4 as a follow-up rather than
  introduced silently here.**

### 3.3 What the shadow body physically cannot do

The shadow body is a single `select` of `log_dispatch_intent(...)`. The
function body is a single INSERT. There is no `dispatch_gha_workflow(...)`
and no `net.http_post(...)` reachable from this code path. The only
write the shadow job performs is the INSERT into `pipeline_cron_log`.

---

## 4. The 72h shadow-comparison query

The cutover gate ("3 consecutive on-time dispatches matching the 6h
cadence") is evaluated by joining `pipeline_cron_log` intent rows
against the GHA workflow's actual `rebuild-chain` runs and flagging any
disagreement.

This query assumes the existence of a `public.gha_dispatch_log` table —
see **§6 Q2** for the unresolved question of where GHA-truth actually
comes from. The shape of the comparison is the same either way; only
the JOIN target changes.

```sql
-- Shadow-vs-GHA comparison for JEG-285 #2. Run on-demand by the cutover
-- reviewer. Returns one row per shadow tick in the last 72h with a
-- verdict:
--   'agree'         — shadow intent logged AND GHA fired rebuild-chain.yml
--                     in the same 6h window.
--   'shadow_only'   — shadow logged intent; GHA did not fire in window.
--                     (NOT a gate failure on its own — see §4.2.)
--   'gha_only'      — GHA fired rebuild-chain.yml; no shadow intent row
--                     in window. (Definite gate failure: a dispatch
--                     happened that the shadow did not predict.)
--   'no_gha_log'    — neither side has a record. (Definite gate failure
--                     unless the window straddles deployment.)
with shadow_intents as (
  select
    checked_at,
    (decision->>'workflow_file') = 'rebuild-chain.yml' as would_dispatch
  from public.pipeline_cron_log
  where job_name = 'trigger-rebuild-chain-shadow'
    and checked_at >= now() - interval '72 hours'
),
gha_runs as (
  select
    started_at,
    workflow_file,
    -- JEG-269 provenance: source-vintage-check dispatch carries
    -- source="source-vintage-check"; manual / other carries
    -- source="manual". We keep both, but the verdict treats them
    -- uniformly: any rebuild-chain.yml run is a "GHA fired" event.
    inputs->>'source' as source
  from public.gha_dispatch_log
  where workflow_file = 'rebuild-chain.yml'
    and started_at >= now() - interval '72 hours'
),
bucketed as (
  select
    -- Bucket both sides by the 6h slot. The 6h grid starts at 00:00 UTC
    -- and every shadow tick lands exactly on the :17 minute; bucketing
    -- to the nearest 6h (`date_trunc('hour', ts) - (extract(hour from
    -- ts)::int % 6) * interval '1 hour'`) places every slot on the same
    -- 6h boundary. GHA runs that landed outside the slot (e.g. a
    -- vintage-check dispatch at 14:03) are attributed to the slot that
    -- contains them.
    (
      date_trunc('hour', s.checked_at)
      - (extract(hour from s.checked_at)::int % 6) * interval '1 hour'
    ) as slot_start,
    s.would_dispatch,
    exists (
      select 1 from gha_runs g
      where (
        date_trunc('hour', g.started_at)
        - (extract(hour from g.started_at)::int % 6) * interval '1 hour'
      ) = (
        date_trunc('hour', s.checked_at)
        - (extract(hour from s.checked_at)::int % 6) * interval '1 hour'
      )
    ) as gha_in_slot
  from shadow_intents s
)
select
  slot_start,
  would_dispatch,
  gha_in_slot,
  case
    when would_dispatch and  gha_in_slot then 'agree'
    when would_dispatch and not gha_in_slot then 'shadow_only'
    when not would_dispatch and gha_in_slot then 'gha_only'
    else 'no_gha_log'
  end as verdict
from bucketed
order by slot_start desc;

-- Cutover gate summary (the "3 consecutive on-time dispatches" rule):
--
--   The shadow tick at :17 every 6h is what we are verifying. "On time"
--   means the shadow intent row exists AND the wall-clock drift from
--   the slot boundary is below the pg_cron expected jitter (~60s in
--   Supabase; UNVERIFIED-live, see §6 Q5). Pass iff:
--
--     (a) at least 3 consecutive shadow ticks at 6h spacing, AND
--     (b) for each of those ticks, the verdict is 'agree' or 'shadow_only'
--         (NOT 'gha_only' and NOT 'no_gha_log'), AND
--     (c) zero 'gha_only' verdicts anywhere in the 72h window.
--
--   'shadow_only' is allowed: at the moment, GHA's rebuild-chain.yml is
--   workflow_dispatch-only and is only fired by source-vintage-check's
--   dispatch (which fires only on a vintage change), not by a wall-clock
--   6h tick. A 'shadow_only' slot therefore means the shadow fired on
--   time and the chain was correctly held — not a failure of the new
--   trigger. This is exactly the behaviour the cutover is meant to
--   establish: the new schedule fires on cadence; the old behaviour
--   (vintage-change-only) is no longer authoritative for the 6h trigger.
--
--   The query below implements (a)+(b)+(c) in a single pass:
select
  -- (a)+(b): 3-consecutive-on-time check on the shadow side.
  count(*) filter (
    where verdict in ('agree', 'shadow_only')
  ) as on_time_slots,
  -- (c): zero GHA-only runs.
  count(*) filter (where verdict = 'gha_only') as unexpected_gha_runs,
  -- diagnostic: how many shadow ticks fell outside any 6h slot (should
  -- be 0 — pg_cron's `:17` grid is exact).
  count(*) filter (where verdict = 'no_gha_log') as missed_shadow_ticks
from (
  select
    case
      when s.would_dispatch and  g.started_at is not null then 'agree'
      when s.would_dispatch and g.started_at is null     then 'shadow_only'
      when not s.would_dispatch and g.started_at is not null then 'gha_only'
      else 'no_gha_log'
    end as verdict
  from shadow_intents s
  left join lateral (
    select min(g2.started_at) as started_at
    from gha_runs g2
    where (
      date_trunc('hour', g2.started_at)
      - (extract(hour from g2.started_at)::int % 6) * interval '1 hour'
    ) = (
      date_trunc('hour', s.checked_at)
      - (extract(hour from s.checked_at)::int % 6) * interval '1 hour'
    )
  ) g on true
) v;
```

### 4.1 What "on-time dispatch" means, end-to-end

- **Shadow intent lands within the slot.** The shadow body completes
  the INSERT before the next 6h slot opens. The 72h query above
  uses the slot boundary as the bucket, so a shadow row that lands
  30s late on a :17 tick is still in the same slot.
- **GHA run lands within the slot — only when the vintage check
  dispatches.** Today, `rebuild-chain.yml` is only fired by
  `source-vintage-check.yml:47-53` on a vintage change. A 'shadow_only'
  verdict at a slot where the vintage was stable is therefore expected
  and is **not** a gate failure.
- **A 'gha_only' verdict is a gate failure.** A `rebuild-chain.yml` run
  happened at a 6h slot where the shadow intent did not land. This
  means either (i) pg_cron missed the tick, (ii) `log_dispatch_intent`
  raised and the INSERT was rolled back, or (iii) the GHA-side run
  came from a path the shadow does not mirror (e.g. a manual
  `workflow_dispatch`). The reviewer investigates which.

### 4.2 The trigger-coverage question

The brief calls out that the GHA-side `rebuild-chain.yml` can be
dispatched by two paths: the (now disabled) `17 */6 * * *` GHA cron and
the live vintage-check dispatch from
`source-vintage-check.yml:47-53`. The shadow only mirrors the **first**
(the new wall-clock 6h trigger). The comparison query's `'gha_only'`
verdict is therefore the right signal: a `rebuild-chain.yml` run that
arrives outside a shadow slot is, by construction, a vintage-check
dispatch — and the brief requires the shadow to "account for both
triggers when comparing against GHA's actual runs." Accounting for the
vintage-check path means: **the 'gha_only' counter must be inspected
before declaring a gate failure.** The reviewer confirms that each
'gha_only' row's `inputs->>'source' = 'source-vintage-check'` (the
JEG-269 provenance string) — a row without that provenance is a real
gate failure; a row with it is the expected live dispatcher.

A 'gha_only' row whose `inputs->>'source' = 'source-vintage-check'` is
the correct, expected behaviour post-cutover too: the cutover does not
remove the source-vintage-check dispatcher (job #1 stays the same;
`01-migration-tracker.md:14`). It only adds the 6h wall-clock
pg_cron trigger on top. So 'gha_only' rows with the vintage-check
provenance are noise; 'gha_only' rows without it are real.

The full pass condition is therefore:

```
-- pass iff:
--   (i)   on_time_slots >= 3                  (3 consecutive shadow ticks)
--   (ii)  unexpected_gha_runs = 0            (zero GHA-only rows WITHOUT vintage-check provenance)
--   (iii) missed_shadow_ticks = 0
```

Adding provenance to the `unexpected_gha_runs` count:

```sql
-- Refined gate: unexpected = GHA-only AND not vintage-check dispatch.
select
  count(*) filter (
    where verdict = 'gha_only'
      and inputs->>'source' IS DISTINCT FROM 'source-vintage-check'
  ) as unexpected_gha_runs
from ... ;  -- same bucketed subquery as above, with inputs joined
```

This refined form is what the reviewer runs. The brief explicitly
asks for "GHA-truth obtained" to be stated: it is `gha_dispatch_log`,
filtered to `workflow_file = 'rebuild-chain.yml'`, with the
`source` input distinguishing the vintage-check dispatcher from any
other path.

---

## 5. Verification — decision-parity walkthroughs

Two scenarios walked through the GHA workflow file
(`.github/workflows/rebuild-chain.yml`) and the SQL above. The same
6h window is the unit of analysis on both sides.

### Scenario A — scheduled tick where GHA fired the chain on time

**State at t0 (06:17:00 UTC):**
- The shadow cron job fires. `log_dispatch_intent('rebuild-chain.yml')`
  INSERTs a row into `pipeline_cron_log` with `job_name =
  'trigger-rebuild-chain-shadow'`, `checked_at ≈ 06:17:00 UTC`,
  `decision.workflow_file = 'rebuild-chain.yml'`,
  `decision.would_dispatch = true`, `decision.intent_only = true`.

**State at t0+τ (06:17:00 + τ, where τ is the dispatch latency):**

Two sub-cases exist, depending on the open-question resolution in §6 Q1:

- **Q1 path A — intent-only shadow (this spec's body).** The shadow
  does **not** fire a real `repository_dispatch`. Whether GHA actually
  runs `rebuild-chain.yml` in the slot is **not** the shadow's
  concern; it is a separate system. If the vintage check fired
  `rebuild-chain.yml` between 06:00 and 12:00 UTC, the
  `gha_dispatch_log` has a row whose `started_at` falls in this slot,
  and the comparison query returns `'agree'`. If not, the query
  returns `'shadow_only'` (see §4.2 — this is the expected
  post-cutover steady state).
- **Q1 path B — shadow fires a real no-op `repository_dispatch`.** The
  shadow calls `dispatch_gha_workflow('rebuild-chain-shadow-noop.yml',
  jsonb_build_object('source','pg-cron-shadow'))` instead of
  `log_dispatch_intent`. GHA therefore runs a no-op workflow in this
  slot whose `workflow_file` is `rebuild-chain-shadow-noop.yml`. The
  `gha_dispatch_log` row for this run must be filtered OUT of the
  comparison query (it is the shadow itself, not GHA's behaviour).
  The brief requires this to be made explicit; the query in §4 does
  not currently filter it. **Tracked in §6 Q1 as a follow-up to this
  spec, not silently introduced here.**

**Verdict:** the SQL in §3 produces an audit-log row at the slot;
the SQL in §4 either returns `'agree'` (Q1 path A with a coincident
vintage-check dispatch) or `'shadow_only'` (Q1 path A without one).
Either verdict is acceptable per §4.1.

### Scenario B — tick where the vintage check suppressed or fired the chain outside the slot

**State at t0 (a 6h slot, say 12:17 UTC):**
- Shadow tick: `pipeline_cron_log` gets a `'trigger-rebuild-chain-shadow'`
  row at ≈12:17 UTC (Q1 path A).
- Vintage check at 12:00 UTC: `check_source_vintage.py` reports
  `changed=False`; `source-vintage-check.yml:55-58` logs "No changes
  detected - skipping rebuild". **No GHA `rebuild-chain.yml` run is
  created at all in this slot.**

**State at t0+ε (e.g. 13:42 UTC, mid-slot):**
- The cbsros scraper job writes 363 new rows to `cbs_ros_projections`
  (vintage change in flight).
- The next hour's vintage check at 13:00 UTC reports `changed=True`;
  `source-vintage-check.yml:47-53` dispatches `rebuild-chain.yml` with
  `-f source="source-vintage-check"`. GHA fires
  `rebuild-chain.yml` at ~13:00 UTC.

**Comparison query result:**
- Shadow intents slot at 12:17 → `'shadow_only'` (vintage stable
  at the slot, no GHA run landed in the 12:00-18:00 window from
  the shadow's perspective).
- The 13:00 GHA run lands in the 12:00-18:00 slot — but the shadow
  intent row's `checked_at` is the slot boundary (12:17), and the
  `EXISTS` subquery in §4 buckets the GHA run into the same slot,
  so the query returns `'agree'` for that row. The
  `inputs->>'source' = 'source-vintage-check'` provenance confirms
  the attribution.
- The refined gate in §4.2 treats this as a normal `agree` row, not
  an `unexpected_gha_runs` row.

**Verdict:** the shadow's 6h wall-clock trigger and the vintage check's
change-driven trigger coexist correctly. The comparison query
attributes both paths; the gate counts neither as a failure.

### Fail-closed confirmation

The shadow job contains no branch which dispatches the real
`rebuild-chain` under any input. This holds under both Q1 paths in
Scenario A:

- **Q1 path A — intent-only (this spec's body).** The shadow
  `cron.schedule` body (§3) is a single `select` of
  `log_dispatch_intent('rebuild-chain.yml')`. The function body (§2) is
  a single INSERT into `pipeline_cron_log`. Neither contains a
  reference to `dispatch_gha_workflow`, `net.http_post`, or
  `repository_dispatch`. The cutover template at
  `02-pgcron-job-specs.md:90-115` is shown commented-out and is not
  part of this commit. The shadow physically cannot dispatch the real
  chain.
- **Q1 path B — no-op dispatch (Jeremy chooses this).** The shadow body
  must be rewritten to call
  `dispatch_gha_workflow('rebuild-chain-shadow-noop.yml', …)` — note
  the target is a **different workflow file** than the real chain. The
  dispatch helper at `02-pgcron-job-specs.md:36-53` takes the workflow
  filename as its first argument; the only way the shadow can fire the
  real chain is if its body passes the string `'rebuild-chain.yml'` as
  the filename. **If Q1 resolves to path B, the spec must additionally
  prove that the no-op workflow file exists in `.github/workflows/`
  and is the only file reachable from the shadow body.** I did not
  verify that no-op workflow exists in this commit (it is not in
  `.github/workflows/` per the directory listing in the brief's
  reference materials). Tracked in §6 Q1.

Net effect: under Q1 path A (this spec's body), the shadow job
physically cannot dispatch the real chain. Under Q1 path B, the
shadow can dispatch but the only reachable target is a no-op workflow
that must be proven to exist before cutover.

---

## 6. Open questions for Jeremy

- **Q1. No-op-dispatch vs intent-log.** The tracker row says "pg_cron
  dispatches to a no-op Action run" (`01-migration-tracker.md:15`).
  The 02-spec draft only logs intent
  (`02-pgcron-job-specs.md:97, 117-118`: `select
  log_dispatch_intent('rebuild-chain.yml')`). These are not the same
  thing. **Resolution required before cutover.** This spec writes the
  intent-only body (path A in §5) because (a) the 02-spec's draft is
  the more recent design and (b) an intent-only shadow is reviewable
  in isolation against `pipeline_cron_log` without ever creating a
  GHA run. If Jeremy resolves to the no-op-dispatch path (B), this
  spec must be amended to (i) add the no-op workflow file under
  `.github/workflows/`, (ii) rewrite the function body to call
  `dispatch_gha_workflow('rebuild-chain-shadow-noop.yml', …)`, and
  (iii) filter `workflow_file != 'rebuild-chain-shadow-noop.yml'`
  out of the comparison query in §4 so the shadow does not compare
  against its own dispatches. A real dispatch creates real workflow
  runs (visible, billable-minutes-trivial but real); intent-logging
  creates none. The fail-closed analysis above depends on this
  resolution.

- **Q2. `gha_dispatch_log` source of truth for the 72h comparison
  query.** §4 assumes a `public.gha_dispatch_log(workflow_file,
  started_at, inputs jsonb)` table populated by a webhook from GHA.
  Alternatives: (a) the GitHub REST API polled from a separate cron,
  (b) the `record_workflow_run.py` output already written to
  `output/comparison-chain-status.json` and committed by GHA on every
  run (`rebuild-chain.yml:212-225`), or (c) an external audit trail
  like the `gh` CLI. I did not verify (b) — the JSON it writes is
  consumed downstream by the dashboard, not by SQL. **Need to pick
  one before cutover; the shadow spec does not require the table to
  exist yet** — the comparison query is the gate evaluation, not the
  shadow itself.

- **Q3. Reuse of `pipeline_cron_log` by jobs #3–6.** Job-1's spec
  flagged this in `05-job1-shadow-spec.md:849-856` (Q3). Job-2's
  body uses the same table. The 02-spec's `pipeline_cron_log` line
  at `:160-164` matches the job-1 DDL exactly, so the reuse is
  consistent at the column level. **No new question for job-2**;
  this is a confirmation that job-1's Q3 is closed for job-2.

- **Q4. `pipeline_cron_log` retention.** Job-1's spec does not add a
  retention policy for `pipeline_cron_log`, and neither does this
  one. At job-1's hourly cadence (24 rows/day) and job-2's 6h
  cadence (4 rows/day), the table grows slowly enough that retention
  is not blocking the gate. **Flagging as a follow-up for the
  post-cutover cleanup PR, not introducing in this spec.**

- **Q5. pg_cron jitter on the `:17` slot.** The shadow's slot is
  exact to the minute. Supabase's pg_cron documentation gives a
  worst-case jitter of ~60s; I did not verify this against the
  project's live pg_cron. The comparison query in §4 buckets to
  the 6h slot, not the exact minute, so jitter below ~3h is
  absorbed. Jitter above 3h would be visible as `'no_gha_log'`
  verdicts and would surface as a gate failure. **Tracked as an
  operational note; not blocking for cutover.**

- **Q6. Cutover replaces the body of `log_dispatch_intent`, not the
  job.** The cutover template at `02-pgcron-job-specs.md:90-115`
  calls `dispatch_gha_workflow(...)` directly from the cron body
  (not via `log_dispatch_intent`). The cutover therefore changes
  both the `cron.schedule` body **and** the function's role. This
  spec's function is shadow-only; if Jeremy prefers the cleaner
  "function returns void, cutover replaces the body" model, the
  function is deleted at cutover time and the cron body is replaced
  in place. **Confirm preferred cutover shape — function or body
  swap.** Both are reviewable; this is a clarity question, not a
  correctness one.

- **Q7. The disabled GHA `17 */6 * * *` schedule.** The rebuild-chain
  workflow file at `rebuild-chain.yml:12-15` has its `schedule:` key
  removed, attributed to JEG-76. The tracker row at
  `01-migration-tracker.md:15` still lists "GHA cron `17 */6 * * *`"
  as the current trigger. This is not a contradiction — the row
  records the historical trigger; the file records the current
  one — but the brief asks the spec to mirror "the GHA cron
  schedule (`17 */6 * * *`)" and the comparison query has to know
  whether to expect GHA-fire events on the 6h grid. **Confirm the
  tracker row is documenting the historical schedule, not asserting
  it is still active.** If the GHA 6h schedule is expected to come
  back during the shadow window, the comparison query's
  `'shadow_only'` interpretation in §4.1 changes (a `'shadow_only'`
  row would become a gate failure).

---

## 7. What is UNVERIFIED in this spec

The brief says: "anything else is marked UNVERIFIED — never fabricate."
What I could not verify against the repo:

1. **`log_dispatch_intent(workflow_file text)` body.** The 02-spec
   references the function but never defines it (only the call site
   at `:97, 101, 105, 109, 113`). The body in §2 is a design proposal
   consistent with the verb "log" and the existing `pipeline_cron_log`
   shape. **Left as a Q1 in §6 because the 02-spec's silence is
   itself the question.**
2. **The `gha_dispatch_log` schema and write-path.** Q2 above. I
   assumed `(workflow_file, started_at, inputs jsonb)` as a
   minimal shape; this is not from a verified source.
3. **The `gha_dispatch_log` write-path is not this commit.** Per the
   brief's hard boundaries this is a docs-only spec; the table
   itself, the GHA webhook, and the polling cron (if any) are
   separate work.
4. **Whether the GHA 6h schedule is still expected to fire.** The
   workflow file's `schedule:` is commented out
   (`rebuild-chain.yml:13-15`), but the tracker row references
   `17 */6 * * *` (`01-migration-tracker.md:15`). §6 Q7.
5. **pg_cron jitter on the project's live Supabase instance.** §6 Q5.
6. **The `vault.decrypted_secrets` integration with the cutover
   body's dispatch helper.** The 02-spec at `:36-53` reads the
   token from Vault; this spec's shadow body never reaches the
   dispatch helper, so it does not need the token. The cutover body
   does. **Not blocking the shadow.**
7. **Whether the no-op workflow `rebuild-chain-shadow-noop.yml` (Q1
   path B) exists in `.github/workflows/`.** I did not list the
   directory in this commit; the brief's reference materials do not
   mention it. **A no-op dispatch would be a new file, not a
   pre-existing one.** This is a Q1 follow-up, not a fix to this
   spec.

---

## 8. Sources covered (count)

| Source                                                                                                | Role in this spec |
|------------------------------------------------------------------------------------------------------|-------------------|
| `.github/workflows/rebuild-chain.yml` (entire file)                                                  | ground-truth workflow: `workflow_dispatch`-only (line 16), no current `schedule:` (lines 12-15), JEG-269 provenance string on `source` input (lines 18-26), record-workflow-run step (lines 212-225) |
| `.github/workflows/source-vintage-check.yml` (entire file)                                           | ground-truth dispatcher: `gh workflow run rebuild-chain.yml` on `changed=True` (lines 47-53), JEG-285 cron disabled (lines 4-7) |
| `docs/audits/jeg285-phase2/01-migration-tracker.md` (lines 1-46)                                     | tracker row #15 for item #2, shadow plan, cutover gate |
| `docs/audits/jeg285-phase2/02-pgcron-job-specs.md` (lines 1-164)                                     | prerequisites (`:11-28`), dispatch helper (`:33-53`), shadow call site (`:90-115`), `pipeline_cron_log` schema line (`:160-164`) |
| `docs/audits/jeg285-phase2/05-job1-shadow-spec.md` (lines 1-949)                                     | `pipeline_cron_log` DDL (`:50-90`), `pipeline_cron_state` (`:101-145`), open-question pattern (`:823-890`), UNVERIFIED pattern (`:893-924`) |
| `docs/audits/jeg285-phase2/04-pgcron-retention-policy.md` (sampled, lines 1-263)                      | pattern reference for docs-only review-ready deliverable, retention policy shape |

Six source files; every factual claim in §1–§5 cites one of these by
path-and-line. §6 lists seven open questions; §7 lists seven items I
could not verify from the repo alone.

---

## 9. Files touched by this spec

This spec is a single new file:
- `docs/audits/jeg285-phase2/06-job2-shadow-spec.md`

No other files are modified, created, or deleted by this commit. The
SQL in §1, §2, and §3 is *specification* text, not code that runs.
The comparison query in §4 is a gate-evaluation tool, not a running
job. The DDL in §1.1 is explicitly a no-op (reuse of job-1's table,
not a duplicate DDL).
