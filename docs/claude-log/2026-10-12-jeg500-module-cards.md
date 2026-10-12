## 2026-10-12 - JEG-500 every module expandable and collapsible

Contract: GL-17 and GL-18 (Jeremy, 2026-10-09): every card on every data tab expands and collapses, collapsed it shows its title plus a one-line summary, and the state is remembered. Bundling decision (Jeremy, 2026-10-12): JEG-542 (three DDF versions) and JEG-498 (Customize on every page) were read and NOT bundled; each touches the picker, defaults, rank, Compare, Risers and Targets in v2.js (39 DDF_KEY sites for 542), so neither is small. They stay in waves 5 and 6.

### Verified (check named)
- `tests.test_v2_modules_render` (headless, 1440 and 390): every card on Player values, Trade targets, Risers & fallers and Compare has a 44 px chevron with aria-expanded, collapses (body hidden, title kept, non-empty one-line summary), survives a reload, opens again; the non-Player-values expand spans the row and restores; Player values chart and table expand opens the JEG-483 dialog; no sideways scroll at 390; the table beside a collapsed chart is not squashed.
- Same file, `test_guard_fails_on_broken_builds`: six broken builds (state not saved, collapsed body still shown, empty summary, no aria-expanded, expand does nothing, small chevron) each fail.
- Contract test: GL-17 and GL-18 are live checks (every visible card on the four tabs has an expand control and a chevron); `docs/feature-contract.md` drops "to build".
- `make validate` exit code is in the PR description.

### Claimed, not confirmed
- Visual polish was checked by two headless screenshots (Targets with Buy collapsed, Player values with the chart collapsed), not by Jeremy.
- Cards added after this PR need an entry in `CARDS` in `app/v2/modules.js`; the contract test only sees cards visible on the four data tabs.
- How values work and Manifesto cards are not modules (reading pages).
