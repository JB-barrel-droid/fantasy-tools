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

## Current-main qualification checkpoint

The parent explicitly resumed this same sole-writer lane for ordinary
ticket-branch integration and a true final-integrated-head full validation
receipt. The previous invocation does not clear the integrated head.

### Verified before the qualification commit

- Reconciled JEG-1176 and JEG-1348 ticket comments, current PR branches and own
  checkout. Parent confirms #1292 owner `01a1a1a3-e9de-75fd-8be1-6733381420d3`
  is doing read-only compatibility work, with no writes. Repair-first ordering
  stays with this #1304 lane; parent remains the sole release owner.
- Normally merged main `83e57734d04516dd26f2144d431f1267afbe24c8` into the
  existing `codex/JEG-1176-rail-history` branch, from repaired `bf64c4ea`.
  Git found no conflicts. Nine inherited main paths include substantive ESPN
  Week 9 projection changes and operational status artifacts. For example,
  player 171's projection becomes zero; the CSV grows 4,608 to 4,609 rows.
  This is not covered by the status-only exception. No source from #1292 was
  merged or copied into #1304.
- Independently inspected #1292 head `932ec24c8c82fed9d93e921079097e8cf511533c`
  in the two overlapping files. Its `benchShareReadout` hunk adds display-only
  `weeksLeft`, `byesLeft`, `byeTeams` from the existing resolved window/bye map,
  around line 2457. #1304 changes `preloadCompositeHistory`, around line 3028.
  Its Makefile hunk adds the feature test command to core and shard 4; #1304
  adds the preload regression to core and shard 1.
- `git apply --check` accepts those two #1292 hunks against the integrated
  working tree. Applying them only to a scratch copy preserves both commands;
  combined `shard_problems` and `validate_problems` report no errors, combined
  widget `node --check` passes, and #1304's loader remains byte-identical.
  This is bounded compatibility evidence, not an approving or high-risk review.
- Feature semantics to preserve on later #1292 integration: count from the
  actual resolved model window, including an empty window; unavailable byes
  stay unavailable, distinct from zero. Keep the fixed historical O3 cohort
  context separate from a forecast. Its owner must run feature tests and the
  unchanged bench/reference, transition and contract checks on the combined
  head, then obtain the required independent review and wording approval.

### Gates at commit time

- Commit the integration and this note before starting one sequential full
  `python3 -m pipelines.baseline_reds --context local -- make validate`, followed
  by `tests.test_v2_contract_render`, with required Chromium and repository
  identity. Both receipts must identify this exact integrated head and be
  recorded on #1304 and JEG-1176; no later implementation edits may reuse them.
- Inventory all tracked/public-tree content after the build and before any
  branch publication. Preserve existing untracked outputs and unrelated work.
  A publication denial stops that action without an alternate route.
- Keep #1304 draft. Parent last reported ready capacity 8/8. Admission and
  permission are required before full exact-head CI; draft finalizer failures
  do not constitute green required CI. High-risk independent review follows
  green full CI and remains a separate gate.
- Preserve the four supplemental render-shard baseline failures without waiver.
  Release merge, deployment, protection changes, Supabase actions, deletion and
  approving reviews are outside this lane. Fresh chain/live acceptance remains.

## Qualification after the subsequent player-status input update

- Exact head `501504378aed25ba11fc61f077e8c8fa6fb04d39` completed its full
  required-browser `make validate` with exit 0 (started 13:04:12 UTC; finished
  by 14:02:56 UTC). It actually ran the final-wired preload case inside core:
  28,599 minority-newest and 49,368 all-newest values agree. Strict comparison
  agrees on 1,234,507 values, max absolute difference 6.394884621840902e-14;
  integration checks pass. Its subsequent contract module passed all six tests
  in 452.847s. These are true receipts for that head, not for a newer base.
- During that qualification, main gained `2d335471` (JEG-1363), changing
  `data/inputs/player_status.json` and its history output. The input advances
  Nov 3 to Nov 4: 81 injury-status changes, three team changes, and three added
  Sleeper records (874 to 877). The history report writes 947 rather than 948
  resolved rows. These are substantive data changes, so no status-only exception
  is used and the completed `50150437` results do not clear the newer base.
- Preserved all 22 tracked generated outputs from that completed run in stash
  `475cd30a9c3fc76dc001ad4a8e8e0f9aa459da38` and a binary patch at
  `/tmp/jeg1176-generated-50150437.patch`. Untracked generated outputs remain
  untouched. No stash was dropped and no files or work were deleted.
- Refetched latest main `fae7776412699ce31c23a61022644454a81aef97` and normally
  integrated it into this same ticket branch without conflicts. Its five newer
  commits contain the player-status input and operational status updates only.
  Makefile and widget are unchanged from the main base used in the #1292
  compatibility analysis, so the textual ordering finding remains applicable;
  it still does not establish combined-feature behavioral validation.
- The next qualification commit includes this note before another single full
  validation invocation. That invocation and its sequential contract check must
  produce their own exact-head receipts. No earlier result, registry change or
  assertion waiver may substitute for them. Public-tree inventory still precedes
  any push. At 14:04:12 UTC all eight ready slots were occupied; admission and
  explicit permission remain required before full CI. No #1292 import, ready
  promotion, workflow cancellation, protection change or release action occurred.
