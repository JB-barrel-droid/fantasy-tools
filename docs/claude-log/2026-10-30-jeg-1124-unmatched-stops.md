## 2026-10-30 - JEG-1124: a name that matches no player stops compare_trade too

Contract: apply Jeremy's pick on JEG-1124 (2026-10-30 13:40 UTC, "Letter A.") to draft PR #1200. A
compare_trade name that matches no player now stops the compare and asks which player was meant,
with the closest names, the same way an ambiguous name already does. read_state gives no total for
a list with an unmatched name.

What changed (branch `claude/JEG-1124`):

- `supabase/functions/mcp/names.ts`: `closestNames(players, query, hit)`. It returns matchName's own
  "Closest" list when it has one; otherwise the same edit distance (`fuzzyDistance`) with no cap, so
  the stop always has names to offer ("Zzyzx Notaplayer" has none within matchName's 3 edits).
- `supabase/functions/mcp/tools.ts`: `stopOnAmbiguous` became `stopOnUnresolved`. It stops on
  ambiguous names (same text as before) and on unmatched names (`"Zzyzx Notaplayer" matches no
  player; closest: ...`), then "Ask the user which player they meant, then call again with the full
  name." The "Warning: not found, left out of the total" line is gone; `not_found` stays in the
  reply as an empty list. read_state prints `give (no total: 1 name not matched):` for such a list,
  and its closing line asks which player was meant.
- `tests/node/mcp_remote_check.mjs`: three assertions that pinned the old rule now pin the new one
  (Jeremy changed the rule): the "Ghost" compare (was "roughly even" with `not_found`), the compare
  link that carried "Ghost" by name (that compare now stops; the link check uses matched names), and
  read_state's get list (now no total). New test: "Zzyzx Notaplayer" in a trade gives a tool error,
  no verdict, no total, and a which-player prompt with closest names.

find_trades, find_trades_league and make_state are untouched: `resolveNames`, `missed()` and
`ambiguousOf()` are unchanged and the finders still count unmatched names and keep going.

No deploy. The connector changes live only after an mcp redeploy, which needs Jeremy's yes.

### Verified (check named)

- New Zzyzx assertion fails on the PR's previous head 1a6ebc4b: `node tests/node/mcp_remote_check.mjs`
  stops at the new `isError` assertion; the reply was "Verdict ... roughly even" plus "Warning: not
  found, left out of the total: Zzyzx Notaplayer". Passes after (script prints `ok`).
- `python3 -m unittest tests.test_mcp_remote tests.test_connector_inventory tests.test_mcp_finder_loader
  tests.test_llm_surfaces`: OK (inventory: expected failures=1). `test_mcp_remote` covers
  `mcp_remote_check`, `mcp_superflex_link_check`, `connector_fit_check`, `batch_trade_check` and
  `connector_both_sides_check`.
- `tests.test_mcp_week.test_get_values_week` and `tests.test_connector_roundtrip` (2 tests): the same
  3 failures on the previous head without this change. On origin/main the round-trip pair also fails
  (find_trades_league route `#find-league` vs `#find-trade`) and the week test passes.
- `tests/jeg-1224/shared_link_regressions.mjs` (14 failing specs, 0 differ from the record) and
  `tests/jeg-1224/harness_mutations.mjs` (18 of 20 as expected): identical with and without the change.
- `tsc --noEmit --strict` on `tools.ts` (bundler resolution): no errors in `tools.ts` or `names.ts`,
  before or after.

### Claimed, not confirmed

- The round-trip and week failures are outside this change (route expectation and the local week
  build); not investigated here.
- Live behaviour: not checked; nothing was deployed.
