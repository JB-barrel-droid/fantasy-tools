# Dependency Map

Last updated: 2026-09-19.

Source basis: handoff PDF. Source export verification is pending.

## Component Classification

| Component | Classification | Reason |
| --- | --- | --- |
| Muse live dashboard | KEEP | Reference implementation until replacement is verified. |
| `ts-spaces/trade-value-chart/index.html` | MIGRATE NOW | Static page shell and inline finished player data are required for local reproduction. |
| `assets/curve-widget.js` | MIGRATE NOW | Owns chart behavior, lock modes, null handling, boundaries, and guards. |
| `assets/comparison-dashboard.js` | MIGRATE NOW | Owns comparison board, filters, sorting, disagreement, and state import/export. |
| `assets/comparison-sources-data.json` | MIGRATE NOW | Primary finished source-comparison data artifact. |
| `assets/*.css` | MIGRATE NOW | Required to preserve responsive behavior and visual equivalence. |
| `space.json` | DELETE/IGNORE | Muse-specific runtime metadata; keep only as reference if needed. |
| `.space-build/` | DELETE/IGNORE | Muse staging output; replacement should build/deploy from source. |
| `trade-value/players.json` or inline `players-data` | MIGRATE NOW | Primary finished player artifact for first local reproduction. |
| `trade-value/build_values.py` | MIGRATE LATER | Master bake logic, but not needed for first static reproduction. |
| `trade-value/sync_chart_data.py` | REWRITE | Muse artifact injection should become a deterministic local build step. |
| `trade-value/publish_chart.sh` | REWRITE | Muse publish path should be replaced by host-specific deploy and verification. |
| `trade-value/dataset_status.py` | MIGRATE LATER | Needed when rebuilding data-health output outside Muse. |
| `lottery/bin/starter_model.py` | MIGRATE LATER | Canonical DDF valuation engine; migrate after golden tests exist. |
| `lottery/bin/build_sources_dashboard.py` | MIGRATE LATER | Source reindex/fixed-pie generation; needed after frontend independence. |
| `lottery/bin/fit_source_variants.py` | MIGRATE LATER | Bias-adjusted variants; migrate after source data tests exist. |
| `lottery/bin/audit_curve_locks.js` | MIGRATE LATER | Useful regression gate; port after source files are available. |
| `lottery/bin/audit_fixed_pie.js` | MIGRATE LATER | Useful regression gate. |
| `lottery/bin/audit_axes.js` | MIGRATE LATER | Useful regression gate. |
| `lottery/bin/render_gate.js` | MIGRATE LATER | Useful Playwright/headless render gate. |
| `engine/canonical_players.py` | MIGRATE LATER | Shared identity authority; must be ported before pipeline migration. |
| `engine/scoring.py` | MIGRATE LATER | Shared scoring engine. |
| `engine/canonical_teams.py` | MIGRATE LATER | Shared team normalization. |
| `engine/week.py` | MIGRATE LATER | Week logic; standalone state unverified in handoff. |
| FantasyPros authenticated browser tasks | MIGRATE LATER | Leave in Muse until collectors are isolated and credentials/session handling is designed. |
| ESPN public API collector | MIGRATE LATER | Candidate early collector after frontend is independent. |
| Razzball collector | MIGRATE LATER | Candidate public collector after frontend is independent. |
| FantasyCalc collector | MIGRATE LATER | Candidate public collector after frontend is independent. |
| USA Today/CBS article collectors | MIGRATE LATER | Candidate public collectors after frontend is independent. |
| Historical trade designer/calculator | DELETE/IGNORE | Not part of current live product scope. |

## Finished Artifact Dependencies

The local dashboard needs:

- Static app files.
- `players.json` or equivalent inline `players-data`.
- `comparison-sources-data.json`.

It does not initially need:

- Supabase write access.
- Scrapers.
- Pipeline rebuilds.
- Muse artifact editing.
- Historical trade designer/calculator code.

## Runtime Dependencies

Expected after source export inspection:

- Static file server for local development.
- Browser automation for regression testing.
- Python for pipeline and fixture tests.
- Node or browser runtime if existing audits use JavaScript.

No dbt, Airflow, Prefect, Kubernetes, or microservice platform is justified by the current handoff.

## Supabase Dependencies

Read-only connection is needed after static reproduction. The key production objects reported by the handoff are:

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

Supabase production writes are not required for the first local reproduction.

## Missing From Workspace

Currently missing:

- Muse ZIP/code/data export.
- Actual static dashboard source files.
- Current `players.json`.
- Current `comparison-sources-data.json`.
- Pipeline scripts and existing tests.
- Dependency manifests.

