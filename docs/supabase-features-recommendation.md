# Supabase features for pipeline stability — JEG-110

**Scope:** research-only. No code or schema changed. Each recommendation cites the
real script or workflow it would replace; all gaps and costs are stated against
the actual repo state on `minimax/jeg-110-supabase-features` at 2026-10-02.

**Reading order:** §1–§4 cover the four features (replace / stability-gain /
cost-complexity / visibility-impact). §5 ranks them for adoption. §6 is the
process commit log entry; §7 is the lane handoff note.

The four features:

1. Database triggers (validate-on-write, auto-stamp vintages, derived rollups)
2. Postgres functions / RPC (consolidate repeated multi-step writes)
3. pg_cron / scheduled jobs (move pull schedules into Supabase)
4. Constraints as guards (the fail-closed layer JEG-104 proved we need)

## Cross-cutting ground rules every recommendation respects

These are pulled from `docs/pipeline-rules.md`, `docs/claude-log.md` (JEG-104,
GAP-023, GAP-012, GAP-036), and the migrations — they are **not** new
constraints, just the floor under which every recommendation below sits:

- The Supabase `players` table is the identity authority. Identity is numeric
  `player_key`; unmatched/ambiguous names go to `review_rows`, never guessed
  (`pipelines/save_espn_cbs_references.py:159-187`, `save_usatoday_references.py:179-189`).
- Freshness is content vintage, never pull time. `pulled_at` is acquisition
  time; `source_content_date` / `espn_snapshot_date` / `week` are the only
  legitimate vintage signals (`pipeline-rules.md` §5,
  `check_source_vintage.py:71-84`).
- Multiple immutable bakes per week. Each ingest writes a new `bake_id`;
  readers select exactly one bake per week via
  `import_supabase_references._select_latest_bake`
  (`check_source_vintage.py:51-61`, `migration 004`).
- Every Supabase write is gated by `WriterAudit.start()` →
  `audit.audit_rows()` → upsert → `audit.complete()` (or `.fail()`), and a
  post-write row-count must match the upsert or the writer exits fail-closed
  (`save_usatoday_references.py:413-423`, `writer_audit.py:75-208`).
- The promote / fixture chain fails closed when the import-health gate is
  red; "no fixture update on a red gate" is the standing rule
  (`docs/pipeline-rules.md` §8, `rebuild-chain.yml:69-94`).
- `make validate` is the single red light; nothing publishes on a red run
  (`AGENTS.md` "Never publish on a known flaw"; `rebuild-chain.yml:160-164`).

Every proposal below is checked against those rules before recommending.

---

## 1. Database triggers — validate-on-write, auto-stamp vintages, derived rollups

### What this is

PostgreSQL `BEFORE INSERT/UPDATE` and `AFTER INSERT/UPDATE` triggers on the
five writer tables (`public.source_trade_values`,
`public.espn_season_projections`, `public.cbs_trade_values`,
`public.cbs_ros_projections`, `public.razzball_projections`) plus
`public.pipeline_write_audit`. The triggers run inside the database engine;
the application sends the row and the engine rejects / fills / fans out.

### What it would replace (each citation is a real script)

**(a) Validate-on-write — reject bad rows at insert instead of a later health check.**

- `pipelines/save_usatoday_references.py:413-423` — post-upsert row-count
  re-query: `live = count_rows(...)`; if it does not match `len(clean)`, raise
  fail-closed. Same pattern in `save_espn_cbs_references.py` (the canonical
  writer, used by ESPN and CBS), `save_fantasypros_references.py`, and
  `save_fantasycalc_references.py` (all four savers ship a post-write count
  verification because the upsert is *trusted* to status: 23505 / 400 / etc.,
  but the caller has to verify the round trip happened). A trigger can reject
  invalid rows at the INSERT step with a `RAISE EXCEPTION`; the post-write
  count check collapses into the trigger.
- `pipelines/verify_import_health.py` (`docs/import-health-schema.md`) — the
  `TABLE_DRIFT` failure code (manifest row-count vs Supabase row-count for
  the same grain) is detectable in a `BEFORE INSERT` trigger; today it
  surfaces only when a later `make import-health` reads the table. A
  trigger turns "drift detected at 02:31 UTC after the chain ran" into "drift
  refused at the write".
- The week-vs-content-date mixed-vintage guard at
  `check_source_vintage.py:71-84` (`raise SystemExit(f"Fail closed: mixed
  {date_column} values {dates}")`) is the same kind of integrity invariant;
  a trigger could enforce it before the row lands.

**(b) Auto-stamp vintages — push the writer_audit stamping into the engine.**

