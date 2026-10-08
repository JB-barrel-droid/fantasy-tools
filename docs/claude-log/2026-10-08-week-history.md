## 2026-10-08 - Week history: prior-week inputs for Risers & fallers and Δ (feat/week-history)

Contract: inventory per-source history for Weeks 1–5 and fill Week 3 and Week 4 wherever genuine
content exists, never relabelling another week. Serve a versioned prior-week artifact built in
rebuild-chain (append-only). Add a read-only engine accessor that recomputes a prior week with the
engine's own math. Tests: schema, no-relabel and Δ recompute, each failing on a broken state.

### Inventory (source × content week)

Published-chart natives are as published, 12 teams, 1 QB. Week 1 has nothing anywhere.

| Source | W2 | W3 | W4 | W5 |
| --- | --- | --- | --- | --- |
| USA Today | SB, content 09-15, complete | SB, content 09-23 (pulled 10-01), complete | SB, content 09-29, complete (3 pulls, latest 10-07) | SB, content 10-06, complete; = fixture |
| FantasyCalc | SB, pulled 09-16, complete | SB, pulled 09-23, complete | SB, pulled 10-05, complete (the 10-04 fixture pull has 1 player fewer) | SB, pulled 10-06, complete; = fixture |
| FantasyPros | SB, content 09-15 | SB, content 09-22 | SB, content 09-29 | SB, content 10-06; = fixture |
| CBS | SB, week col 2 (pulled 09-22) | SB, week col 3 (pulled 09-25); = git 14f78c4 natives exactly | SB, week col 4 (pulled 10-07); = fixture | none yet |
| ESPN (espn_ppg) | git players.json 4da1712 (snap 09-17) | git c359e33 (snap 09-22); also data/fixtures/snapshots/players_2026-09-22.json | git fbb904e (snap 10-03); also SB espn_season_projections 09-29 (stats, not ppg) | players.json (snap 10-07); SB 10-07 |
| CBS ROS (cbsros_ppg) | none | none | players.json / SB 10-02 (SB 09-30 superseded) | none |
| Razzball (rz_ppg) | none | data/inputs/razzball_projections.csv + players.json (snap 09-22) | SB razzball_projections 10-01 | SB 10-06 |

Notes on the sources:

- SB = Supabase `api.source_inputs_weekly` for the charts (anon-readable, latest pull per
  source/week/scoring), and `public.razzball_projections` / `public.cbs_ros_projections` for the
  projections.
- Git commits of comparison-sources-data.json are not usable for chart history: before 10-01 their
  `native` cells held transformed values. The 14f78c4 "Week 3" FantasyCalc, FantasyPros and USA
  Today natives differ from Supabase on every player (FantasyCalc 27.3 against 2037). Only CBS W3
  matched.
- data/raw holds only fantasycalc week-4, cbsros 09-30 and espn 09-30 snapshots. All three are
  duplicated in Supabase or git.
- `~/Projects/"fantasy tools"` was not touched.

### Filled

- **Week 3:** USA Today, FantasyCalc, FantasyPros and CBS (complete, from Supabase). ESPN inputs
  (git c359e33). Razzball (the served 09-22 CSV).
- **Week 4:** all four charts (Supabase). ESPN (git fbb904e, 10-03). CBS ROS (10-02). Razzball
  (Supabase 10-01).
- **Week 2:** all four charts and ESPN.
- **Week 5:** open week, frozen after the next Tuesday flip.

All of these are in `data/history/week-<N>.json`, with `origin` and `week_evidence` per entry.
Nothing was written to Supabase.

### Built

- `pipelines/build_week_history.py`: captures and validates the weeks (no-relabel guard), keeps
  frozen weeks append-only, and writes `index.json` with the served week per source, matched by
  content fingerprint.
- `make sync` (`sync_dashboard_artifacts.sync_week_history`) rebuilds the index for the fixture
  being published and copies `assets/history/`. The copies are gitignored, and `data/history/` is
  the committed store.
- rebuild-chain.yml: "Capture week history" runs `--supabase`. It is non-blocking, and a failed
  capture restores the committed history. `data/history` is committed with the fixture.
- curve-widget.js, read-only:
  - New accessors `getWeekValues(source, week)` and `getPriorWeek(source[, week])`.
  - Three pure refactors so the accessor reuses the engine's functions:
    - `ddfTwoTierValuesForSource(key, nativeOverride)`;
    - `normalizedAdjustedMapFor(..., adjustedOverride)`;
    - `legFloorsOf`, extracted from `buildLegFloors`.
- docs/v2-design-notes.md "Back-end contract: history" documents the contract and the Δ rule for
  the front-end session.

### Verified (named checks)

- **Supabase natives match the served fixture:** current-week natives in Supabase equal the
  served fixture natives exactly for all 4 charts × 3 scorings. Checked by a scratch comparison
  against data/fixtures/current, and CBS W3 against git 14f78c4.
- **`ValueModel.derivePublishedSetup` matches the engine:** fed the served natives, it equals the
  engine's `getAllRows()` values for the 4 charts in all 12 scoring × team combos, with 0
  mismatches, including the saved 12-team setup where the engine reads the saved values. This was
  first checked with the prior week's own peers: CBS was then off by 0.1–0.2 at 12 teams PPR. The
  fix uses the served peers (`publishedPeers`), so only the chart's own natives come from the
  saved week.
