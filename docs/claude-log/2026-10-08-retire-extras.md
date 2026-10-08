## 2026-10-08 - Retire producer-less extras (chore/retire-extras)

Row: RETIRE-EXTRAS (new); GAP-LIVE-SCRAPE-STALE marked superseded.
Jeremy's decision (2026-10-08): retire three leftovers that had no producer and
only showed as permanent stale warnings. Git history keeps everything; the last
commit carrying all of it is `aefb8f7` (origin/main at branch point). Per-file
last-touching commits: `ingest_player_news.py` / `player-news.json` 6cbf22b,
`build_source_value_lineage.py` / `build_view_artifacts.py` 132665d,
`scrape_live_source_pages.py` / `live-page-scrape.json` bdf43bd,
`source-value-lineage.json` f7e6645, `vorp-view.json` 85b5619,
`validate_imputed_vorps.py` 39a3f29.

### Changes
- **Player news + news.trade_values_published_at:** deleted the fixture, app and
  dist copies of `player-news.json` and `pipelines/ingest_player_news.py`;
  `make source-news` gone; `sync_dashboard_artifacts.py` no longer copies it.
  `product-data.js` no longer fetches it (`getPlayerContext()` and
  `snapshot.context_meta` removed). `comparison-dashboard.js` lost the news
  loader, news/adjustment normalisers, expandable player rows and the dead
  `latest_news` column branch; its CSS lost the news/expand rules. The main
  page's data-health dialog lost the "Player news pipeline" card and news
  counts; dead `.recent-news*` / `.news-tag*` CSS removed.
  `check_reference_freshness.py` dropped both `news.*` items and the news hash;
  `build_reference_data.py` dropped the news requirement/validation;
  `build_chart_input_coverage.py` dropped the news row.
- **Lineage audit + vorp-view/adj-view:** deleted `build_source_value_lineage.py`,
  `build_view_artifacts.py`, `scrape_live_source_pages.py`,
  `validate_imputed_vorps.py` (its only real input was the lineage artifact),
  and the four `dist/modules` artifacts. Removed `make monitor-lineage`, the
  lineage step in `pages.yml`/`preview.yml`, the per-view build in `make sync`,
  the lineage card, VORP/Adj view cards and view-status headline tally in
  `modules/dashboard.html`, the "Lineage audit (manual)" derived row in
  `modules/status.html`, and four `modules/surfaces.json` entries.
  `check_fantasycalc_drift.py` no longer invokes the deleted builder.
  The chart's saved VORP views (`vorp_views` inside the fixture, read by
  curve-widget.js) are a different thing and are untouched; the page never read
  `vorp-view.json` / `adj-view.json`.

### Tests
- Deleted: `test_lineage_freshness`, `test_lineage_stage_retired`,
  `test_lineage_group_vorp_loader`, `test_lineage_merge`,
  `test_lineage_parent_chart_semantics`, `test_lineage_snapshot_guard`,
  `test_lineage_view_indicators`, `test_lineage_vorp_roundtrip`,
  `test_view_artifacts`, `test_validate_imputed_vorps`,
  `tests/rendered_gate/fleet-headline.mjs` (unwired; tested the view-status tally).
- Removed test methods: `test_static_export` (4 news tests),
  `test_status_warnings.LineageCardStaleNoteTest`,
  `test_razzball_monitor_coverage.test_razzball_lineage_is_projection_calculated`.
- Pinned assertions changed (reason: the pinned thing was retired):
  `test_reference_freshness` expired counts 6->4 and 5->3, chart-input keys
  drop `news.generated_at`; `test_preview_workflow_matches_pages` expected build
  steps drop the lineage step (its continue-on-error check now covers every
  build step; reorder/flag-drift mutations retargeted to the e2e/accuracy steps);
  `test_chart_input_coverage` now asserts player-news is NOT listed;
  `test_razzball_monitor_coverage` drops the `razzball:"Razzball"` label check
  (that map lived in the lineage card); `test_ops_dashboard` fixtures drop the
  lineage audit file.
- New: `tests/test_retired_extras.py` (in test-unit) and
  `test_reference_freshness.test_retired_news_items_are_not_reported`.

### Verified (check named)
- `tests/test_retired_extras.py`: 4/4 fail with the branch changes stashed
  (origin/main state), 4/4 pass on the branch.
- `test_retired_news_items_are_not_reported` fails against origin/main's
  `check_reference_freshness.py` (lists the two news keys), passes on branch.
- 12-combo headless sweep (standard/half/full x 8/10/12/14, Chrome) of
  `make sync` builds, origin/main vs branch, root page and /classic/: zero
  diffs in fixedPieIndexed, sourceScaleAgreement, sourcePeaks and getAllRows;
  comparison table text identical after whitespace normalisation (the only
  render change: 24 rows lose the "+" expand button that opened 3-week-old
  news); no page errors, no 404s, no player-news fetch; data-health dialog
  minus the "Player news pipeline" card.
- `modules/status.html` and `modules/dashboard.html` from the branch build
  render with no page errors and no lineage/news/view items; status derived
  rows are e2e, accuracy, input lineage only.
- `make sync` + `CHROMIUM_PATH=... make validate`: exit 0.
- Supabase (read-only): `public.player_news`, `player_adjustments`,
  `player_review` exist with 0 live rows; `api.player_context` is a view.

### Claimed, not confirmed
- `test_razzball_monitor_coverage` (2 failures: vintage pin, index-math
  status) and `test_razzball_dashboard_render` (1 failure) fail identically on
  origin/main; not caused here (tests-hygiene lane territory).
- The status page's "Freshness labels" card now shows Unknown instead of
  Attention locally: with the red news rows gone, its worst item is the
  `players.kdst_snapshot` unknown row (kdst lane is removing K/DST).

### Follow-up: merge with origin/main (fix/kdst-daily) and drop migration
- Merged origin/main; kept both lanes' removals. `player-news.json` stays
  deleted; `DEFAULT_CHART_INPUT_KEYS` is now just `players.as_of`;
  `test_reference_freshness` expired counts recomputed to 3 and 2 (pm_snapshot,
  kdst_snapshot and both news rows gone) and chart inputs to 1. The kdst lane's
  rewrite of the news fixture test was dropped with the news tests.
- Verified (after merge): 12-combo sweep of `make sync` builds of the new
  origin/main vs this branch, root + classic: zero fixedPieIndexed /
  sourceScaleAgreement / sourcePeaks / getAllRows diffs, table text identical
  (whitespace-normalised), no errors or 404s. `make sync` + `make validate`
  exit 0.
- Added `supabase/migrations/retire_player_context_20261008.sql` (NOT applied).
  It aborts if any of public.player_news / player_adjustments / player_review
  has rows, redefines `api.gate_context_valid_fresh` without table reads (the
  live function reads public.player_news unconditionally and is called by
  `api.run_publish_gate` on every bake, so dropping the tables alone would
  break the publish gate), then drops `api.player_context` and the three
  tables without CASCADE. Verified read-only: 0 live rows in each table; only
  `api.player_context` (view) and `api.gate_context_valid_fresh` reference them;
  only `api.run_publish_gate` calls that function; no repo code writes them.
  Claimed, not confirmed: the migration itself has not been executed anywhere.
