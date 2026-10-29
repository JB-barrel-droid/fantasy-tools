## 2026-10-27 - Edge drift check (JEG-1049, session:cma)

Contract: add a scheduled, read-only check that fails when the deployed Supabase edge functions `mcp` and `get-values` are behind `main` (option 2 of JEG-1049: no deploy credentials in CI, no secrets, never deploys).

### Verified (check named)
- Matching tools exit 0; a missing tool plus an extra tool exit non-zero and name both; get-values without chart fields exits non-zero; an unreachable endpoint exits 2 with a one-line message and no stack trace: `python3 -m unittest tests.test_edge_drift_check` (node fake server in `tests/node/edge_drift_check.mjs`).
- Tool names on main are read by importing `TOOLS` from `supabase/functions/mcp/tools.ts` with `--experimental-strip-types`, the way `tests.test_mcp_remote` does: 9 tools found.
- The nearby MCP test still passes: `python3 -m unittest tests.test_mcp_remote`.
- The sandbox cannot resolve supabase.co: running `tools/edge_drift_check.mjs` here printed `EDGE CHECK ERROR ... ENOTFOUND` and exited 2.

### Claimed, not confirmed
- Behaviour against the real production endpoints (default URL `https://iskiybsimubiujwuchsl.supabase.co/functions/v1/...`) is unconfirmed: no network to supabase.co here. To be verified by a `workflow_dispatch` run of `edge-drift-check.yml` after merge; it should fail while production is behind main.
- That production `mcp` accepts `tools/list` without `initialize` and replies JSON: inferred from `supabase/functions/mcp/index.ts` / `rpc.ts` (stateless), not observed live.
- The workflow YAML has not been run on GitHub; the cron time (12:40 UTC) was picked arbitrarily.
- Not wired into `make test-core` (it has shard-mirroring guards); the Python test is run by name only.
