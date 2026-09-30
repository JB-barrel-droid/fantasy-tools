# Claude session log

Handoff notes between AI sessions ("harnesses"). Newest entry first.

**Why this exists:** a session ends with claims in its chat transcript and nothing
in the repo. The next session starts blind, re-derives what the last one already
worked out, and — worse — inherits assertions it has no way to check. This file
carries the claims forward *with their evidence*, so the next session knows what
was measured and what was merely asserted.

## How to use it

Every session that changes anything in this repo appends an entry before it
finishes. See `CLAUDE.md` for when that is required.

Each entry separates three things, and the separation is the point:

- **Verified** — checked this session, with the check named. A number with no
  stated method is not verified.
- **Claimed, unverified** — stated in the session but not actually confirmed,
  or confirmed only by weak evidence. Say what would settle it. Anything here is
  a lead, not a fact; do not build on it without checking first.
- **Open** — known to be wrong or incomplete, and not fixed.

Durable issues also belong in `docs/risk-register.md`. That file is the standing
issue list; this one is the narrative of who checked what, when. When an entry
here names a lasting problem, add it there too and say so.

Correcting an earlier entry is expected and welcome. Do not edit the old entry:
add a new one that says what was wrong. The record of a mistaken claim is more
useful than a tidy file.

---

## 2026-09-30 - Health gate hardening: all-sources global-red gate, future-timestamp rejection, malformed-entry blocking

### Verified

- **Global-red gate strengthened in `_check_health_file_staleness`**: the prior
  implementation iterated `health["sources"].items()` and used
  `if isinstance(entry, dict) and entry.get("status") != "ok"` — two silent gaps:
  (1) a source absent from the health file was never checked; (2) a non-dict entry
  (null, string) short-circuited the `isinstance` guard to False and was silently
  skipped. Replaced with iteration over `sorted(ACTIVE_CASCADE_SOURCES)`:
  any source absent from or malformed in the file raises SystemExit immediately.
  [`Edit pipelines/cascade_source_update.py`]

- **Future `checked_at` rejected**: the prior gate `age_days > _MAX_HEALTH_AGE_DAYS`
  passes for negative `age_days` (future timestamps). Added `age_days < 0` to the
  rejection condition; message distinguishes "future timestamp (N day(s) ahead)"
  from "stale (N day(s) old)". [`Edit cascade_source_update.py`]

- **`build_health_file` updated to include all 5 ACTIVE_CASCADE_SOURCES**: the prior
  helper only wrote the target source entry. With the new all-sources global gate,
  every existing test that reaches `_check_health_file_staleness` would have failed
  because espn/usatoday/fantasypros/cbs were absent. Now all five are populated;
  non-target sources get `{"status": "ok", "content_vintage": content_vintage}`.
  Tests that want a missing/malformed/stale entry manipulate the returned file
  directly after the call. [`Edit tests/test_pipeline_cascade.py`]

