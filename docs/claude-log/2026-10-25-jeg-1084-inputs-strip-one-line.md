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

### Claimed, not confirmed
- No wording was changed. At 1366 the full default note fits on one line in Inter and DejaVu Sans (the test asserts the
  text is not cut). On narrower desktop widths (768 to about 1100) the note text ends in an ellipsis with the full text in
  its title; not looked at by eye across those widths.
- The phone layout (wrapping note, 44 px buttons) was checked at 390 by the test only, not by eye.
- Light and dark colours of the strip were not changed and were not re-checked.
