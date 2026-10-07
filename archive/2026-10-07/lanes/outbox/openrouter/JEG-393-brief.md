# Brief: JEG-393 — atomic promotion RPC for weekly dashboard runs

## Task
Write a complete, ready-to-apply Postgres migration that makes publishing a
weekly dashboard run atomic. Do NOT apply anything — output SQL only, as a
code block, plus the exact loader change as a unified diff. Roman reviews and
applies.

## Context (verified live ground truth, 2026-10-05)
- Tables: `public.weekly_dashboard_runs` (run_id uuid PK, week int, season int,
  created_at timestamptz, source_manifest jsonb, is_current bool) and
  `public.weekly_dashboard_signals` (run_id uuid, player_key text, position
  text, team text, signal jsonb, created_at timestamptz). No FK currently.
- View `public.v_current_weekly_signals` = runs JOIN signals WHERE is_current.
- Current publisher (`pipelines/load_weekly_dashboard.py`) does, in order:
  1. INSERT run (is_current=false), 2. batch INSERT signals, 3. read back and
  count-verify, 4. PATCH all other runs is_current=false, 5. PATCH new run
  is_current=true. Steps 4–5 are two separate REST calls — a crash between
  them leaves zero current runs (view empty) or two loaders can leave two
  current runs (view mixes weeks).
- RLS is ON on both tables; service_role has SELECT/INSERT/UPDATE policies;
  anon has no access to base tables. The loader authenticates as service_role.

## Requirements
1. A `SECURITY DEFINER` function, e.g.
   `public.promote_weekly_dashboard_run(p_run_id uuid, p_expected_signals int)`:
   - fixed `search_path`, schema-qualified tables;
   - take a transaction-scoped advisory lock so concurrent promotions serialize;
   - validate: candidate exists, is currently NOT current, has exactly
     p_expected_signals signal rows, and its (season, week) is NOT older than
     the current run's (season, week) — reject regressions;
   - clear is_current on ALL runs, then set the candidate current — one
     transaction, no zero/two-current window visible to readers.
2. `REVOKE ALL ON FUNCTION ... FROM PUBLIC, anon, authenticated;`
   `GRANT EXECUTE ... TO service_role;`
3. Partial unique index as a backstop (only safe with ≤1 current row — note
   the precondition check in a comment):
   `CREATE UNIQUE INDEX weekly_dashboard_one_current ON public.weekly_dashboard_runs (is_current) WHERE is_current;`
4. Loader diff: replace the two PATCHes with one RPC call
   (`POST /rest/v1/rpc/promote_weekly_dashboard_run` with run_id and count).
   Keep the pre-promotion read-back count check in the loader.

## Output
- The full migration SQL in one code block (function + revoke/grant + index),
  with a header comment stating the precondition (≤1 current row).
- A unified diff for the loader change.
- A short test plan: kill between insert and promote; two concurrent
  promotions; older-week promotion attempt — expected outcome for each.
- Flag anything one-way-door.
