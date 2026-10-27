## 2026-10-26 - Fit label rewrite (JEG-1108, JEG-885)

Contract: Rewrite fit labels from depth-band system to roster-construction system.
Natural = constructionOk + yourValueOk + theirOk. Market supported = theirNet > theirTau
(renamed from Market fit, definition flipped). Force = everything else. Value label retired.
JEG-885: at most 2 rows per received player, rest folded under "N more for <player>".

### Verified (check named)

- `test_v2_finder_fit.py`: 11 positive test cases and 7 negative mutants all pass.
  Mutants: construction bypassed, starter drop allowed, their loss allowed, noise ignored,
  market always, tiers reversed, tiers unstable.
- `test_v2_finder_trifit.py`: rewritten for new rules (tri-view variants retired, projections
  don't affect label). 7 assertions pass.
- `test_v2_finder_balance.py`: headline text updated ("market supported or force fits").
  All tests pass including 6 mutants.
- `test_v2_finder_import.py`: unchanged, passes.
- `make test-core`: all tests pass except test_rank_guard (Playwright not installed on this
  machine -- infrastructure issue, not code).

### What changed

- `app/v2/finder.js`: new rosterConstructionOk(), rewritten tradeFit(), viabilityLabel(),
  balanceCounts(), FIT_TIER/FIT_VARIANTS simplified, headline text updated.
- `app/v2/opportunities.js`: ourFitOf/theirFitOf/overallFit rewritten for new labels,
  filter options updated (naturalMarket replaces naturalValue).
- `app/v2/league.js`: filter dropdown and detail panel viability display updated.
- `tests/test_v2_finder_fit.py`: completely rewritten with construction-based test cases.
- `tests/test_v2_finder_trifit.py`: rewritten (old tri-view mutants removed, new assertions).
- `tests/test_v2_finder_balance.py`: headline text assertion updated.

### Claimed, not confirmed

- Label distribution on real fixtures not computed (no fit-diagnostic.cjs found, no real
  league fixtures available in worktree). Before: Natural 2, Value 91, Market 4, Force 92
  of 189. After: expected more Naturals (construction check is more permissive than
  depth-band check), Market supported count depends on their-side chart averages.
- Viability display in connector output not verified (would need Supabase edge function
  changes, which are out of scope per lane rules).
- test_v2_finder_fit_render.py and test_v2_chart_fit_render.py not run (Playwright-dependent
  render tests, reference old "Value fit:" text that would need updating).

### Why tests changed

- test_v2_finder_fit.py: definition changed from depth-band to construction-based. Old
  tests were structured around "natural/value/force" with projection variants. New tests
  verify the three new guards (construction, starter delta, noise-scaled their-side tau)
  and negative-test each via code mutation.
- test_v2_finder_trifit.py: tri-view escalation (projections upgrading force to natural)
  retired. Old mutants referenced code patterns that no longer exist. Simplified to verify
  projections are computed but don't affect label.
- test_v2_finder_balance.py: headline text changed from "value-only or force fits" to
  "market supported or force fits" because value label is retired.
