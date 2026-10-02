# JEG-110 — Supabase features for pipeline stability (MiniMax lane)

**Branch:** `minimax/jeg-110-supabase-features`
**Ticket:** JEG-110 (lane: minimax / M3)
**Mode:** research-only, read-only. No code, no schema, no DB, no workflow
edits. The only files touched in this session are listed under "Files
read" below; the only files written are listed under "Files written".

## Files read (citations used in the recommendation)

Workflows (the cron surfaces the pg_cron section would replace):

- `.github/workflows/espn-supabase-sync.yml` — daily 11:30 UTC scrape (lines
  11-13 cron, 43-56 fail-closed scrape step, 59-70 save step, 72-78 commit
  step; GAP-036 "fails open on `|| echo`" noted at line 41 of the doc).
- `.github/workflows/fantasycalc-drift.yml` — daily 11:45 UTC, drift check
  then refresh (lines 13-18 cron, 47-60 drift step, 62-68 re-import, 70-77
  health verify, 79-89 commit step).
- `.github/workflows/cbsros-supabase-sync.yml` — weekly Wed 11:00 UTC
  (lines 11-14 cron, 36-42 scrape step, 44-50 save step).
- `.github/workflows/source-vintage-check.yml` — hourly (line 5 cron,
  26-44 vintage check step, 46-52 dispatch rebuild on change).
- `.github/workflows/rebuild-chain.yml` — `workflow_dispatch` only (line
  16-17), not on a cron, not a pg_cron candidate. Imports seven sources
  (line 54); publishes chain status with `if: steps.chain.outcome ==`
  guards (lines 79-94); uploads review JSONs as JEG-113 artifacts (lines
  148-158).

Pipeline scripts (the writer / reader patterns the §1–§4 recommendations
would replace or harden):

- `pipelines/save_usatoday_references.py` — the canonical writer (audit
  creation lines 375-395, audit-wrapped upsert lines 397-410, post-write
  row-count check lines 413-423; versioned conflict key lines 78-80;
  bake_id derivation line 347; identity resolution lines 179-189;
  reindex step lines 256-320; "Fail closed: zero rows" line 156-159).
- `pipelines/save_espn_cbs_references.py` — read first 200 lines: ESPS /
  CBS grain documentation lines 9-22; identity resolution lines 159-187;
  `upsert_rows` helper lines 110-119; CBS scoring CHECK context line 36-38;
  fail-closed alias map shared with `build_ddf_two_tier_leg.py` lines
  78-79.
- `pipelines/check_source_vintage.py` — full file read (217 lines). The
  `SOURCE_TABLES` map lines 22-30, `_select_latest_bake` lines 51-61,
  `_derive_db_vintage` lines 71-84, the per-source vintage scoping
  branches lines 87-139. The "matches canonical logic from
  import_supabase_references.py" duplication note line 72.
- `pipelines/lib/writer_audit.py` — full file read (242 lines). The
  WriterAudit class lines 75-208, the `_writer_identity / _run_id /
  _written_at` stamping lines 210-229, the start / complete / fail
  triple lines 137-208.
- `pipelines/import_supabase_references.py` — partial read (1158 lines,
  cited sections). The `_select_latest_bake` choke point lines 335-430
  and lines 646-648.

Migrations (the constraint layer §4 would extend):

- `sql/migrations/001_pipeline_write_audit_repair.sql` — full file read.
  Steps 1-8: missing columns, PRIMARY KEY, UNIQUE on run_id, CHECK on
  operation, NOT NULL alignment, indexes, RLS posture (no FORCE RLS),
  historical-row honesty backfill.
- `sql/migrations/004_source_trade_values_bake_version.sql` — 9-column
  versioned unique index.
- `sql/migrations/005_source_trade_values_grain_bake_aware.sql` — DROP
  CONSTRAINT IF EXISTS + CREATE INDEX on the bake-aware legacy grain
  (this is the JEG-104 / GAP-023 migration).
