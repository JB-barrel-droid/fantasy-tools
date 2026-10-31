## 2026-10-30 - Retire the legacy local (stdio) MCP server (JEG-1372)

Contract: remove the old locally run MCP server (`mcp-server/`), which described a 0-70 scale and an 85% starter weight that contradict the site and the hosted connector, and point the maintained docs at the hosted `mcp` function only (Jeremy picked A, Oct 29, audit decision 4). The deployed `mcp` edge function is untouched.

### Verified (check named)
- Nothing live pointed at the local server before removal: `rg` over `app/`, `pipelines/`, `supabase/functions/`, `.github/`, `Makefile`, root JSON and shell files found no import, build step or workflow using `mcp-server/`. `app/llm/llms.txt` and `docs/use-ddf-in-claude-chatgpt.md` already name only the hosted URL (`{{MCP_URL}}` / `.../functions/v1/mcp`).
- `tests/test_local_mcp_retired.py`: 4 failures on main (folder exists; HANDOFF.md, docs/README.md and docs/values-endpoint.md mention it), passes after.
- `tests.test_doc_staleness`, `tests.test_mcp_remote`, `tests.test_llm_surfaces`: pass.

### Claimed, not confirmed
- `make test-core` stopped at `tests.test_week_history` because Playwright is not installed in this cloud container (`ModuleNotFoundError: playwright`), unrelated to this change; full CI on the PR is the check.
