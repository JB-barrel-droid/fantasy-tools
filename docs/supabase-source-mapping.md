# Supabase source mapping — dashboard-active trade-value sources

## Import stage — Supabase -> versioned snapshots (stage 1, added 2026-09-21)

`pipelines/import_supabase_references.py` pulls the scraped references from
Supabase and stamps versioned, content-vintage-stamped snapshots under
`data/raw/sources/<source>/<content-vintage>/snapshot.json`, with a
`snapshot-manifest.json` sidecar per snapshot. Snapshots reuse the
`trade-value-source-snapshot-v1` schema and record shape of
`pipelines/import_source_snapshot.py`, so the downstream
match -> reference -> section chain (`make source-match` etc.) works unchanged.

```bash
# DB-backed sources (public.source_trade_values, variant='as_published' only)
make supabase-import SOURCE=fantasycalc
make supabase-import SOURCE=usatoday
make supabase-import SOURCE=fantasypros
# Gap sources (no Supabase table yet): from workspace file caches
make supabase-import SOURCE=espn FROM_FILE=goals/football-signal-database-and-app/files/espn_projections.csv
make supabase-import SOURCE=cbs  FROM_FILE=goals/football-signal-database-and-app/lottery/data/sources_cache/cbs.json
```

Layout per snapshot directory:

