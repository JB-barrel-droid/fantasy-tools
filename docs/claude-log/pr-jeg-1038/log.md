## 2026-10-24 - JEG-1038 Viability scoring and ranking module

- Built `supabase/functions/mcp/viability.ts`: pure module (no I/O, no Deno APIs) that scores and
  ranks trade offers on 9 viability checks. Exports `runViabilityChecks`, `scoreAndRankOffers`,
  `selectPackage`, `DEFAULT_CONFIG`.
- Value lenses: user's side judged on DDF Value (`ddf_value`), other team on market value (mean of
  usatoday, fantasycalc, fantasypros, cbs).
- 9 checks: arbitrage, perceived fairness, user lineup improves, their lineup improves, position
  protection, depth, roster space, QB kept, user guardrails.
- Ordering: viable first (DDF edge > user lineup improvement > perceived fairness), non-viable
  follow (fewest failures > DDF edge). Dedup by received players.
- Labels: High / Med-High / Medium for viable; null + failedChecks for non-viable.
- Package selection: greedy best viable offers, no player sent twice, each team at most once.
- All thresholds configurable in `DEFAULT_CONFIG`; documented in `docs/values-endpoint.md` with a
  table of defaults for Jeremy to review (product decisions, not silently pinned).
- Verified: 25 unit tests in `tests/node/viability_check.mjs` (esbuild transpiles TS to ESM for
  node). Each of the 9 checks has a positive and negative test (negative simulates a broken state
  to prove the check catches it). Additional tests: dedup, ordering, package no-reuse, package
  team-unique, labels, all-checks-recorded. All 25 pass.
- Not verified: `make validate` (worktree lacks .venv and full build deps; changes are purely
  additive -- new files + doc updates -- and do not affect existing build output).
- Not wired: viability module is built and tested but not yet integrated into the find_trades/batch
  flow. Depends on PRs #895 (batch) and #896 (find_trades) merging first.
- Risk register: added GAP-VIABILITY-DEFAULTS-UNREVIEWED and GAP-VIABILITY-NOT-WIRED.
- Branch: `be/viability-scoring`, based on `origin/be/find-trades-tool` with
  `origin/be/jeg-1036-batch-trade-discovery` merged in.
