## 2026-10-29 - JEG-1030 connector parity and state round-trip guards

Contract: recheck existing-tool parity on current main and add tests (tests only, no runtime,
method or default change) for custom-league consistency across the connector's tools,
state -> tool -> site-link round trips, and one tool/route inventory. Branch
`claude/JEG-1030-parity-guards` from main `ff351526`.

Added:
- `tests/node/connector_roundtrip_check.mjs` + `tests/test_connector_roundtrip.py`: 8 state-reading
  tools x 4 leagues (3-WR/6-bench SF with shares, bso, inj, conf and weeks incl. a reader week;
  PPR 14 teams roster+shares; Standard 8 teams weeks+bench+conf; plain PPR 12) plus 3
  explicit-override cases. Checks: A the answer priced the pasted league (engine inputs via
  league.ts `mapLeague`), B the link opens what was priced, C the link loses no league field,
  D the link pasted back is a fixed point; work lists survive. The 3-WR league's engine inputs
  are written out literally. Seven broken variants (link drops bso / shares / weeks / inj+conf /
  teams, roster rewritten to default, pasted league ignored) must each be caught.
- `tests/node/connector_inventory_dump.mjs` + `tests/test_connector_inventory.py`: every listed tool
  with the route its link opens (observed by calling it) and its checks; every site tab route is
  linked by a tool or an explicit exception (JEG-n, by design, or untracked); six drift cases.
- Makefile `test-unit-modules`: both modules, beside the existing connector tests (nightly full
  suite). Not the deploy gate.

### Verified (check named)
- `node --experimental-strip-types tests/node/connector_roundtrip_check.mjs`: 32 round trips and
  the scoring/teams override pass, 2 known gaps (F1), all 7 mutations caught, exit 0; `--strict`
  exits 1 while F1 stands.
- `python3 -m unittest tests.test_connector_roundtrip tests.test_connector_inventory`: 4 OK.
- F1 fix candidate, applied locally and reverted (not committed): writing `settings.superflex` into
  the link's roster in `state.ts finish()` makes both gaps pass (the script then reports them as
  fixed and exits 1 until removed), and `tests/node/mcp_remote_check.mjs` stays ok.
- Edge side of endpoint parity on main `ff351526` (`tests/_edge_pipeline_runner.cjs`, served-week
  clock 2026-10-26): 738 players per setting, nonzero values 197 / 159 / 221 / 210 for
  PPR 12 / Half 10 / Std 14 / PPR 12 SF.
- `tests.test_endpoint_parity` passed in the nightly full suite run 40702258196 on `759a4f90`
  (2026-10-28 14:03 UTC; not in its failed list, RENDER_TESTS_REQUIRED=1).
- Guards still green: test_run_suite, test_render_sweep_shards, test_validate_shards,
  test_validate_runner, test_doc_staleness, test_ddf_state.

### Findings for the connector owner (no runtime change here)
- F1: an explicit `superflex` argument prices one league and links another (state.ts `finish()`
  keeps the pasted roster's SUPERFLEX). Repro: the check with `--strict`.
- F2: get_values / get_player_value link to Trade targets, not the value chart; find_trades_league
  links to the one-opponent finder, not Find a trade: league-wide. Recorded as untracked
  inventory exceptions; where links go is a product call.
- F3: no waiver analysis in the connector or in JEG-1029's proposal (untracked exception).
- F4: `tests.test_mcp_remote.test_connector_fit_label` is red on main `ff351526`:
  connector_fit_check.mjs:121 "the diagnostic's rows are the same trades 5693 !== 189", after #1072
  (opportunities.js keeps every candidate). Owned with #1072.
- Also red on main, not this ticket: test_render_sweep_coverage (unwired render modules).

### Claimed, not confirmed
- The page half of parity on current main: `tests.test_endpoint_parity` needs Chromium, which this
  environment cannot download; main has changed value-model.js and get-values/index.ts since
  `759a4f90`. The next nightly full suite on main is the check.
- Nothing here was run against the deployed `mcp` or `get-values` functions or a live chat client.
