## 2026-10-25 - JEG-1081 PR 3: projections in the roster assessment, impact and score chips

Contract: show DDF Value (projections) beside DDF Value and the Trade chart average in Find a trade (spec v2 2a-2c, 2i): a third, subdued column group in the roster assessment with a "Show projections" toggle where narrow, a secondary delta line in the roster impact ("Starters +a DDF Value (+b projections, +c market). Bench ..."), and a three-value tooltip on the score chips.

### Verified (check named)
- `tests.test_v2_finder_triview_display`: hasProjections, chipTooltip, deltaLine (true minus sign, missing views left out) with six broken-build mutants.
- `tests.test_v2_finder_triview_render` (one file under the render lock): column groups present at 1440, 1366x768, 1024, 1023, 768, 767 and 390; projections visible and toggle hidden from 1024; hidden with a working toggle (aria-expanded flips) below; team headings' colspans equal the visible cell count before and after the toggle; the projections group adds up (starters + bench vs total); chips carry the same three-line tooltip equal to the row values; the secondary impact line shows from 768 and hides below behind "Show other views"; no sideways page scroll at 390. Eight broken builds fail it (projections never hidden, label dropped, chip title old, secondary line hidden, headings hardcoded to 8, aria-expanded not flipped, two breakpoints moved).
- Screenshots read at 1366x768 (table fits without scroll, projections subdued) and the 390 group card.

### Fresh-eyes review (separate subagent) and what changed
- Blocker fixed: team headings were hardcoded to span 8 columns, so below 1024 they sat over the wrong columns; now 6 or 8 from the width and the toggle (matchMedia listener).
- Fixed: the projections delta is computed only when that team's rows carry projections; chips are focusable with an aria-label carrying the three values; "Starters: no value" copy; toggle sticks to the left of the scrolling table; flag column gets a minimum width so "Under" does not wrap.
- Deviation noted: the projections group hides below 1024px (spec 2a says phone under 768px) because three groups of two columns plus the team columns do not fit a tablet.

### Claimed, not confirmed
- The tooltip is a title attribute plus aria-label; no visible touch affordance beyond focus. Spec 2c allows hover/tap tooltip; a tap popover was not built.
- Waivers' one-team assessment gets the same third group (shared assessmentTable); its own render tests ran inside make validate only.
- Rubric items 1-4 are covered by the render test above; the fresh-eyes review did not run the page.
