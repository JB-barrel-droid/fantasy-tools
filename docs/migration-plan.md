# Migration Plan

Last updated: 2026-09-19.

## Operating Principles

- Preserve the Muse product as the reference implementation.
- Do not modify production Supabase data or schema during discovery.
- Keep the first replacement static and data-compatible.
- Do not rebuild scrapers first.
- Preserve numerical behavior before improving architecture.
- Prefer small, reversible changes and commits.
- Treat DDF/projection-derived values as legacy/stale in-season until refreshed and revalidated. The current migration target is the fixed-pie comparison dashboard behavior, not resurrecting stale preseason projection logic.

## Phase 1 - Discovery

Status: in progress.

Completed:

- Extracted and inspected the 42-page migration handoff PDF.
- Confirmed the workspace does not currently contain the Muse ZIP/code/data export.
- Identified the minimum viable first target: static frontend plus existing finished data artifacts.

Pending:

- Inspect the ZIP export source files and representative data.
- Compare implementation with the handoff and document discrepancies.
- Identify missing internal dependencies from the export.
- Confirm exact local run requirements.

## Phase 2 - Establish Repository

Status: partially blocked by Git metadata permissions.

Initial target structure:

```text
app/
trade_value/
pipelines/
shared/
tests/
docs/
```

The first actual layout should preserve Muse paths if that reduces verification risk. Restructuring can follow once the app runs and equivalence tests exist.

Required baseline files:

- `.gitignore`.
- `.env.example`.
- `README.md`.
- dependency file or files after source inspection.
- start command.
- test command.

## Phase 3 - Reproduce Dashboard Locally

Minimum viable path:

1. Import the Muse static dashboard directory.
2. Extract the inline `players-data` blob from `index.html` into `players.json` if needed.
3. Keep `assets/comparison-sources-data.json` as supplied.
4. Serve the static dashboard locally.
5. Verify visible behavior against the current Muse product.

No UI redesign should happen in this phase.

Verification checklist:

- Eight source curves render.
- Source values match representative known-good players.
- Ordering and lock modes match.
- Standard, Half PPR, Full PPR selection works.
- 8/10/12/14-team selection works where the current app supports it.
- Position filters work.
- Source toggles and column toggles work and prevent zero selected sources.
- Nulls render as missing values, not zeros.
- Disagreement calculations match current behavior.
- Starter/Bench/Waiver boundaries match current behavior.
- Search works in the comparison table.
- Export/import round-trips version-5 state.
- Mobile layout is usable.

## Phase 4 - Regression Protection

Add tests before migrating business logic.

Initial tests:

- JSON fixture validity.
- Canonical player identity and player-key preservation.
- Known player golden values.
- Null versus zero handling.
- Combo-key selection.
- Source totals and source counts.
- Starter/Bench/Waiver boundary math.
- All lock ordering modes.
- Source disagreement.
- Source-value preservation.
- Frontend regression guards, preferably via Playwright.

## Phase 5 - Supabase Read-Only Connection

Do only after local static reproduction works.

Tasks:

- Add read-only Supabase configuration via environment variables.
- Inventory relevant production objects.
- Compare production objects to the handoff.
- Identify which finished artifacts can be read directly from Supabase and which still exist only as Muse/local files.

No production schema or data changes in this phase.

## Phase 6 - Deploy Outside Muse

Do only after local equivalence is proven.

Tasks:

- Select the simplest host suitable for a static/lightweight dashboard.
- Deploy the replacement while leaving Muse live.
- Verify desktop and mobile behavior against Muse.
- Do not cut over public traffic until discrepancies are understood.

## Phase 7 - Move Build Logic

Migrate one component at a time, comparing old and new output before switching production.

Priority:

1. Canonical player identity.
2. Scoring.
3. Current fixed-pie source comparison and source-level normalization.
4. Source normalization.
5. Source comparison calculations.
6. Source reindexing/fixed-pie logic.
7. Bias-adjusted variants.
8. Legacy value-above-waivers/DDF logic only if it is still needed after a freshness and product-use review.
9. Final JSON/data artifact generation.

## Phase 8 - Move Source Collectors Last

Do not start with authenticated FantasyPros scraping.

Move easier public/API sources first. Each source should become:

```text
source -> dedicated collector -> raw data -> validation -> Supabase/canonical input -> downstream calculation
```

Credential and session handling must remain outside source control.

## Current Blocker

The Muse ZIP/code/data export is not present in this workspace. The handoff PDF is enough to plan the minimum viable path, but not enough to verify implementation or reproduce the dashboard locally.
