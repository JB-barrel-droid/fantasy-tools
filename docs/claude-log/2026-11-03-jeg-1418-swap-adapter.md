## 2026-11-03 - JEG-1418 local swap adapter

Contract: implement a separate pure adapter on the merged #1239 waiver-board
0.1 model, reusing Waivers/finder rules. No shared sections-builder, routes,
threshold policy, Supabase or runtime activation. Jeremy approved the ownership
claim and In Progress status after their initial automatic-review rejection;
both succeeded on the single approved retry. No label was added.

### Verified (check named)

- Ownership check: ticket initially had no comments, no matching remote 1418
  branch or open PR. Isolated branch `be/JEG-1418-swap-adapter` started at
  `ad0cfc3a40ed3cdbb6d3291e4bb1c735d5bd6dfc`; merged #1239's commit
  `89cc7a0884db165d01f805b7c23e5b6cd11c52e1` is an ancestor.
- `node --test tests/waiver_board_swaps.test.cjs`: 18 tests pass. Hand-worked
  swaps have raw gains 10 and 6, while the first weighted roster change is 5.8.
  The suite reads the six existing frozen waiver fixtures and board golden;
  no fixture was edited. Direct Waivers evaluations and finder roster impacts
  agree at each selected move.
- `python3 -m unittest tests.test_waiver_board_swaps
  tests.test_waivers_math.WaiversMathTests.test_rules`: 2 tests pass, including
  the new Node suite through the Python runner and existing Waivers rules.
- Cases cover additions/removals, duplicate and own-player exclusion, conflicting
  overrides, missing identities, missing values versus real zero, bench-only
  priced drops, thin positions, partial rosters, one use per player, explicit
  gain acceptance and independence from weekly fields.
- `make validate` initially stopped at `sync`: Playwright's registered browser
  was absent. A retry uses the existing `/usr/bin/chromium` through
  `CHROMIUM_PATH`. Final outcome is recorded below when available.

### Claimed, not confirmed

- No live behavior is activated by this module. It exports
  `TradeValueWaiverBoardSwaps` in a browser only if explicitly loaded, or a
  CommonJS API offline. No script tag or build inclusion was added.
- Independent review, CI and publication remain separate gates. The earlier
  full Waivers mutation-suite process no longer exists after the resumed
  session; its result was unavailable and is not claimed as passing.
- Automatic approval review denied `github_create_tree` for the four new files
  in `datadrivenfootball/fantasy-tools`, citing unclear authorization for remote
  source/document publication and commit preparation. No tree was created;
  no other transport was tried. Branch publication, draft PR and CI await
  explicit approval. The Linear claim/status retry succeeded independently.

### Integration handoff

`buildSwapPlan(board, options)` accepts `rosterKeys`, `wireKeys`,
`wireOverrides: {add, remove}`, `context: {shape, expected, weights, rosterSize}`
and REQUIRED `acceptGain(rawDdfGain)`. Keys must already be resolved by the
existing paste resolver. The caller supplies its existing wire policy and gain
cutoff; this module chooses neither. Conflicting add/remove overrides are refused
instead of inventing a precedence. No local storage is read or written.

The result is `{available, missing_reason, swaps, unresolvedWireKeys}` (an
unavailable result has no swap rows). Each swap is `{add, drop, gain,
evaluation}`; `drop` is null for an open roster slot. `gain` is add DDF Value
minus drop DDF Value (zero cost only for an open slot). `evaluation` is the
existing Waivers result, including weighted change and finder depth information.
The module reuses Waivers' best drop and ordering, then reevaluates on the
resulting roster. It omits a move if that drop is an unpriced player, a starter,
already used, or would worsen a thin position; it does not search for a
separately ranked alternative drop.

Integration still needs the shared schema/builder owner to evolve the 0.1
`swaps` placeholder, supply league allocation-derived expected depth and bench
weights, and settle/reuse the cutoff policy. The board row's weekly lane never
feeds ranking or gain. Register `tests.test_waiver_board_swaps` in the shared
Makefile test list with its owner; this slice leaves that shared file untouched.
