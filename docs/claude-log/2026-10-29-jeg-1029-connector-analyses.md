## 2026-10-29 - JEG-1029 connector analyses with page parity

Contract: add the analyses the site has and the connector lacked (Risers & fallers with the market vs
projections disagreements, Compare a trade by source, Values auditing health and source views), priced
by get-values and read by the page's own modules, with reference and page parity in CI. Stacked on
#1119 (connector week, fit, superflex link) with #1101 (JEG-1030 round trips and inventory) merged in;
neither is on main yet. No method change, no deploy, no Supabase.

What changed:
- get-values: `include` is a comma list; new opt-in `series`, `prior`, `audit` blocks
  (`get-values/analysis.ts`; `pipeline.ts` exports `savedNatives`). The default answer is unchanged.
- MCP: `risers_fallers`, `audit_values`, and `compare_trade` `by_source` (`mcp/analyses.ts` loads
  movers.js, trade.js, audit-pie.js and audit-source.js from the site; `tools.ts` handlers;
  `state.ts` route `audit` -> `#values-auditing`). Server card lists the two new tools.
- Tests: `tests/test_connector_analyses.py` + `tests/node/connector_analyses_driver.mjs` (offline),
  `tests/test_connector_analyses_page.py` (browser), the parity runner's `--include` / `--mutate`,
  inventory (two JEG-1029 route exceptions removed, three tools listed), round trips (the new tools
  added; the two JEG-1030 F1 known gaps removed because #1119's `finish()` fixed F1). All in
  `test-unit-modules`.

### Verified (check named)
- `python3 -m unittest tests.test_connector_analyses` (3 tests OK): at ppr/12, half_ppr/10 SF and
  standard/14 the edge `series` and `prior` blocks equal `value_reference.compute()` rows and
  `prior_result()` for all 10 series to 1e-6 (observed max diff about 1e-13; 738 players with a prior
  DDF Value at ppr/12), the audit diagnostics' pie, included set and per-source position counts equal
  the reference's; each tool's structured answer equals the page module run on the reference
  (risers, fallers, counts for all 10 series, disagreements, 4 compare trades incl. one with a missing
  projection value) and on the same inspection (health checks, 7 source views).
- Broken variants caught (same test): prior from Week N-2 labelled N-1, prior equal to this week, a
  source dropped from the prior week, charts read as Adjusted, compare sides swapped. An earlier
  "prior on its own pie" mutation was not caught because the pie does not change between the two
  weeks at this build; it was replaced, not kept as a passing check.
- `tests.test_connector_inventory` (OK, 1 expected failure: the JEG-1030 F2/F3 routes stay
  unresolved), `tests.test_connector_roundtrip` (11 tool cases x 4 leagues, 0 failures, 0 known gaps,
  8 mutations caught), `tests.test_mcp_remote`, `tests.test_mcp_week`, `tests.test_llm_surfaces`,
  `tests.test_ddf_state`, `tests.test_league_mapping`, `tests.test_run_suite`,
  `tests.test_validate_shards`, `tests.test_doc_staleness`: OK.
- Both edge `index.ts` files parse and resolve their imports under node strip-types (stop at `Deno`).

### Claimed, not confirmed
- `tests/test_connector_analyses_page.py` (live page getPriorWeek / getAllRows / getInspection vs the
  edge blocks) was not run: no Chromium in this cloud environment. The nightly full suite or the Mac
  is that check.
- Nothing ran against deployed functions. get-values and mcp need a deploy (Jeremy's yes) before
  the tools work in a chat client; until then the live mcp lists no new tools.
- Deno itself did not type-check these files here (no deno binary).
- Not covered: earlier week pairs on Risers & fallers (the N-1 -> N control), the league team
  summary, SKILL.md / llms.txt prose for the new tools (copy, Jeremy's), and per-source prior pairs for
  a source serving a different week from the view during a transition (reported unavailable with the
  reason instead of the page's per-source pair).
