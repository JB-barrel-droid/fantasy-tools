## 2026-10-30 - JEG-1376: unmatched player names get no verdict in compare_trade or read_state

Contract: check whether the connector's compare_trade and read_state still score a name that
matches no player as 0 and give a verdict (ticket example: "Gibbs" vs "Hubbard, Zzyzx Notaplayer"
returned "team B ahead by 35.6"). Fix what is left and add a test that fails before and passes after.
PR #1231, branch `claude/JEG-1376`.

Finding: #1200 (JEG-1124, 6b33b67) had already fixed both tools. compare_trade stops with the closest
names, and read_state gives the list holding the unmatched name no total. This PR pins that with the
ticket's own example and makes read_state's "Could not match" line name each player the way
compare_trade does.

What changed:

- `supabase/functions/mcp/tools.ts`: `resolveEntry` keeps its `matchName` result (`hit`). A new
  `missLabels` builds read_state's "Could not match" entries:
  - a misspelled name gets its closest names (`closestNames` with the kept hit, so nothing is matched
    twice), for the first 5 such names only;
  - an ambiguous name gets every player it fits (`could be ...`);
  - a key-only miss is named alone.
  `lists` in structuredContent keeps its old shape (`input`, `player`, `note`). No value math change.
- `tests/node/mcp_unmatched_check.mjs` (new, run by `tests/test_mcp_remote.py`): the ticket's trade
  through compare_trade and read_state under standard, half_ppr and ppr, plus read_state edge cases
  (ambiguous name, key-only miss, unmatched target, 8 junk names with the closest-names cap).
- `tests/node/mcp_remote_check.mjs`: the read_state "Could not match: Nobody." assertion now allows
  the closest-names suffix. The assertion pinned the exact text, and this ticket (Jeremy's) changes
  that text to name the closest players; the new test requires the suffix.

No deploy. It goes live only with the next mcp redeploy, which needs Jeremy's yes.

### Verified (check named)

- Fails before #1200: `tests/node/mcp_unmatched_check.mjs` copied into a worktree at 6f3010b fails.
  compare_trade replied "Verdict ... team B comes out ahead by 35.4". With the compare part removed,
  read_state failed `get (no total: 1 name not matched)` because it printed `get (total 27.0)`, which
  scored the unmatched name as 0.
- Fails on main eb9a75d with only the test added: "read_state did not name closest players".
- The edge cases fail on the PR's first commit ffbe8a2 and pass on 37fd663.
- Passes on 37fd663:
  - `node --experimental-strip-types tests/node/mcp_unmatched_check.mjs` and
    `tests/node/mcp_remote_check.mjs` print `ok`;
  - `python3 -m unittest tests.test_mcp_remote tests.test_connector_inventory` is OK (inventory:
    expected failures=1, as before).
- CPU on a pasted state of 160 junk names against `data/fixtures/current/players.json` (1,161
  players), one local run each (scratch script): main 5.4 s, ffbe8a2 about 15 s, 37fd663 5.9 s.
- One independent Claude review (subagent): approve. Its findings were fixed in 37fd663:
  - repeated matching and an uncapped scan;
  - made-up closest names for key-only misses;
  - ambiguous names cut to three and labelled as misspellings;
  - edge-case tests.

### Claimed, not confirmed

- Most of the 5.4 s on main for a 160-junk-name state is the per-entry `matchName` cost that was
  there before this change. Not measured against the edge function's CPU limit and not addressed here.
- The duplicate "Closest" text on a row line and the summary line only adds reply size. Not changed.
