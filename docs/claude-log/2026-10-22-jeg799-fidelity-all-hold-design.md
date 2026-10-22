## 2026-10-22 - JEG-799: design for the all-held week boundary (GAP-FIDELITY-ALL-HOLD)

Contract: docs-only design PR, `docs/design/fidelity-all-hold.md`. No pipeline
or workflow edits (another session is clearing the Week 7 chain on main).

### Changed
- `docs/design/fidelity-all-hold.md` (new): what the all-held state does to the
  page and the tests, whether holding on lag is right, options A/B/C with
  reader-visible number, wrong-number risk, size, files and proving test;
  recommendation B2 (a hold applies to the build it measured) then C2
  (measure the candidate inside the chain); decision for Jeremy as MC.
- `docs/risk-register.md`: GAP-FIDELITY-ALL-HOLD next action points at the design.
- `docs/README.md`: index row.

### Verified (check named)
- Chain run 39706506402 log (`gh run view --log`): import stamped fantasycalc
  Week 7, cbs Week 7, fantasypros 2026-10-20, usatoday 2026-10-13, espn/cbsros/
  razzball 2026-10-19; the chain promoted all 7 sources; the fidelity hold step
  then held usatoday, fantasycalc, fantasypros, cbs, espn, razzball; validate
  failed at `test_launch_front_door.py:291` with `2 not greater than or equal
  to 3 : {'compared': 50, 'skipped': 0, 'cells': 100, 'columns': 2}`.
- The pulse the run consumed is commit 70afae04 (`checked_at` 00:54:20Z,
  measured on the live Week 6 page): five red holds, fantasypros amber.
- Local reproduction on origin/main 041c87af in this worktree: the 70afae04
  holds applied to the committed fixture with `fidelity_hold.apply_fidelity_holds`,
  `make sync`, then `python -m unittest tests.test_launch_front_door.FrontDoorRenderedTests.test_v2_table_equals_engine_and_guard_fails_on_drift`:
  run's holds -> FAIL `2 not greater than or equal to 3`; same six holds all
  amber -> OK; no holds -> OK. Playwright probe of the held build:
  `plotKeys ['ddf_value', 'fantasypros']`, `vorpKeys []`, header "7 sources
  not updating". Fixture and build outputs restored afterwards (`git status`
  clean apart from the docs).
- Pulse run durations from `gh run list` (2026-10-22): 15.3, 23.3, 23.3 min.
- `make validate` on the branch: rc 0 (74 suites OK). PR #749 checks: preview
  pass (15m48s), v2-render pass (4m14s). Squash-merged as `acd636df`.
- Linear JEG-799: decision question posted (Q1 mechanism, Q2 lag), `needs-review`, In Review.

### Claimed / not confirmed
- The B2 identity comparison (chart `source_provenance.snapshot_fetched_at`
  against the pulse's stored bake `saved_at`, or a `bake_id` written by the
  import) is specified, not implemented or tested.
- C2's cost (15+ min and publisher fetches per chain run) is read from the
  pulse's own runs, not measured inside the chain.
- The deadlock description (pulse `holds_changed` false -> no re-dispatch) is
  from `fidelity-pulse.yml:145-154` and the repeated "chain failed" status
  commits on main, not from a traced loop of runs.
