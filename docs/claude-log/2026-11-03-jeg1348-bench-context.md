## 2026-11-03 — Bench context beside the share (JEG-1348)

Contract: implement the display-only weeks/byes readout and the committed O3
historical breakout cohorts. Preserve valuation math, ranking and defaults.
Base: `a552c00884287147a099a1279c94b3fdb0d4ca88`.

### Verified (check named)

- Linear ticket/comments and GitHub open-PR/file search: no active claimant or
  matching PR; prerequisites #1139 and #1105 are merged. Claimed JEG-1348 before
  creating `fe/JEG-1348-bench-context`.
- GitHub metadata also confirms content-week prerequisite PRs #1127 and #1012
  merged. A final main-ref read remains the pinned base above.
- `tests.test_jeg1348_bench_context`: four tests pass. The widget counts the
  resolved window and its own config's bye map; week 8 is 9 weeks and 18/32
  teams, week 14 is 3 weeks and 0/32, weeks 17/18 are 0 weeks and 0/32.
  Unknown data is unavailable, and a historical zero retains its sample count.
- Negative control: the widget-context regression fails against the original
  widget from the pinned base (all six context pairs are missing).
- `build_readout_asset.py --check`: the shipped asset reproduces precisely the
  12 O3 rows in the committed evidence matrix, including their counts and rates.
  No O1 by-week rates are included. The asset records the matrix SHA-256.
- Existing `tests.test_bench_decay_evidence`: 29 tests pass; original evidence
  rerun matches 81 rows and 10 documented gaps. `tests.test_validate_shards`:
  16 tests pass, including the new tests' core/shard wiring.
- `git apply --check docs/claude-log/2026-11-03-jeg1348-integration.patch` passes
  against the pinned source. `app/v2/v2.js` and `pipelines/build_v2_page.py` are
  untouched; the patch is the proposed integration, held for the coordinator.
- JavaScript syntax checks and Python compilation pass.
- Focused Chromium run with rendering required: all 7 tests pass (26.8s),
  including desktop weeks 8/14/17/18, the selected playoff window, override
  reset, all 12 historical rates/counts staying fixed, 390px overflow and the
  unintegrated-page negative control. The harness MIME correction is verified.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest
  tests.test_jeg1348_bench_context tests.test_jeg1348_bench_context_render
  tests.test_bench_share_readout_matches_reference tests.test_v2_contract_render`:
  all 16 tests pass (485.9s). The two existing suites are unchanged, including
  all contract mutation guards. Browser work ran sequentially.
- Final focused rerun: 7/7 pass (25.1s) after the harness also executes the
  held builder in a temporary output directory and reads the copied modules.
  The harness supports both the pending and already-integrated patch state.
  The phone check also pins the disclosure's 44px minimum target using the
  existing `v2-padv` styling. No shared CSS was edited.
- Before/after `tools.engine_dump` sweeps, overriding only the widget with the
  original base version for the before run: complete output is identical at
  all 13 settings; `fixedPieIndexed` and `indexedOrderOk` are true throughout.
  Sorted JSON SHA-256 for both:
  `5489276dd3aa77c382e1c78079fc438924b3c7c135f14526a1fa53296151bda4`.
- `make value-check-compare test-integration` passes: strict engine/reference
  comparison agrees on 1,234,507 values across 25 settings, zero mismatches
  and zero page errors; all 170 hermetic integration tests pass.
  `pipelines/check_rank_guard.py`: 12 checks, zero failures or inversions.
- Raw `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make validate`
  stops at the unchanged
  `tests.test_fractional_seats_stability.FractionalSeatStability.test_hard_rule_fails_the_bound`:
  worst move `0.0` is not greater than `1.0`. The positive stability test passes.
  This is the existing JEG-1479 / PR #1287 negative-control blocker. That test,
  its Python reference, config and input fixtures are unchanged by this lane.
  No gate is waived and no assertions are weakened.

### Claimed, not confirmed

- Full validation is blocked as recorded above; there is no green-gate claim.
  Draft PR CI is pending publication. Required preview/render checks defer
  expensive work for drafts and deliberately report red; keep the PR draft.
- Nothing is published by this PR yet. The new modules are deliberately not
  loaded until the coordinator applies the held integration patch after the
  PR #1290 file ownership is released. Re-run the browser integration and
  unchanged contract suite on that combined head.
- Proposed display: a measured line under the share; an expandable historical
  table shows all three backup-depth groups for QB/RB/WR/TE, counts beside each
  rate, and the week-9 / 2015–2025 / 12-team / half-PPR basis. Depth groups are
  fixed historical cohorts, not a mapping to a current player or league. The
  full-season target and source missing-score fallback remain explicit.
- Jeremy still approves the final wording at review. The coordinator assigns
  review risk; `curve-widget.js` triggers the high-risk floor regardless of
  the older ticket label. No independent review, merge, deployment, cancellation,
  deletion or Supabase change is authorized or claimed in this lane.