- `snapshot.json` — the v1 snapshot (rows carry `native_value` as an additive
  extra: the source's scraped native; `value` is the table value as-is).
- `snapshot-manifest.json` — schema version, source, `supabase_table` or
  `from_file`, `content_vintage` (+ how it was derived), `pulled_at` labeled
  as PULL TIME (never vintage), row/review counts, sha256 of the snapshot
  bytes, the filter used, and `save_gap` for the file-backed sources.

Fail-closed guards (negative-tested in `tests/test_supabase_import.py`):
unknown source names (ECR/Vegas/Razzball can never sneak in); zero rows;
undeterminable content vintage (NULL `source_content_date` with no week/file
vintage); a stamped snapshot already existing with different bytes (no silent
overwrite — re-running an unchanged pull is an idempotent no-op); non-numeric
`player_key` or non-numeric/non-null `value` -> `review_rows`, never guessed or
zero-filled; FantasyPros ECR-flavored rows excluded even if the table filter is
widened. ESPN/CBS DDL for the missing tables lives at
`pipelines/sql/create_espn_cbs_reference_tables.sql` — written for review,
NOT executed (creating tables is persistent state, out of scope for stage 1).

---

Researched 2026-09-21 (read-only). Single Supabase project reachable:
`iskiybsimubiujwuchsl.supabase.co`, schema `public`
(the `ross` schema holds Ross-league data only — draft results, keeper
contracts, rosters — no source data). Access method: the vault-backed
`custom.supabase-football-signal` credential via the skill's `sbclient`
surrogate flow (Management API `mgmt.py` for DDL/SQL). No keys are stored
or pasted anywhere in this process.

Dashboard-active trade-value sources in scope:
ESPN projections, USA Today trade values, FantasyCalc trade values,
FantasyPros **trade values** (NOT ECR — ECR is excluded even though it is
also a FantasyPros product), CBS trade values.
Hard exclusions respected: no ECR/expert-consensus tables
(`fp_season_projections`, `fp_season_latest_norm`, `fp_season_kdst_projections`,
`rankers`/`ranker_rankings` — verified ECR-only: `ranker_rankings` holds
2858 rows and every row joins to an `ecr_type`-set ranker; the non-ECR
`ESPN` and `FantasyPros` ranker rows have zero `ranker_rankings` rows),
no Vegas/prediction-markets tables (`vegas_season_totals`, `odds_history`),
no Razzball (no table exists for it).

## The one Supabase table that holds scraped trade-value references

### `public.source_trade_values`

Holds the saved scraped values for **3 of the 5** in-scope sources:
`fantasycalc`, `usatoday`, `fantasypros` (the trade-value chart, not ECR).
Written by `~/workspace/football-signal/trade-value/fit_source_variants.py`
as the `as_published` variant (the script also writes a derived
`bias_adjusted` variant per row — that is OUR fitted calibration, not the
source's scraped number; only `variant='as_published'` is the source's own
value).

- **Player identity:** numeric `player_key` (bigint) — canonical key into
  the Supabase `players` table (the naming authority). `player_norm` is a
  human-readable normalized-name join label, NOT the key. `player_id`
  (uuid) is a legacy backfill column from the key migration. Zero rows
  have NULL `player_key` for any of the three sources (fail-closed
  identity resolution at bake time).
- **Value columns:** `value` = source's published value isotonic-reindexed
  onto the chart's common scale (what the dashboard shows);
  `native_value` = the source's original published number before
  reindexing (e.g. FantasyCalc's raw dollar-ish scale).
- **Vintage columns:** `source_content_date` (date) = when the SOURCE last
  changed its numbers — the honest vintage. `pulled_at` (timestamptz) =
  when WE pulled it — never use this as vintage. `bake_id` = the bake
  grain (re-runnable; a different bake_id on the same
  (source, scoring, league, season, week) grain aborts fail-closed).
- Grain per row: `source`, `scoring` (std/half/full), `league_teams`=12,
  `qb_slots`=1, `season`=2026, `week`=2, `position`, `team`.
- **Current row counts** (2026-09-21):

| source       | variant       | rows | bake_id            | source_content_date | pulled_at (UTC)        |
|--------------|---------------|------|--------------------|---------------------|------------------------|
| fantasycalc  | as_published  | 594  | fitwk2_2026-09-17_v3 | NULL (week designation only — FantasyCalc is a weekly snapshot, no published date) | 2026-09-16 |
| fantasycalc  | bias_adjusted | 594  | fitwk2_2026-09-17_v3 | NULL | 2026-09-16 |
| usatoday     | as_published  | 714  | fitwk2_2026-09-17_v3 | 2026-09-15 | 2026-09-17 04:42:37 |
| usatoday     | bias_adjusted | 714  | fitwk2_2026-09-17_v3 | 2026-09-15 | 2026-09-17 04:42:37 |
| fantasypros  | as_published  | 534  | fitwk2_2026-09-18_v1 | 2026-09-15 | 2026-09-18 20:47:09 |
| fantasypros  | bias_adjusted | 534  | fitwk2_2026-09-18_v1 | 2026-09-15 | 2026-09-18 20:47:09 |

Sample rows (`variant='as_published'`):

- usatoday: `player_norm='tre tucker'`, `player_key=3116`, WR/LV, scoring=full,
  `value=1.8`, `native_value=2.0`, `source_content_date=2026-09-15`,
  `pulled_at=2026-09-17 04:42:37+00`, week=2, season=2026.
- fantasycalc: `player_norm='jahmyr gibbs'`, `player_key=2227`, RB/DET,
  scoring=half, `value=82.0`, `native_value=10606.0`,
  `source_content_date=NULL` (weekly snapshot — vintage is "Week 2",
  carried in the `week` column, not a date), `pulled_at=2026-09-16`.
- fantasypros: `player_norm='joshua allen'`, `player_key=869`, QB/BUF,
  scoring=std, `value=25.3`, `native_value=29.1`,
  `source_content_date=2026-09-15`, `pulled_at=2026-09-18 20:47:09+00`.

Sibling table (derived, not scraped references):
`public.source_value_adjustments` — 96 rows; the per-(source, scoring,
position, tier) OLS affine fit cells (`alpha`, `beta`, `r_squared`,
`method='ols_affine_pos_tier_hierarchy_v1'`) that produce the
`bias_adjusted` variant. Fit artifact, not a source reference.

## GAPS — sources with NO Supabase table holding their scraped values

### ESPN projections — GAP (file only)
No Supabase table holds ESPN season projections. Verified: no
`espn_*` data table exists (`espn_fetch_config` is just a
`current_week`/`updated_at` config row, no projection columns); no
espn/cbs columns exist on any public table; `ranker_rankings` has zero
rows for the non-ECR ESPN ranker.
Saved scraped reference lives in files only:
- `goals/football-signal-database-and-app/files/espn_projections.csv`
  (per-player ROS stat projections; has an `espn_snapshot_date` column;
  current file vintage 2026-09-21, Mike Clay model)
- `goals/football-signal-database-and-app/hidden_files/espn_projections_meta.json`
  (vintage/payload-hash sidecar)
Daily pull writes these; the chart's ESPN leg is computed from them via
the DDF methodology at bake time.

### CBS trade values — GAP (file only)
No Supabase table holds CBS (Dave Richards) trade values. The only saved
scraped reference is:
- `goals/football-signal-database-and-app/lottery/data/sources_cache/cbs.json`
  (scraped from the CBS Sports trade-chart article; pulled live at bake
  time by `lottery/bin/build_sources_dashboard.py::pull_cbs`, cached here)
USA Today's file cache sits beside it (`sources_cache/usatoday.json`);
FantasyCalc's weekly snapshot beside that
(`sources_cache/fantasycalc_snapshot.json` + per-combo files);
FantasyPros' trade-chart CSV at `goals/football-signal-database-and-app/files/fantasypros_trade_chart.csv`.
ESPN/CBS are the two sources whose scraped references exist ONLY as files.

## Summary map

| Dashboard source        | Supabase table              | Identity | Vintage column              | Status |
|-------------------------|-----------------------------|----------|-----------------------------|--------|
| ESPN projections        | — none —                    | n/a      | `espn_snapshot_date` (in CSV) | GAP: file only |
| USA Today trade values  | `public.source_trade_values` (`source='usatoday'`) | numeric `player_key` | `source_content_date` | live (714+714 rows) |
| FantasyCalc trade values| `public.source_trade_values` (`source='fantasycalc'`) | numeric `player_key` | `week` (weekly snapshot; `source_content_date` is NULL by design) | live (594+594 rows) |
| FantasyPros trade values| `public.source_trade_values` (`source='fantasypros'`) | numeric `player_key` | `source_content_date` | live (534+534 rows) |
| CBS trade values        | — none —                    | n/a      | article published date in bake meta | GAP: file only |

Note on scope: `variant='bias_adjusted'` rows are our fitted calibration,
not the source's numbers; consumers wanting "the source's scraped value"
must filter `variant='as_published'`.

## Import health gate — fail checking before any fixture update (stage 1, added 2026-09-21)

Jeremy directive: every active source's snapshot must VERIFY it landed with
fresh content vintage before any fixture update. `pipelines/verify_import_health.py`
(`make import-health NFL_WEEK=<n>` — the watchdog/cron passes `NFL_WEEK`) checks,
for each of the five sources (espn, usatoday, fantasycalc, fantasypros, cbs —
never ecr/vegas/razzball): snapshot + manifest exist; snapshot bytes match the
manifest sha256; each source's Supabase table is re-queried (row count +
vintage) against the manifest — expected rows = clean + review + ECR-dropped
for fantasycalc/usatoday/fantasypros (the importer reads the table directly),
clean rows only for espn/cbs (review rows were excluded before the save);
freshness is judged on content vintage (week-designated charts fresh iff their
NFL week == `NFL_WEEK`; ESPN fresh iff within 2 days).

**No fixture update (match/reference/section/promote) may run on a red health
check.** The gate is standalone; the pull watchdog reads
`output/source-import-health.json` after each pull's expected time. The JSON is
a consumer contract documented in `docs/import-health-schema.md` — do not
change its shape without coordinating with the watchdog builder.
