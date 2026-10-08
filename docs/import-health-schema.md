# Import health JSON — consumer contract for the pull watchdog

**Status:** mixed; each section says which.

- **Normative** (code reads it; change only with the consumers):
  "Sources covered", "Schema" (field names and types), "Status enum",
  "`failure_reason` codes" and "Gate semantics". Consumers:
  `pipelines/promote_comparison_section.py` (promotion contract),
  `pipelines/check_reference_freshness.py` (L1 freshness rows),
  the rebuild chain and `health-artifacts.yml` (publish the file to the
  monitor), and the monitor dashboard's import-health table.
  `tests/test_import_health_schema_doc.py` fails when this document and
  `pipelines/verify_import_health.py` disagree on the source list, the
  failure codes, the advisory statuses or the hard exclusions.
- **Informative** (description, not contract): "File" (where and when it
  runs), "Per-source content_vintage" and its freshness colour bands, and
  "Stage 1b closed" (history).

## File (informative)

- **Path:** `output/source-import-health.json` (repo-relative). `output/` is
  gitignored. The served copy is `dist/modules/source-import-health.json`,
  committed by the producers below.
- **Writer:** `pipelines/verify_import_health.py --nfl-week <n>` (also
  `make import-health NFL_WEEK=<n>`), which verifies all seven active
  dashboard trade-value sources and writes this file.
- **Where it runs (2026-10-08):** every rebuild-chain run
  (`.github/workflows/rebuild-chain.yml`, "Run import health check") and
  `.github/workflows/health-artifacts.yml`. Since go-live (2026-10-07) a red
  gate is a warning in the chain (`::warning title=import-health`), not a
  stop; promotion still enforces the per-source contract below. `NFL_WEEK`
  is optional: when omitted, the verifier uses the content week from
  `pipelines/nfl_week.py` (flips Tuesday). Never pass the Thursday-flip
  `ops/watchdog/_common.nfl_week`. A `--nfl-week` that differs from the
  content week for the check date prints a `NOTE:` line (it does not block).
- **Sources covered (normative; exactly these seven, never others):**
  `fantasycalc`, `usatoday`, `fantasypros`, `espn`, `cbs`, `cbsros`, `razzball`.
  ECR, Vegas, and prediction markets are hard exclusions — an unknown source name is a
  hard error in the verifier.

## Schema (normative)

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
| `sources` | object | Exactly the seven source keys above. |

### Per-source entry

