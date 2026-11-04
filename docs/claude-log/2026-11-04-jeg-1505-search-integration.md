## 2026-11-04 - Local search-only integration / JEG-1505

Contract: local integration from reviewed base
`03184e01f9badccb90758cc4033e68f1c237678c`. Parent relayed #1304's explicit
function-level clearance for searchPlayers/playerRow; its preload/history
work stays untouched. PR1301 alias/snapshot files are inputs only. No push,
PR, publication, backend operation, denied-bind retry or value-math change.

### Verified (check named)

- Checkpoint 2026-11-04T23:00:06Z: `node --check
  app/trade-value-chart/assets/curve-widget.js` and the same command for
  `product-data.js` exited 0. No test command was active at the checkpoint.
- `python3.12 -B pipelines/build_jeg1505_search_identities.py` completed:
  1,517 identities from dated local inputs, lifecycle and pricing unknown.
- Draft changes at checkpoint: curve-widget.js search boundary, optional
  product-data.js reader, new builder and new search-only JSON asset. This
  file records the in-progress session. No other writer/workspace was made.
- Local source evidence includes the full saved canonical export, partial
  October 31 naming manifest, grounded provider spellings and verified alias
  notes. They do not establish current freshness. Three historical duplicate
  claims are held pending confirmation rather than activated as redirects.
- Final local implementation: `searchPlayers` uses a distinct search identity
  map; `playerRow` retains computed/canonical lookup precedence and only
  materializes additional identities as unknown/null-valued metadata. New
  rows have `search_identity_only`, never fabricated projections or the
  legacy universe_only flag that the readout displays as 0.0.
- `product-data.js` exposes an optional cached `getSearchIdentitySelection`
  reader for the new JSON asset. The widget starts it without awaiting it
  during pricing init; missing/invalid coverage does not block priced data.
  The existing asset copy step already includes the new file. No script tag,
  preload function, pricing player collection or math function was changed.
- Additive real controls `resolveSearchIdentity` and `prepareSearchSelection`
  require explicit canonical/Sleeper namespaces. Provider 4046 resolves to
  Mahomes key 3594; canonical 4046 remains Hyatt. Inputs and override adds
  resolve/deduplicate together before own/other-team ownership filtering.
  Incomplete ownership, unknown IDs, conflicts and unpriced selections hold
  submission; wire keys come only from the actual current computed universe.
- Optional provider conflicts do not remove an existing canonical identity
  from search. Preflight still holds those conflicted selections pending;
  explicit retirement excludes default search and retains history/lookups.
- `tests/test_jeg1505_integrated_search.py` evaluates the actual widget search
  functions and public accessor expressions verbatim, with no DOM/init. Its
  numerical witness calls the existing ValueModel on the committed worked
  example. Installing 1,517 search identities leaves its 30 computed keys,
  complete pipeline result, copied numeric rows and canonical input unchanged.
  This is actual engine-computed test membership, not 875 universe flags or
  a claim to have reproduced the separately reported 741-player board.
- Final command (no browser/server/network): `python3.12 -B -m
  pipelines.baseline_reds --context local -- python3.12 -B -m unittest
  tests.test_searchable_identity_eligibility
  tests.test_jeg1505_search_only_consumer_contract
  tests.test_jeg1505_integrated_search tests.test_nfl_universe
  tests.test_sync_players_active tests.test_universe_chart_only
  tests.test_bake_espn_zero_universe tests.test_product_data_wiring
  tests.test_source_combo_contract
  tests.test_value_pipeline_engine.WorkedExampleTest`: all 104 tests passed
  (12 new integration cases). Log: `../jeg-1505-integrated-combined-tests.log`.
- `node --check` on both changed JS files and `git diff --check` passed.
  Eighteen protected files (including all used PR1301 inputs, adapter, UI,
  overrides, waivers and pricing sources) match base byte-for-byte. Nine
  protected function blocks also match, including pipelinePlayers,
  runPipeline, computePipeline, rebuildDomain, preloadCompositeHistory and
  product-data's getPlayers/initProductData. Evidence and hashes:
  `../jeg-1505-search-integration-evidence.json`.
- Additional input evidence narrows the earlier historical audit's limit:
  player_platform_spellings.json contains 929 grounded Sleeper spelling/ID
  records, including Aiyuk and the namespace collision. The earlier audit's
  219 no-link bucket was scoped to GSIS/idmap/fixture-history joins and must
  not be treated as a global absence across every local input. Its 356-key
  missing-fixture count is unchanged. No shared input was corrected.

### Claimed, not confirmed

- Sources remain dated and freshness unverified: a full canonical snapshot
  committed October 23, an October 29 matching active companion, a partial
  October 31 fixture/manifest, and grounded but dated provider spellings.
  All 1,517 snapshot identities have unknown lifecycle. The JSON's 1,506
  default-eligible entries exclude eight provider/position issues and three
  pending duplicate-key claims. Existing canonical records remain searchable
  despite optional mapping conflicts. No historical completeness or factual
  retirement claim is made.
- The migration source says NOT APPLIED while a later JEG-1391 log records
  merged-away keys. Verified alias notes identify 4653/2785, 4655/437 and
  4660/4363 as duplicate pairs. Current registry confirmation/identity-owner
  attestation is still required; no active key redirect or DB operation was
  inferred from that discrepancy. Real lifecycle input remains absent.
- The new source-only identity rows deliberately avoid the existing
  universe_only UI path, which displays 0.0. The existing readout is unchanged;
  UI presentation of the additional unknown-price rows needs separate work.
- The additive preflight API is implemented and tested. Existing #1296
  waiver/override callers are not rewired here; their owner must consume it
  or the equivalent qualified boundary, including override ownership checks.
- The asset is checked in and reproducible using the explicit builder
  command. Automatic refresh and shared CI registration are not added under
  this freeze. Regenerate after source-owner changes; qualify source freshness,
  canonical redirects and a reviewed lifecycle input before release.
- Full validation retains the prior loopback-bind blocker. No local browser,
  runtime/live coverage, CI or completion claim is made.
- These are author-run pure tests. The new integration head needs independent
  review; the earlier 4,810 + 181 adapter qualification does not qualify this
  newly changed consumer boundary. Nothing was pushed or published.
