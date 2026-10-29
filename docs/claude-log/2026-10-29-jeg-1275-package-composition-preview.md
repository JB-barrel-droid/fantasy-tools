## 2026-10-29 - JEG-1275 selected-package composition preview (part of JEG-1183)

Contract: an isolated component that shows an already chosen package of trades, its counts, the injected JEG-1262 roster
check's answer and a separately supplied final lineup, with no optimizer, ranking or lineup calculation. Spec:
`docs/design/package-composition-preview-contract.md`.

### Verified (check named)
- View model contract on 11 synthetic cases (valid with and without a lineup, duplicate team, duplicate player, unknown
  ids, roster check missing / throwing / unreadable, empty selection, incomplete lineup, long names with four
  counterparties): `python3 -m unittest -v tests.test_package_composition_preview_contract`, 4 tests OK.
- Each of six mutants (errors sorted, first error only, helper rosters shown as the lineup, unavailable shown as passed,
  trades sorted, invalid trades dropped) is caught: `test_checks_fail_on_broken_builds`.
- Deep-frozen inputs unchanged and adapters called with the same objects: the contract checks' call log and JSON
  comparison.
- The recorded roster-check answers in `cases.json` came from running the JEG-1262 helper at PR 1116 head acf2e43 on the
  fixture league.
- DOM smoke under jsdom (scratch script, not committed): every case renders, the first disclosure toggles hidden and
  aria-expanded, no script errors.

### Claimed, not confirmed
- Layout at 1280 / 390 / 320, keyboard Enter/Space disclosure and no storage writes in a real browser:
  `tests/test_package_composition_preview_render.py` is written but was not run here (no Chromium in this cloud session;
  it skipped). It needs one run where Chromium exists, and wiring by the CI coordinator.
- Runtime integration: not done and not claimed. It waits on the reviewed JEG-1262 helper and a real lineup adapter.
