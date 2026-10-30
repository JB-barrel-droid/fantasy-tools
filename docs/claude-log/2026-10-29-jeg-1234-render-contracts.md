## 2026-10-29 - JEG-1234 source-framework and disclosure render contracts

Contract: repair the three render tests that went red after JEG-1212 and JEG-1213 merged, by correcting test drift
against the approved behavior, with no weakened assertion and new mutation guards. Tests only; no runtime change.

Base main `5ec64d24`. Local Chromium 131 via `CHROMIUM_PATH`, `RENDER_TESTS_REQUIRED=1`.

### Failing before (main `5ec64d24`, check named)
- `tests.test_v2_customize_cleanup_render` test_d1_done_matches_the_dialog FAIL: after Published charts "Select none"
  the dialog said "2 series selected" and Done applied `ddf_value, fantasycalc`. FantasyCalc is in the separate
  Observed-trade estimates group since JEG-1212 (f88a96e), so the scenario no longer built an empty draft. The dialog
  counter and Done agreed with each other: test drift, not a reset regression.
- `tests.test_v2_names_render` test_names FAIL: the popovers and deal read show the JEG-1212 Trade chart average
  definition; the test still expected "What the market will pay: the rescaled trade charts, averaged."
- `tests.test_v2_modules_render` test_every_card_expands_collapses_and_is_remembered ERROR: Page.click timeout. The
  control locator climbed to `ancestor::section`; the league editor card is a `<details>` since JEG-1213 (fd2b79a).

### Changes
- Customize D1: clears every source group that has a ticked source with its own Select none, and requires each press
  to clear exactly its group, the draft to be DDF Value alone, and the counter to match, before Done must block. New
  guard test_d1_guard_catches_a_partial_clear: Select none that keeps FantasyCalc, and one that clears every group at
  once, must each fail.
- Names: the Trade chart average definition follows the merged JEG-1212 wording. Two new mutations (the old wording
  put back; FantasyCalc dropped from the eligible inputs) must fail.
- Modules: the control locator finds the heading's nearest `.v2-card` (section or details, whole class token), scoped
  to the card's own `.v2-mod-ctl`. The league editor also gets check_disclosure: Enter on its summary closes it (body
  hidden, title shown, focus kept), a click opens it again. Visibility uses checkVisibility(), since a closed details
  keeps offsetParent. New guard test_guard_fails_on_broken_league_disclosure on Find in league: collapse hides nothing,
  expand does nothing, summary turned into a div, summary toggle cancelled; each must fail.

### Verified (check named)
- `tests.test_v2_names_render`: 2 tests OK.
- `tests.test_v2_customize_cleanup_render`: 13 tests OK (D1 three re-run after the final message edits: OK).
- `tests.test_v2_modules_render`: 3 tests OK, 1440x900 and 390x844 (both viewports for the positive run).
- Each new mutation fails for its named reason, not a broken page (direct run of each check with each patch, errors
  printed): e.g. "Select none on observed left ['fantasycalc'] ticked"; "Select none on pub also changed other groups
  {'observed': ...}"; "v2LgTitle: collapsed but the body is still shown"; "not a disclosure with its title in the
  summary"; "Enter on the summary did not close it"; the names popovers show the reverted or FantasyCalc-less text.
- Screenshot of the closed league editor: only the summary row is shown.

### Claimed, not confirmed
- CI on the PR head; not run here beyond these three files. No broad sweep launched.

### Observed, not changed (runtime owner: JEG-1213)
- While the league editor `<details>` is closed, its module chevron and expand controls are not rendered (they are
  not inside the summary). With the editor open (an empty league, the fixture) both work. Not a test-contract change;
  flagged for the JEG-1213 owner.
