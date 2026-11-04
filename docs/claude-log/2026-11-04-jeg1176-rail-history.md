## 2026-11-04 - JEG-1176 transition history preload

Contract: repair the candidate comparison rail's browser/reference disagreement
without changing pricing rules, production inputs, provenance or release gates.
Parent retains merge and live acceptance ownership.

### Verified (check named)

- Ownership reconciled against the supplied Nov 4 11:22 UTC Mac/native-session,
  process, cwd and file-handle inspection and unreleased Linear takeover claim
  `48dbf79e-8150-480e-90d3-4cab19e5d538`. Cloud continuation claim
  `510ec80e-28bf-4c9f-84ce-b077ace33f68`; exact scope checkpoint
  `99525e25-0fdd-4b4f-af2a-837079cdf9fd`. Original cloud checkout was clean;
  this isolated branch starts at `d7881b1c105f33a51caecba74e76326987f802eb`.
- Baseline `tests.test_value_check.ReferenceMatchesEngine` passed: 25 settings,
  1,234,507 values, maximum absolute difference 6.39e-14. The ordinary committed
  build therefore did not reproduce the candidate failure.
- A fixed Week 8/9 replay with three known newest-week projections and four
  unmatched charts reproduced all seven source disagreements. Browser startup
  fetched Week 8 only; its diagnostics said Week 7 was not loaded. The Python
  reference loaded Week 7 and paired only the three projections. This matches
  the recorded pre-hold failure signature; later all-source holds explain the
  zero chart-priced rows, so changing the assertion or test date is insufficient.
- `tests.test_value_check.TransitionHistoryPreload` fails against the original
  loader only for the minority-newest subcase; its all-newest control passes.
  With the repair both subcases pass, including source membership, current/prior
  weeks, available prior values and numeric engine/reference comparison.
  Commands used `python3 -m pipelines.baseline_reds --context local --` with
  `RENDER_TESTS_REQUIRED=1`, `CHROMIUM_PATH=/usr/bin/chromium` and the repository
  identity set. Before: 24.305s, one failure; after: 24.123s, pass.
- The runtime delta only preloads N-2 as well as N-1, with deduplicated requests
  and the existing retained-version/failure handling. No source input, saved
  history, hold, pricing formula, tolerance or existing assertion is edited.
- Open draft #1292 also touches the widget for a separate bench readout, but
  has no update since Nov 3 16:13 UTC and remains dependency-held. Its branch is
  untouched. Parent must reconcile future movement before serial integration.
- The old transition fixture has a separate live-input dependency: under the
  recorded drift it produces three sources on Week 9, CBS/USA Today on Week 8
  and two unmatched sources, while its assertions require five-of-seven newest.
  The new fixture regression rejects that original helper (loaded directly
  from the tested base without changing source files).
- `transition_overrides` now replays saved Week 7/8 chart natives and projection
  PPG on both implementations. Its reference consumers receive the same replay
  players; its browser consumers pin to the replay date. Explicit replay setup
  clears live holds, and the held-CBS test still adds its own red hold. Existing
  majority, corruption, carry-forward and rank-inversion assertions are intact.
  `make validate` ran all 36 history tests and all 17 bench-budget tests after
  this change; both passed, including numeric parity and negative controls.
- Required `python3 -m pipelines.baseline_reds --context local -- make validate`
  completed with exit 0: core checks, strict comparison (1,234,507 values,
  no disagreeing sources, max absolute difference 6.394884621840902e-14) and
  integration checks. The new focused preload command was added to Makefile
  after this invocation parsed its recipes; the final module run separately
  covers that command and the updated rank-replay date consumer.
- Standalone `pipelines/check_rank_guard.py --out /tmp/jeg1176-rank.json`:
  12 chart/setting checks, zero failures and zero inversions.
- Core/shard wiring: all 16 `tests.test_validate_shards` checks pass.
  Supplemental render wiring has four **unregistered, pre-existing reds** in
  `tests.test_render_sweep_shards`: `test_uso_site_journey_render` is listed in
  test-render-extra but no shard. The same four failures reproduce on the
  untouched base Makefile; the new core command does not change that defect.
  All four `tests.test_render_sweep_coverage` checks pass. No assertion, registry
  entry or separate render-sweep schedule was changed to hide those failures.
- Final-version regression on the original loader: minority-newest disagrees
  across 36,042 compared values; the all-newest control agrees across 49,368.
  This expected negative run is recorded separately from validation results.
- Final `python3 -m unittest tests.test_value_check tests.test_rank_guard
  tests.test_v2_contract_render`, under the same required-browser baseline
  wrapper: all 58 tests passed (607.591s), including the full contract's broken
  build controls and the updated held-CBS/rank-inversion replay. The repaired
  minority case agrees on 28,599 compared values; all-newest agrees on 49,368.
- `tools.engine_dump` on 13 settings (three scorings x four sizes plus
  superflex), with the original base widget served as an override and then the
  repaired widget on identical built inputs: complete output is exactly equal.
  Every setting has `fixedPieIndexed` and `indexedOrderOk` true. No reference or
  spec formula changed; browser startup now supplies the already-required prior.
- The full base-to-main comparison through
  `f9fdbb82065e46b533735f8c3f3caec9550a4110` contains only the four operational
  status JSON files (two newer commits). Per Jeremy's approved option A, no
  integration/restart solely for those status updates. Parent must recheck the
  actual main delta and preserve it in a clean merge immediately before release.

| Fixed Week 8/9 replay | Original loader | Repaired loader |
| --- | --- | --- |
| Three known newest / four unmatched | Default Week 8; Week 7 not loaded; pipeline participation differs from reference | Default Week 8; Week 7 available; exactly the reference's three projection inputs |
| All seven known newest | Default Week 9; agrees | Default Week 9; agrees |
| Ordinary inputs, 13-setting complete dump | Baseline | Exactly identical; all fixed-pie and order checks true |

Production fixture/history and unmatched provenance remain unchanged. Fresh
candidate and live before/after acceptance belong to the parent release lane.

### Claimed, not confirmed

- Independent high-risk review, required exact-head CI, parent-owned merge,
  deployment and a fresh candidate chain/live acceptance remain pending.
  A passing replay does not establish that the live rail has recovered or that
  the whole date-gated JEG-1176 ticket is complete.
