# Engineering notes (moved from AGENTS.md, 2026-10-09)

Dated incident and design notes that used to live in `AGENTS.md`. Moved verbatim
under JEG-524 so agents load them only when a task touches these areas.
Older briefs cite `AGENTS.md:<line>` for these sections; the content is here now.

## FantasyCalc drift auto-trigger (2026-09-30)
- Standing rule (Jeremy): the project reruns the FantasyCalc pipelines when
  native doesn't match live. `pipelines/check_fantasycalc_drift.py` compares
  the live API (top-25 by value) against the snapshot's native_value; if >20%
  moved by >5%, it exits 1. With `--trigger` it refreshes the snapshot from
  the live API and runs match -> reference -> section -> reindex -> fixture
  -> monitors automatically. (Thresholds tuned 2026-09-30: FantasyCalc updates
  through the day, so 1-3% intraday moves are normal noise — the 5%/20%
  bands prevent constant refresh churn while still catching real corruption
  like the JSN defect.)
- Live-verification bypass (Jeremy 2026-10-04): when the review stage's
  `native_drift` check fails for a source with a live API (currently only
  FantasyCalc), it verifies the top-25 candidate natives against the live
  site before failing. If 80%+ match within 5%, the drift is genuine (source
  moved, not a pipeline bug) and the check passes as "live-verified". Network
  failures fail closed (no pass on unverifiable). `--no-live-verify` skips
  the check for CI/offline (drift fails hard). Sources without a live API
  keep the hard fail. Regression: 4 new tests in test_review_candidate.py.
- The 2026-09-30 JSN defect proved why: `match_source_snapshot.py` was
  dropping `native_value`, so the pipeline used the flattened `value` (50.7)
  instead of the raw FantasyCalc number (9914). The matcher and
  `build_source_reference.py` now carry `native_value` through every stage.
- Regression tests: `tests/test_fantasycalc_drift.py` (5 tests).
- Refresh (updated 2026-10-08): the scheduled FantasyCalc producer is
  `.github/workflows/fantasycalc-weekly-save.yml` (pg_cron
  `trigger-fantasycalc-weekly-save`, Tue + Fri 13:07 UTC): pulls the 12-team
  lists and saves a reindexed bake via `save_fantasycalc_references.py`.
  `fantasycalc-drift.yml` is a manual-only drift check now.
  `refresh_fantasycalc_supabase.py` (wrote raw natives into `value`, hardcoded
  Week 4, no bake_id) was deleted; see docs/watchdog.md "Producer schedules".

## As-published indexing: proportional scaling (2026-09-30)
- User directive: "there is no need for rounding like this, so figure out a logic that applies to all the ones sourced from trade value charts." The per-position quantile mapping was destroying real value differences (Jeanty 6365 vs Cook 7157 → both 41.4) and scrambling cross-position rank.
- New logic in `pipelines/reindex_comparison_section.py`: sources with `value_provenance == "published"` (FantasyCalc, USA Today, FantasyPros, CBS) use GLOBAL proportional scaling instead of per-position quantile mapping.
- Formula: `indexed = native × (anchor_total / native_total)` over shared players. This preserves exact value ratios (Cook 12.4% above Jeanty stays 12.4% above), cross-position order, and all differences. No quantile mapping, no rounding in storage.
- Fixed-pie invariant holds: sum(indexed) = anchor_total by construction.
- DDF-methodology sources (ESPN) keep the per-position quantile mapping.
- Verified: Jeanty 6365→42.36, Cook 7157→47.63 (ratio 1.1244 preserved); Taylor 70.0→51.71, Walker 57.9→42.77 (ratio 1.209 preserved).

## VORP>0 overlap calibration (2026-09-30 PM)
- Refinement to as-published proportional scaling (Jeremy): "players with vorp>0 should all add up to the same amount. Some trade charts don't go as deep into vorp>0, but they'll all have overlapping players for the first 50-150, so we can set the index on that set and then use the relative values on the remainder of the chart for the balance."
- Implementation: scale is calibrated on the VORP>0 overlap set (players with anchor_value > 0, typically 150-170 players), not all shared players. The deep tail varies in depth by source and shouldn't drive the scale.
- Formula: scale = sum(anchor_overlap) / sum(native_overlap); indexed = native * scale for ALL priced players.
- Fixed-pie target is the anchor's overlap total; the source's overlap players sum to it.
- Method name: `proportional_scaling_vorp_overlap`. Overlap slugs stored in fit metadata for test verification.

