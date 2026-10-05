# OpenRouter lane result — JEG-395

_Model: z-ai/glm-5.3-flash. Review-only unless the brief says otherwise. Roman integrates; OpenRouter results never merge/push/deploy._

---

# J-395 Audit Probe Plan — Weekly Backend Read Path

Note before the probes: your brief says "2 base tables, 2 views" but requirement 3 says "any other exposed view." The SQL inventory in P1 may surface more views; the REST probes must cover everything P1 finds, not just the 4 named objects. The plan below is the 4-object baseline plus a conditional extension.

---

## Part A — SQL probes (dashboard owner, SQL editor)

**P1 — Inventory every view referencing the weekly tables**
```sql
SELECT DISTINCT
  v.view_schema, v.view_name,
  pg_get_userbyid(v.viewowner) AS owner,
  v.options  -- look for security_invoker=true presence
FROM pg_views v
JOIN pg_class c ON c.relname = v.view_name
JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = v.view_schema
WHERE pg_get_viewdef(c.oid, true) ~ '(weekly_dashboard_runs|weekly_dashboard_signals)'
ORDER BY 1,2;
```
Proves: complete attack surface for the read path, including any view the grants were never applied to (the known suspect: `public.v_current_weekly_signals`).

**P2 — Exact grants on base tables + discovered views**
```sql
SELECT table_schema, table_name, grantee, privilege_type
FROM information_schema.role_table_grants
WHERE (table_name IN ('weekly_dashboard_runs','weekly_dashboard_signals',
                      'v_current_weekly_signals','current_weekly_signals'))
   OR (table_name IN (SELECT view_name FROM P1_result))
   OR (table_schema='api')
ORDER BY 1,2,3;
```
Proves: exactly which roles hold what, without relying on memory of what was revoked. Do **not** filter to anon/PUBLIC/authenticated only — grant to a parent role (e.g., a group role) is how leaks hide.

