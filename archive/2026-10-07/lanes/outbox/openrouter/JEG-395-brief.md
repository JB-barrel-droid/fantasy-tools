# Brief: JEG-395 — anon read-path audit probe plan for the weekly backend

## Task
Produce a concrete, step-by-step audit probe plan that Roman will execute
(he holds the credentials). You cannot reach the database — output the exact
commands and the expected-results table. No DDL, no fixes; this is a
verification brief only.

## Context (verified 2026-10-05 via SQL editor as the dashboard owner)
- `api.v_current_weekly_signals` exists; anon has SELECT on it (verified
  `has_table_privilege('anon', ..., 'SELECT') = true`).
- `public.weekly_dashboard_runs` / `public.weekly_dashboard_signals`: RLS
  enabled; anon SELECT revoked (`has_table_privilege = false`); service_role
  has SELECT/INSERT/UPDATE policies.
- `public.v_current_weekly_signals` (the pre-existing public-schema view)
  was NOT addressed by the grants — unknown whether anon can read it.
- PostgREST serves the `public` and `api` (via Accept-Profile) schemas at
  https://iskiybsimubiujwuchsl.supabase.co/rest/v1/.
- Security model: views use security_invoker=false (owner's privileges),
  security_barrier=true.

## Requirements
1. SQL probes (run as dashboard owner in the SQL editor): inventory every
   view that references the weekly tables; list all grants on the two base
   tables and both views involving anon/PUBLIC/authenticated (exact query
   against information_schema.role_table_grants or pg_catalog); confirm view
   owners; confirm RLS policy definitions.
2. REST probes with a real anon JWT (no Authorization header = anon role):
   exact curl commands against each of the 4 objects (2 base tables, 2
   views — the api one with `Accept-Profile: api` header), recording HTTP
   status + body shape. Then the same with an authenticated JWT if one is
   available, else note it as untested.
3. A bypass checklist: schema USAGE for anon on `api`; any other exposed
   view/function selecting from the weekly tables; PostgREST schema exposure
   list.
4. Expected-results table: object × role → expected status BEFORE drawing
   conclusions (anon: 200 only on api.v_current_weekly_signals; 401/403/404
   elsewhere).

## Output
- Numbered probe steps, each with the exact SQL or curl and what it proves.
- The expected-results table.
- A verdict template: for each probe, PASS/FAIL criteria stated up front so
  Roman only fills in observed values.
- List what this audit CANNOT prove (be honest about limits).
