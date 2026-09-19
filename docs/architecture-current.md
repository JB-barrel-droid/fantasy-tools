# Current Architecture

Last updated: 2026-09-19.

Source basis: `trade-value-migration-handoff.pdf`, extracted locally for discovery. The Muse ZIP/code export is not present yet, so this document records handoff-verified facts and flags source-file verification as pending.

## Product Surface

The live product is the public Trade Value Dashboard at `https://muse.ai/s/trade-value-chart-xgxi6fxa8xexp2nq`.

The current build described by the handoff is `tv-20260919-1729-2fa512ef`. It is a static single-page dashboard with no login, no user accounts, and no state persistence. State is in memory only.

The live dashboard includes:

- Eight source curves.
- Position filters: ALL, QB, RB, WR, TE, FLEX.
- Scoring controls: Standard, Half PPR, Full PPR.
- League-size controls: 8, 10, 12, 14 teams.
- Ten lock modes: preseason, largest disagreement, and one per source.
- Dynamic chart Y-axis scaling with no artificial 70 cap.
- Starter, Bench, and Waiver boundary markers.
- Tooltips, source toggles, source comparison table, disagreement metric, search, state export/import, source-health panel, and responsive/mobile behavior.

The historical trade designer/calculator is not live and is out of scope for the first migration stage.

## Current Frontend Runtime

The handoff identifies the Muse static artifact at:

```text
~/workspace/ts-spaces/trade-value-chart/
```

Required files:

- `index.html` - page shell, inline `players-data` JSON blob, dataset-health renderer, build stamp.
- `assets/curve-widget.js` - chart widget, lock ordering, boundaries, zoom, tooltips, guards.
- `assets/comparison-dashboard.js` - comparison board, filters, sorting, export/import.
- `assets/comparison-sources-data.json` - eight source sections, combos, source validation, fixed-pie metadata.
- `assets/curve-widget.css` - chart styling and responsive behavior.
- `assets/comparison-dashboard.css` - board styling and responsive behavior.
- `assets/dashboard-integration.css` - product-tab sticky rule.
- `space.json` - Muse static runtime metadata.

The first local reproduction should copy this static runtime outside Muse and serve it as a normal static web app.

## Finished Data Artifacts

The first migration target should consume finished artifacts rather than rebuilding upstream pipelines:

- `players.json`, currently embedded into `index.html` as `<script id="players-data">`.
- `comparison-sources-data.json`, currently loaded from `assets/comparison-sources-data.json`.

The handoff reports `players.json` includes 596 skill players and metadata such as `as_of`, ECR snapshot dates, player keys, preseason ECR rank, ECR/ESPN/PM values, prior values, games remaining, and pricing notes.

The handoff reports `comparison-sources-data.json` includes:

- `built_at`.
- `value_weeks`.
- `display`.
- `teams`.
- `player_keys`.
- `source_validation`.
- Eight source sections with combo values, native values, fit metadata, and fixed-pie index totals.

## Frontend Calculations

The handoff says these calculations happen in the browser and must be preserved:

- Roster boundary ordinals.
- Dynamic nice-step Y-axis scale.
- Zoom window and slider fill math.
- Source disagreement, defined as max minus min across finite source values and requiring at least two finite values.
- All lock ordering modes.
- Null rendering, where missing values remain null and display as `--`/line breaks rather than zero.
- Tooltip nearest-rank lookup.
- Combo-key selection by scoring/team/source.

Everything else should initially be treated as baked data.

## Canonical Identity

The canonical identity source is Supabase `players.player_key`, a numeric key. The canonical display name is `players.full_name`.

The dashboard and pipelines must preserve fail-closed behavior:

- Unmatched or ambiguous players remain unmatched.
- Missing values remain null.
- Genuine below-waiver values may be zero.
- No silent name guessing.

## Supabase

The existing Supabase project remains the database:

```text
https://iskiybsimubiujwuchsl.supabase.co
```

The handoff reports 57 tables, 17 views, and 2 RPCs. Discovery and first migration steps must remain read-only.

Core trade-value-related objects include:

- `players`.
- `fp_season_projections`.
- `fp_season_latest_norm`.
- `season_actuals_ytd`.
- `games`.
- `player_value_notes`.
- `source_trade_values`.
- `source_value_adjustments`.
- `projection_snapshots`.
- `player_identities`.
- `player_identity_aliases`.

RLS and `pg_cron` state are unverified in the handoff and must not be assumed.

## Current Pipeline Shape

The Muse system currently handles:

- Authenticated FantasyPros exports.
- Public/API pulls for ESPN, Razzball, prediction markets, FantasyCalc, USA Today, CBS, and FantasyPros chart values.
- Supabase reads/writes for staging and derived data.
- `trade-value/build_values.py` generation of `players.json`.
- `lottery/bin/build_sources_dashboard.py` and related scripts for source comparison data.
- `trade-value/sync_chart_data.py` to inject baked data into the Muse artifact.
- Muse artifact staging, audit, render gate, and share/publish.

For migration, this upstream system should remain in Muse until the static dashboard is reproduced and protected by tests.

## Source-Verified Gaps

Pending the ZIP export, these items are not yet verified from source files:

- Exact current file contents.
- Exact `players.json` and `comparison-sources-data.json` data values.
- Exact dependency manifests.
- Whether any internal imports are missing from the export.
- Whether local commands in the handoff still run outside Muse.