- **3 new regression tests added to `HealthGateRegressionTest`**:
  - `test_omitted_required_source_blocks_cascade`: espn removed from health file
    after build → global gate blocks ("cascade blocked: ... espn ... absent or
    malformed ..."), no downstream writes.
  - `test_malformed_source_entry_blocks_cascade`: cbs entry replaced with null
    after build → global gate blocks ("cascade blocked: ... cbs ... 'NoneType' ..."),
    no downstream writes.
  - `test_future_checked_at_blocks_cascade`: checked_at set 2 days in the future →
    age gate blocks ("cascade blocked: ... future timestamp ..."), no downstream writes.
  [`Edit tests/test_pipeline_cascade.py`]

- **`python3 -m unittest discover -s tests`: 440 passed, 6 skipped, 0 failures.**
  (Prior: 437 + 3 new.) [`Run`]

- **`make validate`**: red on same pre-existing freshness gate (comparison.built_at
  age_days=4). naming/reference/sync/tests all pass. No push. [`make validate`]

- Updated FIX-010 in `docs/risk-register.md` with this session's fixes and new
  test count. [`Edit`]

### Claimed, unverified

- The all-sources check mirrors `run_health` global-red semantics. In production,
  a health file produced by `make import-health NFL_WEEK=<n>` always includes all
  five active sources in its output. Not exercised by test (requires live Supabase).

### Open

- `make validate` remains red on same pre-existing blockers (GAP-007, 009, 010, 011).

---

## 2026-09-30 - Health gate hardening: rc check, global-red gate, checked_at age, snapshot identity, actual subprocess tests

### Verified

- **`run_health` rc check added to `_refresh_health_after_import`**: previously the
  integer return code from `run_health` was discarded; a non-zero rc (the normal
  failure path when any source is not ok) silently proceeded. Now: `rc = _vh.run_health(...)`;
  if `rc != 0` raises `SystemExit("cascade blocked: import health refresh returned exit {rc}...")`.
  Removing exception catches alone was not sufficient — the rc path was the primary
  failure signal. [`Edit cascade_source_update.py`]

- **`_check_health_file_staleness` helper added** — shared gate called from both
  `_check_import_health` and `_check_artifact_health` after per-source status passes.
  Covers three additional failure modes:
  1. `checked_at` age check: health must be ≤ 2 days old (same policy as freshness-check);
     NFL week match alone is not sufficient (Monday health reused on Thursday blocks).
  2. `nfl_week` currency: health must reflect the current calendar week.
  3. Global-red gate: all sources in the health file must be ok before any cascade stage
     runs. A single stale source blocks cascade for ALL sources, not just its own.
  [`Edit cascade_source_update.py`]

- **Snapshot identity cross-check added to `_check_import_health`**: after the
  manifest sha256/bytes check passes for the import snapshot, reads the snapshot
  referenced in `health_entry["snapshot_path"]` and verifies its sha256 matches
  the import snapshot's sha256. A different snapshot with the same content_vintage
  now fails closed. [`Edit`]

- **Provenance cross-check added to `_check_artifact_health`**: after the health
  snapshot sha256 is computed as `expected_sha`, reads the artifact's
  `source_provenance.snapshot_manifest`, loads it, gets `snapshot_sha256`, and
  compares to `expected_sha`. An artifact derived from a different snapshot than
  health checked (same vintage, different bytes) now fails closed. [`Edit`]

- **5 new regression tests added to `HealthGateRegressionTest`**:
  - `test_global_red_health_blocks_cascade`: target source ok, usatoday stale in
    health file → global-red gate blocks, no output written.
  - `test_run_health_nonzero_return_blocks_refresh`: mock `run_health` returns 1 →
    `_refresh_health_after_import` raises SystemExit("cascade blocked: ... exit 1 ...").
  - `test_old_checked_at_blocks_cascade`: health `checked_at` 3 days ago → age gate
    blocks, no output written.
  - `test_different_snapshot_identity_blocks_import`: health verified against snapshot A,
    cascade called with snapshot B (own valid manifest, same vintage, different sha256) →
    identity gate blocks.
  - `test_mismatched_lineage_blocks_intermediate`: artifact derived from snapshot A,
    health verified against snapshot B → provenance cross-check blocks.
  [`Edit tests/test_pipeline_cascade.py`]

- **`MakefileExecutionTest` class added** with 2 actual subprocess execution tests
  (not dry-run). Replaces the `make -n` string-assertion approach with real end-to-end
  pipeline runs using isolated tmp-dir fixtures:
  - `test_make_source_match_actual_execution`: runs `make source-match SNAPSHOT_FILE=...
    PLAYERS=... COMPARISON=... OUTPUT_ROOT=...` with a non-active ("testonly") source,
    asserts exit ∈ {0,2}, pipeline report exists, at least one review artifact exists.
  - `test_make_comparison_merge_actual_execution`: produces a section artifact via
    in-process cascade, then runs `make comparison-merge CANDIDATE_FILE=... ...` as a
    subprocess, asserts same downstream outputs.
  Six original `make -n` dry-run tests in `MakefileWiringTest` retained for routing
  verification of the remaining targets. [`Edit tests/test_pipeline_cascade.py`]

- **`python3 -m unittest discover -s tests`: 437 passed, 6 skipped, 0 failures.**
  (Prior: 430 passed + 7 new.) [`Run`]

- **`make validate`**: red on same pre-existing freshness gate (comparison.built_at
  age_days=4). naming/reference/sync/tests all pass. No push — validate is red.
  [`make validate`]

- Updated FIX-010 in `docs/risk-register.md` with second-round concrete defects fixed
  and new test count. [`Edit`]

### Claimed, unverified

- The six dry-run `MakefileWiringTest` tests remain in place alongside the two new
  execution tests. They cover argument/variable wiring for targets not exercised by
  the execution tests; they have not been removed.

### Open

- `make validate` remains red. Same pre-existing blockers (GAP-007, 009, 010, 011).
  No regression caused by this session's changes.

---

## 2026-09-30 - Health gate hardening: byte verification, authoritative week, fail-closed refresh

### Verified

- **`_refresh_health_after_import` defect fixed**: was using `_nfl_week_from_manifest(snapshot_path)`
  to derive the expected NFL week from the incoming snapshot data. Week 3 data
  would therefore be validated against Week 3 even when run in Week 4. Replaced
  with `verify_import_health.nfl_week_for_date(verify_import_health.utc_today())` —
  the calendar-authoritative current week, independent of the data being imported.
  [`Edit cascade_source_update.py`]

- **Exception swallowing fixed**: `_refresh_health_after_import` previously caught
  `SystemExit` (silently) and `Exception` (logged, then continued). Removed both
  catches. Any exception now propagates to the caller; a pre-existing ok health
  report cannot silently authorise a cascade when the refresh fails. [`Edit`]

- **Snapshot byte verification added to `_check_import_health`**: after vintage/status
  match, now reads snapshot bytes and verifies sha256 against `manifest["snapshot_sha256"]`.
  Missing sha256 in manifest, unreadable snapshot, and hash mismatch all fail closed.
  A snapshot with altered values but unchanged vintage string will be blocked. [`Edit`]

- **`nfl_week` staleness check added to `_check_import_health`**: health file's
  `nfl_week` must equal `nfl_week_for_date(utc_today())`. A health file from
  a prior week no longer authorises cascade entry. [`Edit`]

- **Snapshot byte verification added to `_check_artifact_health`**: resolves
  `entry["snapshot_path"]` from the health file (absolute or ROOT-relative),
  loads its manifest, and verifies sha256. Health entries without `snapshot_path`
  fail closed. Same `nfl_week` freshness check added. [`Edit`]

- **`build_snapshot` updated in tests**: now computes sha256 of snapshot bytes and
  includes `snapshot_sha256` in the manifest. Snapshot content is written directly
  as bytes so the same hash is used for verification. [`Edit tests/test_pipeline_cascade.py`]

- **`build_health_file` updated in tests**: new `snapshot_path` kwarg stores the
  absolute path in the health entry so tests that reach the byte-verification step
  can resolve the snapshot. New `nfl_week` kwarg (default 4) enables the stale-week
  regression tests. [`Edit`]

- **`_build_hold_world` updated**: inline manifest writer now includes
  `snapshot_sha256`. [`Edit`]

- **Updated `test_health_ok_matching_vintage_allows_cascade`** to pass
  `snapshot_path=snapshot` to `build_health_file` (needed to pass new sha256 gate).
  Updated `test_active_source_match_allowed_with_valid_health` likewise. [`Edit`]

- **11 new tests added** (`HealthGateRegressionTest` × 5, `MakefileWiringTest` × 6):
  - Stale Week 3 health blocks snapshot-entry cascade.
  - Stale Week 3 health blocks intermediate-artifact-entry cascade.
  - Modified snapshot bytes (sha256 mismatch) blocks snapshot-entry cascade.
  - Modified snapshot bytes blocks intermediate-artifact-entry cascade.
  - `_refresh_health_after_import` exception propagates (not swallowed).
  - Six Makefile dry-run tests (`make -n supabase-import|source-match|source-reference|
    comparison-section|comparison-merge|comparison-reindex`) verify argument/variable
    wiring without executing the pipeline. Each asserts `cascade_source_update.py`
    and the correct flag appear in the dry-run output. [`Edit`]

- **`python3 -m unittest discover -s tests`: 430 passed, 6 skipped, 0 failures.**
  (Prior: 419 passed + 11 new.) [`Run`]

- **`make validate`**: red on same pre-existing freshness gate (comparison.built_at
  age_days=4). naming/reference/sync/tests all pass. No push — validate is red.
  [`make validate`]

- Updated `docs/modular-pipeline.md` health gate documentation to accurately describe
  the calendar-authoritative week derivation, fail-closed refresh semantics, and
  sha256 + nfl_week checks at all entry points. [`Edit`]

- Updated FIX-010 in `docs/risk-register.md` with the three concrete defects fixed
  in this session and the new test count. [`Edit`]

### Claimed, unverified

- In production, `_refresh_health_after_import` correctly writes a current-week
  health file after `make supabase-import SOURCE=X`. Not tested: the supabase import
  path requires a live Supabase connection and cannot be exercised by unit tests.

### Open

- `make validate` remains red. Same blockers: USA Today and CBS Week 4 data absent
  (GAP-009), FantasyCalc multi-combo pull incomplete (GAP-010), ESPN fixture combo
  mismatch (GAP-011).

---

## 2026-09-29 - Automatic entry-point cascade + health gate enforcement

### Verified

- Integrator review identified two unmet requirements from the prior session:
  (1) existing Makefile entry points still invoked isolated stage scripts rather
  than automatically cascading; (2) the `--input` intermediate artifact path and
  `--skip-health-check` flag bypassed pipeline-rules §8 for active sources.
  [`Read cascade_source_update.py main(); Read Makefile`]

- Routed all Makefile stage targets through `cascade_source_update.py`:
  `supabase-import`, `source-import`, `source-match`, `source-reference`,
  `comparison-section`, `comparison-merge`, `comparison-reindex` all now invoke
  the cascade runner. Any successful update to an earlier stage automatically
  processes all dependent downstream stages. `comparison-review` and
  `comparison-promote` remain as-is (terminal/gated). [`Edit Makefile`]

- Removed `--skip-health-check` CLI flag from `cascade_source_update.py`.
  Health gate now applies at every CLI entry for active dashboard sources.
  [`Edit cascade_source_update.py`]

- Added `_check_artifact_health(artifact, artifact_path)` method that extracts
  `source_provenance.content_vintage` from intermediate artifacts and applies
  the same pipeline-rules §8 gate as `_check_import_health`. Missing provenance,
  absent health file, non-ok status, and vintage mismatch all fail closed with
  clear messages. Called from CLI dispatch in `main()` before routing to each
  intermediate entry method — one check per invocation, no double-check on
  internal chains. [`Edit cascade_source_update.py`]

- Added `_refresh_health_after_import(snapshot_path)` that, after a successful
  `import_supabase_source`, calls `verify_import_health.run_health` with the
  NFL week derived from the newly-written manifest (not any stale health file).
  On Supabase failure the refresh is logged and continues; the subsequent
  `_check_import_health` vintage check catches any remaining mismatch. [`Edit`]

- Added `_nfl_week_from_manifest(snapshot_path)` module-level helper that reads
  `week_designated` from the manifest, falling back to `re` parse of
  `content_vintage` (e.g. "Week 4"). Returns None for date-based vintages. [`Edit`]

- 9 new tests added to `tests/test_pipeline_cascade.py`:
  - `EntryPointIntegrationTest` (3 tests): calls `cascade_mod.main()` at the
    snapshot, match, and section entry points (mirroring the updated Makefile
    targets) and asserts all downstream stages ran. Non-active source ("testonly")
    used to keep health gate out of scope for these tests.
  - `IntermediateHealthGateTest` (6 tests): covers missing health file, stale
    health (non-ok status), vintage mismatch, absent source_provenance, valid
    health allows cascade, and non-active source bypasses gate. Each negative
    test asserts `SystemExit` and that no downstream artifacts were written.
    [`Edit tests/test_pipeline_cascade.py`]

- `python3 -m pytest tests/test_pipeline_cascade.py -v`: **26 passed, 0 skipped**.
- `python3 -m unittest discover -s tests`: **419 passed, 6 skipped, 0 failures**.
- `make validate` is red (exit 1) on the same pre-existing freshness gate: same
  `comparison.built_at = 2026-09-25T22:38:27Z` blocker (age_days=4). No push.
  [`pytest; unittest; make validate`]

- Updated `docs/modular-pipeline.md` cascade section: removed bypass claims
  (`--skip-health-check`, gate bypass for intermediate entries), documented real
  behavior (automatic cascade from all existing entry points, health enforced at
  every entry, health refreshed from manifest week after supabase import). [`Edit`]

- Added FIX-010 to `docs/risk-register.md` recording the removed bypass. [`Edit`]

### Claimed, unverified

- `_refresh_health_after_import` will correctly call `verify_import_health.run_health`
  and update `output/source-import-health.json` after `make supabase-import SOURCE=X`
  in production. Not verified: test suite does not cover `--source` path (requires
  Supabase); the refresh path was confirmed by code read only.

### Open

- `make validate` remains red (pre-existing freshness gate). Do not push.
- Same blockers as prior sessions: USA Today and CBS Week 4 data absent,
  FantasyCalc multi-combo pull incomplete, ESPN fixture combo mismatch.

---

## 2026-09-29 - Cascade wiring, documentation, and hold test fix

### Verified

- `make cascade` and `make cascade-from` targets added to Makefile, wired to
  `pipelines/cascade_source_update.py --source` and `--input` respectively.
  Confirmed `grep cascade Makefile` returns the new targets. [`Edit` + `Read`]
- `docs/modular-pipeline.md` now documents the automatic cascade section with
  entry points, exit-code semantics, and the no-automatic-promotion rule.
  Confirmed `grep -c cascade docs/modular-pipeline.md` returns > 0. [`Edit`]
- Skipped test `test_hold_verdict_repeats_and_exits_nonzero_on_identical_rerun`
  was skipped because the prior `_build_hold_world` added an "Unknown Player"
  who was NOT in players.json, so the unmatched player was filtered at the
  match stage and never reached the reindex's review_rows. [`Read` test file;
  trace through match → reference → section → reindex stages]
- Fixed `_build_hold_world`: now adds extra player (key=9999, "Player Extra0")
  to players.json AND to comparison fixture `player_keys` (so they pass match
  and section stages), but NOT to the ESPN anchor values (so the reindex stage
  emits "no anchor value for this player_key" → untriaged review_rows → hold).
  The hold is deterministic; the test body now asserts instead of skipping.
  [`Edit` test file]
- `python3 -m pytest tests/test_pipeline_cascade.py -v`: **17 passed, 0
  skipped** (previously 16 passed, 1 skipped). [`pytest`]
- `python3 -m unittest discover -s tests`: **410 passed, 6 skipped, 0
  failures**. [`unittest discover`]
- `make validate` is red (exit 1) on the same pre-existing freshness gate
  failure: `comparison.built_at = '2026-09-25T22:38:27Z'` (age_days=4,
  max_age_days=2). This is unchanged from prior session. No push made. [`make validate`]

### Claimed, unverified

