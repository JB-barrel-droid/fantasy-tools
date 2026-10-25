## 2026-10-24 - JEG-1048 / JEG-1051 / JEG-1052 phone tap-target guards red on main

- Reproduced on a clean worktree of origin/main (69b70317), after `ensure_built()` (the tap-target test reads dist/ and does not
  build it itself; on an unbuilt tree it fails with a 404 page and "no #v2EditSources", which is not the bug). Names below are
  the selector, size and page from the two guards (375 for test_v2_phone_tap_targets_render; 390, 360, 320 and 844x390 for
  test_v2_mobile_phase1_render).
- Offending elements and where each came from:
  1. `a.v2-div-chip.is-reviewed` "Reviewed", 79x19 (74x18 landscape), in the chart legend (`#v2ShowingLegend`) on Player values,
     Targets, Compare, How values; in the Targets note (`.v2-tdiv-item`) and Targets column header (`.th-sub`); 24x24 in Customize.
     Code from #612 (JEG-609, 2026-10-15, `git log -S resolutionHref`): a reviewed chip is a link. It only became visible when the
     published divergence data (`reference-freshness.json`, week 7, `resolution_issue` JEG-795/796) set `status: reviewed`, so
     it is a data-triggered latent defect; #862, #865, #889 and #853 did not introduce it (#853's own guard never saw a link chip).
  2. The same chip's side effect: `a.v2-srclink` "FantasyPros" is under the chip (the source link's 6 px side padding, #865/JEG-817 and
     #854/JEG-884, ends inside the chip) at 375 on four tabs.
  3. `span.v2-div-word` at `font-size: 0` in values-table headers (JEG-1051): the "hide the word" trick from #823 (JEG-870/873) leaves a
     0 px text node, which the 12 px text guard (#853) reports at 390, 360 and 320.
  4. Writing/Research, Writing/Manifesto, Values auditing "only 8-9 controls found, the sweep is not looking at the page": not small
     controls. #864 (hamburger nav, 2026-10-23) moved the six tabs into a closed menu, dropping those pages under the guard's
     10-control floor. The floor is unchanged; the sweep now opens the menu (also puts the six menu tabs under the 44 px and overlap checks).
  5. `button.v2-info` x2 in `#v2CDealNets` at 1280x800 Compare (44 px buttons on rows 26 px apart): #844 (JEG-932, 2026-10-23) tightened
     the net-chip row gap to 2 px for the 1366x768 fold. Overlap guard from #854 fires.
  6. Phase 1 "no clipped name found to tap" at 390: not an element. The first 50 rows all fit the 148 px name column this week (longest
     "Walker III, Kenneth" 133 px), so the tap test had nothing to tap. Data-dependent guard; see test change.
- Fixes (app/v2/v2.css, app/v2/v2.js): chip gets a centred 44 x 44 `::after` on every pointer (box and row unchanged), z-index 2 so a
  header chip beats the value cells; legend chip +3 px left margin (touch) so it clears the source link's padding; Targets note items are
  44 px rows on touch; Compare net-chip info hit box is 24 px tall in the short-viewport block; header chip word is `display: none`
  (aria-label unchanged); Compare row chip (`td.player .th-sub`) is `noLink` (a 44 px link cannot fit under the name in a 44 px row;
  the legend keeps the link). Targets header chip stays a link (test_v2_divergence_chip_render pins that).
- Test changes (none loosen): tap-target sweep opens the nav menu below 768 px; phase 1 name-tap lengthens the first name when no row
  clips naturally and still asserts the popover shows the full name (the "names no longer clip" mutation is still caught); two new phase 1
  mutations (chip hit area removed, header word back to 0 px) and one new tap-target test (chip pseudo and net-info rule removed).
- Verified / not: see the PR body for the runs. Neither file is added to the blocking v2-render list: run time is well over 3 minutes.
