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

### Continuation: opt-in populated artifacts and registration

Jeremy asked the existing JEG-1418 lane to continue with safe independent
schema/builder wiring. Publication of the original four-file slice succeeded
after his explicit branch/draft-PR authorization: PR #1296, exact head
`4f7515bc1a70625eca38bcd2e6b6d73ea0e883b9`. Its offline Waivers mutation CI
passed; required preview/render completion checks are red under draft guards.
The earlier publication denial above is historical and resolved.

Ownership reconciliation: JEG-1419 / PR #1264 is at
`1eea6c340098863a1cbb3df149debcc70614d3fa`, editing the separate site builder,
sync hook, archive, one Makefile registration and the board golden's input hash.
JEG-1416 / PR #1249 is at `2c7a915be6e39b043abec04243e97678669f5b0d`, parked
after its 120 focused tests; it owns the weekly producer/contract and fixtures.
Neither edits `pipelines/build_waiver_board.py` or `pipelines/lib/waiver_board.py`.
JEG-1417 has no active implementation claim or PR. Its threshold choice remains
Jeremy's decision. This continuation leaves their paths and fixtures untouched;
the new Makefile registration is separate from JEG-1419's registration.

Implementation: optional `--swap-request` / `swap_request=` writes a 0.2.0 local
artifact with a compact swap block and its explicit request. Default builds stay
0.1.0 and byte-identical to the pre-change builder. Request policy requires a
finite minimum and explicit gt/gte comparison, with no default. The schema
replays the same JS adapter through the offline Node bridge, so gain, identity,
order and depth decisions have no Python implementation copy. Node is required
only for opt-in 0.2 build/validation. The shared test list now registers both
adapter and pipeline modules. Contract docs describe the new boundary and old
reader compatibility. No site-build activation, source flip, route, threshold,
runtime writer or production change was made.

#### Verified (check named)

- `python3 -m unittest tests.test_waiver_board_swaps
  tests.test_waiver_board_swaps_pipeline tests.test_pipelines_import_standalone`:
  18 Python checks, OK, captured exit 0; the adapter wrapper runs all 18 native
  Node cases. Log `/tmp/jeg-1418-wiring-new-tests.log`.
- Added pipeline tests pin raw gain 5.75; two successive moves in existing
  Waivers order; replay rejection of altered gain, identities, repeated players,
  order and changed lineup context; cross-position thin protection; strict versus
  inclusive caller boundaries; explicit reasons for missing roster/depth and
  stale values; default no-Node operation; input refusal preserving an existing
  output file; request-file hash provenance and byte-stable CLI reruns.
- The initial new negative test changed a depth band on a like-for-like swap,
  which correctly left the move valid. The corrected scenario changes the
  lineup so the proposed bench drop is now a starter, and a separate case tests
  cross-position thinning. No existing assertion or fixture was weakened.
- The non-reference board regression run had 95 passes and one failure in the
  existing golden-byte test. An isolated copy of the pre-change builder AND
  validator from `4f7515bc` and the current builder both exit 0 and emit identical
  default bytes. Their sole difference from the committed golden is
  `$.inputs.weekly_inputs.sha256`: actual
  `2fcf34ed369cac27d9276308b0b2e22d279af0d56e89c11caa7a39500e4bff1b`, golden
  `b725cf300623a9fbe9b9b0c0779f710bf3fd42146400688521fd86bb6ca11655`.
  PR #1264's fixture already contains the actual hash. Evidence:
  `/tmp/jeg-1418-golden-provenance.json`. Its owner retains that fix; this PR
  does not edit the shared golden or weaken the byte assertion.
- `make -n test-unit-modules` includes both new swap test modules.
- `git diff --check` passes for the source changes.

#### Claimed, not confirmed

- The original broad validation process (make PID 4823, started before this
  continuation) is still running in this checkout; it has advanced beyond the
  seeded build suite. No duplicate broad run was started and no cancellation or
  cleanup was performed. Its eventual result does not establish an exact-head
  full-gate receipt for the later integration commit. Generated build changes
  remain uncommitted and excluded from this slice.
- The unresolved production gain policy, full exact-head CI and independent
  review remain coordinator gates. Optional 0.2 artifacts require consumers to
  explicitly support 0.2; default site boards remain 0.1.