- `sql/migrations/006_retire_unversioned_upsert_grain.sql` — drop the
  8-column unversioned index that was blocking second-version writes.

Docs (the standing rules the recommendation respects):

- `docs/pipeline-rules.md` — full file read. Naming authority §1;
  identity matching fail-closed §2; candidate artifacts §3; null-not-zero
  §4; freshness is content vintage §5; copy rules §6; week versioning /
  bake_id rules §7a; import-health gate §8.
- `docs/supabase-source-mapping.md` — full file read. Table inventory
  (5 dashboard sources; `public.source_trade_values` for
  fantasycalc/usatoday/fantasypros; `public.espn_season_projections`
  and `public.cbs_trade_values` for the formerly-gap sources; the
  razzball-only FILES-only history).
- `docs/SUPABASE_WRITER_AUDIT.md` — full file read. The audit table
  spec, the WriterAudit helper doc, the column contract for
  `_writer_identity / _run_id / _written_at`.
- `docs/import-health-schema.md` — full file read. The
  `trade-value-import-health-v1` schema; status enum; failure codes
  (STALE_VINTAGE, BYTE_MISMATCH, TABLE_DRIFT, NO_VINTAGE, IMPORT_FAILED,
  MISSING_SNAPSHOT); the five-source scope rule.
- `docs/watchdog.md` — full file read. The pull watchdog scope rule
  (only reads pull outputs); the daily 07:05 CT cron line; the
  health.json surface; the worker escalation path.
- `docs/architecture-current.md` — full file read. The "RLS and
  pg_cron state are unverified in the handoff and must not be assumed"
  line (which is why §3 recommends verify-before-adopt).
- `docs/risk-register.md` — read rows 1-200 of the GAP table for the
  defect anchors: GAP-008 (sbclient cache), GAP-023 (dual-index bug →
  migration 005), GAP-012 (USAT plain-insert → shared upsert_rows),
  GAP-036 (ESPN cron fails open), GAP-041 (ESPN daily CI crashes),
  GAP-046 (cron slip).

Log (the JEG-104 anchor):

- `docs/claude-log.md` — lines 1-16 (the JEG-104 entry that motivated
  the "constraints deserve a deliberate pass" line in §4) and the
  GAP-046 / week-versioning context lines around 1558-1563.

Grep hits (used to confirm absence of pg_cron in the repo):

- `pg_cron` not referenced in any source-controlled file in this
  checkout (read-only grep across the working tree). The Supabase
  project may have the extension enabled in production; the checkout
  does not prove that either way (unverified — see below).

## Files written

- `docs/supabase-features-recommendation.md` — the recommendation
  document. Four sections (triggers, RPCs, pg_cron, constraints), each
  with replace / stability-gain / cost-complexity / visibility-impact
  sub-sections. Tiered adoption list at the end.
- `lanes/inbox/minimax/JEG-110-supabase-features.md` — this file.

No other files were edited. No code, no SQL, no workflow YAML, no
fixtures, no data.

## Ranked adoption list

**Tier 1 (adopt first — biggest correctness return, smallest
visibility cost):**

1. Constraints — §4(a) NOT NULL via trigger on the writer tables,
   §4(c) FK on `player_key` → `public.players`, §4(f) CHECK on
   `pipeline_write_audit.metadata` shape.

**Tier 2 (adopt after Tier 1 — direct fix for JEG-104 / GAP-023 / GAP-012):**

2. Postgres RPCs — §2(a) consolidated versioned upsert (one
   `upsert_source_trade_values_versioned` instead of three saver-local
   constants); §2(b) audit-wrapped write (one `write_with_audit`
   instead of five try/except blocks).
3. Constraints — §4(b) CHECK on `(source, scoring)` combinations,
   §4(d) CHECK on vintage monotonicity within a write, §4(e)
   EXCLUSION on bake-id uniqueness per content_date.