| Field | Type | Meaning |
|---|---|---|
| `status` | string enum | `ok` \| `warning` \| `stale` \| `red` \| `missing` \| `failed`, plus Razzball's `warn` \| `bad` \| `unk`. See below. |
| `blocking` | bool | build-lag-001: true when this entry holds the gate RED (`entry_is_blocking`). Read this, not the status, to decide whether the gate can pass. |
| `content_week` | int \| null | build-lag-001: the NFL content week the vintage maps to (`"Week 4"` → 4, `2026-09-29` → 4). null until the vintage is derivable. |
| `last_successful_import` | string \| null | UTC timestamp of the last check in which this source's snapshot verified (bytes + table drift + vintage derivable). Carried forward from the previous health file when the current check fails; null if the source never verified. Note: a `stale` source still verified its bytes, so its import time is current — staleness is about the source's vintage, not the import. |
| `content_vintage` | string \| null | The manifest's content vintage verbatim (e.g. `"Week 3"`, `"2026-09-15"`). Never pull time. |
| `vintage_kind` | string enum | `week_designated` \| `source_content_date` \| `file_meta` \| `unknown`. How the vintage was derived: `week_designated` = the manifest's `week_designated` field or a `"Week N"` vintage; `source_content_date` = a dated Supabase vintage mapped to an NFL week; `file_meta` = a dated content vintage from the source's own metadata (ESPN's `espn_snapshot_date` column — DB-backed since 2026-09-22); `unknown` = not derivable (always paired with a failed status). |
| `row_count` | int \| null | Clean rows in the verified snapshot (from the manifest). The fields the watchdog needs most: `last_successful_import`, `content_vintage`, `row_count`, `failure_reason`. |
| `supabase_table` | string | The Supabase table backing the source: `public.source_trade_values` (fantasycalc/usatoday/fantasypros), `public.espn_season_projections` (espn), `public.cbs_trade_values` (cbs). Always non-null since stage 1b closed (2026-09-22). |
| `supabase_landing` | bool | true when the snapshot's bytes were re-verified against the Supabase table this run. Always true since stage 1b closed — every source re-queries its table. |
| `snapshot_path` | string \| null | Repo-relative path of the verified snapshot (`data/raw/sources/<source>/<vintage>/snapshot.json`), null when no snapshot exists. |
| `vintage_date` | string \| null | Razzball only: ISO date (`YYYY-MM-DD`) of the newest snapshot directory under `data/raw/sources/razzball/`. Drives the c5 health verdict (JEG-307). null when no snapshot exists. |
| `age_days` | int \| null | Razzball only: `check_date - vintage_date`, in days. Razzball has no CI puller (GAP-024), so this entry detects a snapshot that has drifted while the DB landing still agrees. |
| `failure_reason` | string \| null | null on `ok`; otherwise `"<CODE>: <one-line detail>"`. Codes: |

## Per-source content_vintage surfaced in `pipeline-checkpoints.json` (JEG-315, GAP-043) (informative)

GAP-043: `comparison-sources-data.json` carries both `built_at` (the fixture
build time, conflates across all sources) and a per-section
`content_vintage` per source. The dashboard's fleet summary cited only
`built_at`; per-source content freshness was not surfaced.

`pipelines/build_pipeline_checkpoints.py` now resolves each source's
content vintage directly from the fixture's per-section field and exposes
it on the source's checkpoint record:

```json
{
  "sources": {
    "<source>": {
      "label": "...",
      "content_vintage": "2026-10-03" | "Week 4" | null,
      "content_vintage_source": "content_vintage" | "vintage" | "lineage.raw_vintage" | "source_provenance.content_vintage",
      "checkpoints": { ... }
    }
  }
}
```

Resolution order (highest priority first):

1. `sources[<src>].content_vintage` — direct per-section content vintage
   (cbs, fantasycalc, fantasypros, usatoday).
2. `sources[<src>].vintage` — top-level dated vintage (espn, cbsros,
   razzball use this field name).
3. `sources[<src>].lineage.raw_vintage` — the raw input's dated vintage
   (espn, cbsros; preserves the publisher release date separately from
   the fixture build time).
4. `sources[<src>].source_provenance.content_vintage` — cbs / espn /
   usatoday carry this nested field with `content_vintage_derived_from`
   provenance notes; used as a final fallback.

`content_vintage` may be an ISO date (`"2026-10-03"`) or a `"Week N"`
label (e.g. CBS week-designated charts). The dashboard renders the
**freshness bands** below only for dated vintages — `"Week N"` values
are rendered in the unknown band because week labels do not carry
absolute age information.

### Freshness color bands (dashboard per-source card) (informative)

| Band | Color | Age (today − content_vintage) |
|---|---|---|
| Fresh | green | ≤ 4 days |
| Aging | amber | 4–7 days |
| Stale | red | > 7 days |
| Unknown | grey | not a dated vintage (`null` or `"Week N"`) |

The bands are evaluated client-side from `content_vintage` against
`Date.now()`. They are not part of the import-health gate — they are a
display signal that lets a reader see at a glance which sources are
stale, independent of the pipeline checkpoints' pass/fail status.

### Status enum (normative)

- `ok` — snapshot exists, bytes match the manifest sha256, table (if any)
  matches, vintage is fresh. Week-designated charts are fresh when their
  content week is `>= nfl_week` (a source ahead of the others is fresh).
- `warning` — non-blocking. Two producers:
  - `LAGGING_ONE_WEEK (non-blocking): ...` (build-lag-001): a week-designated
    chart (fantasycalc, usatoday, fantasypros, cbs, cbsros) exactly one
    content week behind `nfl_week`. The build uses it, labelled with its own
    week, and promotion accepts it under its own `content_vintage`. The
    reason keeps the publication-window verdict (`yellow` awaiting, `red`
    missed window, or `stale` unverified schedule).
  - `TABLE_DRIFT` stamping lag: the table is fresher than the manifest. Not
    promotable.
- `stale` — the snapshot verified (bytes + table) but its content vintage is
  too old: a week-designated chart two or more weeks behind with no
  verified publication schedule, or ESPN more than 2 days from the check
  date.
- `red` — `MISSED_WINDOW`: a week-designated chart with a verified schedule
  (usatoday, cbsros) two or more weeks behind. Blocks.
- `warn` / `bad` / `unk` — Razzball snapshot age (JEG-307). Advisory: these
  never block (`ADVISORY_FRESHNESS` in the verifier). Its byte or table
  failures (`failed`) still do. (Razzball has been a rebuild-chain source with
  a scheduled puller, `razzball-supabase-sync.yml`, since 2026-10-08; the
  advisory rule was written before that and is unchanged.)
- `missing` — no snapshot/manifest exists under `data/raw/sources/<source>/`.
- `failed` — a check itself failed: byte mismatch, table drift, undeterminable
  vintage, or a failed Supabase re-query.

### `failure_reason` codes (normative)

| Code | Meaning |
|---|---|
| `MISSING_SNAPSHOT` | No snapshot-manifest.json under `data/raw/sources/<source>/`. |
| `STALE_VINTAGE` | Verified bytes, but content vintage is not current (detail names the vintage and the expected week / age). |
| `LAGGING_ONE_WEEK` | build-lag-001, status `warning`, non-blocking: a week-designated chart exactly one content week behind. Always written as `LAGGING_ONE_WEEK (non-blocking): ...`, with the publication-window verdict appended. |
| `MISSED_WINDOW` / `AWAITING_PUBLICATION` | Publication-window verdicts (`pipelines/lib/publication_windows.py`). Standalone only at two or more weeks behind (`red`, blocking); at one week behind they appear inside a `LAGGING_ONE_WEEK` reason. |
| `BYTE_MISMATCH` | `snapshot.json` bytes differ from the manifest's sha256 — unverified bytes are never promoted. |
| `TABLE_DRIFT` | The Supabase table's row count or unanimous vintage no longer matches the manifest — a partial or stale table is not treated as complete. |
| `NO_VINTAGE` | No content vintage is derivable from the manifest — a vintage-less snapshot may never back fixture updates. |
| `IMPORT_FAILED` | The verification itself could not run (e.g. Supabase re-query error, unreadable snapshot, missing file ref for a gap source). |
| `RAZZBALL_STALE` | Razzball only (JEG-307): the snapshot directory is older than the freshness window (`age_days > 2` warn, `> 6` bad). The DB landing can still be fresh; this entry watches the snapshot itself (written when Razzball had no CI puller, GAP-024). |

## Stage 1b closed (2026-09-22) (informative)

The former stage1b gap no longer exists: ESPN and CBS each have a dedicated
Supabase table (`public.espn_season_projections`, `public.cbs_trade_values`),
saved by `pipelines/save_espn_cbs_references.py` and imported DB-backed like
the other three sources. There is no `GAP ... stage1b` line anymore, no
`save_gap: "no-supabase-table-stage1b"` manifests, and `supabase_landing` is
true for all seven sources. The old file-backed ESPN/CBS snapshots were
migrated, not silently replaced: the importer archives the prior pair under
`_superseded/<utc-timestamp>/` and records a `supersedes` audit field on the
new manifest. Watchdog note: all seven sources are DB-backed — no special
file-cache handling remains.

Per-source table notes for the watchdog: ESPN vintage comes from the
`espn_snapshot_date` content column (fresh iff within 2 days of the check
date); CBS vintage is week-designated (`week` column, e.g. `Week 2`). CBS QBs
are written once per scoring (standard/half_ppr/ppr) from the single published
`1QB-4` column — labeled IMPLIED, not three separately published values.

## Gate semantics (normative)

- The verifier exits **0 only if no entry is `blocking`** (build-lag-001).
  The check is fail-closed: only `ok`, `warning`, and Razzball's advisory
  `warn`/`bad`/`unk` are non-blocking. Every other status blocks, including
  `stale`, `red`, `yellow`, `missing`, `failed`, and any status outside this
  list. A blocking entry gives a non-zero exit and a loud stderr summary
  ending in `GATE: RED ... (blocking: <sources>)`. Before build-lag-001 the
  check counted only stale/missing/failed, so `red` and `yellow` passed.
- **No fixture update (`match`/`reference`/`section`/`promote`) may run on a
  red health check.** Promotion is wired to this contract for the seven active
  raw sources: `promote_comparison_section.py` refuses when the source entry is
  neither `ok` nor a `LAGGING_ONE_WEEK` warning (`entry_is_promotable`), when
  the candidate lacks immutable `content_vintage` provenance, or when the
  candidate vintage differs from the fresh L1 vintage. A lagging source is
  therefore promoted under its own week, never relabelled. Earlier
  stages also carry `source_provenance` forward so processing time cannot
  relabel stale source data.
- Gaps (`supabase_landing: false`) are reported loudly but do **not** fail
  the gate.
