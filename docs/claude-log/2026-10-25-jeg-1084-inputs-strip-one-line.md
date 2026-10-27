## 2026-10-25 - JEG-1084 inputs status strip as one slim line

Contract: shrink the inputs status strip (#915, JEG-1076) from 45 px to one compact line (about 28 px) on every tab, keeping its text, Edit league and Dismiss, so Compare's give/receive/verdict boxes are above the 1366x768 fold again (Jeremy, 2026-10-25, multiple choice: "Shrink the strip to one compact line (Recommended)"). PR #918 (JEG-1056) holds until this merges.

### Verified (check named)
- Strip height at 1366 wide on the built page: 45 px on origin/main, 27 px on this branch
  (`tests.test_v2_inputs_status_render.InputsStatusRender.test_strip_is_one_slim_line_on_desktop_and_phone_safe`, which
  asserts <= 32 px, the note text not cut, both buttons on that line, and at 390: no sideways overflow and both buttons
  >= 44 px). The same test run on origin/main fails with `45 not less than or equal to 32`.
- Compare fold, `tests.test_v2_waterfall_render.WaterfallRenderTest.test_waterfall_verdict_layout_example` from PR #918
  (branch be/JEG-1056), run in a scratch worktree with a temporary merge, #918 not committed here. Bottom of the give,
  receive and verdict boxes at 1366x768, with the strip showing:
  - Inter (Chromium headless shell, Playwright 1.64.1): origin/main + #918 775.5 (test fails), this branch + #918 757.5 (passes).
  - CI font setup (Python Playwright 1.49.1 in a scratch venv, FONTCONFIG_FILE rejecting Inter, JetBrains Mono, Carlito
    and Caladea so `fc-match sans-serif` is DejaVu Sans): origin/main + #918 822.9 (fails), this branch + #918 756.9 (passes).
- Bottom of the boxes at 1440x900 in the CI font was 911.2 on origin/main + #918 (fails, 900 high) and 845.2 here.
- `make validate` and `RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_v2_contract_render tests.test_v2_inputs_status_render`: see the PR body for exit codes.

### Found while doing it
- The 45 px strip was not the only cause in the CI font. Since #917 the league row holds the Copy / Paste buttons, and in
  DejaVu Sans the row broke into two lines (an extra 68 px), which alone left the boxes at 804.9 even with a 27 px
  strip. Fix in `app/v2/v2.css`: on >= 768 px the roster line (`.v2-league-inner > .v2-meta`) has `flex: 1 1 120px; min-width: 0`
  so the row breaks only when the buttons cannot fit, and the roster line wraps inside its own cell.

### After merging current main (693c0ca4, then fb6c5e54): the league row decision
- With the strip at 27 px and the league row one line, `test_waterfall_verdict_layout_example` (scratch merge of #918) was
  Inter 757.5 (passes) but CI fonts 773.7, 5.7 px past the fold (one more wrapped verdict line in DejaVu Sans; data
  rebuild 693c0ca4). Jeremy, 2026-10-25, multiple choice: "Trim the league row height": let the league row shrink to
  its content, nothing else (verdict column width untouched).
- Done in `app/v2/v2.css`: from 768 px `.v2-league-inner { min-height: 0; padding-block: 6px; }` (44 px buttons + 6 + 6; the
  row is 57 px with its border instead of 65). Phones keep their own rule (padding 10px 16px).
- Fold, bottom of give/receive/verdict at 1366x768 (scratch merge of #918, #918 not committed here): Inter 749.5, CI fonts
  (Playwright 1.49.1, DejaVu Sans) 765.7, both <= 768 and `test_waterfall_verdict_layout_example` passes in both. The CI
  margin is only 2.3 px: a further wrapped line would fail it again.
- Same runs at 1440x900 (the guard checks both viewports), bottom of give/receive/verdict: Inter 826.6, CI fonts 854.0
  (both under 900; main + #918 with the 45 px strip was 835.8 Inter, 911.2 CI). Re-measured after merging main
  eeafdd5f: unchanged.
- Other checks on the head: `make validate` exit 0. `tests.test_v2_league_phone_render.test_phone_contrast_keyboard` fails
  with "[320px] sideways scroll by 10px" and `tests.test_v2_assist_render.test_copy_paste_round_trip_links_and_footer`
  fails ("name-only find-trade link"), and BOTH fail the same way on a clean origin/main worktree (b0fc1282 for assist,
  693c0ca4 for phone), so neither comes from this change; not fixed here. The assist test passed once in the scratch
  worktree and failed on three other runs, so it is unstable on current data.
- League row looked at (screenshots, CI font and Inter) at 390, 768, 1024 and 1366: Edit league, Position weights, Copy and
  Paste all shown, at least 44 px tall, no sideways overflow. At 768 and 1024 the buttons wrap to two rows with the
  existing 24 px row gap (unchanged).
- With #918 merged in the same scratch run, the guard mutation "verdict not DDF" is NOT CAUGHT: since JEG-1073
  `ddf_value_charts` has the same numbers and name as `ddf_value`, so the fixture's "other series" is invisible. That
  fixture fix belongs in #918 (its test file), not here (Jeremy 2026-10-25).

### Claimed, not confirmed
- No wording was changed. At 1366 the full default note fits on one line in Inter and DejaVu Sans (the test asserts the
  text is not cut). On narrower desktop widths (768 to about 1100) the note text ends in an ellipsis with the full text in
  its title; not looked at by eye across those widths.
- The phone layout (wrapping note, 44 px buttons) was checked at 390 by the test only, not by eye.
- Light and dark colours of the strip were not changed and were not re-checked.