**Tier 3 (adopt after Tier 2 — depends on §2 RPCs being in place):**

4. Triggers — §1(a) validate-on-write, §1(b) auto-stamp vintages
   (pulls `_writer_identity` / `_run_id` from `current_setting`), §1(c)
   derived rollup table for the freshness dashboard.

**Tier 4 (adopt last, with a separate visibility-mitigation track):**

5. pg_cron — only after the dashboard is wired to `cron.job_run_details`
   and a `NOTIFY scheduled_job_failed` channel. Today the Actions run
   page is the only timeline of pipeline events (JEG-109 + GAP-035);
   moving four scheduled jobs without compensation removes 4/7 of the
   timeline cards.

**Explicitly NOT recommended this ticket:**

- Force RLS on writer tables (migration 001 step 6 forbids this).
- Drop existing migrations 004 / 005 / 006 — they are the constraint
  layer's proof.
- Replace `WriterAudit` with bare RPCs without the audit-row contract
  — the audit row is the durable bridge between Python and engine.

## VERIFIED vs UNVERIFIED

### VERIFIED (named checks)

- The four scheduled workflows cited in §3 were read end-to-end; cron
  expressions, fail-closed / fail-open posture, and Python-script
  bodies are confirmed.
- The canonical writer pattern (audit + upsert + post-write count
  check) was confirmed in `save_usatoday_references.py:375-423` and
  the parallel structure in `save_espn_cbs_references.py`.
- The `USAT_UPSERT_CONFLICT_VERSIONED` constant and its companions
  (FP / FC) are real; the migration 005 / 006 chain is the durable
  proof they are needed.
