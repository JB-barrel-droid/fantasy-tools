# 03 — Supabase Current State (objects the connector can read/invoke today)

**Phase:** JEG-285 Phase 1 (Discovery / current-state inventory)
**Method:** read every file under `sql/migrations/` and `supabase/migrations/`; cross-checked the table list against `pipelines/import_supabase_references.py` (which enumerates the seven in-scope sources + their tables), `pipelines/gh_sbclient.py` (the runtime client surface used by every GH workflow), `pipelines/save_*_references.py` (writers), and `docs/supabase-source-mapping.md` + `docs/architecture-current.md:96–121`.
**Constraint:** read-only. No connection was opened. Every table below was named either in a committed migration file, in `docs/supabase-source-mapping.md`, or in code that calls it. **RLS and `pg_cron` state are unverified** (the handoff said this and `docs/architecture-current.md:120` repeats it; nothing in the repo changes the answer). Phase 2 must verify live before designing writes.

## Project + connector surface

**Supabase project** — `iskiybsimubiujwuchsl.supabase.co`, schema `public` (the `ross` schema holds Ross-league data only — draft results, keeper contracts, rosters — no source data, per `docs/supabase-source-mapping.md:53–55`).

**Read path the GH connector uses today** — `pipelines/gh_sbclient.py` is a thin `urllib`-based shim dropped on `PYTHONPATH` as `sbclient.py` by every GH workflow (`.github/workflows/*.yml` lines that copy it to `/tmp/gh_shim/sbclient.py`, e.g. `rebuild-chain.yml:45–47`). The shim exposes:

```text
get(sbclient_path, params="")             (single page, no pagination)
get_all(sbclient_path, params="", batch=1000)  (paginated, enforced order=id, line 62–77)
post(sbclient_path, body, params="", prefer="return=representation")
patch(sbclient_path, body, params)
delete(sbclient_path, params)
```

All calls use the bearer service-role key (`gh_sbclient.py:40–42`). **There is no anon-key path** in any GH workflow — every GH-side action is service-role. Local runs use the skill-bundled `~/workspace/skills/supabase-football-signal/bin/sbclient.py` (a compiled .pyc per GAP-008), read-only.

**What the connector CAN read/invoke today**
- `GET /rest/v1/<table>` with PostgREST filters (`?column=eq.value&select=…&order=…&limit=…&offset=…`). `get_all` paginates past the 1000-row cap.
- `POST /rest/v1/<table>` (insert / upsert with `Prefer: resolution=merge-duplicates`).
- `PATCH /rest/v1/<table>?filter` (targeted update — used by `WriterAudit.fail()` to set `failed_at`/`error_message` per `docs/SUPABASE_WRITER_AUDIT.md:65–74`).
- `DELETE /rest/v1/<table>?filter`.

**What the connector CANNOT do today** (Phase-1 read-only; flagging for Phase 2)
- No call to a Supabase Edge Function (`/functions/v1/...`) appears anywhere in `pipelines/`, `ops/watchdog/`, or any workflow.
- No call to a Postgres function (`/rest/v1/rpc/<funcname>`) by name appears in any workflow. The repo calls into `pg_cron` only by name in doc comments (`docs/architecture-current.md:120` notes `pg_cron` is unverified).
- No Management API call (DDL) by any GH workflow — every workflow that needs DDL changes tells the user to run them in the Supabase SQL editor (e.g. `sql/migrations/002_cbs_ros_projections.sql:3`, `sql/migrations/004_source_trade_values_bake_version.sql:18–20`).
- No realtime / websocket / storage path is used.

## Existing Supabase tables (read paths from this repo)

The tables below are referenced by `pipelines/import_supabase_references.py`, `pipelines/save_*_references.py`, or `pipelines/verify_import_health.py`. Counts and vintages are taken from `docs/supabase-source-mapping.md:102–111` (snapshot 2026-09-21; counts may have grown since).

### Trade-value source tables (the seven dashboard sources)