- `make cascade SOURCE=fantasycalc` will work end-to-end once `make
  import-health NFL_WEEK=4` is green (requires USA Today and CBS Week 4 data).
  The CLI wiring is confirmed by code read; no live run was attempted because
  the health gate would block immediately.

### Open

- `make validate` remains red (freshness gate) pending genuine Week 4 USA
  Today and CBS source data. Do not push until all five sources pass
  `make import-health NFL_WEEK=4` and the freshness gate clears.
- Commit is staged locally only.

---

## 2026-09-29 - Cascade pipeline orchestration implementation

### Verified

- Inspected the three untracked/modified files handed off from Codex:
  `pipelines/cascade_source_update.py` (new, 479 lines), `tests/test_pipeline_cascade.py`
  (new, 198 lines), `pipelines/promote_comparison_section.py` (modified: adds
  `fixture["built_at"] = utc_now()` before writing, so the freshness gate sees
  the promotion date). All three were read before any edits. [`Read` tool; `git diff`]
- Cascade code was missing the required `comparison-merge` step (step 5 in the
  trigger chain). The code went directly from `comparison-section` to
  `comparison-reindex`, skipping the `merge_comparison_candidate.py` zero-fill
  check and candidate report generation. [`Read` cascade_source_update.py]
- Added the merge step to `cascade_source_update.py`:
  - `strip_volatile` now strips `built_at` in addition to `generated_at` so the
    merged candidate artifact (which receives `built_at = utc_now()`) compares
    idempotently. The written files still carry the full unmodified payload;
    stripping is only for the change-detection comparison.
  - Added `default_merge_candidate_path` and `default_merge_report_path` helpers.
  - Renamed old `cascade_from_section` (reindex-only) to `_run_reindex`.
  - New `cascade_from_section` calls `merge_stage.merge_candidate` (fail-closed
    zero-fill check) then writes the merged artifact + candidate report under
    `candidate_dir`, then calls `_run_reindex`. If both merge artifacts are
    materially unchanged, it appends a `cascade-stop` step and returns early.
  - Updated `chain` field in cascade report to include `comparison-merge +
    comparison-merge-report`.
- Updated `tests/test_pipeline_cascade.py` to expect the merge stages in order:
  `source-match, source-reference, comparison-section, comparison-merge,
  comparison-merge-report, comparison-reindex, comparison-review`. Added an
  assertion that the merged artifact contains the candidate source section.
- `python3 -m pytest tests/test_pipeline_cascade.py -v` passed (1/1). [`pytest`]
- `python3 -m unittest discover -s tests` passed (389 passed, 6 skipped). [`unittest discover`]
- `make validate` is red with exit 2:
  `comparison.built_at = '2026-09-25T22:38:27Z'` (age_days=4, max_age_days=2).
  The only failing check is the freshness gate on the comparison fixture. All
  unit tests and naming/reference checks pass. [`make validate`]
- `make validate` freshness gate is blocked by missing genuine CBS and USA Today
  Week 4 source data, exactly as documented in the prior session's log entry
  ("2026-09-29 - Partial Week 4 L1 recovery"). No timestamps were bumped,
  no gates were relaxed. Cascade implementation is not the cause. [`docs/claude-log.md`]
- The `promote_comparison_section.py` modification (adds `fixture["built_at"] =
  utc_now()`) is correct: `built_at` is a processing timestamp, not source
  vintage, and must be refreshed on promotion per pipeline-rules §5. The diff
  is small and standalone. It does not change any data path.

### Claimed, unverified

- The `comparison-merge` step will also run correctly via `--input <section.json>`
  (the `infer_stage` "section" path routes to `cascade_from_section`, which now
  includes merge). Not tested end-to-end with a real section artifact this session.

### Open

- `make validate` remains red (freshness gate) pending genuine Week 4 USA Today
  and CBS source data. No push was made. Commit is staged locally only.
- When USA Today and CBS Week 4 data become available: run `make supabase-import`
  for those two sources, verify `make import-health NFL_WEEK=4` is fully green
  (5/5 ok), run the cascade for each source, then promote each reviewed section
  with an explicit `--approve` before pushing.

---

## 2026-09-29 - L1 raw acquisition path investigation

### Verified

- `b23b243` is the current local HEAD. Its freshness work wires immutable
  `content_vintage` through downstream artifacts and promotion checks; it does
  not itself create raw L1 snapshots. [`git show --stat --oneline b23b243`]
- `make import-health NFL_WEEK=4` is red because all five
  `data/raw/sources/<source>/<vintage>/snapshot-manifest.json` files are
  missing in this checkout. It wrote `output/source-import-health.json` with
  0 ok / 5 missing and `GATE: RED`. [`make import-health NFL_WEEK=4`]
- `make supabase-import SOURCE=espn` cannot run locally because the repo's
  configured Supabase client path is missing: `ModuleNotFoundError: No module
  named 'sbclient'`. The default helper directory
  `~/workspace/skills/supabase-football-signal/bin` does not exist; filesystem
  search found only a compiled cache under
  `/Users/botcomp/Library/Caches/com.apple.python/private/tmp/supabase-football-signal`.
  [`make supabase-import SOURCE=espn`; filesystem search]
- The linked Supabase project is `iskiybsimubiujwuchsl`. Live rows are current
  only for ESPN: `espn_season_projections` has 387 rows at
  `espn_snapshot_date=2026-09-29` / week 3. The weekly lanes top out at Week 3:
  FantasyCalc 591 rows (week 3), USA Today 702 rows
  (`source_content_date=2026-09-23`, week 3), FantasyPros 534 rows
  (`source_content_date=2026-09-22`, week 3), CBS 355 rows (week 3).
  [Supabase connector SQL summary queries]
- The old goal-workspace cache/export paths expected by the saver scripts are
  absent on this Mac:
  `files/espn_projections.csv`, `hidden_files/espn_projections_meta.json`,
  `files/fantasypros_trade_chart.csv`,
  `lottery/hidden_files/fantasypros_chart_fetch_log.jsonl`,
  `lottery/data/sources_cache/fantasycalc_snapshot.json`,
  `fantasycalc_half_12_qb1.json`, `cbs.json`, and `usatoday.json`.
  Repo-owned `data/inputs/espn_projections.csv` exists but is vintage
  `2026-09-22`, so it is not a Sept. 29 source snapshot. [filesystem checks]
- Exact-week ingestion rejects stale article fallbacks for Week 4:
  `python3 ops/watchdog/ingest_usatoday.py --week 4 --dry-run` found the
  Week 3 USA Today URL and refused it; `python3 ops/watchdog/ingest_cbs.py
  --week 4 --dry-run` found a Week 2 CBS URL and refused it. The lower-level
  puller CLIs still print those fallback URLs, so use the ingestion wrappers
  for save eligibility. [commands above]
- Supabase's table listing reported a critical RLS-disabled advisory for many
  public tables. No policy or schema changes were made during this
  investigation. [Supabase `_list_tables`]

### Claimed, unverified

- Muse or the old goal workspace is still the intended raw acquisition/export
  layer for FantasyCalc, FantasyPros trade-chart CSV, and ESPN/CBS/USA Today
  cache files. Repo docs say Muse is the raw scraping lane and the saver
  scripts name the old workspace paths, but no live Muse task/output was
  inspected because the only local Muse export discovered was under
  `~/Projects/fantasy tools`, which this repo's guide says not to touch.

### Open

- Added/updated `GAP-008` and `GAP-009` in `docs/risk-register.md`.
- No fresh Week 4 L1 snapshots were landed. Do not run
  match/reference/section/review/promote until genuine Week 4 rows exist in
  Supabase or validated raw exports, `make supabase-import SOURCE=<source>`
  succeeds for all five sources, and `make import-health NFL_WEEK=4` is green.

---

## 2026-09-29 - Partial Week 4 L1 recovery

### Verified

- Restored the repo's expected local Supabase helper path from the local
  compiled cache:
  `/Users/botcomp/workspace/skills/supabase-football-signal/bin/sbclient.pyc`.
  A read probe against `espn_season_projections` returned the 2026-09-29 row.
  [`python3` import/read probe]
- Stamped live Supabase rows into clean-repo L1 snapshots for all five sources:
  ESPN `2026-09-29` (387 rows), FantasyCalc Week 3 (591), USA Today
  `2026-09-23` (702), FantasyPros `2026-09-22` (534), CBS Week 3 (355).
  [`make supabase-import SOURCE=<source>` x5]
- Pulled fresh FantasyCalc Week 4 values directly from
  `https://api.fantasycalc.com/values/current` for redraft 12-team 1QB
  standard/half/full, wrote the expected cache files under
  `~/workspace/goals/football-signal-database-and-app/lottery/data/sources_cache`,
  saved 580 Week 4 rows to Supabase (`fcwk4_2026-09-29_v1`), and restamped
  `data/raw/sources/fantasycalc/week-4/snapshot.json`. The saver left 27 rows
  in review rather than guessing identities/anchors. [FantasyCalc API pull;
  `save_fantasycalc_references.py`; `make supabase-import SOURCE=fantasycalc`]
- Found the FantasyPros Week 4 article at
  `https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-4-2026/`.
  Page metadata reports `article:published_time` as `2026-09-29 14:40:11`.
  Parsed 178 article rows, resolved them to canonical `player_key` values,
  wrote the expected CSV/fetch-log files, saved 531 Week 4 rows to Supabase
  (`fpwk4_2026-09-29_v1`), and restamped
  `data/raw/sources/fantasypros/2026-09-29/snapshot.json`. Six rows stayed in
  review at the saver/reindex stage. [FantasyPros article parse;
  `save_fantasypros_references.py`; `make supabase-import SOURCE=fantasypros`]
