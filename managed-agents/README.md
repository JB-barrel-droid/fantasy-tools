# Managed Agent (`session:cma`): RETIRED

**Retired by Jeremy on 2026-10-27; torn down under JEG-1173.** Don't apply these files, create deployments or start sessions from here. Work is split between Codex and Claude by the `codex` / `claude` Linear labels (see `HANDOFF.md`). The `session:*` labels were retired in Linear on 2026-10-28, so the agent's queue no longer exists.

Teardown state (2026-10-29): PRs #1001 and #1002 merged on 2026-10-27, nothing to close. `ddf-queue` was still firing hourly through 2026-10-29 15:00 UTC; each run stopped without work after reading JEG-1173. Pausing both deployments needs Jeremy's Anthropic account (no key in agent sandboxes): `ant beta:deployments pause --deployment-id depl_0194kATtQ6xdicZiw7wnkzmT` and `--deployment-id depl_01PE9v6akCH9muDEUwxdioSs`. Pause only; deleting a deployment, agent, environment or vault waits for Jeremy's yes. The JEG-1173 ticket records whether the pause has happened.

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
