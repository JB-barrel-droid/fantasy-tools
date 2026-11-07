## 2026-11-04 - Provider-only GSIS ambiguity correction / JEG-1505

Contract: address the independent review's P2 finding against
`7d8710b193d81a642fbe4a5786412c11eb60bfbf`, preserving that commit and all
local-only restrictions. No consumer, shared universe, production policy,
identity snapshot, pricing or methodology changes.

### Verified (check named)

- Acknowledged the review finding: two canonical keys with different Sleeper
  IDs incorrectly remained selectable when their provider records shared one
  GSIS ID and neither canonical row supplied GSIS.
- Added
  `test_provider_only_shared_gsis_preserves_both_identities_but_rejects_selection`.
  Running that test against the old adapter failed: eligible keys were
  `[1, 2]`, expected `[]`. No existing assertion was weakened.
- Added a two-line guard against the matched provider record's GSIS appearing
  on multiple Sleeper IDs. Both identities remain present, receive mapping
  issues, omit unsafe provider IDs and are excluded from default selection.
- `python3.12 -m unittest -v tests.test_searchable_identity_eligibility`:
  all 19 tests passed, including the new regression.
- `python3.12 -m pipelines.baseline_reds --context local -- python3.12 -m
  unittest tests.test_searchable_identity_eligibility tests.test_nfl_universe
  tests.test_sync_players_active tests.test_universe_chart_only
  tests.test_bake_espn_zero_universe`: all 69 tests passed. Logs are in sibling
  `../jeg-1505-gsis-focused-tests.log` and `../jeg-1505-gsis-targeted-tests.log`.
- Pure fixture comparison loaded the original adapter from commit 7d8710b
  and compared its complete result with the corrected adapter: identical
  output for all 1,161 identities / 1,155 eligible keys. Aiyuk remains once
  and selectable at key 568 / Sleeper 6803. All fixture inputs and numeric
  fields remained unchanged; pricing membership was left unknown because
  no computed priced key set was supplied.
- Ten protected files, including shared universe code/tests, active sync,
  bake, aliases, identity snapshots, players fixture and both frontend data/
  engine consumers, remain byte-identical to 7d8710b. Full evidence and source
  hashes are in sibling `../jeg-1505-gsis-invariance.json`.
- The same six real position disagreements remain documented and unchanged:
  955 Tanner Conner WR/TE; 1011 Velus Jones Jr. RB/WR; 2127 Mitch Van Vooren
  TE/WR; 3472 Hakeem Butler WR/TE; 3677 Garrett Greene WR/QB; 3837 Justin
  Shorter TE/WR (baked canonical position / Sleeper position). No correction
  to these source records was attempted.

### Claimed, not confirmed

- This is an unwired adapter correction; it does not change live coverage.
- Full `make validate` retains the prior loopback-bind sandbox blocker. No
  retry, alternate browser validation route, permission expansion, publishing
  or production operation was attempted. New evidence is limited to the
  pure regression, targeted tests and fixture comparison above.
- The corrected head still requires independent delta review; this session's
  checks do not constitute that review or successful CI/full validation.
