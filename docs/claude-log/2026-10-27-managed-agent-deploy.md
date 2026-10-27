## 2026-10-27 - JEG-1173 managed agent: deployments, board hygiene, takeover

Contract: make the `session:cma` agent live (vault, deployments, smoke run), and add the board cleanup and takeover rules Jeremy asked for.

### Verified (check named)
- Vault `vlt_011CgT6uFXb2P9VSqWaBUzYC` lists GitHub, Linear, OpenRouter, MiniMax credentials (`ant beta:vaults:credentials list`).
- Each key authenticated against its own service before loading: GitHub repo + pulls + actions 200, Linear `viewer` = Jeremy Burstyn, OpenRouter `/key` limit 50, MiniMax `/v1/models` listing M3 and M3.1-Flash.
- `ddf-queue` and `ddf-weekly-usage` deployments created; `upcoming_runs_at` matches every 2 hours and Monday 07:00 America/Chicago.
- Smoke session `sesn_01PjnfyGkQLa9khUH1jFwPpA`: Linear MCP calls auto-allowed and returned data (session event stream).
- `ant apply` updated `ddf-lead` after each prompt change.

### Claimed, not confirmed
- GitHub MCP auth, push and merge from the sandbox, and `make validate` in the sandbox: not yet exercised by a run.
- Board hygiene and takeover rules behave as written: first exercised by the Board cleanup run.
