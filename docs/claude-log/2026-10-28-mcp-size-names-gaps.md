## 2026-10-28 - MCP reply size and short names: remaining gaps (JEG-1123, JEG-1124)

Contract: close the gaps a read-only check of main (951b32be) found after PR #958. The find_trades and
find_trades_league text lists only the top 5 trades (every row stays in structuredContent once, plus the site
link); find_trades_league defaults to 10 rows (max stays 100); the size budgets in the test are tightened so a
regression fails; every player-name field has `minLength: 2` in its schema and a run-time check that rejects a
trimmed name under 2 characters ("name too short ... Use a fuller player name"). get-values, finder.js and the
viability logic were not changed. The edge function was not deployed.

### Verified (check named)
- `node --experimental-strip-types --no-warnings tests/node/mcp_remote_check.mjs` (exit 0 on the branch). Synthetic
  15v15 fixture, JSON-RPC result bytes, main 951b32be -> branch: find_trades default 6748 -> 6056; find_trades
  limit 50 20941 -> 15374; find_trades_league with 11 opponents 8892 (default 25) -> 7221 (default 10);
  find_trades_league limit 100 is 10280 on the branch; get_values limit 200 unchanged at 21857. New caps:
  6700, 17000, 8000 and 11500 bytes.
- The same test file run against main's `supabase/functions/mcp` (a worktree at origin/main) fails: first at
  "get_player_value.names has minLength 2"; with the schema asserts removed, at `get_player_value {"names":"J"}`
  not being an error; with the name block removed, at "find_trades text lists the top 5 trades only" (10 !== 5).
- New name cases in that test: "J" is rejected for get_player_value (alone and inside a list), trade_targets,
  both compare_trade sides, find_trades mine/theirs, find_trades_league mine and an opponent roster, and
  make_state give/target; "" and "   " are rejected for get_player_value and both compare_trade sides. "Jr"
  (2 characters) still reaches the matcher and is reported ambiguous. "Bijan Robinsen" carries the note
  `interpreted "Bijan Robinsen" as Bijan Robinson`, "Jamar Chase" a matched/interpreted note for Ja'Marr Chase.
- `node --experimental-strip-types --no-warnings tests/node/batch_trade_check.mjs`, `node tests/node/ddf_state_check.cjs`,
  `python3 -m unittest tests.test_mcp_remote tests.test_ddf_state tests.test_llm_surfaces` (12 tests) and
  `tests.test_mcp_finder_loader`: all pass on the branch.
- `tsc --noEmit --strict` on `supabase/functions/mcp/tools.ts`: no errors.
- Correction to `2026-10-26-mcp-assistant-outputs.md`, which says the function was not deployed: it was. Supabase
  `get_edge_function mcp` (read-only) shows version 12, updated 2026-10-28 04:27 UTC, and its files equal
  `supabase/functions/mcp` at 764a2cfe (names.ts differs only in how the upload rendered a `̀-ͯ` escape).

### Claimed, not confirmed
- Live MCP still serves 764a2cfe until an mcp edge function deploy, which waits on Jeremy. Sizes on live rosters
  were not re-measured; the review rosters are not in the repo, so the budgets use the synthetic fixture.
- `make validate` was not run (no site, app or dist file changed).

## 2026-10-29 - refresh on #1024 and current main (JEG-1123)

Contract: bring PR #1032 up to date so it lands after #1024. Merged `origin/muse/jeg-1176-mcp-week` (#1024 head
179288b) into this branch, then `origin/main` (6be60d2). `mcp/tools.ts` merged cleanly both times (#1024's week
plumbing and main's JEG-1115 fit labels sit beside the top-5 text). One conflict, `docs/risk-register.md`: two
independent new rows (GAP-ENDPOINT-CALENDAR-WEEK from #1024, GAP-LEAGUE-EARLY-CANDIDATE-CAP from main); both kept.
No tool output, default, limit or ranking changed. Added a size check with fit labels on (the live shape since
JEG-1115: get-values sends bench_share, every trade carries fit and fitReason); the fit-off caps are unchanged.

### Verified (check named)
- `tests/node/mcp_remote_check.mjs`: ok. Fit off: 6148, 15466, 7313, 10372, values200 21921 (caps 6700, 17000,
  8000, 11500, 24000). Fit on: 8478, 22971, 9938, 14627 (new caps 9300, 25300, 10900, 16100). With TEXT_ROWS in
  tools.ts set to 100 the fit-on block fails at "findDefault: text still lists the top rows only (10)".
- `python3 -m unittest tests.test_mcp_week tests.test_mcp_remote tests.test_mcp_finder_loader`: 9 run, 8 pass
  (includes get_values_week_check on a fresh sync). The one failure is test_connector_fit_label, which fails the
  same way on origin/main 6be60d2: `connector_fit_check.mjs` "the diagnostic's rows are the same trades" 5693 !== 189.
  It passes at 676e96c~1 and fails at 676e96c (#1072, league candidates kept before fit ranking).
- `batch_trade_check.mjs`, `ddf_state_check.cjs`, `get_values_handler_check.mjs`, `tests.test_ddf_state`,
  `tests.test_llm_surfaces`, `tests.test_week_calendar`, `tests.test_week_state`: pass.
- `tsc --noEmit --strict` on `supabase/functions/mcp/tools.ts`: no errors.

### Claimed, not confirmed
- `tests.test_week_history` transition sentinel and the endpoint week parity need Playwright/Chromium, not
  installed here; CI runs them. `make validate` was not run locally; preview CI runs it on this head.
- Nothing deployed. The fit-on sizes use the synthetic fixture, not live rosters.
