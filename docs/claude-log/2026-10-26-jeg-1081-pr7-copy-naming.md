## 2026-10-26 - JEG-1081 PR 7: copy, naming and tooltips for the three views

Contract: one canonical vocabulary across the trade tools (spec v2 4a to 4c, 5b): DDF Value, DDF Value (projections), Trade chart average; plain tooltips; the Overrides-basis wording. Also (coordinator): a broken-build test for a combo that exists in only one view.

### Verified (check named)
- `tests.test_v2_copy_names`: no user-visible string in any `app/v2/*.js` (audit-* excluded, comments skipped) says "Trade chart avg", "Fundamentals", "fundamental evaluation" or "DDF Projections"; five fit tooltips are five different plain sentences (an unknown variant reads as force); `viewTip` returns the spec's exact sentences for the three views, says "not our methodology" under a basis of the reader's own, and "Rescaled to X's point scale." (single source) or "...the point scale of X." (a blend); eight broken copies are each caught.
- `tests.test_v2_finder_triview_render` (7 widths, render lock): assessment header tooltips equal the spec text; each fit line carries its tooltip; under a FantasyCalc basis the header reads "DDF Value (FantasyCalc)" and the market tooltip says it is rescaled to FantasyCalc's point scale; three new guards (header unchanged, no rescaling clause, no fit tooltip) are caught.
- `tests.test_waivers_views` now has a fixture where a pair exists in one view only (Ca+Cb priced only by DDF Value, Pa+Pb only by the projections, Ma+Mb hidden from DDF Value by its own noise but visible to a single source): the combo list follows the view; two new mutants (combo key, combo noise) are caught. This closes the PR 6 gap.
- Renames: chips and Waivers text "Trade chart average"; opportunities column "DDF Value capture"; card line "DDF Value:"; Waivers note "The DDF Value evaluation is unaffected."; test strings moved with them (chips render, tables render, phone render, triview render).

### Fresh-eyes review (separate subagent) and what changed
- Fixed: fit-tooltip sentences matched to the code (a side is served when it does not lose, depth counts toward need; "gains less than the noise"); blends no longer read "Rescaled to 60% ESPN + 40% Razzball's point scale"; the scan test is case-insensitive and covers every app/v2 file; added the viewTip and caption mutants.
- Also wired the JEG-1081 unit tests (waivers views, copy names, tri-view fit, projection noise, display helpers) into the Makefile; they were not part of `make validate` before.

### Claimed, not confirmed
- Title-only tooltips are not available on touch or by keyboard (risk register GAP-TRIVIEW-TITLE-TOOLTIPS).
- Spec 4b headline "Pick up X: +a DDF Value (+b projections, +c market)": the Waivers verdict keeps its existing sentence with the other views on a second line ("Other views: ..."); the frozen waiver fixtures pin the first sentence.
