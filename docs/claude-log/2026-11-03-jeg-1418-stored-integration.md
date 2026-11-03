## 2026-11-03 - JEG-1418 stored-board integration acceptance

Contract: author integration acceptance for corrected adapter
`a704715880d2dca50ff5d9bc6a4da867d6d20af7`; not an independent review.
PR #1296 still owns the adapter/integration tests. PR #1295's renderer owner
is concurrently adding 0.2 support in its own files. No renderer, builder,
main UI, Fieldnotes or Simplified source is changed here.

### Receipts reconciled

The prior exact-head focused run has 21 Python checks passing. Its settings,
security and offline Waivers CI checks passed; required preview/render checks
remain red under draft guards. The original broad run ended at the phone
source-link target check (zero links at widths 320/375). No broad process is
left running in this checkout, and no new broad run or cancellation occurred.
The prior generated churn is untouched. Denied correction-ticket writes were
not retried.

### Concrete renderer handoff

`tests/fixtures/waiver_board_swaps/` contains:

- `stored-default.json.gz`: byte-exact board member extracted from the stored
  JEG-1419 archive at `1eea6c340098863a1cbb3df149debcc70614d3fa`, without
  repricing. Week 8 / 12-team Half PPR / sf0; 741 real player records.
- `stored-opt-in.json.gz`: validated 0.2 integration copy using the corrected
  adapter; every player lane, source, setting and unresolved/sections field is
  preserved. Producer is explicitly marked as a test fixture.
- `request.json`: explicit illustrative test roster, wire, overrides, context
  and test-only gt 0 policy. This is not a user's roster or a production policy.
  Context comes from the existing Waivers thin-RB fixture, with K/DST slots
  explicitly zero because this stored board contains only tradable positions.
- `provenance.json`: pinned archive commit, source/blob hashes, extracted-board
  hashes, expected rows, real decimal-boundary case and renderer API contract.

The renderer's API is `TradeValueWaiverBoardView.render(host, board,
{onSettings})`. The populated 0.2 `swaps` block contains exactly `available`,
`missing_reason`, `request`, `rows` and `unresolved_wire_keys`; each row is
`{add, drop, gain}`. Resolve player names/positions from `board.players` by
`player_key`. A null drop means an open slot; do not invent a zero-valued player
or substitute weighted roster change for raw DDF gain. Keep 0.1 unavailable
swaps and unavailable sections honest. All display policy stays with the
renderer owner.

Expected opt-in rows:

- add James Cook (1110), drop Pat Freiermuth (786), gain 58.19165721595734.
- add Ja'Marr Chase (2730), drop Dalton Schultz (260), gain 52.51902503504703.

The real boundary case uses Christian McCaffrey (3189) and Mark Andrews (324):
54.37460245144543 - 0.55925748534344 = 53.81534496610199 in canonical decimal
arithmetic. gt at that exact minimum excludes the move; gte includes it.

### Verified (check named)

- The stored default and derived opt-in artifacts pass `waiver_board.validate`.
  Their 741 player records and sources compare equal. The extracted source
  bytes hash to `a4ee3e9c01987a10ef50a9832f10ba5a1c805ddfe4fd21b0d822596d271238fd`.
- Added real-data tests in the existing owned native/Python modules cover
  shared-rule reproduction, raw-gain Decimal checks, unique player use,
  A/B/A repeated selections, a true open slot, unknown roster refusal,
  exact decimal boundaries and unsupported/missing positions. Missing-value
  negatives modify only in-memory test copies and prove no zero fill; the
  stored source has 549 real zeros and no missing DDF Values.
- Focused command: `python3 -m unittest tests.test_waiver_board_swaps
  tests.test_waiver_board_swaps_pipeline tests.test_pipelines_import_standalone`.
  The exact-head result is recorded in the PR body; no heavy suite is included.
- Executed the actual renderer from pinned head
  `979bdedc48cecc545fc94ad0fcb5d3037cae1eca` against both artifacts with a small
  DOM harness: default renders 741 rows, real zero remains 0, missing weekly
  fields show unavailable, settings callbacks receive a clone, and repeated
  calls clear the host. Its explicit 0.1-only guard rejects opt-in 0.2. Receipt:
  `/tmp/jeg-1418-renderer-contract-979bdedc.log`. This is DOM contract acceptance,
  not a new browser/layout or accessibility review.

### Claimed, not confirmed

Positive 0.2 rendering awaits the concurrently owned renderer change. The
pinned 979bdedc reader is not claimed to support it. The fixtures provide that
owner a concrete compatible payload for explicit 0.2 support while retaining
0.1 behavior. Independent review and full green CI remain separate gates.
No source activation, merge, deployment, shared-file edit or access change was
performed.