| Table | Sources it holds | Read by | Writer name in repo | Identity column | Vintage column | Migration that defines it |
|---|---|---|---|---|---|---|
| `public.source_trade_values` | `fantasycalc`, `usatoday`, `fantasypros` (all as `variant='as_published'`) | `import_supabase_references.py` (`SOURCE_TABLES` line 86–94), `verify_import_health.py` (`SOURCE_CONFIGS` line 66–121) | `pipelines/save_fantasycalc_references.py`, `save_usatoday_references.py`, `save_fantasypros_references.py` (and `refresh_fantasycalc_supabase.py` for the Week-4 reset) | numeric `player_key` (bigint) | `source_content_date` (NULL for fantasycalc — weekly snapshot, vintage carried by `week` column); `week` always | original Muse migration; evolved by `sql/migrations/004_source_trade_values_bake_version.sql`, `005_source_trade_values_grain_bake_aware.sql`, `006_retire_unversioned_upsert_grain.sql` |
| `public.espn_season_projections` | `espn` | `import_supabase_references.py`, `verify_import_health.py` | `pipelines/save_espn_cbs_references.py` (ESPN half — line 5–80 of that script) | numeric `player_key` | `espn_snapshot_date` (in CSV; mapped to `source_content_date`) | referenced in code; DDL not in this repo's `sql/migrations/` (table was DDL'd 2026-09-22 per `import_supabase_references.py:11–13` and `save_espn_cbs_references.py:5–7`) |
| `public.cbs_trade_values` | `cbs` (trade values, weekly) | `import_supabase_references.py`, `verify_import_health.py` | `pipelines/save_espn_cbs_references.py` (CBS half — same file, line 17–22) | numeric `player_key` | `source_content_date=NULL` (article date unknown; vintage carried by `week`); `week` always | same as ESPN — DDL not in this repo's `sql/migrations/`; created 2026-09-22 |
| `public.cbs_ros_projections` | `cbsros` (CBS ROS projections) | `import_supabase_references.py`, `verify_import_health.py` | `pipelines/save_cbsros_references.py` | numeric `player_key` | `cbs_snapshot_date` | `sql/migrations/002_cbs_ros_projections.sql` (committed; ran in Supabase SQL editor 2026-10-01) |
| `public.razzball_projections` | `razzball` | `import_supabase_references.py` (`DB_SOURCES` line 80, `SOURCE_TABLES` line 93); `verify_import_health.py` (`DB_SOURCES` line 54) | `pipelines/save_razzball_references.py` | numeric `player_key` | `razzball_snapshot_date` | `sql/migrations/003_razzball_projections.sql` (committed; **NOT YET RUN** — line 5 of that file, also GAP-030 — table created 2026-10-02 empty; first real save 692 rows per the GAP-030 update) |

### Sibling / derived / audit tables

| Table | Holds | Read by | Writer | Migration |
|---|---|---|---|---|
| `public.source_value_adjustments` | 96 rows; per-(source, scoring, position, tier) OLS affine fit cells (`alpha`, `beta`, `r_squared`, `method='ols_affine_pos_tier_hierarchy_v1'`) that produce the `bias_adjusted` variant | read at bake time by the bias-adjusted builders | the Muse-side `~/workspace/football-signal/trade-value/fit_source_variants.py` (not in this repo; per `docs/supabase-source-mapping.md:79–84` and `:127–131`) | pre-dates this repo |
| `public.pipeline_write_audit` | Write-audit trail | none yet by name — `pipelines/lib/writer_audit.py` POSTs + PATCHes on every successful/failed save | `pipelines/lib/writer_audit.py` (`WriterAudit.start/.complete/.fail`) | `sql/migrations/001_pipeline_write_audit_repair.sql` (committed; `DESIGNED — DO NOT EXECUTE` per its own header — the audit table exists but missing columns block every save; this is a known defect per GAP-014/GAP-018 in risk-register notes and the audit doc line 11–17) |
| `publisher_roster_assumptions`, `publisher_vorp`, `publisher_translated_values` | JEG-62 VORP translation tables | `pipelines/translate_via_vorp.py` + `pipelines/refresh_vorp_translation.py` (used by `make test-unit` per `Makefile:127`) | `pipelines/translate_via_vorp.py` (likely — not re-read in this audit) | `supabase/migrations/jeg62_vorp_translation.sql` (committed; not verified as run) |
| `public.players` | The naming authority: numeric `player_key`, `full_name`, `pos`, `team`. Read-only. | every pipeline that resolves identity (`save_espn_cbs_references.py:25`, `save_cbsros_references.py:14–17`, `import_supabase_references.py:148`, `lib/canonical_players.py`) | outside this repo | pre-dates this repo (handoff lists it, `docs/architecture-current.md:108`) |
| `fp_season_projections`, `fp_season_latest_norm`, `season_actuals_ytd`, `games`, `player_value_notes`, `projection_snapshots`, `player_identities`, `player_identity_aliases` | Surrounding domain objects (ECR, identity, season actuals) | documented in the handoff (`docs/architecture-current.md:106–120`); no repo writer reads them by name in the workflows inventoried here | outside this repo | pre-dates this repo |

### Hard-exclusion tables (never read by any pipeline)

- `vegas_season_totals`, `odds_history` (Vegas / prediction-markets; `HARD_EXCLUSIONS = ("vegas", "prediction_markets", "prediction-markets")` per `pipelines/import_supabase_references.py:97`).
- `ranker_rankings`, `rankers` (ECR rows; backstop at `pipelines/import_supabase_references.py:112–114` — "any source string smelling of ECR is excluded, always").
- `fp_season_kdst_projections` (K/DST ECR — hard-excluded by the import stage).

