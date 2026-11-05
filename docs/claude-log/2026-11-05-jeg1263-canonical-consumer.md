## 2026-11-05 - Simplified canonical readout consumer (JEG-1263)

Contract: resume the existing draft #1297 lane during Jeremy's parallel DDF push, close concrete Simplified-only gaps
against JEG-1483, preserve the previous private artifact and avoid shared shell, Fieldnotes identity/readiness,
finder/league provider, pricing or JEG-1505 files. No math or classification is implemented in this consumer.

### Verified (check named)

- Fresh #1297 remained draft/unmerged at this lane's eecf7372. Current JEG-1483 and source contract from PR1302 head
  `061fd5fed6930b7e5c24d7b1fc291003f483006b` were read. Operations registry preserves independent Fieldnotes/canonical
  and identity-search owners; this lane retains only Simplified and dedicated tests. No local validation was running
  before the focused run. No .agents skills were present. Prior artifact and Library item remain unchanged.
- Concrete gaps: canonical rows have no legacy likelihood/band requirement, their headline is the supplied starter
  quantity (not legacy edge/package gain), unknown quantities must remain unavailable, and add-only Pickup must not
  fabricate a drop, a manager or an opposing lineup. These are now handled by the scoped consumer.
- `canonicalContext(result, options)` consumes the existing `runCanonical` page without cloning row identity, search,
  sorting or store writes. It retains producer bounds/page disclosures and rank. Cancelled/pending/missing contexts
  withhold old results; an empty page does not claim the full search has no matches. A supplied detail readout must
  match the exact record; the old live bridge refuses to reprice canonical records through legacy settings.
- The renderer copies all four ordered question statuses, subject/scope/basis, values, coverage, sources, aggregation,
  tolerance and active threshold metadata. The source's label is authoritative even if a synthetic test's pass flags
  disagree. Unknown starter values never become zero; known package zero remains visible. Pickup shows the source's
  not-applicable questions and skips the fictional opposing roster. No coverage minimum or fit predicate is derived.
- `python3 -m unittest tests.test_jeg1263_simplified_site`: 3 tests pass, with 23 consumer/legacy checks and 22 mutation
  guards. Canonical guards catch legacy-edge substitution, unknown-to-zero and mismatched detail records. Existing
  legacy guards remain. Input objects and captured row identity are preserved.
- Required focused unit/render run: 11 tests pass (96.330s), including canonical questions/detail/Back three times at
  1280/390/320 with no overflow/storage writes, source unknown update, previous seven-state fixture coverage and loaded
  legacy USO contract checks. Final scoped canonical-browser rerun after page-rank/empty-page/bridge guards also passes.
- `node tests/node/jeg1263_canonical_consumer_check.cjs /tmp/jeg1263-canonical-owner-061fd5fe` passes four cases using
  PR1302's actual readout producer in a read-only archived checkout: both owner-pinned real witness inputs, one remaining
  published source (unknown judgment) and explicit add-only Waivers. Source values/labels/coverage and exact selected
  readout survive consumption; no producer suite or pricing implementation is copied. Team IDs are explicit test
  context IDs, not claimed live user IDs. Original input/result bytes are unchanged.
- JavaScript syntax and scoped diff checks pass. Generated app/history/dist output stays unstaged and excluded.

### Exact controller handoff (not an edit to its files)

The canonical route owner should feed its own completed result and generation/settings/week invalidation through:

```js
const S = TradeValueSimplifiedSite;
const handle = S.mount(container, {
  hash: () => location.hash,
  getContext: () => S.canonicalContext(currentCanonicalResult, {
    league: {name: sharedLeague.name, myTeam: sharedTeam.name},
    basis: sharedDisplayBasis,
    detailId: S.parseRoute(location.hash)?.detail,
    readoutFor: row => TradeValueOpportunities.canonicalReadout(row)
  })
});
// On the controller's shared result/generation change:
handle.update(false);
```

`currentCanonicalResult` is the original `runCanonical` output with original row objects; its WeakMap-captured readout
must not be rebuilt from legacy finder rows. The controller owns selection, pagination, cache identity (including
normalized calculationSettings/week), cancellation and shared URL transport. Only explicit fixture callers set
`fixture`. No shared source hunk is changed by this lane. Keep existing exact-name route/full access reachable.

### Claimed, not confirmed

- Exact new-head legacy real-provider artifact/navigation parity is qualified separately using the already-permitted
  local build/verifier and pinned #1084 provider. Its new output directory does not replace the prior private bundle.
- This is a component consumer and scoped contract test, not shared-controller adoption, completed Fieldnotes design,
  whole-project qualification or production acceptance. Full validation, independent current-head review, current-main
  and publication gates remain. PR stays draft. No superseding another writer's shared hunks, deployment, Supabase,
  access change, deletion, direct-main/force push or retry of denied live/log/other-lane bind actions.
