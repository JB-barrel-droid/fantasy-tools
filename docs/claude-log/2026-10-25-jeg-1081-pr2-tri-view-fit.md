## 2026-10-25 - JEG-1081 PR 2: tri-view fit rule

Contract: `tradeFit` judges your team in DDF Value and in DDF Value (projections) and their team in the trade chart average; fit labels show all variants (natural, natural (charts only), natural (projections only), value, force); headline "Natural fit found: N groups" with the qualifier as subtitle (Jeremy 2026-10-25).

### Verified (check named)
- `tests.test_v2_finder_trifit`: agreeing views, charts-only, projections-only (the frozen "disagree trade": two-view rule gives force, tri-view gives natural (projections only)), missing projections fall back to the two-view rule, neither view serves you is force, market decides their side, balanced one-for-one stays value, texts and headline subtitle. Eight broken copies of finder.js (including forcing `usProj.ok` false, which turns natural into natural (charts only)) each fail the checks.
- Existing `test_v2_finder_fit` (pinned two-view cases), `_impact`, `_groups`, `_balance`, `test_waivers_math` pass.

### Claimed, not confirmed
- Held-out label-shift measurement on real data (spec 3d): not run.
- DOM rendering of the subtitle at 390/1366 and the render suites: left to CI v2-render plus the validate run.
- Spec table row 4 (value when they would not accept) not implemented: it contradicts the pinned rule that a team the market does not serve makes the trade force. Kept the pinned rule; decision for Jeremy.
- `docs/claude-log/2026-10-25-jeg-1081-pr2-tri-view-fit.md` edit to `test_v2_finder_fit.py`: only a mutant anchor string, no assertion.

### Fresh-eyes review (separate subagent) and what changed
- Fixed: opportunities.js `ourFitOf` read DDF Value only, so a "projections only" trade was "force" in the table but "Natural fit (projections only)" on the card; it now reads the serving view (unit test and mutant in test_v2_finder_trifit). Cache `rowSig` now includes the projections value (pinned mutant anchor in test_v2_league_units updated, no assertion changed).
- Fixed: fit text named only the DDF Value depth move; it now names the view that moves toward depth (fixture: DDF Value gains with no slot filled, projections fill one).
- Method call made, flagged: depth counts in EITHER view that serves you (before, the charts view only). Same result whenever projections are missing or agree.
- Fixed: headline subtitle separated by a space for the live region, and reworded in plain language ("N are backed by the trade charts but not the projections").
- Added mutants for the both-agree qualifier, the depth rule, the projections-key guard and the opportunities half.