## Lineage rebuild must not run in CI without snapshots (2026-10-01)
- The 09-30 "auto-rebuild source value lineage on every deploy" step runs `build_source_value_lineage.py` in CI, where the gitignored `data/raw` snapshots are ABSENT. The builder silently fell back to TRANSFORMED combo natives and compared live raw values against them: served FantasyPros showed 0/25 live matches (live Gibbs 75.1 vs transformed 88.8) — a monitor false-red caused by the build environment, not the data.
- Fix: `require_snapshot_natives()` in the builder now raises SystemExit when any SNAPSHOT_PATHS source loads zero natives. The write happens at end-of-main, so a CI failure leaves the committed (locally built, correct) `dist/modules/source-value-lineage.json` untouched and the deploy proceeds (step is continue-on-error).
- Rule: any committed `dist/modules/*.json` that CI regenerates must be buildable from repo inputs alone, or the rebuild step must fail closed instead of writing degraded output. Same class as the import-health staleness bug.
- Regression: `tests/test_lineage_snapshot_guard.py` (4 tests: empty refuses, partial refuses, full passes, real local snapshots satisfy — the last is `skipUnless` the gitignored snapshots exist, because a test asserting their presence can never pass in CI; the first version of it failed CI validation and blocked the 3c2136bf deploy). Rebuilt locally 2026-10-01: FantasyPros 25/25, CBS 25/25, FantasyCalc 22/25 (3 genuine intraday moves), USA Today 19/25 + 6 no-live (scrape 402, recorded in live_stale_sources), ESPN N/A-by-design.
- Oddity found during the fix: `data/raw/sources/fantasycalc/week-4/snapshot.json` is force-added to git despite `.gitignore` carrying `data/raw/`; the fantasypros/usatoday snapshots are properly ignored. That's why CI loaded 196 fantasycalc natives while fp/usa loaded 0. Left as-is (removing it would change FantasyCalc lineage behavior); flagging for the next snapshot-management pass.

- Retired 2026-10-08 (chore/retire-extras): the lineage builder, its CI step and `tests/test_lineage_snapshot_guard.py` are gone (last present at `aefb8f7`). The rule above still stands for every other CI-regenerated artifact.

## CI sync must prefer the freshest health file, not the fixture (2026-10-01)
- The 30-min health cron pushes a fresh `dist/modules/source-import-health.json` with every run, but CI's `make sync` (where the gitignored `output/` runtime file is absent) unconditionally fell back to the committed fixture `data/fixtures/current/source-import-health.json` and OVERWROTE the fresh pushed copy before upload. On 2026-10-01 the served monitor read `checked_at` 08:37Z while main held 10:07Z, because the last three health pushes (4e035da, 46638ad, 28b346f) had stopped including the fixture copy.
- Fix in `pipelines/sync_dashboard_artifacts.py::import_health_source()`: candidates (runtime, checked-in dist copy, fixture) are now ranked by `checked_at` and the freshest valid payload wins; the write step skips the self-copy when the source IS the dist file. Regression: `tests/test_sync_health_freshest.py` (4 tests, incl. a simulation proving the OLD code chose the stale fixture against the broken state), wired into `make validate`'s test-unit list.
- Rule: any committed `dist/modules/*.json` that CI rewrites must resolve to the freshest valid input, never a hardcoded fallback. Both candidates must remain committed: the fixture copy is refreshed by the health runs so the fallback path never drifts by more than one cycle. Note the 30-min cron body itself never contained the fixture-copy step -- the fix makes that omission harmless.
- The fixture was also refreshed to the 10:37Z green gate (6/6 ok) in the same push.

## Watchdog: status marker before content words; repo pulls before legacy cache (2026-10-01)
- `ops/watchdog/_common.py::classify_run_line` used to match the standalone word FAILED before checking the run's status marker (`| OK |`, `SUCCESS`, `no-update`). Razzball's pull log legitimately writes detail notes like "1 rows failed PPG consistency" on an OK run (a tolerated single-row anomaly under the gate threshold), which false-tripped `failed` and then cascaded into a false "CRITICAL: artifact rewritten AFTER the failed run". Rule: status marker wins over detail-text words; genuine `| FAILED |` lines are unaffected. Regression test uses the real 2026-10-01 log line.
- Weekly-article watchdog checks (`check_weekly_article`) read the newest `ops/watchdog/pulls/<src>-<date>.json` first and fall back to the legacy goal-workspace cache. The legacy cache (`lottery/data/sources_cache/*.json`) went dead after the repo ingest pipelines replaced the old lottery pullers (Sep 21); reading it first false-alarmed STALE on CBS/USA Today while Supabase already held fresh rows. When a watchdog source false-alarms stale, check which cache path the watchdog reads before assuming the ingest is broken.
- USA Today 2026-09-29 week-3 article layout note: the QB table sits under the generic "Week N fantasy trade charts" h2 (lazy h2->table pairing); `pull_usatoday.py::_clean_title_position` infers the QB title from the 1QB/6-TD/SFLEX header signature. Also 2026-10-01: curl fetches of usatoday.com article pages now return persistent 402 while sitemap + browser render still work. FIXED same day: the 402 is header-based blocking — adding full browser `Accept`, `Accept-Language`, and `Upgrade-Insecure-Requests` headers to `ops/watchdog/_common.py::fetch` restores 200 (verified on the week-3 article). This is the shared fetch, so CBS and any other watchdog puller get the headers too. The 2026-10-01 fresh pull (238 rows, content-identical to 2026-09-30) used this path.