- `pipelines/lib/writer_audit.py:210-229` — `audit_row()` adds `_writer_identity`,
  `_run_id`, `_written_at` to every row before upsert; this is repeated by
  every saver (USAT, ESPN, CBS, FantasyPros, FantasyCalc, Razzball). A
  `BEFORE INSERT` trigger can pull `_writer_identity` / `_run_id` from a
  `current_setting('weaver.identity', true)` / `current_setting('weaver.run_id', true)`
  PG variable that the writer helper sets in the same connection — the Python
  helper is reduced to a one-line `SET LOCAL`. Migration 001's
  "historical-row honesty" backfill at `migration 001 §7-8` is also handled
  by a trigger that refuses `UPDATE` setting `_written_at` to NULL for any
  row where `_writer_identity` is non-NULL.
- `save_usatoday_references.py:347` (`bake_id = f"usatwk{week}_{today}_v1"`)
  and the equivalent scheme in `save_fantasypros_references.py` (FP),
  `save_fantasycalc_references.py` (FC) — three savers each stamp a
  date-prefixed bake_id with their own format. A trigger can default
  `bake_id` to `format('usatwk%s_%s_v1', NEW.week, current_date::text)` when
  `NEW.bake_id IS NULL`, with one strategy per writer identified by
  `source`.

**(c) Derived rollups — maintain read-optimised counts / freshness signals.**

- `pipelines/build_pipeline_checkpoints.py` C10 reads the live served JSON
  and checks `content_vintage` against the fixture (read-only check today,
  `docs/health/best-practices.md`). The freshness rollup lives in
  `app/trade-value-chart/assets/reference-freshness.json` and is hand-built by
  `check_reference_freshness.py`; 7 of 16 items are past their 2-day budget and
  only 1 is enforced (`docs/risk-register.md` GAP-033). An `AFTER INSERT
  UPDATE OR DELETE` trigger on the writer tables can maintain a
  `public.source_freshness_rollup(source, last_content_vintage, last_pulled_at,
  row_count, last_updated)` row in real time, and the dashboard reads it
  directly — `check_reference_freshness.py` becomes a per-source join, not a
  re-derivation.
- `output/source-import-health.json` (the import-health gate) is hand-built
  by `verify_import_health.py` on every `make import-health` invocation. A
  trigger-maintained rollup table replaces the manual re-query per source
  in `verify_import_health.py` (see `docs/import-health-schema.md` field
  `last_successful_import`).

### Stability gain

- The JEG-102 root cause (`docs/risk-register.md` GAP-041) was that a
  missing Python module silently swallowed the ESPN scrape; a trigger sees
  the row landing and would only have triggered if the row actually landed.
  Today the bad path is silent; with a trigger the bad row is either
  accepted (real save) or rejected (loud failure) — never "appears saved but
  the table didn't grow".