## Existing Supabase functions / cron jobs / edge functions (Phase-1 read-only findings)

**Functions** — No `CREATE FUNCTION` is committed in `sql/migrations/` or `supabase/migrations/`. The committed `supabase/migrations/jeg62_vorp_translation.sql` is DDL on tables only (no function body). Every repo writer is Python; there is no PL/pgSQL function the repo invokes by name.

**Cron jobs (`pg_cron`)** — **Unverified in this repo.** `docs/architecture-current.md:120` says "RLS and `pg_cron` state are unverified in the handoff and must not be assumed." Nothing in `sql/migrations/` or any committed file changes that. Phase 2 must verify by reading `cron.job` in Supabase.

**Edge Functions** — None committed in this repo. The repo has no `supabase/functions/`, `supabase/edge-functions/`, or equivalent directory. Phase 2 design starts from a clean slate on this surface.

## Existing Supabase management surfaces the repo already exercises

| Surface | Where in repo | Purpose |
|---|---|---|
| PostgREST read | `pipelines/gh_sbclient.py` `get/get_all` (every GH workflow) | imports, health, snapshot reads |
| PostgREST write | `pipelines/gh_sbclient.py` `post/patch/delete` (savers + writer_audit) | ESPN/CBS-ROS/CBS-Razzball save paths; `WriterAudit.complete()/fail()` PATCHes the audit table |
| SQL editor (DDL) | documented migrations (`sql/migrations/*.sql` + `supabase/migrations/*.sql`) — never run by the repo | DDL changes require a human in the Supabase SQL editor; every migration file ends with `NOTIFY pgrst, 'reload schema';` |
| Supabase Management API | not used by this repo | not wired into any pipeline |

## What the connector path can read/invoke today (concrete summary)

The Phase-1 connector path is the union of:

1. The seven source tables + their sibling fit/audit/identity tables (listed above) via `GET` (read).
2. The same seven source tables via `POST`/`PATCH`/`DELETE` (write), but only from `pipelines/save_*_references.py` and `pipelines/refresh_fantasycalc_supabase.py` — never from the GH workflow steps directly (the workflow steps invoke the save scripts which use the local skill's `sbclient`).
3. No Edge Functions, no `pg_cron` calls, no RPCs by name, no Management API. The connector is a pure PostgREST shim with bearer service-role auth.

## What is NOT verifiable from the repo alone (Phase 2 must check live)

- Live `pg_cron` jobs (none in `sql/migrations/`; unknown whether any exist on the project).
- Live RLS posture on every table (the repo assumes service-role bypass per `sql/migrations/001_pipeline_write_audit_repair.sql:33–37`; anon/authenticated access patterns are unknown).
- Whether the audit table is in the live-as-spec state or in the reduced-state (the migration is `DESIGNED — DO NOT EXECUTE` per its own header; status on the project as of this audit is unknown).
- The live row counts for each table (`docs/supabase-source-mapping.md:102–111` snapshot was 2026-09-21; current counts have grown).
- Whether the `import_supabase_references.py` import_health.json pattern is the only consumer of `public.players` reads today, or if a downstream dashboard read also uses anon key.

## Migrations the repo has ready but not yet executed (Phase-2-relevant)

| Migration | Status | What it does |
|---|---|---|
| `sql/migrations/001_pipeline_write_audit_repair.sql` | `DESIGNED — DO NOT EXECUTE without Jeremy's review` (line 3) | Brings the live audit table up to spec (4 missing columns, PK, UNIQUE, CHECK, RLS default-deny). Will unblock every save step that currently hits `HTTP 400` because the live table lacks `code_revision` and `error_message`. |
| `sql/migrations/004_source_trade_values_bake_version.sql` | "Apply via the Supabase SQL editor, then NOTIFY pgrst" (line 18–20) — implied-ran given GAP-023's "Fixed 2026-10-02" status | Adds 9-column bake-versioned unique index |
| `sql/migrations/005_source_trade_values_grain_bake_aware.sql` | same | Evolves the player_norm grain to be bake-aware |
| `sql/migrations/006_retire_unversioned_upsert_grain.sql` | same | Drops the 8-column index (GAP-023's resolution) |
| `supabase/migrations/jeg62_vorp_translation.sql` | not verified as run | Three new tables (roster_assumptions, vorp, translated_values) — currently only referenced from `make test-unit` via the VORP translation tests |

The audit table's "designed but not executed" status is the single most important Phase-2-relevant item: every GH-side save (`espn-supabase-sync.yml`, `cbsros-supabase-sync.yml`, `fantasycalc-drift.yml`) currently fails closed when the writer hits the missing-columns defect, which is one of the root causes of the long-standing red chain (GAP-019).