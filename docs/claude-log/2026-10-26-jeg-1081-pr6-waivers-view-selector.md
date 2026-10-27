## 2026-10-26 - JEG-1081 PR 6: Waivers view selector

Contract: the Waivers tab gets a compact "Decide by" selector (Jeremy 2026-10-25): DDF Value (default), DDF Value (projections), Trade chart average, any single source, the Overrides basis. Every verdict, drop, headline and combo recomputes for the chosen view; the other views are shown as context ("+2.1 on projections, +1.8 on market"). Find a trade gets no selector (spec 2g).

### Verified (check named)
- `tests.test_waivers_views` (node, frozen "view-switch" fixture written in the file: a thin-RB roster and candidates priced differently per view): DDF Value says pick up where projections say not, and the reverse; the swap, the fit and the drop are read in the deciding view (a WR priced 1 in DDF Value and 45 in projections is the first drop only in DDF Value); the context names the other views and never the deciding one; single sources have tau 0.05 (noise 0); DDF Value tau is half the charts-vs-projections gap and 0.05 where they agree; a candidate with no value in the view (or a market value that shows 0.0) is Not evaluated, never 0; a roster player the view cannot price is not the first drop; the default view equals calling without a view; unknown ids fall back to DDF Value; the basis choice judges on the DDF Value key and says so; headline note and context. Twelve broken copies are each caught.
- `tests.test_waivers_math` (the frozen waiver fixtures, unmodified) passes: default headlines are unchanged, the context sits in a separate field.
- `tests.test_waivers_view_render` (1366x768 and 390, render lock): selector options, 44px, no sideways scroll, headline inside the first screen, context on every evaluated row, projections / market / single-source recompute and say "judged on", DDF Value restores the first answer exactly, the choice survives a reload, a saved id that no longer exists falls back to DDF Value. Four broken builds caught. `tests.test_waivers_render` (existing) passes.

### Fresh-eyes review (separate subagent) and what changed
- Fixed: a roster player the view cannot price was the first drop; the Overrides basis option showed on the default basis and the market option showed with no charts (both now hidden); mutants added for the market price floor and the unpriced drop; a render check for a stale saved view.
- Not changed: "Judged on ..." repeats in every reason (kept: it states the view in the row text); the DDF Value and Value above waivers columns do not change with the view (the legend says the swap columns do).

### Deviations and claims
- One select at every width (spec: segmented control on desktop, dropdown on phone).
- finder.js `valueNoise` now returns 0 for any key other than DDF Value, projections and the Trade chart average (a single source has no spread). The two-for-two combos follow the view (key and noise) but no fixture has a combo that exists in one view only, so that path is not proven by a broken-build test.
- Overrides basis with a non-default basis was not rendered in a browser (only the pure rules).
