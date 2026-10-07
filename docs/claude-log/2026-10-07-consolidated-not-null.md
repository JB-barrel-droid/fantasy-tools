## 2026-10-07 - JEG-324 / JEG-380: consolidated_values NOT NULL columns (rebuild run 37641559947)

Contract (coordinator): the consolidation step failed with 23502 and blocked
the Pages deploy. Find where the NOT NULL columns came from, make the writer
set `player_key`, `bake_uuid` and `source_generated_at` (fail closed, never
fuzzy), add a negative-tested guard, check the other writers, no Supabase
writes, and say whether the step should block Pages.

### Verified (check named)
- Live schema (read-only SELECT, information_schema): `consolidated_values.player_key`
  bigint NOT NULL, `bake_uuid` uuid NOT NULL, `source_generated_at` timestamptz
  NOT NULL. `bakes`: bake_id uuid PK, `source`, `source_generated_at` and
  `contract_version` all NOT NULL.
- Origin: `supabase_migrations.schema_migrations` has only
  `20261005223330 jeg377_jeg380_api_lockdown`, which sets `source_generated_at`
  NOT NULL. The player_key/bake_uuid NOT NULL and the FKs were applied directly
  (header of `supabase/migrations/jeg377_jeg380_api_mirror.sql`; Linear JEG-380
  scope: "require pipeline to set true timestamps going forward", which was
  never done for this writer).
- The last successful write by this builder was 2026-10-04 00:21 (bake_id =
  fixture built_at). Those 20,865 rows were backfilled at 19:12 the same day,
  with one `bakes` row per source and source_generated_at = built_at.
- The fix lives in `pipelines/build_consolidated_values.py`:
  - player_key comes from the fixture's `player_keys` (all 610 players have
    one; no name matching).
  - source_generated_at is the content vintage from section provenance, in
    `SGA_FIELDS` order.
  - bake_uuid comes from one `bakes` row per source per fixture sha256, reused
    on re-run.
  - Pre-flight runs before any write: source FK, the 70 cap, player FK and
    missing fields.
- Guard `tests/test_consolidated_write_fields.py` (11 tests), negative-tested:
  - Old writer (no write fields): 23502 on `bake_uuid`.
  - Fields dropped from `attach_write_fields`: FAIL.
  - No player_key: 4 errors.
  - No pre-flight: the fake DB raises 23514/23503 mid-write.
  - origin/main's builder: 8 errors.
- The current fixture would fail next on `ck_combo_reindexed_cap`: 15 adjusted
  values are above 70 (GAP-CONSOL-CAP). Pre-flight now refuses the whole write
  with that list, and nothing is written.
- Other writers: `load_ddf_leg_to_supabase.py` already writes all three fields.
  No other repo code writes `consolidated_values` or `bakes`. The
  `sync_dashboard_artifacts` export reuses `build_rows`; it now passes the
  review list (a no-op today), and `dist/consolidated-values.json` is
  unchanged.
- Validation: running all 135 `make validate` commands separately, the only
  failure is `tests.test_static_export` (25.5 != 25.3). That failure is the
  same on clean origin/main (GAP-MAIN-STATIC-PIN), so `make validate` exits 2
  on this branch for a reason unrelated to this change. I did not touch the pin.

### Claimed, not confirmed
- The write path has not run against Supabase (no writes allowed). The
  PostgREST filter `context->>fixture_sha256=eq.<sha>` on `bakes` is untested
  live.
- Content-vintage choice: week-labelled sources (cbs, fantasycalc) get their
  `fetched_at`. Dated publications get the content date, so usatoday and
  fantasypros will read 8 days old to `gate_source_freshness`, which is the
  truthful value JEG-380 asked for. That may turn freshness gates red where the
  built_at backfill had hidden it.
