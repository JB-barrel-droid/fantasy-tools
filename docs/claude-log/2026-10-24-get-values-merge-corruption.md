# get-values did not parse on main: stray `\n\1` from a merge

**Date:** 2026-10-24

## What happened
Found while preparing to deploy the MCP find_trades work (JEG-1037) and the league pricing (JEG-1031, #898).
`supabase/functions/get-values/index.ts` on main had literal `\n\1` text in four places (request parsing
and the `mapLeague` call), and `league` / `rawLeague` were never declared. `deno check` reported a parse error.
Introduced in the merge of #896 into #898 (commit ae50db63); #898 reached main that way. The live Supabase
`get-values` (version 3) is the older deploy and was not affected; nothing was deployed from main.

## Changed
- Rebuilt the request parsing so both features work: `include=charts` (JEG-1037) and the `league` section (JEG-1031).
- `tests/test_edge_functions_parse.py`: fails on a stray `\n\1` / `\1` artifact in any edge function source,
  and `deno cache --no-check` parses both entrypoints.

## Verified
- Negative test: reintroducing `\n\1` in get-values makes both new tests fail.
- `deno check` on get-values and mcp: only the 3 type errors that were already on main.
- Local run of get-values against the live site: `include=charts` returns 734 players with chart values;
  `league={"roster":{"RB":3}}` returns `league_custom: ["roster"]`.

## Not verified
- Deployed behavior (deploy follows this PR).
- That the three existing type errors in mcp/index.ts are unrelated to this fix (they predate it).
