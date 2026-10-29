# Managed Agent (`session:cma`): RETIRED

**Retired by Jeremy on 2026-10-27; torn down under JEG-1173 (corrections JEG-1269).** Don't apply these files, create deployments or start sessions from here. Every script in `scripts/` exits unless `CMA_ALLOW_RETIRED=1`.

**Which protocol applies.** Work is split between Codex and Claude under the two-agent protocol Jeremy confirmed on 2026-10-28 (JEG-1218, draft PR #1073): `codex` / `claude` labels, Codex coordinates and merges. The `session:*` labels were retired in Linear on 2026-10-28. Until #1073 lands, the `AGENTS.md` rules on `Session` labels, session queues, takeover and Claude merging are obsolete where they conflict with that protocol; this file grants no merge authority.

**Operational state: UNVERIFIED.** The repository guard does not pause anything already deployed. No authenticated read has shown either deployment paused. To close the teardown, from Jeremy's Anthropic account in workspace `wrkspc_01A4qjuy7wHWubEvx73fHKym`:

1. A paused-state read of `depl_0194kATtQ6xdicZiw7wnkzmT` (`ddf-queue`, hourly).
2. A paused-state read of `depl_01PE9v6akCH9muDEUwxdioSs` (`ddf-weekly-usage`, Mondays 7 AM CT).
3. An inventory of active runs/sessions in that workspace showing none doing project work.

Record each with the time it was read on JEG-1173. A missing run comment on JEG-1173 is corroboration only, never proof. Last observed run: `ddf-queue` at 16:05 UTC on 2026-10-29. Jeremy saw an empty Deployments page at about 15:20 UTC that day, so that view was likely another workspace. Pause only (`ant beta:deployments pause --deployment-id <id>`); deleting a deployment, agent, environment or vault waits for Jeremy's yes.

PRs #1001 and #1002 merged on 2026-10-27; nothing to close. The agent's last open PR is #1003 (`cma/JEG-1049`).

The files below are kept as the record of what was deployed.

## As built (historical)

Hosted Claude Managed Agent that works the `session:cma` Linear queue, turns Jeremy's ideas into tickets, and reports its own usage (JEG-1173). Decisions are quoted on the ticket.

- `agents/ddf-lead.md` - Opus 5.5 lead: claims up to 3 non-overlapping tickets per run, one git worktree each, merges in order on green gates. Its Markdown body is the system prompt.
- `agents/ddf-builder.md`, `agents/ddf-reader.md` - Sonnet 5.5 and Haiku 5.5 workers it delegates `T2 build` / `T3 light` work to.
- `environments/ddf-cloud.yaml` - cloud sandbox, `limited` networking.
- `vaults/ddf.yaml` - vault container only; secrets are loaded from macOS Keychain by `scripts/setup-credentials.sh`.
- `scripts/create-deployments.sh` - `ddf-queue` (hourly) and `ddf-weekly-usage` (Mondays 7am Central), $50 cap per run.
- `scripts/idea-session.sh` - open an idea-intake session in your terminal.
- `claude-lock.json` - resource IDs written by `ant apply`; commit it, or the next apply creates duplicates.

Change the agent: edit the file, then from this directory run `ant apply --dry-run -v <files>` and `ant apply <files>`.

Deployments (created by `scripts/create-deployments.sh`, not tracked in `claude-lock.json`): `ddf-queue` = `depl_0194kATtQ6xdicZiw7wnkzmT`, `ddf-weekly-usage` = `depl_01PE9v6akCH9muDEUwxdioSs`. Pause one with `ant beta:deployments pause --deployment-id <id>`; run one now with `ant beta:deployments run --deployment-id <id>`.

Deployments pin the agent version they were created or last updated with. After every `ant apply` that changes `ddf-lead`, re-pin: `ant beta:deployments update --deployment-id <id> --agent agent_0115fHS9Z8D43ah95S6LYAe8`. One-off runs: `scripts/start-session.sh "<title>" "<first message>"`.