- JEG-104 (the constraint-bug ticket referenced in the task) and the
  pre-fix GAP-023 dual-index bug (`docs/risk-register.md` "Low ... Fixed
  2026-10-02") both demonstrate that *application-level* guards on
  multi-grain unique indexes are brittle; moving the guard to a trigger
  inside the engine removes the application layer from the critical path.
- Drift detected at 02:31 UTC after the chain ran becomes drift refused at
  the write — the watchdog's CRITICAL/RED budget shrinks because there is
  no window in which bad rows exist.

### Cost / complexity

- Every trigger has to be tested with the same fail-closed rigour the
  pipeline currently demands of application code. `tests/test_writer_audit_enforcement.py`
  is the existing pattern (negative test for "write without audit"; same
  shape extends to "write that violates the trigger"). Trigger tests need
  hermetic Supabase access, which today is via the `~/workspace/skills/supabase-football-signal/bin/sbclient.pyc`
  cache (`docs/risk-register.md` GAP-008, "recovered binary helper, not a
  source-controlled durable client"); this needs resolving before trigger
  tests are mergeable.
- Triggers fire on every write; per-row cost is small but visible at the
  FantasyCalc row counts (~594 × `as_published` + 594 × `bias_adjusted` per
  pull, `docs/supabase-source-mapping.md`). On Postgres triggers fire in the
  same transaction as the row, so the cost is paid by the upsert that
  already exists.
- Each of the four migration-004–006 vintage-grain shifts required a
  careful application-side migration (`migration 005` "evolves the legacy
  player_norm grain to be bake-aware ... not removal"; `migration 006` "retire
  the unversioned 8-column upsert grain"). A trigger that owns the
  bake_id defaulting makes future versioning shifts a SQL change, not a
  Python change across three savers.
- RLS must stay service-role-friendly. `migration 001` row 6-8 step 6
  explicitly: "DO NOT use FORCE ROW LEVEL SECURITY here ... would break
  service_role pipeline writes". Triggers must respect that.

### Visibility reduction (explicit per ticket)

- Triggers fire inside Postgres; there is no GitHub Actions log of "trigger
  X fired and rejected row Y" unless we wire the rejection to a side table
  or `RAISE NOTICE`/log line. The pipeline currently relies on the
  workflow run page as the single timeline of pipeline events
  (`pipelines/build_github_actions_status.py`, `rebuild-chain.yml:96-113`,
  JEG-109). A trigger failure surfaces only in the Supabase log explorer
  (or in a notification side table we wire up), not in the Actions log —
  Jeremy's daily review path is currently "open Actions tab" (the only
  workflow-health dashboard); a trigger rejection has to be added to the
  same surface.
- The `pipeline_write_audit` row is the only durable record of a write
  attempt today. A `BEFORE INSERT` trigger that rejects a row does not
  create an audit record by default (the rejection is pre-row). We must
  add an explicit "rejection log" table or a Postgres `NOTIFY` channel
  that surfaces in the same monitor pipeline the audit table feeds. This
  is additional wiring; the current behaviour (count-mismatch =
  fail-closed in Python) is naturally visible because the Python process
  is the Actions job step.
- Auto-stamping `_written_at` from `current_setting('weaver.run_id')` is
  invisible to `gh workflow run` output. A debug call (`SELECT
  current_setting('weaver.run_id')` from the workflow step) restores it,
  but it costs another step.

**Net visibility impact: medium.** The pipeline stops being able to claim
"the Actions run log tells the whole story." We need to wire a parallel
"trigger-side log" surface (NOTIFY → tail, or a rejection log table the
build_github_actions_status step reads) or Jeremy's daily review loses
visibility into bad writes.

---

## 2. Postgres functions / RPC — centralise repeated multi-step write patterns

### What this is

Stored procedures (`CREATE FUNCTION ... LANGUAGE plpgsql` then `CREATE
PROCEDURE` or `rpc()` wrappers) callable as RPCs from the pipeline. They
own: identity resolution, audit-row creation, vintage derivation, and the
upsert call. The Python saver stops short at the call site.

### What it would replace (each citation is a real script)

**(a) The versioned-upset dance, currently reimplemented in three savers.**

- `save_usatoday_references.py:78-80` —
  `USAT_UPSERT_CONFLICT_VERSIONED = "source,variant,scoring,league_teams,qb_slots,season,week,player_key,bake_id"`.
- `save_fantasypros_references.py` — equivalent constant
  (`FP_UPSERT_CONFLICT_VERSIONED`, parallel column list).
- `save_fantasycalc_references.py` — equivalent constant
  (`FC_UPSERT_CONFLICT_VERSIONED`).
- `save_espn_cbs_references.py:110-119` — the `_default_upsert` helper
  (`for chunk in chunks: sbclient.post(table, chunk, prefer="merge-duplicates")`)
  is the actual upsert call; each caller passes its own `on_conflict` string.
- A `public.upsert_source_trade_values_versioned(jsonb rows, text source, text
  bake_id, text run_id)` RPC owns the chunking, the
  `prefer=merge-duplicates`, the `on_conflict` constant, and the
  bake_id defaulting. The Python savers stop carrying the constant and the
  chunking loop; the saver just builds the row JSON and calls the RPC.

**(b) The audit-creation → row-stamping → upsert sequence, currently
reimplemented in every saver.**

- `save_usatoday_references.py:375-410` — the canonical pattern:
  `WriterAudit(...)` → `audit.start()` → `rows_to_save =
  audit.audit_rows(clean)` → `upsert_rows(...)` → `audit.complete(...)` or
  `audit.fail(...)`. This same 35-line block is in `save_espn_cbs_references.py`,
  `save_fantasypros_references.py`, `save_fantasycalc_references.py`,
  `save_razzball_references.py`. A `public.write_with_audit(text table_name,
  text source, text writer_identity, jsonb rows, jsonb metadata)` RPC owns
  the audit-row create, the data-row stamp (via trigger as in §1), and the
  upsert in one transaction.
- `WriterAudit` itself becomes a thin client that calls the RPC instead of
  building the audit record itself. The fail-closed semantics stay the
  same; the wire shape simplifies.

**(c) The content-vintage derivation, currently duplicated.**

- `check_source_vintage.py:71-84` — `_derive_db_vintage(rows, source)`
  picks the right date column per source. Same logic exists in
  `import_supabase_references.py::derive_db_vintage` (cited at
  `check_source_vintage.py:72` "Matches canonical logic from
  import_supabase_references.py").
- A `public.derive_source_vintage(text source) returns text` RPC owns
  this; the Python readers (`check_source_vintage.py:87-139`,
  `import_supabase_references.py`) become one-line RPC calls. Drift
  between the two Python copies (already documented at
  `check_source_vintage.py:72`) disappears.

**(d) The fail-closed reindex → review split.**

- `save_usatoday_references.py:256-320` (`apply_reindex` →
  `build_reindex_candidate` → `reindex_section` → review list) is the only
  place the reindex dance is plumbed end-to-end today. The candidate-shape
  JSON it writes is a Python temporary file (`apply_reindex` writes to
  `tempfile.NamedTemporaryFile`). An RPC version takes the row JSONB, calls
  the same `reindex_section` math (which can stay in Python or move into a
  Postgres extension if the isotonic fit is acceptable as a SQL helper),
  and returns `(clean_rows, review_rows)`. Worth doing only if a second
  saver adopts the same dance; today only USA Today reindexes at save time,
  so this is **optional** unless FantasyPros / FantasyCalc adopt the same
  pattern.

### Stability gain

- JEG-104 / GAP-023 — the dual-index bug ("An upsert arbitrates only the one
  it names, so a row that is new on the player_key grain but collides on
  the player_norm grain would still raise a unique violation",
  `docs/risk-register.md` row 40) and GAP-012 ("`save_usatoday_references.py`
  plain-inserted into `source_trade_values` through a hardcoded
  `sbclient.post` loop and bypassed the shared `upsert_rows`", row 29) both
  show that the *application's* knowledge of "which index arbitrates which
  grain" is the failure surface. Moving the upsert into a single RPC owned
  by the schema migration authors (the same hands that wrote migration 004 /
  005 / 006) collapses the failure surface to one place.
- GAP-041 (ESPN daily CI crashes on missing `identity` module, fails open)
  — the worker audit + upsert call happen in the same transaction in the
  RPC; if the audit row fails, the data row never lands. Today an
  exception in the audit step leaves the data row to its own fate
  (`save_usatoday_references.py:393-395` "Warning: audit unavailable,
  proceeding without audit").
- The "post-write count verification" at `save_usatoday_references.py:413-423`
  is a separate HTTP round trip (the saver re-reads the table to count).
  An RPC that returns the inserted row count in the same response makes the
  post-write check atomic with the write — no race between the upsert
  response and the count read.

### Cost / complexity

- The PostgREST surface does not currently expose RPCs in our schema
  (`docs/architecture-current.md` §Supabase: "57 tables, 17 views, and 2
  RPCs"; we have 2 already and they are unused for writes). Adding writer
  RPCs is a one-time `supabase/migrations/<n>_*.sql` plus a `NOTIFY
  pgrst, 'reload schema'` (the same pattern as migration 004 / 005 / 006).
- Each RPC must be tested hermetically. Today the savers have unit tests
  via module-level injection (`save_espn_cbs_references.py:136-139`,
  `save_espn_cbs_references.py:102-119` `_default_fetch_players /
  _default_upsert / _default_count / _default_fetch` are swappable for
  tests). RPC tests need a live Supabase or a `pg_temp`-backed fake; the
  current `sbclient.pyc` cache makes this awkward (GAP-008).
- The application gains a "where does this magic happen" question: today
  every save step is in Python, debuggable from the Actions run log. With
  RPCs the audit failure surfaces inside the engine. Same logging caveat
  as §1.

### Visibility reduction (explicit per ticket)

- An RPC failure (a Postgres exception inside the function) is reported as
  a `pgrst` HTTP error to the saver; the saver's exception handling turns
  it into a Python traceback in the Actions run log. That works today.
- The **inside-the-function** debugging (e.g. "why did the function emit
  this audit row with this run_id?") is invisible from the Actions log;
  the engineer has to look at the Postgres log or the audit table. This is
  the same shape as the §1 trigger concern and is partially solved by the
  audit table itself (every write has a durable audit row).
- The `metadata` JSONB column on `pipeline_write_audit`
  (`docs/SUPABASE_WRITER_AUDIT.md`) is the bridging surface — the RPC can
  write metadata into the audit row that the Python side would have
  printed to stdout. If the saver's `print`/`WriterAudit.start()` log
  lines are replaced by "RPC `write_with_audit` returned run_id X, row_count
  Y", the information is the same but the path to it is one step deeper.

**Net visibility impact: low.** The audit table carries the same data the
Python helper logs today; the workflow run log loses the per-step Python
traceback in favour of an HTTP error code. We keep the same shape, move
where the engineer looks for the detail.

---

## 3. pg_cron / scheduled jobs — moving scheduled pulls into Supabase

### What this is

`pg_cron` is a Supabase-supported Postgres extension that schedules SQL
statements inside the database. The candidate jobs are our `cron:` blocks
in `.github/workflows/*.yml`:

- `espn-supabase-sync.yml:11-13` — daily 11:30 UTC (06:30 CT).
- `fantasycalc-drift.yml:13-18` — daily 11:45 UTC.
- `cbsros-supabase-sync.yml:11-14` — weekly Wednesday 11:00 UTC.
- `source-vintage-check.yml:5` — hourly.
- `rebuild-chain.yml:11-17` — `workflow_dispatch` only (already not on a
  cron; not a candidate).
- `pages.yml`, `preview.yml` — deploy workflows; not candidates.
- The host-side cron `source-pull-watchdog` (`docs/watchdog.md` §Schedule)
  is a separate machine cron, not a candidate for pg_cron (it reads local
  pull outputs).

### What it would replace

- The four scheduled Actions workflows above (each replaces the `cron:`
  block with `select cron.schedule('name', 'cron-expression', $$ ... $$);`).
- The worker's local `cron` for `source-pull-watchdog` cannot move to
  `pg_cron` (it reads from local pull outputs on the worker's machine).

### What we lose (the explicit visibility reduction)

- **GitHub Actions run page** — the single timeline Jeremy uses to review
  pipeline health. pg_cron jobs do not appear in `pipelines/build_github_actions_status.py`'s
  enumeration (`build_github_actions_status.py` lists 7 workflows × 6 calls;
  the page badge would just lose four cards). A `cron.job_run_details`
  table in Postgres is the equivalent surface; the dashboard would have to
  be wired to it.
- **Native GitHub Actions alerts** — the cron start logs, the failed-run
  emails, the badge on the README. `AGENTS.md` says
  "default GitHub emails: unknown" for the current chain-failure case
  (`docs/risk-register.md` GAP-035), so this loss is partially already paid;
  but a working alert path today is "Action failed → Jeremy's GH email";
  pg_cron gives no equivalent out of the box.
- **Per-job retention / artifacts** — `rebuild-chain.yml:148-158` uploads
  the `output/reviewed/` review JSONs as workflow artifacts (JEG-113,
  retention 14 days). pg_cron has no equivalent artifact store; the data
  has to live in a Postgres table or a Supabase Storage bucket.
- **Cron slip visibility** — `docs/risk-register.md` GAP-046 documents
  that "Scheduled workflows start up to about 6 hours after their cron
  time, so freshness limits have no slack accounted for" (ESPN cron 11:30
  UTC ran at 17:26 and 16:45 UTC). On GitHub Actions this slip is visible
  from the Actions log timestamps. pg_cron runs inside the database; the
  slip is visible only if we wire `cron.job_run_details` into the
  dashboard. Without that wiring, the slip becomes invisible.
- **Cron expression audibility** — the workflow file is in the repo
  (`espn-supabase-sync.yml:11-13`); a code reviewer can read the schedule.
  pg_cron schedules live in `cron.job`; they require a separate read
  surface. We can write the schedule as `select cron.schedule('espn-supabase-sync',
  '30 11 * * *', $$ ... $$);` in a migration file so the schedule is
  versioned — but this is more discipline than today.

### What we keep

- **Local cron `source-pull-watchdog`** — must stay (it reads local pull
  outputs by absolute path; `docs/watchdog.md` §Scope rule).
- **GitHub Actions deploy + workflow_dispatch** — `rebuild-chain.yml`,
  `pages.yml`, `preview.yml` stay on GitHub. The cron jobs are pure
  write-side.

### Stability gain

- **Single infra plane** — pull, save, verify, and freshness rollup all
  live in the same database. A Supabase outage is the same outage, not
  three. Today an Actions runner hiccup and a Supabase hiccup are two
  independent failure modes.
- **No GitHub Actions minute budget** — long pull jobs (ESPN scraping
  ~5–10 min, GAP-046 cron slip shows 6-hour starts) eat into GitHub's
  free-tier minutes; pg_cron is gated only by Postgres CPU.
- **Tighter scheduling** — pg_cron's resolution is one minute and runs
  on the database clock; Actions cron is "best effort within about an
  hour" (GAP-046).
- **Atomic chain start** — today `source-vintage-check.yml` finishes, then
  `if: steps.check.outputs.changed == 'True'` dispatches
  `rebuild-chain.yml` via `gh workflow run`
  (`source-vintage-check.yml:46-52`). The dispatch is best-effort and
  racey (the dispatch itself takes seconds and the rebuild reads
  potentially-stale data). A pg_cron trigger that calls the rebuild chain
  RPC directly would be atomic.

### Cost / complexity

- pg_cron requires the extension to be enabled in the Supabase project;
  `docs/architecture-current.md` §Supabase flags "RLS and pg_cron state
  are unverified in the handoff and must not be assumed". This needs a
  verify step before any schedule lands.
- The cron bodies today are Python scripts in the repo. pg_cron schedules
  SQL or stored procedures — the Python work has to be either (a) called
  from a SQL wrapper that invokes `pg_net`/`http_get` to a Python runner,
  or (b) ported to plpgsql. Option (a) re-introduces the GitHub-Actions-
  style HTTP hop we were trying to remove; option (b) is a real port.
- **The verification path has to be re-built.** Today every cron workflow
  runs `make validate`-equivalent checks (`espn-supabase-sync.yml:43-56`
  "test -s /tmp/espn_projections.csv" + floor-of-100 rows). pg_cron jobs
  need to write their results to a status table the same dashboard reads.

### Visibility reduction (explicit per ticket)

**This is the largest visibility-reduction of the four features.** The
Actions run tab is the only working timeline of pipeline events today
(JEG-109 + GAP-035 = "no notify/issue/webhook step in any workflow").
Moving four scheduled jobs into pg_cron with no compensation removes 4/7
of those timeline cards. **Mitigation required before adoption:**

1. Wire `cron.job_run_details` into a `public.scheduled_job_runs` rollup
   and feed it into `dist/modules/pipeline-checkpoints.json` (the same
   artefact `build_pipeline_checkpoints.py` writes).
3. Update `pipelines/build_github_actions_status.py` to read the pg_cron
   rollup too — keep the workflow-health dashboard surface the same.
2. Wire a `NOTIFY scheduled_job_failed` channel to a tail/buffer the
   dashboard ingests. The cron body raises on failure; the channel fires;
   the dashboard records.

Until the mitigation is built, **pg_cron adoption is the only one in this
document that I would say "do not pay straight up"** — the visibility cost is
large and the gain is mostly operational (one infra plane), not
correctness-related.

**Net visibility impact: high, mitigatable.** With the wiring above, the
visibility is equivalent. Without it, four of seven workflow cards
disappear from the dashboard Jeremy uses daily.

---

## 4. Constraints as guards — the fail-closed layer JEG-104 proved we need

### What this is

Postgres UNIQUE / CHECK / NOT NULL / FOREIGN KEY / EXCLUSION constraints,
plus RLS posture. The constraints are the last guard that survives a buggy
save call, a botched trigger, or a future puller rewrite — they are the
"even if every line of Python is wrong, the database still refuses the
bad row" layer.

### JEG-104 was a constraint bug — what the class deserves

`docs/claude-log.md` lines 3–16 (JEG-104 migration replay correction):
migration 005 originally tried to drop a UNIQUE constraint and CREATE a
replacement, but the original SQL dropped the *index* of an inline-named
constraint without preserving the replacement. Both tests in
`tests.test_migrations` failed; the suite is wired into `make test-unit`;
the fix is one-line (`ALTER TABLE ... DROP CONSTRAINT IF EXISTS ...`).

The class: **constraints as guards are real, but only as strong as the
migrations that maintain them.** A constraint that doesn't compile or
that conflicts with a sibling is the same shape of bug as the savers
they're guarding — invisible until the next write. The deliberate pass
this section proposes is: catalogue every existing constraint on the
five writer tables and the audit table, prove each one catches the bug
it names (the standing rule from `AGENTS.md` — "Every regression guard
must prove it catches the bug it names"), and add the ones we are
currently missing.

### Existing constraints worth re-confirming (each cited)

- `public.source_trade_values_bake_version_uidx` — 9-column unique index
  on `(source, variant, scoring, league_teams, qb_slots, season, week,
  player_key, bake_id)` (`migration 004`). This is the only arbiter for
  the three versioned writers (USAT, FP, FC). Gap test: assert that a
  duplicate `(source, week, player_key, bake_id)` insert returns 23505.
- `public.source_trade_values_grain` — bake-aware legacy grain on
  `(source, player_norm, scoring, league_teams, qb_slots, season, week,
  variant, bake_id)` (`migration 005`). Catches the ambiguous-name
  dedupe case the original GAP-023 index bug had. Gap test: assert that
  two distinct `player_norm` rows for the same `(source, variant, scoring,
  ..., week, bake_id)` would have been blocked pre-migration-005 (i.e. a
  synthetic row that pre-dates the migration is the right regression).
- `public.pipeline_write_audit_run_id_key` — UNIQUE on `run_id` so the
  PATCH `?run_id=eq.X` never hits multiple rows (`migration 001` step 3).
- `public.pipeline_write_audit_operation_check` — CHECK on `operation IN
  ('insert','upsert','delete','update')` (`migration 001` step 4).
- `public.pipeline_write_audit_* NOT NULL` — `run_id`,
  `writer_identity`, `source`, `operation`, `table_name`, `started_at`,
  `created_at` (`migration 001` step 5). The writer always provides
  these; the docstring of migration 001 step 5 is explicit: "If it ever
  does fail, that itself is a signal of corrupt audit data — investigate,
  do not weaken the constraint."
- CHECK on `cbs_trade_values.scoring IN ('standard','half_ppr','ppr')`
  (cited at `save_espn_cbs_references.py:36-38` "the cbs_trade_values
  CHECK requires scoring in ('standard','half_ppr','ppr')"). Enforces the
  CBS QB representation decision (one row per scoring from a single 1QB-4
  column).
- `public.pipeline_write_audit RLS` — enable, no public policies
  (`migration 001` step 6). Service-role bypass; anon/authenticated
  denied.

### Constraints that would replace real scripts

**(a) `NOT NULL` on `_writer_identity` for new rows — replace the writer
helper's "audit unavailable, proceeding without audit" warning.**

- `save_usatoday_references.py:393-395` — `try: audit = WriterAudit(...)`
  / `except Exception as e: print("Warning: audit unavailable, proceeding
  without audit", flush=True); audit = None`. Same pattern is in the
  other five savers (`save_espn_cbs_references.py`,
  `save_fantasypros_references.py`, etc.).
- A `CHECK (_writer_identity IS NOT NULL)` (or `NOT NULL` enforced via
  trigger that fills it from `current_setting('weaver.identity', true)`)
  on each writer table turns the "Warning" into a hard refusal. The
  writer helper's try/except can be removed.
- Negative test: write to `source_trade_values` with `_writer_identity =
  NULL` and assert 23502 / 23514 (NOT NULL violation). The migration 001
  step 5 docstring explicitly refused to add this ("It does NOT make
  _writer_identity / _run_id / _written_at NOT NULL on the data tables.
  Historical rows predate the audit system and have no provenance;
  inventing sentinel values would corrupt the 'undeclared write'
  detection"). So the constraint must be **trigger-mediated** (default
  from current_setting), not bare NOT NULL — preserving the migration 001
  decision that NULL = unaudited.

**(b) CHECK on `(source, scoring)` combinations — replaces the
in-Python scoring-suitability check.**

- `save_espn_cbs_references.py:34-53` (the CBS QB scoring decision
  docstring) — "Alternatives rejected: scoring=NULL violates the table
  CHECK". A wider CHECK on `(source, scoring)` combinations prevents the
  FantasyCalc writer from accidentally writing `scoring='half'` (FP label)
  instead of `'half_ppr'` (DB label) — `check_source_vintage.py` already
  documents the label drift as a chronic concern.
- Negative test: insert with `source='cbs', scoring='std'` and assert
  constraint violation (CBS does not publish a 'std' label).

**(c) FOREIGN KEY on `player_key` → `public.players(player_key)`.**

- The identity authority is `public.players`
  (`docs/pipeline-rules.md` §1 "Naming authority"). Every writer inserts
  into a `player_key` column (`save_usatoday_references.py:195`,
  `save_espn_cbs_references.py:103`). The Python saver already fails
  closed if `resolve_name` returns None
  (`save_espn_cbs_references.py:159-187`). A FK is a second line of
  defence: a row with a `player_key` not in `players` is refused by the
  engine.
- Negative test: insert with `player_key=999999999` and assert FK
  violation. The current behaviour would write a 999999999 row and surface
  it only at `make supabase-import` time.

**(d) CHECK on vintage monotonicity within a write.**

- `check_source_vintage.py:76-79` — "Fail closed: mixed `date_column`
  values" / "Fail closed: mixed week values". This is enforced today as
  a fail-closed Python check *at read time*. A CHECK `(DISTINCT
  source_content_date) <= 1` per write batch (or a row-level CHECK
  against the prior row's date) would catch the case at write time.

**(e) EXCLUSION constraint on bake_id uniqueness for a given source +
  week + content_date.**

- The current `source_trade_values_bake_version_uidx` allows two bakes
  per `(source, week, player_key)` — by design (multiple immutable bakes
  per week, `migration 004` rationale). An EXCLUSION constraint that
  prevents two bakes with the *same content_date* for the same `(source,
  week, player_key)` would catch re-ingests of unchanged content
  silently creating new bake rows. The "unchanged content skips
  quietly" rule (`docs/pipeline-rules.md` §7a) is enforced in Python
  today (`save_usatoday_references.py` and the FP / FC equivalents); a
  constraint moves the guard into the engine.
- Negative test: insert two distinct bakes with the same
  `(source, week, player_key, source_content_date)` and assert
  exclusion violation.

**(f) CHECK on `pipeline_write_audit.metadata` shape.**

- The audit table's `metadata` JSONB column stores operation-specific
  context (`docs/SUPABASE_WRITER_AUDIT.md` row 14). Today there is no
  shape constraint. A CHECK that `metadata ? 'size' AND (metadata->>'size')::int > 0`
  would catch "audit row written with zero rows" — a real shape of bug
  when a saver's row-count arithmetic goes wrong.
- Negative test: PATCH `row_count=0` on a fresh audit row and assert
  constraint refusal.

### Stability gain

- Every existing constraint already caught (or would have caught) a real
  bug — the migration 005 / 006 chain is the proof. Adding the four above
  tightens the same guarantee to four more bug shapes.
- The Python fail-closed paths can be deleted because the database
  enforces the same rule; the saver becomes shorter, the
  test-as-fail-closed-proof becomes shorter, and the audit story is
  simpler.

### Cost / complexity

- Each constraint requires a migration. The migration template is
  identical to migration 001 step 4 (the operation CHECK); the rest is
  picking the right column lists.
- Each constraint requires a negative test that proves it catches the
  bug. `AGENTS.md` standing rule: "Every regression guard must prove it
  catches the bug it names." That is the bar.
- FK on `player_key` requires that `public.players.player_key` is the
  declared primary key. Verified: `docs/supabase-source-mapping.md` line
  86 "numeric player_key (bigint)"; `pipelines/lib/canonical_players.py`
  reads from this column. **UNVERIFIED on this checkout:** the actual
  `pg_constraint` row on `players.player_key` PK. Should be verified in a
  pre-migration step.

### Visibility reduction (explicit per ticket)

- A constraint refusal surfaces as a Postgres error in the saver, which
  surfaces in the Actions run log. No visibility cost — same path as
  today, just one layer down.
- The constraint is the *truth* of the data shape. The Python "fail-closed"
  prints become shorter; the engineer has to read the error code (e.g.
  `23514 check_violation`) rather than a Python message. This is the same
  shape of trade as RPCs in §2.

**Net visibility impact: very low.** The Actions log gains an HTTP error
code, loses a Python traceback; same information.

---

## 5. Ranked adoption order

The ranking balances correctness gain vs visibility cost vs implementation
effort, with a hard line on "no step that removes visibility from Jeremy's
daily review path until the replacement surface exists".

### Tier 1 — adopt first (correctness gain, near-zero visibility cost)

1. **Constraints as guards — §4 items (a) NOT NULL via trigger, (c) FK on
   player_key, (f) CHECK on metadata size.**
   - Why first: cheapest migrations, smallest test surface, biggest
     correctness return. JEG-104's whole point is that the constraint
     layer is the last guard that survives a buggy saver — every writer
     table deserves the basic FK + NOT NULL pair.
   - Visibility cost: very low; the Actions run log still tells the
     story, just with a Postgres error code.

### Tier 2 — adopt after Tier 1 (correctness gain, low visibility cost)

2. **Postgres functions / RPC — §2 item (a) consolidated versioned upsert
   and (b) audit-wrapped write.**
   - Why second: directly addresses the JEG-104 / GAP-023 / GAP-012 class
     of bugs (multiple writers re-implementing the same upsert dance
     each with their own slightly-wrong knowledge of which index
     arbitrates which grain). One RPC owns the dance; the saver is a
     row-builder + RPC call.
   - Visibility cost: low; the `pipeline_write_audit` row carries the
     same metadata today.

3. **Constraints as guards — §4 items (b) CHECK on `(source, scoring)`,
   (d) CHECK on vintage monotonicity, (e) EXCLUSION on bake-id
   uniqueness per content_date.**
   - Why third: depends on §2 (b) being in place so the audit row is
     always present when the constraint fires (so we can attribute
     failures). Also depends on the trigger-mediated default for bake_id
     (§1 (b)) so the EXCLUSION can rely on a single bake_id scheme.

### Tier 3 — adopt after Tier 2 (correctness gain, but visible re-wiring)

4. **Database triggers — §1 items (a) validate-on-write, (b)
   auto-stamp vintages, (c) derived rollups.**
   - Why fourth: depends on §4 NOT NULL via trigger (Tier 1) and §2 RPCs
     (Tier 2) being in place. Triggers alone, without the RPC, push too
     much behaviour into the engine before the call-site failures are
     consolidated.
   - Visibility cost: medium. Needs the "trigger-side log" surface wired
     into `dist/modules/pipeline-checkpoints.json` so the
     `build_github_actions_status.py` / dashboard path keeps showing
     what happened.

### Tier 4 — adopt last, with a separate visibility-mitigation track

5. **pg_cron — §3 (entire section).**
   - Why last: largest visibility cost; needs the
     `cron.job_run_details` rollup, the `NOTIFY scheduled_job_failed`
     channel, and the dashboard update before any schedule moves.
   - **Hard prerequisite:** the dashboard read for the four cron jobs
     (`espn-supabase-sync.yml`, `fantasycalc-drift.yml`,
     `cbsros-supabase-sync.yml`, `source-vintage-check.yml`) must be
     wired *before* any schedule moves. Until then, "do not pay
     straight up" — the visibility cost is too high.
   - Once Tier 1–3 are in place and the dashboard surface is wired,
     pg_cron becomes a single infra-plane win rather than a visibility
     regression.

### Explicitly NOT recommended in this ticket

- **Force RLS on the writer tables.** Migration 001 step 6 explicitly
  forbids this ("DO NOT use FORCE RLS here. ... would break service_role
  pipeline writes"). Any future recommendation to enable FORCE RLS is a
  stop-the-line event.
- **Drop the existing migrations (004 / 005 / 006).** They are the
  proof that the constraint layer works; they stay.
- **Replace `WriterAudit` with bare RPCs without the audit-row contract.**
  The audit row is the durable bridge between Python and engine; without
  it the RPC path is the same invisibility problem pg_cron has.

---

## 6. Process entry — appended to `docs/claude-log.md`

(The new entry is committed in the same change as this file. Per
`AGENTS.md`: "Any session that changes anything in this repo appends an
entry to `docs/claude-log.md` before it ends.")

The session produced one file change only (`docs/supabase-features-recommendation.md`).
No code, no schema, no workflow edits. No DB access attempted.

---

## 7. Lane handoff note

(Written as `lanes/inbox/minimax/JEG-110-supabase-features.md`. No code
or schema changes were made on this branch; the only commit is the doc
above plus the log entry in §6.)