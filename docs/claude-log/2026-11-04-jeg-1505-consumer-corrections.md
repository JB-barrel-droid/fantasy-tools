## 2026-11-04 - Own-roster pricing and override lookup corrections / JEG-1505

Contract: address both independent P2 findings against
`8db289b3a4cd2e57e4551fd7735029277765e846` in the sole local branch/workspace.
Parent authorized the owned preflight and narrow override-consumer correction.
Publication waits for clean independent delta review and release-lead admission.
No source value math, methodology, registry/snapshot or #1296 caller edits.

### Verified (check named)

- Added actual-function regressions before fixing code. Running
  `python3.12 -B -m unittest -v
  tests.test_jeg1505_integrated_search.IntegratedSearchTest.test_own_roster_unpriced_identity_blocks_priced_candidate
  tests.test_jeg1505_integrated_search.IntegratedSearchTest.test_override_select_opens_retained_identity_by_canonical_key`
  failed as expected: two Aiyuk namespace cases wrongly returned ready=true,
  and the actual override select/rowOf path returned editorRow=null.
  Log: `../jeg-1505-review-regressions-before.log`.
- Preflight now tracks resolved own-roster keys separately. An own-roster
  key absent from the actual computed universe is listed in new output field
  `unresolvedOwnKeys` and adds pending reason
  `Own-roster identity has no computed pricing`, with
  `boundary: "own_roster_pricing"`. It prevents wire submission without
  fabricating a roster value. Known unpriced other-team players remain
  ownership exclusions and do not create a global pricing block.
- Input API is unchanged:
  `prepareSearchSelection({inputs, overrideAdds, ownership:{complete,mine,others}})`.
  Existing outputs remain; `unresolvedOwnKeys: number[]` is additive.
  `ownershipReady` describes resolved ownership identities; own pricing can
  be pending while that flag is true. Only `readyForPricing` and `wireKeys`
  gate submission. A priced candidate may remain in diagnostic `pricedKeys`
  while wireKeys is empty. Namespace resolution semantics are unchanged.
- Override `rowOf` now tries the existing canonical `engine.getPlayer(key)`
  after computed rows, verifies the returned key, then retains the name-search
  compatibility fallback. Actual select caches its supplied display name.
  No value/basis setter or calculation was changed.
- Newly retained search_identity_only override hits are explicitly labeled
  `Pending pricing`, disabled, and their actual click handler cannot invoke
  editing. This avoids implying that unpriced retained rows can already be
  overridden through every tab. Internal canonical lookup works; ordinary
  priced hits remain enabled and retain their exact computed row.
- `python3.12 -B -m unittest -v tests.test_jeg1505_integrated_search`:
  18 passed, including six new cases/controls. These evaluate real widget
  functions and real override renderSearch/select/rowOf functions, with small
  DOM/render stubs and the actual ValueModel worked-example computed rows.
  Log: `../jeg-1505-review-corrections-focused.log`.
- `python3.12 -B -m pipelines.baseline_reds --context local -- python3.12 -B
  -m unittest tests.test_searchable_identity_eligibility
  tests.test_jeg1505_search_only_consumer_contract
  tests.test_jeg1505_integrated_search tests.test_nfl_universe
  tests.test_sync_players_active tests.test_universe_chart_only
  tests.test_bake_espn_zero_universe tests.test_product_data_wiring
  tests.test_source_combo_contract
  tests.test_value_pipeline_engine.WorkedExampleTest`: all 110 passed.
  Log: `../jeg-1505-review-corrections-combined.log`.
- Syntax checks on widget/overrides and git diff --check passed. Fifteen
  protected files and ten pricing/preload/editor math function blocks match
  the reviewed base. The actual 30-key worked-example pipeline and numeric
  rows remain identical. Evidence: `../jeg-1505-consumer-corrections-evidence.json`.

### Claimed, not confirmed

- These are author-run pure function tests, not full DOM/browser qualification
  or independent delta approval. No full-validation retry or bind was made.
- Main readout still filters universe_only; new retained rows are not claimed
  delivered there. The #1296 caller still requires owner-led integration.
  Newly retained override hits are pending/disabled, not a completed override
  application feature. Numeric override semantics remain untouched.
- Source freshness, three canonical redirect attestations, lifecycle evidence,
  automated refresh and CI registration remain separate dependencies.
- Nothing was pushed, published, merged or deployed in this correction.
