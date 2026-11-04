## 2026-11-04 - Non-runtime consumer contract / JEG-1505

Contract: add distinct test/handoff files only, using actual existing
interfaces. Preserve independently reviewed adapter commit
`b501b3ff39307f775bf9b19f79b2afe644eb59b6`; no runtime consumer, provider-owner,
production policy, pricing, methodology, snapshot or shared test edits.

### Verified (check named)

- `tests/test_jeg1505_search_only_consumer_contract.py` calls the real Node
  exports of `app/v2/waivers.js`: `rowsFor(entries, byKey)`,
  `dedupe(candidates, roster)`, `encodeHash(mineKeys, candKeys, league)` and
  `decodeHash(hash)`. The module's existing Node branch returns before its
  browser-only UI code. There is no server, browser, fetch or recommendation
  calculation. Test helpers `entry` and `consume` are harness functions, not
  new production interfaces.
- `python3.12 -m unittest -v
  tests.test_jeg1505_search_only_consumer_contract`: all six tests pass.
  The command log is sibling `../jeg-1505-consumer-contract-tests.log`.
- `python3.12 -m unittest -v tests.test_searchable_identity_eligibility
  tests.test_jeg1505_search_only_consumer_contract`: all 25 tests pass (19
  existing adapter tests plus six new contract tests). Log is sibling
  `../jeg-1505-consumer-contract-combined.log`. Explicit diff checks against
  b501b3ff confirm adapter, existing tests, consumers, shared universe and
  source fixtures unchanged. Only this handoff and the distinct new test
  file are added.
- Committed Aiyuk metadata ties Sleeper 6803 to canonical 568. The existing
  consumer entry shape is `{key, name, pos, team}` and must carry key `568`.
  Adapter pricing is explicitly unknown when actual computed keys are absent;
  the test gives Aiyuk no numeric prices or projection fields.
- Existing `dedupe` removes canonical 568 when on the supplied own roster.
  Passing raw provider key 6803 fails that own-roster exclusion and remains
  unresolved. This characterizes why verified ID resolution is upstream.
- `dedupe` does not filter other teams' ownership. A test-only caller filter
  demonstrates that other-owned canonical keys must be removed before
  constructing the candidate list. No production ownership filter is added.
- An explicit synthetic computed row map retains exactly its supplied key,
  values and object references after both calls. Retained Aiyuk stays in
  `rowsFor(...).gone`; no numeric row is fabricated or added to that map.
  Frozen inputs are unchanged. This does not establish rendered engine output.
- Unknown retained keys remain serializable through the existing waiver hash
  functions, deduplicate by canonical key, and stay unresolved without fake
  rows. Synthetic sourced retirement excludes default selection while the
  identity/history remains; a sourced return restores the identical key.
  Hash round-tripping is tested, not browser storage persistence.

### Proposal and remaining dependencies, not implemented

- Minimal search-only runtime boundary: existing `searchPlayers` and
  `playerRow`/`getPlayer` in `app/trade-value-chart/assets/curve-widget.js`
  (lines 1468-1497 in the reviewed base). A separate identity lookup would
  need an agreed data ingress. None is added or named as an existing API here.
  `canonicalByKey` is also consumed by `pipelinePlayers` (line 660), so
  expanding it through current `TradeValueProductData.getPlayers()` is not
  qualified as isolated search work. Keep computed pricing membership and
  `getAllRows()` unchanged; preserve existing priced-row lookup behavior.
- A complete canonical history and reviewed lifecycle source remain required
  to recover identities already missing from today's baked players fixture.
  The six real canonical/Sleeper position disagreements remain in the earlier
  JEG-1505 logs; no record or position was corrected in this pass.
- `git cat-file -t c5890a75` reports that the coordinator-qualified owner
  commit is absent from this local object store. No remote lookup or fetch
  was attempted. Meaningful tests of that newer adapter require its source
  at the exact qualified commit, its actual callable interface and its actual
  computed-board keys. No imitation of that adapter or invented production
  API was substituted.
- Coordinator-supplied evidence, not independently rerun here: #1296 at
  c5890a75 passed nine new cases; all 420 universe IDs absent from the 741-key
  priced board remain unresolved wire keys; rostered Aiyuk disables swaps;
  other-team ownership must be filtered before wire keys because the owner
  adapter excludes only the user's roster. These contracts remain required
  for future integration. Existing `rowsFor` has no swaps-enabled output, so
  these tests do not claim to qualify that newer flag or recommendation path.
- Supply actual computed pricing membership explicitly. The 875 fixture rows
  lacking `universe_only` are not the coordinator's 741-key computed board.
  These tests use a clearly synthetic computed control; neither count is
  inferred or hardcoded as actual membership.
- Tests are manually runnable and not registered in shared CI targets. Normal
  owner-coordinated wiring, full validation, independent review and live
  coverage verification remain. Prior full validation's loopback-bind blocker
  was not retried or worked around. Nothing was published or activated.