**P3 — View owners + security flags**
```sql
SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner,
  c.reloptions, v.haslogs
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_views v ON v.schemaname=n.nspname AND v.viewname=c.relname
WHERE c.relname IN (SELECT view_name FROM P1_result) OR n.nspname='api';
```
Proves: `security_invoker` status (pg_views.options shows it only if set; absence = security_definer/owner-rights, meaning view owner's RLS bypass applies). Also verify owner is NOT a superuser and does NOT hold table privileges you don't want transitive (owner's rights define what the view can read — see Limits §7).

**P4 — RLS policy definitions**
```sql
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE tablename IN ('weekly_dashboard_runs','weekly_dashboard_signals');
-- plus the critical negative check:
SELECT relname, relrowsecurity, relforcerowsecurity
FROM pg_class WHERE relname IN ('weekly_dashboard_runs','weekly_dashboard_signals');
```
Proves: RLS is enabled **and** not disabled by an owner-level `FORCE ROW LEVEL SECURITY` omission nuance — more importantly, whether the table **owner** (whoever runs the view under definer rights) bypasses RLS entirely (owners bypass RLS unless FORCE is set). If a view is definer-owned by the table owner, RLS is irrelevant for that path.

**P5 — Functions/SECURITY DEFINER exposure**
```sql
SELECT n.nspname, p.proname, p.prosecdef, pg_get_userbyid(p.proowner)
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE pg_get_functiondef(p.oid) ~ '(weekly_dashboard_runs|weekly_dashboard_signals)';
```
Proves: SECURITY DEFINER functions are the classic bypass RLS grants never fix.

**P6 — PostgREST exposed schemas (server config, not SQL):** read from dashboard Settings → API → Exposed schemas. Record the literal list.

---

## Part B — REST probes (from a shell; no `Authorization` header = anon)

Substitute `{TOKEN_AUTHED}` only if available. Run each twice if both JWTs exist.

```bash
# R1 — public base table, anon
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://iskiybsimubiujwuchsl.supabase.co/rest/v1/weekly_dashboard_runs?select=*&limit=1'
# R2 — public base table #2, anon
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://iskiybsimubiujwuchsl.supabase.co/rest/v1/weekly_dashboard_signals?select=*&limit=1'
# R3 — public schema view (the unaddressed one) — full body, not just status
curl -s -w '\n%{http_code}\n' \
  'https://iskiybsimubiujwuchsl.supabase.co/rest/v1/v_current_weekly_signals?select=*&limit=1'
# R4 — api view, anon
curl -s -w '\n%{http_code}\n' -H 'Accept-Profile: api' \
  'https://iskiybsimubiujwuchsl.supabase.co/rest/v1/v_current_weekly_signals?select=*&limit=1'
# R5/R6 — repeat R1–R4 with -H "Authorization: Bearer $TOKEN_AUTHED"
# R7 — schema USAGE confirmation via PostgREST itself:
curl -s -w '\n%{http_code}\n' -H 'Accept-Profile: api' \
  'https://iskiybsimubiujwuchsl.supabase.co/rest/v1/'   # OpenAPI root; 200 + api spec = USAGE + exposure
```

R1/R2 must capture the body too, not `-o /dev/null` — the interesting failure modes (RLS present but empty result = 200 with `[]`) differ from 401. Use `curl -s -w '\n%{http_code}\n'` for all probes; the `-o /dev/null` in R1/R2 above is wrong for that reason — apply the R3 pattern everywhere. **Do not treat 200-with-empty-array on base tables as a leak, but flag it as RLS-visible-or-empty, which this audit cannot distinguish** (see Limits).

---

## Expected-results table (declare BEFORE observing)

| # | Object | Role | Expected | If otherwise |
|---|--------|------|----------|--------------|
| R1/R2 | public.weekly_dashboard_runs / _signals | anon | 401 or 403 (or 404 if not in exposed list) | **FAIL — leak** if 200 with rows |
| R3 | public.v_current_weekly_signals | anon | 404 (not exposed) or 401/403 | **FAIL** if 200 — definer view leaks |
| R4 | api.v_current_weekly_signals | anon | 200 + JSON array | 404 = missing USAGE/exposure; 401 = grant broken |
| R5/R6 | all four, authenticated | authed | same as anon (no authed grants were granted) | 200 on base tables = accidental authed grant |
| R7 | api OpenAPI root | anon | 200, spec lists only api view | 200 listing base tables = exposure config wrong |
| P2 | grants | — | anon: SELECT only on api view | any other anon/PUBLIC row = FAIL |
| P4 | RLS | — | enabled on both tables, policies scoped to service_role | owner-bypass without FORCE = latent definer risk |
| P5 | definer funcs | — | zero rows | any row = untested bypass path, extend REST probes to RPC |

---

## Verdict template

```
J-395 verdict — run date: ____
P1 views found: ____  P2 extra grant rows: ____  P5 definer funcs: ____
R1 __ R2 __ R3 __ R4 __ R7 __  |  authed R1-R4: ____ (or "untested")
Overall: PASS only if R1=R2∈{401,403,404}, R3∈{401,403,404}, R4=200,
P2 shows no anon/PUBLIC grants beyond api view, P5 empty.
Any deviation → FAIL, list deviation: ____
```

---

## What this audit cannot prove

1. **RLS filtering vs. empty data.** A 200 on a base table with `[]` cannot be distinguished from a correct RLS deny without service_role comparison. If needed, a follow-up probe with the service key (handled by Roman, results not recorded in this doc) would show expected row counts.
2. **Non-PostgREST surfaces.** Edge functions, scheduled jobs, any other API gateway hitting these tables are out of scope.
3. **JWT-forgery resistance.** We assume Supabase's JWT verification works; a crafted-JWT probe (`role=authenticated` claim without valid signature) is worth adding as one extra curl if Roman wants completeness — PostgREST should 401 it.
4. **Future drift.** Nothing here detects a later `GRANT SELECT ... TO PUBLIC`. This is a point-in-time snapshot.
5. **Column-level exposure** via the api view — R4=200 proves row access, not which columns leak.
6. **`public.v_current_weekly_signals` cannot be ruled in/out from SQL alone** if PostgREST's exposed-schema list isn't the live config; only R3's observed status settles it.
7. **View owner privilege transitivity**: if a view owner has broader base-table grants, definer views inherit them; P3+P4 show the pieces but inferring the effective privilege requires reading them together — flag for human judgment, not a boolean.

**One adversarial note on the brief itself:** it asserts security_barrier=true as fact for both views but P3 is the first thing actually verifying it — treat the brief's context section as claims, not findings, until P1–P6 confirm them.