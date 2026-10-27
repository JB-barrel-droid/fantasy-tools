## 2026-10-26 - JEG-1134 phone league bar collapses to a summary line

Contract: on a phone, collapse the league settings bar (scoring, roster, Edit league, Position weights, source
legend, Customize) into one tappable summary line that opens the existing controls, so the first tab content
reaches the first viewport. Jeremy chose option A on 2026-10-26 and approved the build.

Done by an OpenRouter `deepseek/deepseek-v4.1-flash` run (T2/T3). Untrusted until a Claude T1 review re-reads
the diff and runs the gate.

### Verified (check named)

- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_phone_league_bar_render` - 3 tests, OK.
  At 390x844 on `#player-values`: the summary is a `<button>`, 44 px tall, `aria-expanded="false"` on load; both
  controlled blocks (`#v2LeagueBody`, `#v2Methods`) and Edit league / Customize / the legend are hidden; after a
  tap (and after focus + Enter on a separate page) they are visible and `aria-expanded="true"`; the first tab
  content's top is 278 px, above the fold. At 1440x900 the summary is not rendered and both blocks stay visible.
- Discriminating test `test_guard_fails_without_collapse` serves v2.css with the collapse rule removed and
  requires the "hidden before the summary is tapped" errors; it passes.
- Fails without the change: with `git stash push -- app/v2` (source reverted, test kept), the same test errors -
  `Page.click: Timeout ... waiting for locator("#v2LeagueSummary")` and the guard anchor is missing. Restored with
  `git stash pop`, re-ran `pipelines/sync_dashboard_artifacts.py`.
- px gain, measured by `test_report_px_gain`: first tab content top **646 px before this change -> 278 px after**
  at 390x844 (368 px gained); against the same page with the drawer open it is 690 px -> 278 px (412 px, the extra
  44 px being the new summary button). Before the change `#v2League` was 189 px and `#v2Methods` 224 px at 390 px.
- The summary follows a setting change: with the drawer open, Edit league -> Scoring "Standard" -> Done changes the
  summary from `Full PPR · 12 teams · 5 sources` to `Standard · 12 teams · 5 sources` (asserted in the test).
- `RENDER_TESTS_REQUIRED=1 python -m unittest` on `test_v2_phone_header_render`, `test_v2_phone_layout_render`,
  `test_v2_phone_customize_targets_render`, `test_v2_phone_weight_render`: all OK (7 tests). The customize-targets
  test clicks `#v2EditSources` through a JS `element.click()`, so it still passes with the row collapsed on phones.
- `test_v2_mobile_phase1_render` reports failures at 390x844, first being
  `A.v2-link 115x16 "Connect the to"` - that link is `#v2AssistLine` in the page footer, outside both blocks this
  change touches. The probe skips `display:none` elements (`el.checkVisibility()`), so hiding the league blocks can
  only remove elements from the sweep, never add one; the only element this change adds is the 44 px summary button,
  which is not in the list. Not caused by this change.

### Claimed, not confirmed

- `test_v2_phone_tap_targets_render` is already red on clean main: `git stash`-verified to be pre-existing in this
  worktree before any edit here - 3 errors, all `Locator.click: Timeout ... #v2EditSources` at 375x812 (line 179)
  and 812x375 (line 193). At 375x812 the click times out with "element is not visible"; a standalone probe of the
  same URL and viewport finds the button visible, so the cause looks state- or timing-dependent, not structural.
  Left alone (another worker owns the render-test CI fixes).
- `test_v2_mobile_phase1_render` pre-existing status was reasoned from the footer link above, not confirmed with a
  stash run of that file (about 7 minutes); a T1 review should confirm it if it matters.
- Desktop / tablet "byte-for-byte unchanged" is asserted for the measured geometry (content top at 1440x900 is
  223 px with and without the change) and by the CSS scoping to `max-width: 767px`; no other desktop render test in
  the list above was run beyond the one 1440x900 check in the new test.

### Notes for the reviewer

- The collapse covers both `#v2League` (scoring, roster, Edit league, Position weights, and the assist panel) and
  `#v2Methods` (the "On the chart" line, the source legend, Customize). The plan says the source legend and
  Customize move into the drawer; the showing line goes with them because it lives in the same row.
- "N sources" counts the outside series the legend lists, not DDF Value (see the T1 review below).
- The disclosure uses `body:not(:has(#v2LeagueSummary[aria-expanded="true"]))`, inside `max-width: 767px`. If
  `:has()` is unsupported the blocks stay open, i.e. it degrades to today's behaviour.

### T1 review and Jeremy's decisions (Claude Opus, Ba-Nana merge run, 2026-10-26)

Jeremy, 2026-10-26 7:55 PM CT: (1) the "On the chart: ..." line may hide while the phone bar is collapsed - kept;
(2) the summary's source count counts only outside sources, not DDF Value itself, e.g. "Full PPR · 12 teams ·
4 sources" when 4 outside charts plus DDF Value are shown.

Verified (check named):
- `v2.js` counts `shownKeys` minus `isDdfKey` keys. `test_v2_phone_league_bar_render` now requires the third part
  to equal legend items minus DDF Value items (and that DDF Value is in the legend). With the old count restored
  it fails: `the source count '5 sources' is not the outside-source count '4 sources' (5 in the legend, 1 of them
  DDF Value)`. With the fix, `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_phone_league_bar_render
  tests.test_v2_contract_render` - 9 tests OK after merging origin/main.
