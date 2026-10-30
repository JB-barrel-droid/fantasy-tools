## 2026-10-29 - Wire two unrun test files into CI (JEG-1341)

Contract: `tests/test_roster_paste_mutation_proof.py` (#1134, JEG-1272/JEG-1291) and
`tests/test_lineup_presentation_properties.py` (#1133, JEG-1270) merged but no Makefile
run list named them, so CI never ran them. Makefile only: each goes into `test-core`
beside its sibling and into the matching shard (roster paste in shard 1 beside
`node tests/test_v2_roster_paste.js`, lineup properties in shard 4 beside
`tests.test_v2_finder_triview_display`). `test-core` was chosen over `test-unit-modules`
because `test-unit-modules` now runs only nightly (full-suite.yml, JEG-1169), so it would
not run on PRs. No app code or values changed.

### Verified (check named)
- `make -n test-core` names both modules; `make -n test-core-shard-1` names the
  roster-paste proof; `make -n test-core-shard-4` names the lineup properties.
- `python3 -m unittest tests.test_validate_shards`: 16 OK (shards together equal test-core).
- On this head: `python3 -m unittest tests.test_roster_paste_mutation_proof` 14 OK (about 1 s);
  `python3 -m unittest tests.test_lineup_presentation_properties` 4 OK (about 4 s).
- Broken locally, not committed: replacing `if (singleName && teamCode && posCode) {` with
  `if (singleName) {` in `app/v2/roster-paste.js` fails the proof (9 failures, including
  `test_baseline_passes_every_contract`). Applying the test's own `name-as-key` mutant to
  `app/v2/lineup-comparison.js` fails the properties (3 failures, `duplicate-names`).
  Both files restored with `git checkout`.

### Claimed, not confirmed
- Preview CI shard jobs run both modules on the PR head (see the PR's preview-shard 1 and 4 logs).

### Seen, not in scope
- `tests.test_render_sweep_coverage` is red on main before this change: five render modules
  (`test_interactive_trades_release_render`, `test_jeg1263_simplified_site_render`,
  `test_package_composition_preview_render`, `test_v2_compare_rosters_render`,
  `test_v2_finder_guardrails_render`) are in no run list. That test runs only in the nightly
  suite, so PR CI does not show it.