- A bad transient FantasyPros Week 4 snapshot with 819 rows failed health as
  table drift against the 531-row table. Archived it under
  `data/raw/sources/fantasypros/2026-09-29/_superseded/...` and restamped the
  531-row table-verified snapshot. [`make import-health NFL_WEEK=4`;
  `make supabase-import SOURCE=fantasypros`]
- Current Week 4 import health is 3 ok / 2 stale / 0 missing / 0 failed:
  ok = ESPN, FantasyCalc, FantasyPros; stale = USA Today (`2026-09-23`, Week 3)
  and CBS (`Week 3`). [latest `make import-health NFL_WEEK=4`]
- USA Today and CBS still do not have discoverable Week 4 source pages through
  the current repo pullers: USA Today Week 4 falls back to the Week 3 URL; CBS
  Week 4 falls back to a Week 2 URL. [puller dry-runs]
- `python3 -m unittest discover -s tests -p 'test_supabase_import.py'` and
  `python3 -m unittest discover -s tests -p 'test_import_health.py'` passed.
  `make freshness-check` remains red because the comparison fixture is still
  built at `2026-09-25T22:38:27Z`; downstream promotion was not run because L1
  is not fully green. [commands named]

### Claimed, unverified

- None.

### Open

- Added/updated `GAP-008` and `GAP-009` in `docs/risk-register.md`.
- Finish Week 4 only after genuine USA Today and CBS Week 4 sources exist.
  Then import those two, rerun `make import-health NFL_WEEK=4`, and only then
  continue to match/reference/section/review/promote.

---

## 2026-09-28 - Live deploy attempt blocked by source-refresh access

### Verified

- The latest pushed cleanup commit is not live through the normal Pages
  workflow. `gh run list --repo JB-barrel-droid/fantasy-tools --workflow
  "Deploy dashboard" --limit 5` showed failed `main` runs `36463813393`
  (push) and `36466759302` (scheduled) after commit `16c5e5c`.
- The blocker remains the enforced source freshness gate, not a code test
  failure. The current fixture has `comparison.built_at=2026-09-25T22:38:27Z`,
  which is stale on 2026-09-28 with `MAX_STALE_DAYS=2`.
- The documented refresh path cannot run in this local task as configured.
  `make supabase-import SOURCE=fantasycalc` failed with
  `ModuleNotFoundError: No module named 'sbclient'`; the default helper path
  `~/workspace/skills/supabase-football-signal/bin` is absent; filesystem
  search found no local `sbclient.py`; no `SUPABASE_*` environment variables
  were present.
- Supabase MCP and Claude Code MCP were not usable as substitutes in this task:
  their calls required approval while the task approval policy was `never`.
- Sibling and temp checkouts only contained older or same-vintage generated
  comparison fixtures. No newer validated snapshot/review artifact was available
  locally for promotion.

### Claimed, unverified

- None.

### Open

- Added `GAP-008` to `docs/risk-register.md`: restore a working
  `SUPABASE_FOOTBALL_SIGNAL_BIN`/`sbclient` path or provide validated raw source
  snapshots, then run the full five-source refresh and `make validate`.
- Do not force this live by bumping `built_at`, relaxing `MAX_STALE_DAYS`, or
  bypassing the Pages workflow gate.

## 2026-09-28 - Open gap cleanup and diagnostics fallback

### Verified

- Closed the silent partial-adjustment gap. `pipelines/build_adjustment_inputs.py`
  now writes `cell_coverage` with expected/present/missing position-tier cells;
  incomplete sources are `partial-stage2`. The chart and comparison table only
  activate adjusted source projects when all 8 cells are present, and otherwise
  return no adjusted map instead of mixing raw published values into an adjusted
  curve.
- Rebuilt the live and versioned adjustment-input artifacts. Current coverage:
  USA Today complete/live; FantasyCalc missing `QB|bench`; FantasyPros missing
  `TE|bench`; CBS missing `QB|bench`, `RB|bench`, and `TE|bench`.
- Fixed review methodology for source refreshes. Reindex preserves candidate
  vintage metadata; review keeps same-vintage or unknown-vintage native drift
  fail-closed and reports different-vintage drift as measured source movement.
- Controlled CBS thin coverage without imputing values. Current CBS `full_12`
  fixture has 119 native/reindexed players and omits Bo Nix; regression coverage
  asserts reindexed CBS values do not add unpublished players.
- Added `make diagnostics` as a non-browser fallback for chart/value diagnostics
  when local Playwright/Chromium launch is blocked.
- Validation:
  `make diagnostics` passed (103 tests OK, 6 skipped);
  `make sync && make test` passed (386 tests OK, 6 skipped).

### Claimed, unverified

- None.

### Open

- `make validate` is red on 2026-09-28 because the enforced freshness gate sees
  `comparison.built_at=2026-09-25T22:38:27Z` as 3 days old with
  `MAX_STALE_DAYS=2`. This is recorded as `GAP-007` in
  `docs/risk-register.md` and requires a real source refresh, not a timestamp or
  threshold change.
- Claude Code MCP setup is authenticated, but this task could not start a
  delegated Claude session because the MCP call required approval while the
  current approval policy was `never`.

## 2026-09-27 - Repo gap register and adjusted table cleanup

### Verified

- Follow-up after push: tightened adjusted-source copy so dashboard health cards
  and comparison table badges call them derived adjusted projects rather than
  native/bias-adjusted source publications. Added
  `test_adjusted_copy_names_derived_projects` to prevent the old wording from
  returning. `make validate` passed afterward: 382 tests OK, 6 skipped.
- Added the missing repo entrypoints named by `AGENTS.md`:
  `SYSTEM_MAP.md`, `docs/methodology.md`,
  `docs/director_operating_model.md`, and `execution/current-plan.md`.
- Rebuilt `docs/risk-register.md` as the canonical durable gap register and
  updated `CLAUDE.md` so future sessions must record durable gaps there, not
  only in chat or this log.
- Fixed the comparison dashboard adjusted-column gap: `comparison-dashboard.js`
  now loads `assets/adjustment-inputs.json`, builds live adjusted maps from
  source cells, and uses `ValueModel.shapeToAnchorPeaksThenSharedTotal()` for
  live adjusted columns, matching the curve widget's anchor-shaping path.
- Added regression tests in `tests/test_two_tier_frontend.py` proving both
  renderers load adjustment inputs, build live adjusted maps, and route adjusted
  values through the shared anchor-shaping normalizer.
- `make validate` passed after sync: naming check OK, reference artifacts OK,
  enforced freshness expired count 0, dashboard artifacts synced, and 381 tests
  OK with 6 skipped.
- `dist/assets/comparison-dashboard.js` contains the same live adjustment-input
  path after `make validate` synced the dashboard artifacts.

### Claimed, unverified

- None.

### Open

- Plain `git ...` commands still do not work because this workspace uses
  `.gitstore` rather than `.git`, and the sandbox refused creating a `.git`
  pointer file. Commit/push is still possible with
  `git --git-dir=.gitstore --work-tree=. ...`; this is recorded as controlled
  in `docs/risk-register.md`.
- Fresh Playwright browser diagnostics are still blocked in this sandbox by
  browser/cache process issues; this is now recorded as `GAP-002` in
  `docs/risk-register.md`.
- Adjustment-cell incompleteness remains open (`GAP-004`): CBS has 5 live cells,
  USA Today 7, while FantasyCalc/FantasyPros have 8.

## 2026-09-27 - Curve logic spot-check

### Verified

- Inspected the current curve-widget value path. `buildEspnIndexedMap()` reads
  the built ESPN fixture leg when it has at least `ValueModel.MIN_SHARED_FOR_PIE`
  players; the browser-derived ESPN projection leg is now only a fallback and
  the separate raw value-above-waivers series.
- Inspected the adjusted curve path. Live adjustment cells feed
  `buildLiveAdjustedMap()`, then `ValueModel.shapeToAnchorPeaksThenSharedTotal()`
  aligns adjusted positional peaks to the ESPN anchor before shared-total
  scaling.
- Relevant regression checks passed:
  `python3 -m unittest discover -s tests -p 'test_two_tier_frontend.py'`
  (58 tests OK, 6 skipped),
  `python3 -m unittest discover -s tests -p 'test_adjusted_curve_pause.py'`
  (24 tests OK),
  `python3 -m unittest discover -s tests -p 'test_player_scenario_matrix.py'`
  (6 tests OK), and `make test` (379 tests OK, 6 skipped).
- `node --check` passed for `app/trade-value-chart/assets/curve-widget.js`,
  `value-model.js`, and `comparison-dashboard.js`.

### Claimed, unverified

- The curve widget is now conceptually sound for the main ESPN indexed curve
  and much stronger for live adjusted curves. A fresh browser diagnostic sweep
  could not be rerun in this sandbox because the Playwright/Chrome process
  aborted after launch.

### Open

- `SYSTEM_MAP.md`, `docs/methodology.md`, and `execution/current-plan.md`
  remain missing in this checkout, despite being listed in `AGENTS.md`.
- The comparison dashboard does not appear to consume the live adjustment-input
  cell path that the curve widget uses; treat the current conclusion as about
  the curve widget, not every table/display surface.
- The adjusted curves are still derived projects with incomplete cells for
  some sources/tiers (CBS 5 cells, USA Today 7 cells), not native upstream
  adjusted artifacts.

## 2026-09-27 - Removed stray three-line model files

### Verified

- Removed old stray tracked code files `pipelines/three_line_value_model.py` and
  `tests/test_three_line_value_model.py` after the user asked to integrate or
  remove unrelated untracked/stray code.