## cbsros wired through Supabase (2026-10-01)
- `public.cbs_ros_projections` table created (DDL: `sql/migrations/002_cbs_ros_projections.sql` — run in Supabase SQL editor; PostgREST cannot DDL). Grain: (player_key, cbs_snapshot_date). Modeled on `espn_season_projections`.
- DDL was run via the browser SQL editor; afterward PostgREST still 404'd the table (PGRST205) until `NOTIFY pgrst, 'reload schema';` was run in the SQL editor. Expect the schema-cache lag on every future DDL.
- PostgREST table-name rule: sbclient builds `/rest/v1/<table>`, so pass the BARE table name (`cbs_ros_projections`). The first save_cbsros run passed `"public.cbs_ros_projections"` and PostgREST looked for a table literally named that (error: "Could not find the table 'public.public.cbs_ros_projections'"). All working savers use bare names; SOURCE_TABLES keeps schema-qualified names only as manifest labels.
- `pipelines/save_cbsros_references.py` uploads snapshot data to the table (fail-closed identity via public.players, same ALIASES as the DDF leg). 2026-09-30: 363 rows (4 fail-closed identity exclusions: Trubisky, Brooks, Knight, Okonkwo).
- `pipelines/import_supabase_references.py`: cbsros added to DB_SOURCES/SOURCE_TABLES. `build_cbsros_snapshot()` emits the NATIVE shape (schema `trade-value-cbsros-snapshot-v1`, top-level `vintage_date`, rows with ros_*/per_game_*/gp/receptions/raw_stats) — NOT the generic comparison shape. cbsros's production chain is snapshot -> DDF leg -> section (rebuild_comparison_chain.py run_cbsros_source); the DDF leg fail-closes on a missing vintage_date, so the first DB-backed import (comparison-shaped) would have broken the chain. pos from public.players.position, team from the fixture players.json map.
- Round-trip verified 2026-10-01: Supabase table -> import -> native snapshot -> build_cbsros_ddf_leg.py (half_ppr, 12t) produces byte-identical values/ppg for all 329 players common with the old file-backed leg, plus 4 previously-unresolvable fullbacks (Juszczyk, Heyward, Beck, Burton) now resolving at 0.0 via canonical names.
- `.github/workflows/rebuild-chain.yml`: cbsros added to the import loop.
- `pipelines/verify_import_health.py`: cbsros moved from SNAPSHOT_ONLY to DB-backed with table config. Health gate GREEN 2026-10-01 (6/6).
- The force-added `data/raw/sources/cbsros/2026-09-30/snapshot.json` (commit ec4f3986) is retired: archived under `_superseded/` after the DB-backed import was verified live (health gate GREEN, DDF-leg round-trip byte-identical).

## razzball wired through Supabase: code landed, table created 2026-10-02 but EMPTY (JEG-18)
- `public.razzball_projections` was created 2026-10-02 from `sql/migrations/003_razzball_projections.sql` (Jeremy's explicit yes in the Claude session; applied with the Supabase `apply_migration` tool, followed by `NOTIFY pgrst, 'reload schema'`). Verified read-only afterwards: 21 columns, primary key plus the two indexes, RLS off like `cbs_ros_projections`, **0 rows**. No row has been written yet: the first real save has to run on the machine that has `data/raw/sources/razzball/`.
- `pipelines/save_razzball_references.py`: snapshot -> table. Per-game columns `rz_std_ppg/rz_half_ppr_ppg/rz_ppr_ppg` -> `per_game_standard/half_ppr/ppr`; every other row field verbatim in `raw_stats`; stamped from the snapshot's `vintage_date`. Upsert key `(player_key, razzball_snapshot_date)`.
- `pipelines/import_supabase_references.py`: `razzball` in `DB_SOURCES`/`SOURCE_TABLES`, removed from `HARD_EXCLUSIONS` (ecr/vegas/prediction markets stay). `build_razzball_snapshot()` rebuilds the native shape (schema `trade-value-razzball-snapshot-v1`) the DDF leg reads.
- `pipelines/verify_import_health.py`: razzball is DB-backed, judged on the dated daily rule (not week-designated). `.github/workflows/rebuild-chain.yml`: razzball added to the import loop.
- **Merge order matters:** with this merged, the import-health gate needs a Razzball snapshot from Supabase. Until the table exists and holds a vintage, the gate reports `MISSING razzball` and the 6-hourly chain goes red. Run the migration and the first real save (on the machine that has `data/raw/sources/razzball/`) BEFORE merging.
- Tested with synthetic rows only (the real snapshot lives on the owner's machine). The puller named in JEG-18 (`pipelines/pull_razzball_ros.py`) is not in this repo, so the snapshot row shape is inferred from `data/inputs/razzball_projections.csv` and from what `build_razzball_ddf_leg.py` reads.
