# Loading a DDF leg into `consolidated_values` (JEG-381)

Every write to `public.consolidated_values` goes through the versioned
loader `pipelines/load_ddf_leg_to_supabase.py`. No ad-hoc SQL or console
inserts; the 2026-10-04 CBS ROS load wrote `raw_value` into
`combo_reindexed` because nothing versioned existed.

## Field mapping (explicit)

| Leg JSON | Column | View |
| --- | --- | --- |
| `value` (0–70 indexed) | `value` | `combo_reindexed` |
| `raw_value` (native value above waivers) | `value` | `vorp_indexed` |
| `player_norm` (falls back to `canonical_players.norm_plain(player)`) | `player` (PK) | both |
| `player_key` | `player_key` (FK `players`) | both |
| `inputs.source_tag` | `source` (FK `source_config`) | both |
| `inputs.scoring`: `standard` / `half_ppr` / `ppr` | `scoring`: `standard` / `half` / `full` | both |
| `inputs.teams` | `teams` | both |
| `inputs.<source>_snapshot_date` | `source_generated_at` (content vintage, never pull time) | both |
| latest `bakes.bake_id` for the source (or `--bake-uuid`) | `bake_uuid` and `bake_id` | both |
| `<leg path>#values[i].value` / `.raw_value` | `detail_locator` | per view |

The upsert conflict target is the table PK
`(player, source, season, week, scoring, teams, qb_variant, view)`.

## Guards (all fail closed)

- Values must be numeric. `combo_reindexed` is rescaled per source to ≤ 70
  (`pipelines/caps/per_source_rescale.py`), then range-checked. The
  DB CHECK `ck_combo_reindexed_cap` is the final backstop.
- An anti-swap guard refuses a combo leg that looks like `raw_value`.
- Every `player_key` must exist in `public.players`.
- `bake_uuid` must exist in `public.bakes` (FK).

## Commands

```bash
# 1. Dry run: reads players, bakes and current slice counts; writes nothing.
python3 pipelines/load_ddf_leg_to_supabase.py \
  data/ddf-two-tier/<run>/ddf_leg_<source>.json --season 2026 --week 5 --dry-run

# 2. Write. Uses the transactional api.ingest_consolidated_values(p_payload)
#    RPC (all-or-nothing upsert); falls back to chunked PostgREST upsert only
#    if the RPC is not exposed (404).
python3 pipelines/load_ddf_leg_to_supabase.py \
  data/ddf-two-tier/<run>/ddf_leg_<source>.json --season 2026 --week 5 --views both
```

From CI without the Mac: push a branch named `loader/<anything>` and the
`Loader dry run` workflow runs step 1 for every leg listed in
`data/ddf-two-tier/loader-dry-run.txt` (one path per line), using repo
secrets.

## Contract test

`tests/test_load_ddf_leg_contract.py` pins the loader to the live schema
(NOT NULL columns, CHECK values, PK conflict target, RPC argument and
schema, `bakes` columns). It runs in `make test-unit`.