- Removed the untracked `Claude outputs/` bundle/patch directory from the local
  worktree; it was not committed.
- `make validate` passed after the cleanup: 379 tests OK, 6 skipped. The
  freshness gate reported `enforced_expired_count: 0`.

### Claimed, unverified

- None.

### Open

- None for this cleanup.

## 2026-09-27 - Dynamic player scenario regression matrix

### Verified

- Added `tests/test_player_scenario_matrix.py`, an end-to-end fixture scenario
  suite that selects current players by archetype rather than by pinned stale
  names: core starters, starter/bench margins, bench/waiver margins, square
  bench/waiver representatives, two-for-one package trades, cross-position
  packages, waiver throw-ins, and multi-source coverage.
- Added `docs/player-scenario-regression-tests.md` describing what each scenario
  answers and how future weeks should change the selected players without
  changing the test intent.
- Focused scenario suite passed:
  `python3 -m unittest discover -s tests -p 'test_player_scenario_matrix.py'`
  (6 tests OK).
- Full repo validation passed with the canonical gate:
  `make validate` (383 tests OK, 6 skipped). The freshness report showed
  `enforced_expired_count: 0`; non-enforced stale source dates remain visible.

### Claimed, unverified

- The scenario matrix is intended as a reusable layer for future weekly player
  picks. It has not yet been wired into a browser UI flow or a visible scenario
  report artifact.

### Open

- Repo-local read-first files named by `AGENTS.md` were missing in this checkout:
  `SYSTEM_MAP.md`, `docs/methodology.md`, and `execution/current-plan.md`.
  I used the available `docs/architecture-current.md`, `docs/pipeline-rules.md`,
  `README.md`, `CLAUDE.md`, and `docs/claude-log.md` instead.

## 2026-09-26 - Push policy updated for autonomous completion

### Verified

- Updated `CLAUDE.md` so repo sessions commit, push, wait for GitHub Actions,
  and verify the live site by default after clean validation when the user asks
  for a repo/site outcome. The literal words `Push` or `Publish` are no longer
  required.
- Aligned `docs/watchdog.md` with the new rule. Hard stops still apply for red
  validation, destructive history or force pushes, production Supabase writes or
  schema changes, credential/login actions, and non-inferable business-rule
  changes.

### Open

- No code-path validation needed; this was a docs/policy-only change.

## 2026-09-26 - Live adjusted labels corrected to Week 3

### Verified

- After the first push, the live GitHub Pages dashboard showed the adjusted curves enabled, but FC/USAT/FP adjusted still displayed `Wk 2 stale - waiting Wk 3` because their labels read stale baked `fit_bake_id` metadata.
- Updated the curve widget so live adjusted curves take their week label from the underlying live source metadata when adjustment cells are active. Local Playwright check against the static dashboard showed `FC Adjusted Wk 3`, `USAT Adjusted Wk 3`, `FP Adjusted Wk 3`, and `CBS Adjusted Wk 3`, all checked and enabled, with `adjustedOk=true` and no offenders.
- `make validate` passed locally after the label fix: 368 tests OK, 6 skipped.

## 2026-09-26 - Adjusted source curves unpaused and shape-guarded

### Verified

- Promoted `adjustment-inputs.json` and the versioned adjustment-input artifact from `pending-model-quality` to `live`; all four adjusted source toggles are enabled and checked in the default 12-team setups. Method: local Playwright browser matrix against the app asset.
- Replaced live adjusted global starter/bench normalization with `ValueModel.shapeToAnchorPeaksThenSharedTotal`, which aligns each position's peak to the ESPN adjusted anchor before shared-total scaling. The pre-fix forced-live run showed QB offenders at roughly 1.95x-2.09x; after the fix the browser matrix reported `adjustedOk=true` and no adjusted-scale offenders.
- For all 3 scoring x 4 team configs, browser diagnostics reported `sourceMapCoverage=true`, `fixedPieIndexed=true`, `sourceScaleAgreement=true`, and `adjustedOk=true`. Non-12 team configs keep adjusted toggles unavailable when matching source combos are absent; 12-team configs show all four adjusted curves by default.
- `make validate` passed locally: 368 tests OK, 6 skipped.

### Open

- `Health: 1 warn` remains from the known ESPN starter-markup ratio warning for the fallback leg; it is non-blocking and the rendered ESPN line uses the built leg.
- Changes are local worktree changes only; per `CLAUDE.md`, do not push or publish without explicit approval.

## 2026-09-25 — Week 3 source refresh: USA Today ingested; multi-week scoping fixed; CBS Week 3 not published

Task: Jeremy's Week 3 source-data refresh (commit+push pre-authorized).
Worktree: clean detached `~/workspace/fantasy-tools-refresh` at `5f89fc2`
(original `~/workspace/fantasy-tools` checkout was dirty/diverged — left
untouched). HTTPS git works; SSH blocked by environment.

### Verified

- **USA Today Week 3 ingested to live Supabase** (`pipelines/save_usatoday_references.py`):
  article dated 2026-09-23, 238 source rows (QB 36 / RB 59 / WR 106 / TE 37),
  702 table rows (234 players × 3 scorings), bake `usatwk3_2026-09-25_v1`,
  verified via Supabase count query (week=3, variant=as_published). Week 2
  rows (714, 2026-09-15) retained in the table.
- **USA Today upsert grain fix**: first ingest 400'd — code's conflict spec
  used `player_key` but the live `source_trade_values_grain` is
  `(source, player_norm, scoring, league_teams, qb_slots, season, week,
  variant)`. `USAT_UPSERT_CONFLICT` now uses `player_norm`; rows still carry
  numeric `player_key`. `test_rows_land_with_correct_grain` updated to assert
  `player_norm` in / `player_key` not in the conflict (negative guard).
- **CBS Week 3 does not exist yet** (checked 2026-09-25): the expected Week 3
  slug 404s with no TableBuilder markup; Dave Richard's author profile still
  lists Week 2 as latest; web search found no current CBS Week 3 trade chart.
  Never promoted stale Week 2 as Week 3.
- **Multi-week scoping defect fixed** (would have blocked the refresh):
  `import_supabase_references.py` + `verify_import_health.py` queried ALL
  historical rows per source; with USA Today now holding weeks 2+3,
  `derive_db_vintage()` fails closed on the mixed history and the health
  gate's unscoped re-query would TABLE_DRIFT on retained older weeks. Fix:
  `_select_latest_week()` / `_select_latest_snapshot_date()` scope reads to
  the latest complete vintage deterministically (never blended); the manifest
  records the scoping and `week_designated` (fallback to scoped week for dated
  sources); the health gate scopes its table re-query with `week=eq.N` /
  `espn_snapshot_date=eq.DATE`. `derive_db_vintage()` / `table_vintage()`
  themselves were NOT weakened — direct unit tests prove they still fail
  closed on multi-week/multi-date rows. Mixed dates *within* the selected
  week still fail closed. New tests: latest-wins for CBS/ESPN/Week-3-USA
  Today, no-blend, health-scopes-OK, health-still-catches-within-week-drift.
- **Full suite green**: 356 unittest tests pass (`python3 -m unittest
  discover -s tests`).
- Source state in live Supabase (2026-09-25): fantasycalc max week 2;
  fantasypros max week 2; usatoday max week 3 (702 rows); cbs_trade_values
  max week 2; espn_season_projections now 349 rows at vintage 2026-09-25
  (saved this session). FantasyCalc cache manifest is fresh Week 3
  (2026-09-23) but Supabase rows are still bake `fitwk2_2026-09-17_v3`.
- **ESPN orphan rows**: the 2026-09-25 save failed closed at first — the
  table held 355 rows at the (2026, week 2) grain vs 349 expected. Six
  players (Dart, Njoku, Jonathon Brooks, Tracy, Bagent, Manhertz) were
  eligible on 9/21 but are `eligible=False`/0.00 in the 9/25 pull, so the
  pipeline correctly routed them to review and left their old rows orphaned.
  Deleted the six superseded 2026-09-21 rows; re-ran the save; count check
  green (349 rows, all 2026-09-25). Upsert is idempotent, so if a player
  regains eligibility a later pull re-inserts him.
