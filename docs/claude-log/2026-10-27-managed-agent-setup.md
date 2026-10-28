## 2026-10-27 - JEG-1173 Claude Managed Agent (session:cma)

Contract: define a hosted Managed Agent that works the Linear queue in parallel, merges on green gates, takes Jeremy's ideas as tickets, and manages its own usage, with its config version-controlled in `managed-agents/`.

### Verified (check named)
- `ant apply --dry-run -v` on the agent, environment and vault files prints a clean create plan (5 resources) with the fields as written.
- `bash -n` passes on every script in `managed-agents/scripts/`.
- `session:cma` label exists in the Linear `Session` group (created via Linear MCP).

### Claimed, not confirmed
- Linear MCP (`mcp.linear.app/mcp`) and GitHub MCP (`api.githubcopilot.com/mcp/`) accept static bearer tokens; confirmed only at the first smoke-test run.
- `make validate` and the contract test run in the cloud sandbox with package-manager access; not yet run there.
- Resources not created yet: needs `ant auth login`, Keychain secrets, `ant apply`, then a manual deployment run.