- **`getWeekValues(source, served week)` reproduces the chart:** it equals the chart's current
  values for USA Today, FantasyCalc, FantasyPros, CBS, CBS ROS and Razzball in all 12 combos (0
  mismatches, no missing or extra players), and on half/10 with an extra bench spot
  (`tests.test_week_history`).
- **Prior week matches an independent Python price:** the prior week at Full PPR / 12 teams
  equals `unified.translate_natives` on the saved natives with the same peers, player for player.
  Bijan Robinson Δ: FantasyCalc +0.4 (W4 66.2 → W5 66.6), CBS +2.1 (W3 63.8 → W4 65.9), USA
  Today +2.8, FantasyPros 0.0.
- **The guards catch broken states** (`test_delta_guard_fails_on_broken_states`):
  - the week-4 file served relabelled as week 3, and the week-4 file carrying week-3 entries;
  - an accessor that substitutes the served natives (157 FantasyCalc values differ, Bijan 66.6 vs
    66.2);
  - a prior week paired with the served week.
- **Hermetic guards:**
  - Week 3 FantasyCalc moved into the Week 4 file, with or without a relabel, is refused.
  - A USA Today content date moved to 09-23 is refused.
  - Rows are refused when the content date and week column disagree, when FantasyCalc was pulled
    in a later week, or when CBS was pulled before its week.
  - Tampered fingerprints and non-numeric natives are refused.
  - A frozen entry survives a different candidate, and the open week takes only a newer pull.
- **12-combo sweep:** the branch dist against the same dist with origin/main's curve-widget.js.
  `getAllRows()` for all 14 series was byte-identical in all 12 combos (514 rows each).
  `TradeValueCurveDiagnostics` fixedPieIndexed and sourceScaleAgreement were identical (true).
  No page errors.
- **`make validate`:** see the commit message for the final result.

### Claimed, not confirmed

- The rebuild-chain capture step has not run in CI. `fetch_supabase` was written against the
  view's columns and PostgREST paging but only tested offline via `--supabase-dump`.
- Week 2 ESPN (09-17) espn_ppg was baked by the pipeline of that date (ECR-era code), so it may
  not be on today's basis. It is stored as an input only; ESPN priors are not recomputed.
- The FantasyCalc W4 entry is the 10-05 pull (latest of the week). The fixture showed the 10-04
  pull during Week 4, and the two differ by one added player.

### Found (reported, not fixed here)

- RAZZBALL-LIVE-WEEK3: the live Razzball curve is Week 3 content (CSV 09-22) under a Week 4
  label. It is reported to main for the Razzball lane. `index.json` flags it as `label_mismatch`.

### Follow-up: merged with origin/main (fix/value-small, feat/source-resiliency, fix/launch-qa)

**Cause of the failure.** After the merge, `test_prior_week_is_engine_math_on_saved_inputs` failed.
fix/value-small moved players.json per-game rates to `PPG_DECIMALS` (6 dp). The saved CBS ROS Week
4 and ESPN Week 5 entries held the earlier 2 dp values. Their content fingerprints no longer
matched the served inputs, so `index.served` was null for cbsros and espn, and
`getWeekValues(served week)` came back unavailable. The test failed correctly: before the fix,
Δ would have shown "—" for those series.

**Fix.**

- Supabase projection captures round to `games_remaining.PPG_DECIMALS`, as bake_players does.
- `same_content_finer` lets a frozen entry be replaced only by the same content stored at finer
  precision. Same content means the same snapshot or pull, the same players, and every saved
  value a rounding of the new one. Any other candidate is still kept out.
- `make sync` now captures the served players.json projections (`--served-only`, no Supabase), so
  the served week is always saved.
- New test `test_frozen_projection_rebases_only_to_finer_same_content`. It fails without the
  rule, and it shows that different values, another snapshot and coarser values are refused.

**Verified.**

- CBS ROS Week 4 was rebased to 3 dp, and ESPN Week 5 (open) was updated. Served weeks are back:
  USA Today, FantasyCalc and FantasyPros Week 5, CBS Week 4, CBS ROS Week 4, ESPN Week 5, Razzball
  Week 3.
- `tests.test_week_history`: 10/10 OK.
- 12-combo sweep against origin/main cbeac8d's curve-widget.js: `getAllRows()` for all series is
  identical in all 12 combos, and fixedPieIndexed / sourceScaleAgreement are unchanged.

**Simulated fix/razzball-refresh (67e866c).** The branch was merged in a scratch worktree. Its
players.json conflicts with main's, so I used main's players.json with the refresh branch's Razzball
fields and `rz_snapshot`. Then `make sync`:

- served razzball = Week 5 (2026-10-06), with no label mismatch;
- `getWeekValues(razzball, 5)` equals the chart with 0 mismatches;
- `getPriorWeek(razzball)` = Week 4 (Supabase 2026-10-01, 494 players);
- `tests.test_week_history` OK.

Claimed, not confirmed: the real merge will use a re-baked players.json. If its Razzball values
differ from Supabase 10-06 (other than by precision), the open Week 5 entry simply takes the
served one.
