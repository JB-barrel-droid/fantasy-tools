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

### Claimed, not confirmed

- Required `make validate` is running sequentially; its final result is pending.
- Independent high-risk review, required exact-head CI, parent-owned merge,
  deployment and a fresh candidate chain/live acceptance remain pending.
  A passing replay does not establish that the live rail has recovered or that
  the whole date-gated JEG-1176 ticket is complete.
