## 2026-10-22 - JEG-850 Customize values cleanup

Contract: restructure the Customize dialog into two tabs (Chart lines, DDF blend) with the plain copy Jeremy chose on 2026-10-22, and fix the 8 defects in `customize-toggle-audit.md`.

### Changes
- `openSources` (app/v2/v2.js): two tabs sharing one draft; DDF blend tab lists the inputs once (the per-version mirror lists are removed); "Using N of M sources" counter on that tab only; held input shows unticked and locked, "Paused this week"; last usable input locked with "Last source stays on"; Done blocked with "Pick at least one source" when the draft has no engine series (no engine change); VORP group collapsed unless one is selected.
- Strip ("On the chart") says "(custom blend)" and "N hidden with the chart legend"; the dialog counter and row name a legend hide; Reset to default + Done clears legend hides.
- A DDF version with no source on says "No sources are turned on for this DDF Value" instead of "No source prices this player".
- Global copy: variants are "DDF Value: charts only" / "DDF Value: projections only"; chips read "Under review" / "Normal range" (also in the legend and table headers). Source links no longer swallow Escape.
- Phone: footer stacks Done, Cancel, Reset (text link), 44 px targets; chip words dropped (icon plus tooltip).

### Verified (check named)
- tests/test_v2_customize_cleanup_render.py: one check per defect (D1-D5) plus structure, each also run against a one-fault build and required to fail.
- Updated and green: test_v2_contract_render, test_v2_panels_render, test_v2_customize_pages_render, test_v2_phone_customize_targets_render, plus ddf_versions, divergence_chip, source_count, ddf, names, advanced, a11y, offer (see PR for the exact list).
- Live re-run of the 44 audit rows with real clicks (scratch script, not committed): all rows pass; rows 8 and 9 changed meaning (mirrors removed); row 41 table columns not exercised (needs a built deal).

### Claimed, not confirmed
- Full `make validate` not run locally (shared machine overloaded; CI preview runs it).
- Defect 6 (rank-by still DDF Value while its column is hidden) and defect 7 (two tab stops per row) are not changed.