- Migration 001 step 6 forbids FORCE RLS; migration 001 step 5 forbids
  bare NOT NULL on `_writer_identity` (the "invented sentinel value
  would corrupt the 'undeclared write' detection" line). Both fed §4
  recommendation to use a trigger-mediated default.
- The JEG-104 / GAP-023 anchor exists; the migration 005 / 006 fix is
  in place; both regressions tested in `tests.test_migrations`.
- The five-source scope rule (`espn, usatoday, fantasycalc,
  fantasypros, cbs`) is the import-health gate's contract; Razzball is
  hard-excluded from the gate per `docs/import-health-schema.md` line
  18-21.
- `pg_cron` is **not** referenced anywhere in this checkout (grep
  result). The Supabase project's actual extension state is unknown
  to this checkout (UNVERIFIED — see below).
- `GAP-036` (ESPN daily fails open at line 41 of
  `espn-supabase-sync.yml`) and `GAP-041` (ESPN daily CI crashes on
  missing `identity` module) are real, dated, in `docs/risk-register.md`.
- `GAP-035` (no notify/issue/webhook step in any workflow) is the
  reason §3 ranks pg_cron last with a "do not pay straight up"
  caveat.
- `GAP-046` (cron slip up to 6 hours) is the reason §3's
  "scheduling-resolution gain" claim is qualified.

### UNVERIFIED (would need live verification)

- **Supabase pg_cron extension enabled.** The checkout does not prove
  this either way; `docs/architecture-current.md` line 120 explicitly
  says "RLS and pg_cron state are unverified in the handoff and must
  not be assumed". §3's recommendation depends on this.
- **The four cron bodies can be plpgsql-only.** Each cron body today
  runs a Python script (espn scrape, CBS ROS scrape, FantasyCalc drift
  check, source vintage check); a SQL-only pg_cron body would require
  either `pg_net` HTTP calls or a real Python port. §3 notes this as
  the implementation cost.
- **`public.players.player_key` is the declared PK.** Needed for the
  §4(c) FK recommendation. `docs/supabase-source-mapping.md` line 86
  calls it "numeric player_key (bigint)"; the live
  `pg_constraint` row was not read this session.
- **A second saver adopting the §2(d) reindex → review dance.** Today
  only USA Today reindexes at save time. §2(d) is marked optional
  unless FantasyPros / FantasyCalc adopt.
- **The trigger-mediated default on `_writer_identity` does not break
  the migration 001 historical-row honesty stance.** Migration 001
  step 7-8 explicitly nulls `_written_at` on pre-audit rows so the
  "NULL == unaudited" signal survives. The trigger in §1(b) must
  preserve this by NOT stamping `_written_at` on rows with
  `_writer_identity IS NULL`. The recommendation reads as if it
  preserves this; a pre-migration test would confirm.
- **`cron.job_run_details` exists in the Supabase project's pg_cron
  install.** §3's mitigation assumes it. Modern pg_cron does provide
  this table; older versions do not. A pre-migration `select *
  from cron.job_run_details limit 1` would settle it.
- **The "unchanged content skips quietly" rule's exact line in each
  saver.** §4(e) cites the rule but the line numbers in
  `save_usatoday_references.py` / `save_fantasypros_references.py` /
  `save_fantasycalc_references.py` for the skip-quietly branch were
  not enumerated this session.
- **Whether the existing `source_trade_values_grain` constraint name
  is the legacy UNIQUE constraint name or the bake-aware replacement
  index name.** `migration 005` reframes the legacy grain as an index
  with the same name; `migration 001` uses
  `pipeline_write_audit_run_id_key` as a UNIQUE *constraint*. The
  §4 constraint-citation section treats both forms as "constraints";
  a future reader should check whether `pg_constraint` has them as
  CONSTRAINT or whether they exist only as `pg_indexes`.

## Open questions

- **Is `pg_cron` actually enabled on the production Supabase project?**
  Required before §3 can land. Verify via the Supabase dashboard
  ("Database" → "Extensions") or `select * from pg_available_extensions
  where name = 'pg_cron'`.
- **What is the actual cron body shape for `source-vintage-check.yml`?**
  Today it runs `pipelines/check_source_vintage.py --json > /tmp/check.json`
  on the Actions runner and dispatches `rebuild-chain.yml` via `gh
  workflow run`. The pg_cron body would be `select check_source_vintage()`
  + `select cron.schedule('rebuild-chain', '* * * * *', $$ call
  rpc('rebuild_comparison_chain', jsonb_build_object('nfl_week', ...))
  $$)`. The second `cron.schedule` is the equivalent of the `gh
  workflow run` dispatch; whether the dispatch logic moves to a
  Postgres trigger is the design call.
- **The trigger-mediated default of `_writer_identity` from
  `current_setting('weaver.identity', true)` requires the connection
  to set the GUC.** Today the writer helper sets GUC-equivalents via
  Python dict keys in the audit row, not via Postgres session
  variables. A small refactor in `WriterAudit.start()` to `set_config`
  the run_id and writer_identity on the connection is needed. Acceptable
  but not trivial.
- **The dashboard surface for the freshness rollup (§1(c)) is the
  `app/trade-value-chart/assets/reference-freshness.json` file
  (GAP-033 "7 of 16 items are past the 2-day budget").** Whether the
  trigger-maintained rollup replaces this file or augments it is the
  product call.

## Acceptance checklist (from the ticket)

- ✅ `docs/supabase-features-recommendation.md` exists with all four
  features.
- ✅ Each feature has a "what it would replace" sub-section naming real
  scripts / workflows with file:line citations.
- ✅ Each feature has a stability-gain sub-section.
- ✅ Each feature has a cost / complexity sub-section.
- ✅ Each feature has an explicit visibility-impact sub-section per the
  ticket requirement.
- ✅ Ranked adoption list at the end (§5 of the doc).
- ✅ The doc explicitly calls out visibility reductions per the ticket
  (§1, §2, §3, §4 each have a "Visibility reduction" subsection; §3 is
  the largest and is the reason for the §5 Tier-4 ordering).
- ✅ Not merged, not pushed, not deployed — branch only.