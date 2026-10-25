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
- Fixes (app/v2/v2.css, app/v2/v2.js): chip gets a centred 44 x 44 `::after` (box and row unchanged): on touch for every chip (z-index 2
  so a header chip beats the value cells), and on any pointer only on Targets (note and column header), because test_v2_targets_render
  pins 44 px there at 1440/1366/1024 (it was red on the same chip) while on desktop elsewhere the chip's hit area would cross the 44 px
  info buttons (the overlap guard caught that in a first attempt); legend chip +3 px left margin (touch) so it clears the source link's padding; Targets note items are
  44 px rows on touch; Compare net-chip info hit box is 24 px tall in the short-viewport block; header chip word is `display: none`
  (aria-label unchanged); Compare row chip (`td.player .th-sub`) is `noLink` (a 44 px link cannot fit under the name in a 44 px row;
  the legend keeps the link). Targets header chip stays a link (test_v2_divergence_chip_render pins that).
- Test changes (none loosen): tap-target sweep opens the nav menu below 768 px; phase 1 name-tap lengthens the first name when no row
  clips naturally and still asserts the popover shows the full name (the "names no longer clip" mutation is still caught); two new phase 1
  mutations (chip hit area removed, header word back to 0 px) and one new tap-target test (chip pseudo and net-info rule removed).
- Verified (RENDER_TESTS_REQUIRED=1, one file at a time under the lock, final tree): test_v2_phone_tap_targets_render 3 tests OK (327 s),
  test_v2_mobile_phase1_render 2 tests OK (296 s), test_v2_targets_render OK (223 s), test_v2_divergence_chip_render OK (30 s),
  test_v2_held_chip_render OK (17 s, earlier tree). `make -o sync validate` exit 0 (1003 s; the fallback-font render tests skip here, no
  DejaVu Sans on this Mac). Guards fail on a broken build: both new mutations and the old ones pass in the two files above.
- Not mine, found on the way: test_v2_waterfall_render.test_guard_fails_on_broken_builds mutation "no wide verdict column on short
  viewports" is not caught on clean 69b70317 either (JEG-932's chip packing removed the fold pressure it relied on); main waterfall test passes.
- CI list decision: neither file is added to the blocking v2-render job (only test_v2_contract_render runs there). Added run time is
  about 10 minutes here (327 s + 296 s, with other agents using the machine), far over the 3-minute budget.
