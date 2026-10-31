# 2026-10-30 JEG-1124: ambiguous names stop a compare; finder scans list them

Session: cloud thread "Overnight board burn-down" (Jeremy instructed the sweep). Took JEG-1124 over
from the stopped Codex lane (last heartbeat 2026-10-28 19:23 UTC). Branch `claude/JEG-1124`.

## What changed

- `supabase/functions/mcp/tools.ts`: ported `docs/claude-log/2026-10-28-jeg-1124-ambiguity.patch` to
  current main by hand (it no longer applied). compare_trade now stops with a tool error naming each
  candidate ("\"Allen\" could be Josh Allen, Keenan Allen ... Ask the user which player they meant")
  instead of totalling without the name. find_trades and find_trades_league keep going, count the
  name ("1 fits more than one player (left out; ask which)") and list it with its candidates in
  `mine.ambiguous`, `theirs.ambiguous` and `perOpponent[i].ambiguous` (absent when every name is clear).
- `tests/node/mcp_remote_check.mjs`: the patch's assertions (compare stop, finder and league counts).
- Two connector tests that went red on main, fixed here because they are the same test file and suite:
  - The league-link check pinned `shown === 4`. #1178 (JEG-1324) made each row's fit reason longer,
    so 3 rows fit the same budget. The rule it pins (JEG-1329 pick B: the link costs no rows) still
    holds; the check now asserts that the rows shown would not fit if the link were counted.
  - `tests/test_connector_inventory.py` still said find_trades_league links to `#find-trade` and
    listed `#find-league` as unresolved. #1175 (JEG-1329) moved the link to `#find-league`.

No deploy. The connector only changes live after an mcp redeploy, which needs Jeremy's yes.

## Verified (check named)

- `python3 -m unittest tests.test_mcp_remote`: OK with the change. Without the tools.ts change the
  new assertions fail (find_trades `mine.ambiguous` deep-equal).
- `tests.test_mcp_remote` on plain main fails at "the league link costs no trade rows" (3 !== 4);
  bisected: green at 761569fe, red from dd9157c1 (#1178).
- `python3 -m unittest tests.test_connector_inventory`: OK (expected failures=1) after the inventory fix;
  failed on plain main.
- `node tests/node/batch_trade_check.mjs`, `node tests/node/connector_fit_check.mjs`: pass.

## Claimed, not confirmed

- `tests.test_mcp_week.test_get_values_week` fails here (razzball missing from the week sources in a
  local dist build). Not touched by this change; likely this container's local build, not checked in CI.
- Unmatched (not ambiguous) names in compare_trade and read_state still give a total with a warning,
  as the existing tests pin. Changing that is a rule change, asked on JEG-1124.
