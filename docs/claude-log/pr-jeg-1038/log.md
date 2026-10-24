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

## 2026-10-24 - Wired viability into find_trades / find_trades_league tools

- Merged origin/main (PRs #893, #895, #896 now on main) into be/viability-scoring.
- Jeremy (2026-10-24) confirmed: keep checks 6/7 as-is.
- Wired viability scoring into `find_trades` tool in tools.ts: each trade candidate is scored
  on the 9 viability checks, labelled, and the output includes viable/label/failedChecks/
  temporaryGap/checks. Added `viable_only` filter flag.
- Registered `find_trades_league` tool: takes user roster + up to 15 opponents, runs find_trades
  for each pair, scores all candidates via `scoreAndRankOffers`, selects best package via
  `selectPackage`, returns ranked trades + package + projected lineup.
- Exposed viability thresholds as optional tool arguments (roster_shape, min_ddf_edge,
  min_market_net, depth_player_cutoff, dead_weight_cutoff, min_rb_backups, min_wr_backups,
  viable_only) with DEFAULT_CONFIG defaults.
- Updated doc surfaces: llms.txt, server-card.json, SKILL.md, values-endpoint.md,
  tests/test_llm_surfaces.py, tests/node/mcp_remote_check.mjs all list find_trades_league.
- Risk register: GAP-VIABILITY-NOT-WIRED fixed; GAP-VIABILITY-DEFAULTS-UNREVIEWED controlled.
- Verified: 26 viability unit tests pass, 7 LLM surface tests pass, MCP remote check passes,
  make validate green.
- Not verified: Supabase deploy (per instructions: no deploy).
