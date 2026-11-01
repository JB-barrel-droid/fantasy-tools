## 2026-10-30 CT - Finder assessment fixture / JEG-1352

Contract: replace the drifting positive render scenario with labelled deterministic inputs and a proven Natural 1a
candidate, preserving the real engine, rules, four viewports and negative mutations. No fit, value or default changes.

### Verified (check named)

- On main `168aba93f1cf56acdd20e104cac0058194718faf`, `python3 -m unittest
  tests.test_v2_finder_eval_render.FinderAssessmentRenderTest.test_assessment_and_headline` (with `CHROMIUM_PATH` set
  to the installed Mac Chrome) fails at every viewport. The ESPN/Yahoo positive case has no groups. A browser
  diagnostic reports Yahoo has one RB for two starting slots after shared players are removed. Finder code is unchanged.
- Frozen raw 2026 Week 8 inputs replace the moving player island and comparison asset. The roster pairing is modeled;
  it is not an actual league or 2027 data. Only the 12-team source combos are retained; prior-week history is unavailable.
  The full raw player universe is retained because it affects engine allocation and values. Current code/configuration
  still computes every value, lineup, bench weight, trade and fit.
- The named witness gives C.J. Stroud, Rico Dowdle and Marvin Harrison Jr. for Kyler Murray, Aaron Jones and Harold
  Fannin Jr. `PRECONDITION` requires it to pass search and both teams' Natural 1a tests, plus a Natural best package
  among the real groups. Pasted rosters must match the fixture exactly before K/DEF are added through search.
- The first full module run passed the all-viewport assessment and Standard/Half PPR checks, but failed on two stale
  existing mutation anchors. Both were updated to current main. Stale anchors and exceptions no longer count as
  successful mutation detection. The Natural mutation now specifically requires the wrong-headline diagnostic.

- Final check: `CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" python3 -m unittest
  tests.test_v2_finder_eval_render` passes (4 tests, 287.467 seconds). Both scenarios pass at 1366x768, 1440x900,
  390x844 and 320x640 in PPR; the Natural case also passes at desktop in Standard and Half PPR. All seven mutants
  are caught, and the Natural-headline mutant specifically produces the wrong-headline diagnostic.

- Draft PR: [#1241](https://github.com/JB-barrel-droid/fantasy-tools/pull/1241), branch `claude/JEG-1352`.
- The requested push shorthand was rejected as a non-fast-forward to inherited `origin/main` (no main update).
  `git config --get-regexp` confirmed `push.default=upstream` and the initial branch tracking main. The full refspec
  `git push -u origin refs/heads/claude/JEG-1352:refs/heads/claude/JEG-1352` successfully created the correct branch.
  No credential or global Git setting was changed.

### Claimed, not confirmed

- Independent Claude review and CI's full suites are pending. This job does not merge or deploy. F1 is not applicable
  because no product/runtime workflow changes.
