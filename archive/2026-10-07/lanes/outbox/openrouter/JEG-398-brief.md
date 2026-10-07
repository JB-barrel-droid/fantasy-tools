# Brief: JEG-398 — evidence-preserving cleanup of duplicate week-3 runs

## Task
Write the exact SQL transaction(s) for cleaning up the duplicate
overnight backfill runs. Output SQL code blocks only, ordered as runbooks
(step 1 = evidence export, step 2 = cleanup, step 3 = hardening). Do not
apply anything — Roman reviews and runs them in the SQL editor.

## Context (verified live 2026-10-05)
`public.weekly_dashboard_runs` holds 4 runs (all season 2026):
- three week-3 runs created within 33 seconds overnight: one with 0 signal
  rows, two with 402 rows each; the 402-row signal sets point at a run that
  is NOT the current one;
- one week-4 run, is_current=true, 390 signal rows (the live one — DO NOT
  TOUCH it or its signals).
Backfilled week-3 signal rows have `position IS NULL` (the loader now maps
`position` from the row's `pos`, but history is unrepaired). No FK from
signals.run_id to runs; no unique constraint on (run_id, player_key).
RLS is ON with service_role-only policies (dashboard owner bypasses RLS).

## Requirements
1. Step 1 — evidence export (SELECTs only): run IDs, week, created_at,
   is_current, manifests, per-run signal counts, per-run player_key-set
   hashes (e.g. md5 of string_agg ordered keys), and a position-NULL count
   per run. These outputs are the audit record — nothing is deleted before
   they are captured.
2. Step 2 — cleanup, in ONE transaction: delete the empty run; of the two
   populated week-3 runs keep ONE (state how to pick: prefer the run whose
   signals are currently referenced / the richer manifest, and say exactly
   how the SQL identifies it — do not hardcode UUIDs; select by week +
   row-count ranking); delete child signals BEFORE parent runs; assert
   expected IDs/counts with RAISE EXCEPTION guards before COMMIT. If any
   guard fails the whole transaction rolls back.
3. Step 3 — repair + hardening: backfill `position` from `signal->>'pos'`
   on remaining week-3 rows, but ONLY after validating values against an
   allowlist ('QB','RB','WR','TE') and reporting rows where pos is absent or
   inconsistent (separate SELECT first, then the guarded UPDATE).
   Add `FOREIGN KEY (run_id) REFERENCES public.weekly_dashboard_runs(run_id)`
   and `UNIQUE (run_id, player_key)` — with pre-checks that existing data
   satisfies them (queries included; if violated, report instead of adding).
4. Every destructive step must re-assert `week = 3` (never touch week 4) and
   re-assert the target run is NOT is_current.

## Output
- Three ordered SQL runbooks with comments. No placeholders — every
  statement runnable as-is except where you explicitly mark a value to fill
  from Step 1's output.
- State what you would do if the two 402-row sets turn out to have
  DIFFERENT content hashes (keep both? keep richer? — decide and justify).
