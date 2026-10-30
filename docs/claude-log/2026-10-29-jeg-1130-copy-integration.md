## 2026-10-29 - JEG-1130 copy integration (slice 2 of the PMM copy)

Contract: carry the reviewed #1037 copy (muse/jeg-1130-pmm-copy at 121911c, left with its author) onto current
main on a new branch, reconciled with the final naming (Jeremy, 2026-10-26 2:38 PM) and JEG-1212 (#1071), with no
behavior, value, default or ranking change. Not the whole migration: the v2.js and curve-widget.js slice follows.

### What changed
- #1037's hunks in finder.js, league.js, modules.js, team-summary.js, waivers.js and shell.html (empty states,
  Buy / Sell, Rising / Falling, Mixed signals, value above waivers, Positions the market overpays for, paste note).
- Reconciled with the final decisions:
  - The three Find a trade view tooltips are one plain sentence each, rooted in the trade charts or projections and
    adjusted for position weight and league rosters; no publisher names. The Market tooltip says what other
    managers pay, on one scale, before any position-weight adjustment.
  - Labels capitalize Market: team summary "Roster/Starter/Bench value (Market)", "Buy (Market underpays)",
    "Sell (Market overpays)".
  - "The Market, by chart" on the Waivers per-chart table caption and the How values card;
    "Dashed = one chart of the Market" on that card's line key.
  - "The charts moved first" replaces #1037's "The market moved first" (the DDF read is not the Market).
- Kept on purpose: the JEG-1212 table groups (Published charts, Observed-trade estimates); the Waivers headline and
  verdicts pinned by frozen fixtures; the Trade targets footnote (v2.js rewrites it and checks its first words).
- New test tests/test_jeg1130_copy_glossary.py: tooltips name no publisher, the per-chart caption, nav label = H1
  on the eight tool pages; four broken-build mutants.

### Verified (check named)
- `python3 -m unittest tests.test_jeg1130_copy_glossary tests.test_v2_copy_names tests.test_launch_copy_guard
  tests.test_public_copy_no_vorp` passed (platform-claim grep clean).
- Render tests with CHROMIUM_PATH (Chromium 141) on a local `make sync` build: see the PR description for the
  exact list and results.
- Phone (390) and desktop (1366) screenshots of Risers, How values and Trade targets taken from the local build.

### Claimed, not confirmed
- CI fonts and the CI Chromium may differ from the local Chromium 141 used here; exact-head CI is the check.
- Nav renames from the PMM doc (Buy & sell, Check a trade, Read, Settings, Show the math) are not applied: they are
  navigation (JEG-1106 / JEG-1137 lane), and Appendix B question 3 is still open.
