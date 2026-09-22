# Import health JSON — consumer contract for the pull watchdog

**Status:** normative. The pull watchdog codes against this document; do not
change field names, types, the status enum, or the failure codes without
coordinating with the watchdog builder.

## File

- **Path:** `output/source-import-health.json` (repo-relative). `output/` is
  gitignored — the file is runtime state, never committed.
- **Writer:** `make import-health NFL_WEEK=<n>` runs
  `pipelines/verify_import_health.py --nfl-week <n>`, which verifies all five
  active dashboard trade-value sources and writes this file.
- **Update cadence / trigger:** the pull watchdog runs `make import-health`
  after each source pull's expected time and reads this file. `NFL_WEEK` is
  passed by the watchdog/cron (the current NFL week); the verifier does not
  infer it.
- **Sources covered (exactly these five, never others):**
  `espn`, `usatoday`, `fantasycalc`, `fantasypros`, `cbs`.
  ECR, Vegas, and Razzball are hard exclusions — an unknown source name is a
  hard error in the verifier.

## Schema

Top-level object (key order as written; parsers must read by name):

```json
{
  "schema": "trade-value-import-health-v1",
  "checked_at": "2026-09-22T02:31:45Z",
  "nfl_week": 3,
  "sources": {
    "<source>": {
      "status": "ok",
      "last_successful_import": "2026-09-22T02:31:45Z",
      "content_vintage": "Week 3",
      "vintage_kind": "week_designated",
      "row_count": 594,
      "supabase_table": "public.source_trade_values",
      "supabase_landing": true,
      "snapshot_path": "data/raw/sources/fantasycalc/week-3/snapshot.json",
      "failure_reason": null
    }
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `schema` | string | Always `"trade-value-import-health-v1"`. Bump the version if the shape changes. |
| `checked_at` | string | UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`) of this check run. |
| `nfl_week` | int | The NFL week the check judged freshness against (echo of `--nfl-week`). |
| `sources` | object | Exactly the five source keys above. |

### Per-source entry

| Field | Type | Meaning |
|---|---|---|
| `status` | string enum | `ok` \| `stale` \| `missing` \| `failed`. See below. |
| `last_successful_import` | string \| null | UTC timestamp of the last check in which this source's snapshot verified (bytes + table drift + vintage derivable). Carried forward from the previous health file when the current check fails; null if the source never verified. Note: a `stale` source still verified its bytes, so its import time is current — staleness is about the source's vintage, not the import. |
| `content_vintage` | string \| null | The manifest's content vintage verbatim (e.g. `"Week 3"`, `"2026-09-15"`). Never pull time. |
| `vintage_kind` | string enum | `week_designated` \| `source_content_date` \| `file_meta` \| `unknown`. How the vintage was derived: `week_designated` = the manifest's `week_designated` field or a `"Week N"` vintage; `source_content_date` = a dated Supabase vintage mapped to an NFL week; `file_meta` = a dated content vintage from the source's own metadata (ESPN's `espn_snapshot_date` column — DB-backed since 2026-09-22); `unknown` = not derivable (always paired with a failed status). |
| `row_count` | int \| null | Clean rows in the verified snapshot (from the manifest). The fields the watchdog needs most: `last_successful_import`, `content_vintage`, `row_count`, `failure_reason`. |
| `supabase_table` | string | The Supabase table backing the source: `public.source_trade_values` (fantasycalc/usatoday/fantasypros), `public.espn_season_projections` (espn), `public.cbs_trade_values` (cbs). Always non-null since stage 1b closed (2026-09-22). |
| `supabase_landing` | bool | true when the snapshot's bytes were re-verified against the Supabase table this run. Always true since stage 1b closed — every source re-queries its table. |
| `snapshot_path` | string \| null | Repo-relative path of the verified snapshot (`data/raw/sources/<source>/<vintage>/snapshot.json`), null when no snapshot exists. |
| `failure_reason` | string \| null | null on `ok`; otherwise `"<CODE>: <one-line detail>"`. Codes: |

### Status enum

- `ok` — snapshot exists, bytes match the manifest sha256, table (if any)
  matches, vintage is fresh. The only status that permits fixture updates.
- `stale` — the snapshot verified (bytes + table) but its content vintage is
  not current: week-designated charts (fantasycalc, usatoday, fantasypros,
  cbs) are fresh iff their NFL week == `nfl_week`; ESPN is fresh iff its
  content date is within 2 days of the check date.
- `missing` — no snapshot/manifest exists under `data/raw/sources/<source>/`.
- `failed` — a check itself failed: byte mismatch, table drift, undeterminable
  vintage, or a failed Supabase re-query.

### `failure_reason` codes

| Code | Meaning |
|---|---|
| `MISSING_SNAPSHOT` | No snapshot-manifest.json under `data/raw/sources/<source>/`. |
| `STALE_VINTAGE` | Verified bytes, but content vintage is not current (detail names the vintage and the expected week / age). |
| `BYTE_MISMATCH` | `snapshot.json` bytes differ from the manifest's sha256 — unverified bytes are never promoted. |
| `TABLE_DRIFT` | The Supabase table's row count or unanimous vintage no longer matches the manifest — a partial or stale table is not treated as complete. |
| `NO_VINTAGE` | No content vintage is derivable from the manifest — a vintage-less snapshot may never back fixture updates. |
| `IMPORT_FAILED` | The verification itself could not run (e.g. Supabase re-query error, unreadable snapshot, missing file ref for a gap source). |

## Stage 1b closed (2026-09-22)

The former stage1b gap no longer exists: ESPN and CBS each have a dedicated
Supabase table (`public.espn_season_projections`, `public.cbs_trade_values`),
saved by `pipelines/save_espn_cbs_references.py` and imported DB-backed like
the other three sources. There is no `GAP ... stage1b` line anymore, no
`save_gap: "no-supabase-table-stage1b"` manifests, and `supabase_landing` is
true for all five sources. The old file-backed ESPN/CBS snapshots were
migrated, not silently replaced: the importer archives the prior pair under
`_superseded/<utc-timestamp>/` and records a `supersedes` audit field on the
new manifest. Watchdog note: all five sources are DB-backed — no special
file-cache handling remains.

Per-source table notes for the watchdog: ESPN vintage comes from the
`espn_snapshot_date` content column (fresh iff within 2 days of the check
date); CBS vintage is week-designated (`week` column, e.g. `Week 2`). CBS QBs
are written once per scoring (standard/half_ppr/ppr) from the single published
`1QB-4` column — labeled IMPLIED, not three separately published values.

## Gate semantics (for the watchdog)

- The verifier exits **0 only if every source is `ok`**. Any
  `missing`/`stale`/`failed` → non-zero exit plus a loud human-readable
  summary on stderr ending in `GATE: RED`.
- **No fixture update (`match`/`reference`/`section`/`promote`) may run on a
  red health check.** The gate is standalone — it is not wired into the
  promotion script; the watchdog (and any human operator) must consult this
  file first.
- Gaps (`supabase_landing: false`) are reported loudly but do **not** fail
  the gate.
