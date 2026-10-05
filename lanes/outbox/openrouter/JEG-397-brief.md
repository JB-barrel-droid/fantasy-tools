# Brief: JEG-397 — public field list + freshness contract for the api view

## Task
Redesign the anon-facing weekly contract. Output: (1) revised
`CREATE OR REPLACE VIEW api.v_current_weekly_signals` with an explicit
allowlisted column list, (2) a new one-row status view
`api.weekly_dashboard_status`, both as SQL code blocks ready for the SQL
editor. Do not apply anything — Roman reviews and applies.

## Current state (verified live)
`api.v_current_weekly_signals` currently mirrors the public view column for
column:
```sql
CREATE OR REPLACE VIEW api.v_current_weekly_signals AS
SELECT r.season, r.week, s.run_id, r.created_at AS run_created_at,
       r.source_manifest, s.player_key, s.position, s.team, s.signal,
       s.created_at AS signal_created_at
FROM public.weekly_dashboard_runs r
JOIN public.weekly_dashboard_signals s ON s.run_id = r.run_id
WHERE r.is_current;
```
Problems: `source_manifest` exposes internal fields (absolute `bundle_path`,
loader version); `signal` is the whole engine JSON (unreviewed surface);
`WHERE is_current` means "latest published", not "the week the frontend
expects" — a stale-but-valid run looks healthy; previous-week comparison is
impossible from a current-only view.

## Requirements
1. Allowlist the anon view columns explicitly: season, week, run_id,
   run_created_at, a safe `bundle_built_at` (extract from source_manifest —
   do NOT expose the raw manifest), player_key, position, team, and an
   explicit list of signal fields you judge safe and sufficient for a
   signals board (name them; justify each exclusion of engine-internal
   fields like provenance internals).
2. New `api.weekly_dashboard_status`: exactly one row — published season/week,
   bundle_built_at, run_created_at (publication time), signal_count — servable
   even when zero runs are current (use aggregation so it never returns zero
   rows; include an explicit `has_current` boolean).
3. Keep it a pure view (no new tables). Previous-week comparison stays OUT —
   note it as a separate versioned contract, do not broaden this one.
4. Preserve the security posture already applied: the views must keep working
   with `security_invoker=false, security_barrier=true` and anon SELECT only
   (state the needed ALTER/GRANT lines if your rewrite needs them re-applied).

## Output
- Two SQL code blocks (allowlisted view + status view), each with a one-line
  purpose comment.
- The explicit field allowlist with one-line justification per included
  signal field and per excluded risky field.
- How the frontend distinguishes stale vs missing data using the status view.
