## 2026-10-09 - JEG-508 Python reference: source-neutral value pipeline

Contract: rewrite `pipelines/value_reference.py` to the spec in
docs/methodology.md "Value Pipeline (source-neutral, 2026-10-09)" (VP-0..VP-12,
decided OC table), reproduce `tests/fixtures/value_pipeline_worked_example.json`
to 1e-6, and update `pipelines/value_check.py` (compare + hold) for the new
outputs. Written without reading the engine branch or `pipelines/spec_reference/`.
Branch `jeg508-pyref`, draft PR; not merged.

### Verified (check named)
- `tests/test_value_reference_worked_example.py`: `run_pipeline` reproduces all
  3,212 expected numbers of the fixture (expected block and
  `variant_bench_share_0_10`) to 1e-6, 0 mismatches; key sets of estimates,
  peers, rows, players, fill sets compared exactly. The spec's hand-check
  (p1 RB Delta 47.910397; DDF 48.511113 / 50.223260 / 45.086821) passes, and
  every source's Adjusted and VORP-vs-waivers totals equal the pie.
- Discrimination: the same checker reports mismatches for each broken rule
  (fit window 5: 22; mean instead of median: 615; pie 16: 761; min fit 4: 665;
  bench share 0.35: 615; flex pushed to RB; no fill-in), and the pre-change
  reference (15292b6a) errors on the fixture (`no attribute 'run_pipeline'`).
  A fixture perturbation (one fit player, one estimated path) is caught.
- `pipelines/value_check.py compare` ran headless on this worktree's built
  dist/ (old engine): ENGINE_JS runs with 0 page errors on 24 settings; the
  engine reports no `valuePipeline`, so the verdict is `incomparable` and
  nothing is held. Forcing the diff on those dumps (752,395 values) exercised
  the per-source / per-series / per-setting / worst-example report.
- `tests/test_value_check.py` (pure tests), `tests/test_load_value_check.py`,
  `tests/test_espn_listed_rows.ReferenceEspnListedRowsTest`,
  `tests/test_spec_reference.py`, `tests/test_published_views_engine.py`: pass
  with python3.12. The three live-engine tests in test_value_check skip until
  the built engine declares `value-pipeline/2`.
- `make validate` with python3.12 first in PATH: see the PR body for the run.

### Claimed, not confirmed
- Engine vs reference agreement on live data: not run (the engine branch has
  not landed). Command: `python3 pipelines/value_check.py compare --report
  output/value-check.json` after `make sync` on a build with the new engine.
- Live-data sanity only (not checked against anything): at Full PPR 12 with
  no prior week the reference gives 520 of 737 rows a blended DDF Value of 0.

### Reference readings (spec silent or open; also on JEG-508)
- ESPN lists a player it projects at zero (`espn_status` ineligible, no
  per-game points) at native 0.0, so he has a row and ESPN 0 (JEG-496; the
  ESPN week-5 snapshot carries those players at 0 too).
- Current content week for the prior-week pairing = the newest served week
  among the eligible sources (history `served`); a source has a prior-week
  snapshot when it serves that week and week-1 is saved with values at the
  scoring. A history built for a different fixture build gives no prior week.
- Prior week at a superflex setting uses the snapshot's 1-QB natives (the
  history has no superflex natives; VP-8.1 forbids current-week inputs).
- Indexed with no factor (VP-6.4 null) is null for every row of that chart,
  including players below rosterable depth.
- Curve path with fewer than 3 points or equal m and no listed player with
  m > 0: raw = 0 (spec text), reported with `low: null`.
- "Unpublished" applies to weekly charts only (projections always current);
  the weekly test is the existing one (week older than the current NFL week,
  or older than the newest weekly section's week).
- value_check compares projections in the Indexed tab (VP-11: "available,
  off by default"), and does not compare series VP-11 marks "not drawn".

### Follow-up: spec PR #484 rulings (same session)
- (a) projection natives at full precision with ESPN ineligible listed at 0,
  (b) superflex overlay sets and adds every player it lists, and (d) prior
  week from the history as saved: already what the code does (read in
  `Setting.natives` and `snapshot_natives`); no change.
- (c) Indexed factor is now also null when the shared DDF Value sum is <= 0
  (it was 0). Verified: `IndexedNullRule.test_ddf_sum_zero_gives_null_for_the_whole_chart`
  failed before the fix (0.0 is not None) and passes after; the worked example
  still reproduces at 1e-6.