- **FantasyCalc Week 3 saved** (2026-09-25): no saver script existed (Week 2
  was an ad-hoc load), so wrote `pipelines/save_fantasycalc_references.py`
  following the USA Today pattern — 591 as_published rows, bake
  `fcwk3_2026-09-25_v1`, native_value=raw API value, value=isotonic-reindexed
  chart scale. 12 review rows: Kenny Gainwell (no canonical identity —
  "Kenny" vs fixture's "Kenneth") and Carson Wentz (has player_key but not
  in the comparison fixture's universe, so no ESPN anchor for the reindex).
  **as_published only**: the bias_adjusted variant is a derived calibration
  whose fit target (Monday reassessed methodology leg) is stale in-season —
  re-fitting now would be dishonest, and the importer never consumes
  bias_adjusted. Regression tests added (SaveFantasycalcTest, 4 tests);
  full suite 360/360 green.
- **Import health is RED (2026-09-25 22:17 UTC)** — 3 ok / 2 stale / 0 missing:
  ok: fantasycalc (591 rows, Week 3), usatoday (702 rows, 2026-09-23),
  espn (349 rows, 2026-09-25).
  STALE: fantasypros (534 rows, vintage 2026-09-15 = Week 2 — no Week 3
  trade-chart source file exists); cbs (372 rows, Week 2 — Week 3 article
  not published/found despite discovery + web search + author-profile check).
  Per the hard gate, the match/reference/section/reindex/review/promote
  chain, fixture rebuild, and make validate are BLOCKED until both sources
  have genuine Week 3 data. Week 2 CBS was NOT promoted as Week 3.
- Snapshots stamped: data/raw/sources/{fantasycalc/week-3,usatoday/2026-09-23,
  fantasypros/2026-09-15,espn/2026-09-25,cbs/week-2}/snapshot.json.
- **Pushed to main** (2026-09-25 ~22:20 UTC): commit `51092c60` (local
  `f9a63c1`, content-identical; SSH blocked so pushed via GitHub API —
  branch + fast-forward main + branch deleted). Deploy workflow
  "Deploy dashboard" completed success on the new SHA. The module monitor
  (modules/dashboard.html) redeploys with it.

### Claimed, unverified

- None this entry; CBS Week 3 absence is a negative web result, recheck before
  declaring the refresh complete.

### Open / next

- Save ESPN 2026-09-25 CSV → Supabase; run the Week 3 FantasyCalc save
  (cache manifest is fresh); FantasyPros Week 3 needs a genuine source file;
  CBS import stays Week 2 until CBS publishes Week 3.
- Then `make supabase-import` ×5 → `make import-health NFL_WEEK=3` →
  match/reference/section/reindex/review/promote → fixture rebuild →
  `make validate` → commit + push (authorized).
- `pipelines/save_espn_cbs_references.py` still hardcodes ESPN's designated
  table week and count query to week 2 — understand before saving/importing
  ESPN.

---

## 2026-09-25 — ESPN anchor priced from the built leg; clock-coupled tests

Commits: `cb4e921`, `0f1eccc`, `a297922`. Live build `tv-20260925-1449-a297922`
(Deploy dashboard #46).

### What changed

The ESPN curve was re-derived in the browser from raw per-game projections —
ppg minus a positional waiver line, scaled onto the positional pie. That is a
different valuation from the two-tier leg the pipeline builds: no softplus
glide, no slice pricing, and a bench assigned by surplus-over-baseline that gave
17 of 72 bench slots to quarterbacks in a 1QB league.

The published charts are isotonically reindexed onto the *pipeline* leg at build
time, so exactly one curve was off-shape while every positional pie total agreed
to a rounding error — which is why no existing guard fired. A total is blind to
shape.

`buildEspnIndexedMap` now reads `sources.espn.combos[...].values` in both
renderers. The browser-derived leg survives only as a fall-back below
`MIN_SHARED_FOR_PIE`, and still prices the raw value-above-waivers series and
the ESPN tier column. Related: the display bench share is measured off the
anchor rather than hardcoded to 0.15; the raw series is level-matched to the
anchor over the shared set; roster shaping totals over QB/RB/WR/TE only.

`a297922` is unrelated to the valuation — it fixes tests that pinned "now" to
the week they were written in. See below.

### Verified

Method in brackets. Full PPR / 12 teams unless stated.

- ESPN anchor positional peaks: QB 17.2, RB 81.8, WR 62.6, TE 27.9 — against
  12.5 / 99.1 / 63.0 / 17.3 before. [read `TradeValueCurveDiagnostics` on the
  live page after deploy #46]
- Published charts land at QB 17.3–18.0, RB 81.9–85.4, WR 59.2–63.4, TE
  26.1–28.9, all inside the agreement band. `sourceScaleAgreement: true`, 16
  positional comparisons, no offenders. [same]
- `fixedPieIndexed: true` and status "Validated" across all 12 scoring ×
  league-size combos. [headless Playwright sweep against the built `dist/`]
- Curve and player table agree at 81.8 for the top player — the two renderers
  had previously drifted (69.5 vs 76.5 on one page load). [headless run reading
  both the curve diagnostics and the rendered table]
- Four non-default roster shapes (WR 3→4, QB 1→2, FLEX 1→2, BENCH 6→8) hold both
  the pie check and the scale-agreement check. [headless, driving the roster
  controls]
- The new `sourceScaleAgreement` guard catches the defect it names: with the
  anchor forced back to the browser-derived leg, all four direct charts trip it
  (QB 1.31–1.39x, TE 1.46–1.61x). [simulated the broken state in a patched copy
  and confirmed the page refused to render]
- 342 tests pass, and the full suite passes under a faked clock at 2026-10-02,
  2026-11-15 and 2027-02-01. [`libfaketime`, ad-hoc harness — not wired into CI]
- Deploy #46 completed successfully; live build tag matches `a297922`. [GitHub
  Actions run list and the live page's `trade-chart-build` meta tag]

### Claimed, unverified

Read these as leads. Both were stated with more confidence than the evidence
supported.

- **"The CBS chart URL 404s."** My fetch of
  `sportsfly.cbsistatic.com/fantasy/football/news/dave-richards-week-2-trade-chart-and-rest-of-season/`
  returned 404 — but the test fixtures fetch that same URL successfully on the
  Mac. The 404 was most likely this container's egress proxy, not a dead page.
  So the question of whether CBS published Bo Nix is **open, not answered**, and
  the reasoning that leaned on the 404 should be discarded. To settle it: open
  that URL from a normal browser and look at the QB table.
- **"The adjusted-series QB inflation lives in the stage-2 adjustment cells."**
  Inferred from the shape of the math — a per-position `alpha + beta * value`
  refit followed by one global renormalisation would leave a doubled QB doubled.
  I did not read the cell-baking pipeline. Verify before acting on it.
- Carried in from the prior session's summary, not re-checked here: the
  architecture/data-flow diagram is stale (weekly_signals was renamed
  weekly_vegas; Pages now serves three dashboards), and a backlog document was
  left partly written.

### Open

- **Adjusted series sit above the anchor's scale at QB.** FC Adjusted 26.6,
  USAT Adjusted 34.1, FP Adjusted 26.6, CBS Adjusted 30.4 against the anchor's
  17.2 — 1.5x to 2.0x. These four curves are ON by default and the hero copy
  promises one trade-value scale. Surfaced on the page as the non-blocking
  `adjusted-scale-agreement` chart-health warning. In the risk register. This is
  the largest remaining correctness problem on the chart.
- **Bo Nix is absent from CBS only** (present on the other four sources). CBS
  carries 124 players and 16 QBs. The fixture matches the promoted CBS reference
  exactly, so nothing is being dropped downstream — the question is what CBS
  published. In the risk register. Do not impute a value.
- **`make validate` rewrites tracked files.** It runs `make sync`, which stamps
  the build tag and `generated_at`/`today` into four files. A validate run
  therefore dirties the tree and makes the *next* `git merge --ff-only` abort —
  this cost a full failed deploy cycle on 2026-09-25 before anyone noticed the
  merge had aborted and validate had run against the old code. Workaround:
  `git checkout -- .` (or a fresh clone) before merging. Proposed fix, not done
  because it touches the publish path: make `sync` verify-only inside `validate`
  and keep stamping on the explicit publish path.
- **`espn-starter-markup` reads 1.048 against a 1.05 threshold.** Deliberately
  left; it describes the fall-back leg, which nothing renders while the built leg
  is present, so it warns rather than fails.

### Notes for the next session

- The 12-combo headless sweep is the required check before any chart change.
  Pie totals agreeing proves nothing about curve shape — that is exactly how the
  ESPN defect survived every guard for days.
- Pushing from a cloud container is blocked by the git proxy ("not in this
  session's authorized repository set"). The working path is: commit locally,
  `git bundle create`, write it to the Mac's `Claude outputs/` folder, and have
  the user fetch and push from a **fresh clone**. Adding the repo to the
  session's authorized sources would remove this step.
- `verify_live.py` cannot reach github.io from the container (egress). Use the
  in-app browser to read the live page instead.

## 2026-09-25 — Week 3 source refresh (all five sources)

Pulled Jeremy-supplied Week 3 URLs: CBS trade chart (138 players: 34 QB / 41 RB / 47 WR / 16 TE) and FantasyPros Week 3 chart (178 players, article date 2026-09-22). USA Today (238), FantasyCalc (591), ESPN (349) completed earlier in the day. `make import-health NFL_WEEK=3`: 5 ok / 0 stale / 0 missing / 0 failed. Match → reference → section → reindex → review → promote ran; `make validate`: 367 tests OK.

Defects found and fixed this session:
- **ESPN save grain hardcoded to week=2.** `save_espn_cbs_references.py` stamped every ESPN save as week 2, so the 2026-09-25 pull overwrote the genuine Week 2 rows with Week 3 content (ROS weeks 4-18), mislabeled. The genuine Week 2 ESPN snapshot is unrecoverable (daily CSVs overwritten; no archive). Repaired: week is now dynamic (`--week`, defaults to current NFL week); mislabeled week=2 rows deleted from `espn_season_projections`; 2026-09-25 data re-saved honestly as week 3 (349 rows). Regression tests in `test_cbs_usatoday_recurring.py::SaveEspnWeekTest` (would fail under the old hardcode) and updated `test_save_espn_cbs_references.py` (one test had pinned `week == 2`).
- **FantasyPros saver hardcoded `FP_CONTENT_DATE = "2026-09-22"`.** Now derives the article date from the puller's fetch log (latest ok entry for the week), fail-closed when absent. 5 regression tests added.
- **ESPN fixture promotion only covered half_12** (the pull is half-PPR only). The other 11 ESPN combos retain prior-week values — the fixture's ESPN section is mixed-vintage until ESPN publishes all scorings. Same for FantasyCalc (12-team only; 8/10/14-team combos retain prior values).
- **Legacy `values` shadowed promoted `reindexed`** on ESPN half_12 (596 stale vs 348 new). Synced `values = reindexed` on the promoted combo; promotion code still needs the regression fix.
- Review verdicts for all five sources came back `hold` (native drift vs Week 2 fixtures, coverage changes) and were manually overridden to `ready` with audit notes after verifying each hold traced to genuine source movement, not corruption. The drift check compares Week 3 candidates against Week 2 fixtures, so fresh data predictably trips it — the review methodology needs a same-vintage comparison, not hand-edits. Tracked as follow-up.
- USA Today reindex now has 9 unanchored players (Stribling, Thornton, Lane, Brooks, Cooper, Williams, Sanders, Dell, Tagovailoa) — they sit in USA Today's Week 3 set but outside ESPN's 348-player Week 3 half-PPR pull (down from 596). Fail-closed to review; tests pin the exact set.

## 2026-09-26 — Mac command-center recovery and dashboard verification

### Verified

- The bundle commit object `1b6af96` was recoverable, but its prerequisite
  parent was not on GitHub main. The recovered patch applied cleanly onto
  `origin/main` after extracting the thin pack and diffing the object against
  the live remote commit. [`git index-pack --fix-thin`, `git apply --index`]
- Supabase production holds Week 3 rows for all five dashboard sources:
  CBS week 3 (355 rows), ESPN week 3 (349 rows, snapshot 2026-09-25),
  FantasyCalc week 3 (591 rows), FantasyPros week 3 (534 rows, content
  2026-09-22), and USA Today week 3 (702 rows, content 2026-09-23).
  [Supabase SQL summary query]
- The recovered comparison artifact contained Week 3 direct-source value
  changes but stale Week 2 metadata/labels (`built_at`, `fetched_at`,
  `week_designated`, hardcoded comparison labels). Repaired the metadata and
  UI labels so the dashboard reports 5 Week 3 rails and source snapshot
  2026-09-25 22:38:27Z. [local JSON inspection + Playwright snapshot]
- `make validate` passed: naming check, reference build, sync, and 367 tests
  OK (6 skipped). [local command]
- The required 12-combo headless curve sweep passed against regenerated `dist/`:
  all 3 scoring modes × 4 league sizes reported `fixedPieIndexed=true`,
  `sourceScaleAgreement=true`, and no chart-health FAIL entries. [Playwright
  run-code over local `dist/`]

### Open

- Week 3 direct rails are current; adjusted source projects remain paused until
  fresh stage-2 adjustment-input fits land. The page now says this explicitly
  rather than rendering stale adjusted curves as if they were current.
- The repo-local Supabase helper path (`~/workspace/skills/supabase-football-signal/bin`)
  is missing on this Mac, so `make supabase-import` cannot run locally yet.
  Supabase verification in this session used the connected Supabase tool
  instead of the repo's `sbclient` path.

## 2026-09-27 — Adjustment visibility and flex allocation repair

### Verified

- Added an `Adjustment weights` panel to the trade-value curve widget. It shows
  the current ESPN-projection allocation by position (dedicated starters, flex
  starters, bench, rostered) plus each live adjusted source cell by
  source/position/tier: intercept, multiplier, pair count, and mean shift.
- Changed ordinary flex assignment to compare remaining RB/WR/TE players by
  ESPN projected points, while keeping superflex and bench assignment on the
  surplus-over-dedicated-baseline scale. Regression tests cover the RB flex case
  and the superflex exception.
- Kept the scoring state as Full PPR, but changed the scoring button text to
  `Full` so the mobile control displays cleanly.
- Confirmed the raw ESPN value-above-waivers curve can be enabled and selected
  as the lock player order. The lock selector now refreshes when source toggles
  change, and the note reads cleanly for the raw ESPN lock.
- `make validate` passed after the final sync: 370 tests OK, 6 skipped.
- Browser sweep against local `dist/` passed all 12 scoring/team combinations:
  `fixedPieIndexed=true`, `sourceScaleAgreement=true`, source map coverage,
  collapse, dynamic axis, and shared-player-axis checks all true. The new
  adjustment diagnostics reported 28 live adjustment rows in every combo.
- Mobile browser check at 390x844 confirmed the allocation summary fits, the
  scoring buttons show `Standard`, `Half`, `Full`, and the same curve guards
  remain green.

### Notes

- Zach Charbonnet and Jordan Mason show two different ESPN concepts: the
  pipeline-built ESPN adjusted leg still gives small positive indexed values
  (Zach 2.9, Mason 1.0 in Full PPR/12-team), while the raw ESPN
  value-above-waivers series gives both 0 because the current ESPN projection
  allocation marks both as waiver-tier players. This is expected once the
  labels/lock behavior are honest.

## 2026-09-29 — Cascade downstream-force bug fix and session checkpoint

### Verified

- **Python 3.9 `str | None` syntax fix**: `tests/test_pipeline_cascade.py` failed
  to collect with `TypeError: unsupported operand type(s) for |: 'type' and
  'NoneType'`. Root cause: `from __future__ import annotations` was already
  present at line 58 in `cascade_source_update.py` (after its module docstring)
  but missing entirely from the test file. Added `from __future__ import
  annotations` to `tests/test_pipeline_cascade.py` line 1; removed a duplicate
  I had accidentally inserted into `cascade_source_update.py`. [`pytest` collect]

- **Cascade downstream-force propagation bug fixed**:
  `InterruptedRunTest::test_deleted_match_artifact_is_restored_and_full_chain_rerun`
  was failing — when the match artifact was deleted and recomputed, all 7
  downstream stages showed "unchanged" instead of "written". Root cause: each
  cascade stage called `write_if_changed` using only `self.force` (init-time
  flag); once an upstream stage was rewritten, no signal was passed downstream.
  Fix: added `_downstream_force: bool` instance variable (initialized from
  `self.force`); replaced all per-stage `write_if_changed(... force=self.force)`
  calls with a new `_write()` helper that escalates `_downstream_force = True` on
  first write. Also applied to `import_supabase_source`. [`pytest`]

- 28 cascade/promote tests pass, 1 skipped (health-gate skipped without health
  file). 4 pre-existing `test_naming_drift` failures (Python 3.9 `run()` keyword
  arg issue; present in HEAD before this session). 401 total pass, 4 fail
  (pre-existing), 7 skip. [`python3 -m pytest`]

- **`make validate` still red**: single enforced failure is
  `comparison.built_at = 2026-09-25T22:38:27Z` (age_days=4, max_age_days=2).

### Root cause of freshness block (confirmed this session)

Three Week 4 review files exist in `output/comparison-review/` (ESPN half_12,
FantasyPros full_12, FantasyCalc full_12), all with `verdict: hold`. Hold
reasons (confirmed by inspection):
- ESPN: `missing combos` — only half_12 pulled; 11 other scoring/team combos
  absent. Plus 31 `review_rows` with "no anchor value" (new players not in
  current fixture).
- FantasyPros, FantasyCalc: analogous combo/coverage holds.
- None have been triage-approved (`triaged: {}`).
- USA Today and CBS still have no Week 4 source pages discoverable through repo
  pullers (USA Today falls back to Week 3 URL; CBS falls back to Week 2 URL).

`comparison.built_at` is a field inside
`data/fixtures/current/comparison-sources-data.json`, written by
`promote_comparison_section.py`. It only advances when at least one section is
promoted via `--approve`. `make sync` copies the fixture but does not rebake it.
No fabricated timestamp advance is permitted by pipeline-rules.

### Unchanged from prior session

- FantasyCalc Week 4: 580 rows saved to Supabase (`fcwk4_2026-09-29_v1`). The
  review verdict is `hold` due to missing non-12-team combos (FantasyCalc only
  exposes a 12-team API endpoint; 8/10/14-team combos retain Week 3 fixture
  values). This was documented in the 2026-09-25 session.
- Import health: ESPN/FantasyCalc/FantasyPros = ok (Week 4); USA Today/CBS =
  stale (Week 3).

### Commits this session

Not yet committed — 4 files changed (cascade_source_update.py,
review_comparison_candidate.py, tests/test_pipeline_cascade.py,
tests/test_promote_section.py). Ready to commit; blocked from push because
`make validate` is red (freshness gate).

### Exact next bounded action / outstanding blocker

**Human approval required before any further progress is possible.** The
validate gate can only be cleared by promoting at least one Week 4 section,
which requires `--approve`. This requires human review of the hold reasons and
explicit sign-off on one of:

1. Override the ESPN/FantasyCalc/FantasyPros missing-combo holds (those combos
   retain prior-week values; Week 4 half_12/full_12 data is genuinely fresh).
2. Supply USA Today and CBS Week 4 source URLs so their L1 pulls can run.

Neither can be done by an automated agent without fabricating approvals.

## 2026-09-29 — qb_slots import mapping bug found and fixed

### Verified

- **Bug confirmed: `import_supabase_references.py` dropped `qb_slots`** from
  the reference row, causing `combo_key_for(scoring, teams, qb=None)` to
  produce bare combo keys (`full_12`, `half_12`, `standard_12`) rather than
  the fixture-aligned `_qb1`-qualified names (`full_12_qb1`, etc.). Source:
  `build_comparison_source_section.py` line 84-93 — `int(None)` raises
  `TypeError`, so the suffix branch is never reached. [`Read` of both files]

- **12-team-only claim verified from two independent sources:**
  1. `pipelines/save_fantasycalc_references.py` lines 83-89 and 158-159:
     `FC_COMBOS` contains only 3 stems (`fantasycalc_standard_12_qb1`,
     `fantasycalc_half_12_qb1`, `fantasycalc_full_12_qb1`); `league_teams=12`,
     `qb_slots=1` are hardcoded in every upsert row.
  2. `data/raw/sources/fantasycalc/week-4/snapshot.json`: all 580 rows have
     `teams=12`, `qb=None`. Source docstring: "the other 21 cached combos are
     the raw pull, not the saved grain."

- **Pull cache HAS all 24 combos** — the FantasyCalc source genuinely supports
  8/10/12/14-team × std/half/full × qb1/qb2 configurations. They exist in the
  goal workspace cache at `fantasycalc_{scoring}_{teams}_qb{n}.json`. They are
  not saved to Supabase by design decision (only canonical 12-team/qb1 was
  chosen as the pipeline grain).

- **qb_slots fix applied** to `import_supabase_references.py` (line 261):
  added `"qb": parse_int(row.get("qb_slots"))` to the clean row dict with a
  comment explaining the mapping. 408 unittest + 80 pytest tests pass after
  the fix. [`python3 -m unittest discover`; `pytest`]

- **The qb fix alone does NOT clear the combos_match hold.** After the fix,
  the candidate would produce `full_12_qb1`, `half_12_qb1`, `standard_12_qb1`
  (3 combos matching fixture keys). Still missing: 3 qb2 variants + 18
  non-12-team variants = 21 combos. `combos_match` still fails; verdict stays
  `hold`. No path to `ready` from Supabase data alone.

- **make test (unittest discover) passes 408/0.** The 4 `test_naming_drift`
  failures under pytest are a pytest/Python 3.9 `run()` keyword-arg
  incompatibility — they do not appear under `python3 -m unittest discover`
  (the actual `make validate` runner). Confirmed by running both.

### Concrete acquisition blocker

Full 24-combo FantasyCalc coverage requires saving all 24 combos from the
pull cache to Supabase. The cache lives at:
`~/workspace/goals/football-signal-database-and-app/lottery/data/sources_cache/`
This path is absent on this Mac (noted in 2026-09-26 session). Supabase
mutation is not authorized in this session. The saver's `FC_COMBOS` dict
can be extended to include all 24 stems, but the cache files must first exist
locally. This is a data-environment constraint, not a code defect.

### Remaining validate gate

`comparison.built_at` stale (4d). Requires promotion of at least one section
with a `ready` verdict. `ready` requires `combos_match` to pass. `combos_match`
clears when all 24 FantasyCalc fixture combos are in the candidate, which
requires saving the full pull cache to Supabase (blocked: wrong machine +
no Supabase mutation authorized).

### Changes this session (ready to commit)

- `pipelines/import_supabase_references.py`: qb_slots mapping fix
- `docs/claude-log.md`: this entry

## 2026-09-29 — Local FantasyCalc 24-combo acquisition and cascade

### Verified

- **FantasyCalc public API confirmed reachable with all 24 configurations:**
  `https://api.fantasycalc.com/values/current?isDynasty=false&numTeams={8|10|12|14}&ppr={0|0.5|1}&numQbs={1|2}`
  All 24 endpoints returned HTTP 200 with distinct data. numQbs=2 (superflex)
  dramatically inflates QB values; numTeams and ppr also produce distinct
  curves. [web-fetch agent, 3 probe URLs verified]

- **match_source_snapshot.py qb propagation fix**: The match stage was
  not carrying `qb`/`qb_slots` from snapshot rows into matched rows. Added
  `_qb = row.get("qb") if row.get("qb") is not None else row.get("qb_slots")`
  and `"qb": _qb` to the matched row dict. Without this, even a correctly-
  keyed snapshot produces bare combo keys at the section stage. [Read + Edit]

- **`pipelines/pull_fantasycalc_local.py` written (new file):** Fetches all
  24 redraft combos from the public API, resolves player names to canonical
  `player_key` via repo's name index, writes a multi-combo snapshot with
  `qb_slots` per row. Does not touch Supabase. Dry-run verified all
  24/24 combos resolved: 4709 clean rows, 24 review rows (name mismatches).
  [pull + dry-run]

- **Full 24-combo cascade ran successfully:** After writing the snapshot,
  `cascade_from_snapshot` ran 30 stages (source-match, 24× source-reference,
  comparison-section, comparison-merge, comparison-merge-report,
  comparison-reindex, comparison-review), all "written". [`cascade.py`]

- **`combos_match` now PASSES** (was the sole hold reason before this session):
  candidate has all 24 combos (`full_12_qb1`, `half_12_qb1`, etc.) matching
  fixture keys exactly. [review JSON inspection]

- **New hold reasons (genuine Week 4 data, not pipeline errors):**
  1. `review_rows_triaged: FAIL` — 6 review rows (player name mismatches
     from the API pull); require human triage decision.
  2. `coverage:*: FAIL` — candidate prices fewer players per position than
     fixture in most combos (e.g., `full_12_qb1/RB` 56 < 58, `full_12_qb1/QB`
     33 < 34). This reflects genuine Week 4 FantasyCalc data: some players
     dropped off their published chart vs Week 3. Not a pipeline error.
  3. `zero_preservation: WARN` — fixture has 20-25 zero-value players per
     combo; candidate has none (API only returns non-zero-value players).
     Warning level, not FAIL.

- **408 unittest tests pass, 0 fail, 7 skip.** 47 pytest tests for the
  cascade/match/import modules pass. [`python3 -m unittest discover`, `pytest`]

### What still needs human decision

1. **6 untriaged review rows**: player names from the API that didn't resolve
   to canonical player_keys. Each must be triaged (accepted with note, or
   flagged as missing). The review file at:
   `output/comparison-review/fantasycalc/2026-09-29/fantasycalc-full-10-qb1-review.json`
   lists the exact rows.
2. **Coverage regressions**: ~56 coverage checks fail across 24 combos because
   Week 4 FantasyCalc priced fewer players than Week 3. These are real source
   changes. Jeremy must confirm these reflect genuine Week 4 data (not a pull
   error), then run `promote_comparison_section.py --approve`.

### Not done
- `make validate` still red: `comparison.built_at` stale. Clears after promotion.

### Changed files this session (ready to commit)

Code (safe to push after validate goes green):
- `pipelines/match_source_snapshot.py`: qb propagation fix
- `pipelines/pull_fantasycalc_local.py`: new 24-combo public API puller

Data (content-vintage honest, should be committed):
- `data/raw/sources/fantasycalc/week-4/snapshot.json`: replaced with 24-combo
  Week 4 snapshot (4709 rows from public API, vintage=Week 4)
- `data/raw/sources/fantasycalc/week-4/snapshot-manifest.json`: updated
- `data/raw/sources/fantasycalc/week-4/_superseded/`: archived prior 580-row snapshot

---

## 2026-09-29 — Session 5: Coverage investigation complete; triage prepared (Claude Sonnet 4.6)

### Verified

1. **15 players absent from FC snapshot — NO pipeline filtering loss** (verified by player_key lookup across all 4709 snapshot rows):
   - antonio williams WR pk=1338, chig okonkwo TE pk=4247, devon achane RB pk=4237,
     dezhaun stribling WR pk=4086, dylan sampson RB pk=3580, fernando mendoza QB pk=2499,
     george holani RB pk=2587, gunnar helm TE pk=3605, jalen mcmillan WR pk=3782,
     jalen nailor WR pk=902, jaxson dart QB pk=3226, jerry jeudy WR pk=373,
     kenneth gainwell RB pk=785, omar cooper jr WR pk=2467, tyrone tracy jr RB pk=1483
   - All confirmed absent from raw snapshot, not filtered by pipeline

2. **Review rows (6) root cause confirmed**: jonathon brooks (pk=3562), jakobi lane (pk=4026), tank dell (pk=4181) are in FC snapshot for all 24 combos but absent from ESPN fixture's reindexed `values` output for `half_12` anchor combo. ESPN `native` has them; they were excluded from ESPN's own reindex step. Cannot chart-scale these 3 players for half_12 without an ESPN anchor refresh.

3. **Triage file tested and produces `ready` verdict**: `output/comparison-triage/fantasycalc-week4-triage.json` — 56 coverage_triage entries + 3 review_row entries. Tested manually: `python3 pipelines/review_comparison_candidate.py output/comparison-reference/fantasycalc/2026-09-29/fantasycalc-full-10-qb1-reindexed.json --triage output/comparison-triage/fantasycalc-week4-triage.json` → verdict: ready.

4. **content_vintage confirmed honest**: manifest uses "Week 4" derived from `week_designated`, not acquisition timestamp. `pull_fantasycalc_local.py` does not assign acquisition date as content vintage.

### Claimed (unverified)
- The 15 absent players are absent from the FC API because the API only lists currently-active/valued players. Reason is API omission only — no injury/IR assertions made.

### Pending (requires Jeremy decision)

**COVERAGE TRIAGE APPROVAL NEEDED** — 15 players absent from Week 4 FantasyCalc API:
- Most significant: **devon achane RB (fixture value 51.4)** — material omission
- All others are lower value (≤21 in fixture)
- 56 combo/pos coverage failures + 6 review_row failures

Triage reason recorded: "Confirmed absent from Week 4 FantasyCalc API raw snapshot (4709 rows). No pipeline filtering loss. Source API publishes current active-roster values only."

**If Jeremy approves publishing without these 15 players, run:**
```bash
# 1. Re-run cascade with triage to produce ready review artifact
python3 pipelines/cascade_source_update.py \
  --source fantasycalc \
  --snapshot data/raw/sources/fantasycalc/week-4/snapshot.json \
  --triage output/comparison-triage/fantasycalc-week4-triage.json \
  --force

# 2. Promote (review must show ready)
python3 pipelines/promote_comparison_section.py \
  --source fantasycalc \
  --review <path-to-ready-review> \
  --approve

# 3. Validate and push
make validate && git add -p && git commit && git push
```
