## 2026-10-07 - GAP-MAIN-STATIC-PIN: red main after automated rebuild 0b0ddee

### What broke
`python3 -m unittest tests.test_static_export` failed with `25.5 != 25.3`. The
pin was `("fantasycalc_adjusted", "full_12_qb1")`, Josh Allen. Automated rebuild
0b0ddee (run 37641559947) promoted FantasyCalc Week 5 and refit the adjustment
cells. preview.yml and pages.yml both gate on `make validate`, so every PR check
and Pages deploy was blocked.

### Verified (check named)
- 25.3 is the value the pipeline builds. I recomputed it in a standalone script
  that does not import the builder.
  - Allen's raw fantasycalc full_12_qb1 value is 25.0, because he is the top QB
    and takes the QB max.
  - Allen is a QB starter. The fantasycalc QB/starter cell gives
    1.5494364535 + 0.9790246071 x 25.0 = 26.025, which rounds to 26.0.
  - The 33 priced QBs (12 starter, 12 bench, 9 no cell) sum to 153.8. The QB pie
    target is 149.1, so the factor is 0.969441 and Allen becomes 25.205, which
    rounds to 25.2.
  - The rounding residual is +0.3. It is handed out in 0.1 steps from the
    largest value down, so Allen gets +0.1 and ends at 25.3.
  - All 33 QB values match the fixture exactly.
- Rerunning `pipelines/build_adjusted_fixture_sections.py` on a copy of the
  fixture reproduces the committed combo byte for byte.
- The other pins were checked against the new fixture and all still hold:
  - Raw usatoday, fantasycalc, fantasypros and cbs are all 25.0.
  - espn is 26.7 and cbsros is 20.8.
  - usatoday_adjusted is 24.6 and fantasypros_adjusted is 21.1.
- The new recompute guard (`adjusted_recompute_problems`) re-derives all 12
  _adjusted combos, and all 12 match.
  - It gives [] on the fixture and cells from before 0b0ddee, and [] on the
    fixture and cells from after it.
  - It flags 154 diffs when the old fixture is paired with the new cells.
  - It flags a +0.1 hand edit to Allen.
  - It flags the real builder run with the pie rescale disabled, and the real
    builder run with the starter and bench cells swapped.
- rebuild-chain.yml now runs `make validate` inside the chain step, after
  `rebuild_comparison_chain.py`. A red validate fails the step, so the existing
  failure path publishes the status only and never the fixture.
  `pipelines/record_post_rebuild_validation.py` marks the status
  `success: false`, adds `failed: [post_rebuild_validation]`, and records the
  failing test and assertion.
  - `tests/test_rebuild_chain_workflow.py` runs the real chain step with a stub
    validate that replays today's failure.
  - In that run only the status files reach the remote, the status names
    `('fantasycalc_adjusted', 'full_12_qb1')`, and the job fails.
  - Three mutations are caught: removing the validate block, dropping
    `exit 1`, and dropping the recorder.
- `make validate` passes on the branch. The sync stamp files were reverted.

### Test changes and why
The three hand pins on the _adjusted values were removed from
`test_known_full_ppr_12_team_source_values`. Their history and the 25.3
verification are kept in the comment.

This is not adjusting a test to go green. The pins were wrong as a design,
because every legitimate refit moves them. The recompute that replaces them is
stricter: it covers every player in every _adjusted combo, not just Allen in
three of them.

### Claimed, not confirmed
- I have not seen `make validate` run inside the chain on a real GitHub runner.
  It takes about 1 minute locally. Pages runs the same target on ubuntu-latest
  with only stdlib Python.
- I did not check whether the stage-7 fit itself is right. The recompute checks
  stage 8 (cells plus pie onto the fixture), not the cell fit.
