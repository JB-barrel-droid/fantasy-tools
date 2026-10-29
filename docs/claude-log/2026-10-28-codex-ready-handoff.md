## 2026-10-28 - Codex-ready HANDOFF.md on main

Contract: Jeremy asked for a takeover handoff in GitHub so Codex (or any
successor) can continue if the Claude session's usage runs out. Adds root
`HANDOFF.md` on `main` (which `AGENTS.md` already points to), folding in the
PM handoff from branch `banana/agent-handoff`. Docs only.

### Verified (check named)
- Live build tag `tv-20261028-0141-abc4675`: `trade-chart-build` meta tag on the live page at 03:00 UTC.
- Last successful Deploy dashboard run is `abc4675`; later runs cancelled or pending: `gh api .../actions/workflows/pages.yml/runs`.
- `main` not protected: `gh api .../branches/main/protection` (404 Branch not protected).
- Live MCP returns no players: DDF `get_player_value` "Josh Allen, Bijan Robinson" half PPR 12 teams returned `player: null` (as_of 2026-10-26).
- PR #987 closed without merging: `gh api .../pulls/987`.
- No .xlsm/.xlsx/.bas/.ps1/.bat/.cmd files tracked: `git ls-files`.
- Unit tests OK on Python 3.13.17: test_rank_guard, test_doc_staleness, test_comparison_source_integrity, test_spec_reference_value_pipeline.
- Open PRs, In Progress and In Review tickets: GitHub REST pulls list and Linear list_issues at 03:00 UTC.

### Claimed, not confirmed
- Mac, Linux box and wrapper paths, and run patterns come from the prior PM handoff (Ba-Nana), not checked this session.
- Jeremy's decisions and preferences come from his chat words recorded in Claude memory; ticket wording is authoritative.
- Windows build commands are unknown; whether an Excel/VBA workflow exists for this project is unverified.
