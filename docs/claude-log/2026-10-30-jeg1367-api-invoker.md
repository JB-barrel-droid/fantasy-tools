## 2026-10-30 - JEG-1367 Supabase advisor: api views to security_invoker

Contract: write (not apply) one migration that clears the advisor's 11 SECURITY
DEFINER api views and 4 mutable-search_path functions without changing anyone's
access, plus rollback and a dry-run report.

### Verified (check named)
- Advisor findings and live definitions, grants, policies: Supabase `get_advisors`
  and read-only catalog SQL on iskiybsimubiujwuchsl, 2026-10-30 02:15 UTC.
- No anon or authenticated REST request to any api view on 2026-10-25, 10-28 or
  10-29: edge_logs grouped by JWT role and path.
- get-values and mcp read only site files: `rg` over supabase/functions.
- Same rows per role through all 12 api views before, after and after rollback;
  rollback restores reloptions, ACLs, policies and function config; flipping the
  views alone does change anon's rows: `python3 -m unittest
  tests.test_jeg1367_api_invoker_migration` on a local Postgres 16 copy.

### Claimed, not confirmed
- Behaviour on the live Postgres 17 database: not applied; needs Jeremy's yes.
- The advisor clearing the 15 findings after apply: re-run get_advisors then.
