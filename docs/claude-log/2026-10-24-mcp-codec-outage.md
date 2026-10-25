# MCP make_state / read_state outage: codec 404 on live site

**Date:** 2026-10-24

## What happened
A ChatGPT report: `make_state` failed with "shared state writer is unavailable". Reproduced.
Cause: the MCP function loads `<site>/v2/ddf-state.js` at cold start; that URL was 404 because
the site deploy predated the codec commit (534191ab, 16:21Z). After the deploy, the same call succeeded.

## Changed
- `mcp/index.ts` logs a non-200 codec fetch (was silent).
- `ToolUnavailableError` (subclass of `ToolInputError`): same client text, logged as a dependency outage.

## Verified
- Repro before deploy; success with the report's full rosters after (13 mine / 11 theirs, none unmatched).
- `node tests/node/mcp_remote_check.mjs` ok. `deno check` shows the same 3 errors with and without the change.

## Not verified
- Supabase function not redeployed from this change.
