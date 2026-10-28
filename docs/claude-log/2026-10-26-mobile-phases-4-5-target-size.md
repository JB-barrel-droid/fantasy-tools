## 2026-10-26 - Mobile phases 4 and 5, phone target sizes (JEG-955, JEG-956, JEG-903, JEG-927)

Contract: one PR for the mobile batch — collapse the multi-column rows on phones (JEG-955),
respect the device safe areas (JEG-956) and lift the sub-24 px tap targets from the 2026-10-22
a11y audit (JEG-903). JEG-927 (the mobile umbrella) closes with it. CSS only, plus three
Playwright render tests and the Makefile wiring for them. PR #963.

The branch was rebased onto `origin/main` at `1c31d09a` ("Health artifacts (CI, JEG-414)") after the
"Find a trade: two screens" work (`9cffc5cb`, JEG-1093) landed; `4c0ec29c` is this batch's own
commit on top of it. Both sides added CSS at the same place (line 1995 of the merge base), so
`app/v2/v2.css` conflicted; it was resolved by keeping main's JEG-1095/JEG-1099 blocks and putting
this batch's blocks after them (the pre-existing `overscroll-behavior` rules still close the file).
The one set of rules that had to change shape because of it: the horizontal safe-area insets sit on
`.v2-nav` itself, not on `.v2-nav-inner`, because main's nav rules now set the inner element's
padding at a higher specificity (`.v2-nav .v2-nav-inner { padding: 0 24px; }`).

### Verified (check named)

Every local check below ran on the rebased tree (re-run on the same commit by the finishing pass,
2026-10-26); the last bullet is the pull request's own CI.

- `python -m unittest tests.test_v2_phone_target_size_render` (2 tests, OK): every
  `#v2Legend .v2-legend-item` clears 24 px in height and the rank-brush fill clears 24 x 24 px,
  at 375 px and 1440 px; the `#v2TCards .val.has-math` spans that JEG-947 made 44 px on touch
  stay above the 24 px minimum. `test_guard_fails_on_old_css` serves the CSS with the fix removed
  and the check fails, so the test discriminates the fix from the old rule.
- `python -m unittest tests.test_v2_phone_safe_area_render` (2 tests, OK): with the four
  `--v2-safe-*` custom properties set to 47/44/34/44 px (the values a notched phone reports),
  the nav bar's content moves down 47 px, the nav and page content move right 44 px, the page
  bottom and the fixed toast move up 34 px, the player drawer's four sides each clear their
  inset, and the page does not scroll sideways. The same test runs at 1100 px and checks that the
  tablet's own gutters (24 px nav, 48 px page) are unchanged. The guard test fails on the CSS
  without the inset rules.
- `python -m unittest tests.test_v2_phone_layout_collapse_render` (2 tests, OK): the "Value range"
  popover's two number fields stack in one column on a 375 px phone, and a search that matches no
  player shows "No players match." with a "Clear search" button and hides the values table card
  (the JEG-827 empty-state item folded into JEG-955). The guard test fails on the old row
  direction.
- `python -m unittest tests.test_render_sweep_coverage tests.test_v2_phone_layout_render
  tests.test_v2_phone_landscape_render tests.test_v2_phone_trade_rows_render
  tests.test_v2_hamburger_nav_render tests.test_v2_phone_customize_targets_render
  tests.test_v2_phone_rank_overflow_render tests.test_v2_nav_render` (19 tests, OK): the phone and
  nav suites the new rules touch still pass, and the sweep-coverage test confirms the three new
  render modules are named in a Makefile run list (`test-unit-modules`, Makefile:425-427).
- `python -m unittest tests.test_v2_a11y_render tests.test_v2_a11y_batch1_render
  tests.test_v2_a11y_batch2_render` (6 tests: 5 OK, 1 failure): the other five checks pass, but
  `test_v2_a11y_batch1_render.A11yBatch1Test.test_guard_fails_on_broken_builds` fails its
  `mutation='nav ring reverted'` case -- and it is main's failure, not this batch's. The check
  appends a probe `<a>` to the first `.v2-nav .v2-tab`'s parent, focuses it and reads its ring
  contrast; the nav rework in `9cffc5cb` (JEG-1093) hides that parent
  (`.v2-nav .v2-tabs { display: none; }` above 768 px), so the probe is never rendered, never
  matches `:focus-visible`, and `FOCUS_RING` returns its 99 pass, which no CSS change can move.
  Probed at 1440 px with Chromium 131: `a75c9ee5` (pre-batch base) `matched: True`,
  `tabsDisplay: flex`; `1c31d09a` (main) and this tree both `matched: False`,
  `tabsDisplay: none`. This batch's CSS adds no focus or outline rule
  (`git diff 1c31d09a 4c0ec29c -- app/v2/v2.css` has no such line), so it cannot have moved it.
- `python -m unittest tests.test_v2_chart_fit_render tests.test_v2_chart_height_render
  tests.test_v2_phone_layout_render` (6 tests, OK): the chart still fits its box and the phone
  layout is unchanged.
- `gh pr checks 963` and `gh api repos/JB-barrel-droid/fantasy-tools/actions/jobs/<id>` on run
  `40383053763`: the blocking `preview` job (`121784056949`) passed on `4c0ec29c` in 34 min. The
  `Full test suite (informational, non-blocking)` check (`121784057328`) is red because the job
  hits its own `timeout-minutes: 45` while `make test-unit` is still running: the same job on four
  unrelated branches the same day (2026-10-26) is cancelled the same way after 45 minutes, and
  `continue-on-error` keeps it out of the `preview` gate (JEG-978), so it is not this batch's
  doing.

### Claimed, not confirmed

- A real notched phone was not used. The browser cannot fake `env(safe-area-inset-*)`, so the
  test injects the four custom properties with the values a notched phone reports; the inset
  arithmetic is checked, the device is not.
- `make validate` was not run to completion locally: the first run was stopped part-way to
  rebase onto `origin/main`, and the gate (the build, then `test-core`, `value-check-compare` and
  `test-integration`) is longer than this batch's budget -- the blocking `preview` job that runs
  it took 34 minutes on CI. It passed there on the rebased commit `4c0ec29c`.

### Merge-wave review (Claude, 2026-10-26)

- Fixed: the JEG-956 block re-declared `.v2-topnote-detail` at 48 px outside the season notice's
  landscape-phone query (`max-width: 932px and max-height: 500px`), so 768-932 px landscape phones
  lost the 16 px gutter. Added the landscape rule and `test_landscape_phone_keeps_note_gutter`
  plus its guard in `tests/test_v2_phone_safe_area_render.py`.
- Merged `origin/main` (`6be18a2a`), no conflicts.
- Verified (check named): `tests.test_v2_phone_layout_collapse_render`,
  `tests.test_v2_phone_safe_area_render` (4 tests), `tests.test_v2_phone_target_size_render`,
  `tests.test_v2_phone_tap_targets_render` and `tests.test_v2_contract_render` pass locally with
  `RENDER_TESTS_REQUIRED=1`.
- `tests.test_v2_phone_header_render` fails (360 px header 148 px) on this merge and identically
  with `origin/main`'s `v2.css`, so it is not this PR's doing.
