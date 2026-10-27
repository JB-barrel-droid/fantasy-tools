## 2026-10-26 - JEG-1135 compact methodology badge on the league row

Contract: the "Overrides active: ..." indicator in the league row made the row
wrap at 1366x768 (Copy/Paste dropped to a second line). Jeremy (2026-10-26
9:30 PM CT, on JEG-1135) decided: show a compact methodology badge on the league
row; do not move or restyle #v2AssistActions or the league actions. This entry
covers that follow-up on branch `banana/jeg-1135-render-sweep` (part of PR 976).

Done by an OpenRouter deepseek-v4.1-flash run (T2/T3). Untrusted until a Claude
T1 review.

### Change
- `app/v2/overrides.js` `syncBar()`: the badge (#v2OverrideBadge, still a link to
  `v2/#value-overrides`, still `role=status` / `aria-live=polite`) now renders a
  short visible form "Overrides on" (a `.v2-ov-badge-short` span, `aria-hidden`)
  plus the full `activeText()` in a `.v2-sr` (clip, not display:none) span. The
  full text is also the badge's `title`. The reset button `#v2OvResetAll` stays
  present and clickable; its visible label is now "Reset" (aria-label unchanged).
- No change to `app/v2/overrides.css`, `app/v2/v2.css`, #v2AssistActions or the
  league actions. No value math touched.

### Verified (check named)
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_overrides_basis_render`
  → Ran 18 tests, OK (18/18), once at the end. The previously-red
  `test_compare_layout_is_unchanged_at_1366x768_with_the_indicator_showing` now
  passes: league height and #v2Compare top are equal with and without the
  indicator.
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_customize_cleanup_render`
  → Ran 12, FAILED (failures=1). The one failure is PRE-EXISTING and not this
  change: `test_d3_charts_only_survives_a_blend_edit` times out clicking
  `#v2Popover [data-series='ddf_value_charts']` because the built popover has no
  such series (it lists `ddf_value`; probe `/tmp/probe_d3b.py`:
  `['ddf_value', 'ddf_value_projections', 'usatoday', ...]`). Confirmed
  unchanged by this work: the same single test fails identically with
  `app/v2/overrides.js` stashed back to HEAD (`git stash push -- app/v2/overrides.js`,
  rerun, same `TimeoutError`). The D4 check that clicks #v2OvResetAll passes (it
  is in the 11 that pass), so the shortened "Reset" label did not break it.
  Left red on purpose: out of scope (a v2.js/popover series-name mismatch), not
  a value-math or badge issue.
- Probe `/tmp/probe_badge.py` (throwaway, uses the test module's `Session` over
  the built `dist/`, sets `setBasis({mode:'single', source:'fantasycalc'})` and
  re-measures). League-row height and page scrollWidth with / without the
  indicator, per viewport:
  - 1366x768 — without: row 56, #v2League 57, #v2Compare top 215,
    scrollWidth 1367 / clientWidth 1366. With (before fix, full text): row 124,
    Copy/Paste wrapped to a second line, #v2Compare top 283. With (after fix):
    row 56, #v2League 57, #v2Compare top 215 — identical to without; the bar is
    176px wide and the roster line wraps inside its own box (h 35 < the 44px
    actions), so the row does not wrap and Copy/Paste stays on line 1.
  - 1024x768 — without: row 124 (the row already wraps here without the
    indicator: Copy/Paste is on a second line). With (after fix): row 124,
    #v2Compare top 283 — identical. Per the ticket this wrap is acceptable
    because it is present without the indicator too.
  - 320 wide — without: row 254, scrollWidth 353 / clientWidth 320. With (after
    fix): row 304 (the bar wraps, expected on a phone), scrollWidth 353 —
    unchanged, so the bar causes no sideways scroll.
- `page.inner_text("#v2OvBar")` still contains "Overrides active: FantasyCalc
  only" and "1 player override" (the `.v2-sr` clip text is included by
  innerText); the existing rubric assertions were not edited.

### Claimed, not confirmed
- Screen readers announce the full text: the badge's accessible name is the
  `.v2-sr` text and the full text is the `title`. Not confirmed on a real screen
  reader.
- at 1366 the roster line wraps to two lines when the badge is shown (its own
  box, row height unchanged). The 2-line/3-line cliff is ~8px at the current
  fixture (roster 153px vs the ~144px needed for 2 lines); a longer league-name
  or roster string could push it to three lines and grow the row. Not covered by
  a test.

### Open questions
- None for the decided scope. The visible reset label was shortened from
  "Reset all" to "Reset" (needed to reach the 1366 single-line row); the
  aria-label is unchanged. Flagging in case Jeremy prefers "Reset all" kept.
