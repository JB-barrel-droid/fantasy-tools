# Managed Agent (`session:cma`)

Hosted Claude Managed Agent that works the `session:cma` Linear queue, turns Jeremy's ideas into tickets, and reports its own usage (JEG-1173). Decisions are quoted on the ticket.

- `agents/ddf-lead.md` - Opus 5.5 lead: claims up to 3 non-overlapping tickets per run, one git worktree each, merges in order on green gates. Its Markdown body is the system prompt.
- `agents/ddf-builder.md`, `agents/ddf-reader.md` - Sonnet 5.5 and Haiku 5.5 workers it delegates `T2 build` / `T3 light` work to.
- `environments/ddf-cloud.yaml` - cloud sandbox, `limited` networking.
- `vaults/ddf.yaml` - vault container only; secrets are loaded from macOS Keychain by `scripts/setup-credentials.sh`.
- `scripts/create-deployments.sh` - `ddf-queue` (every 2 hours) and `ddf-weekly-usage` (Mondays 7am Central), $50 cap per run.
- `scripts/idea-session.sh` - open an idea-intake session in your terminal.
- `claude-lock.json` - resource IDs written by `ant apply`; commit it, or the next apply creates duplicates.

Change the agent: edit the file, then from this directory run `ant apply --dry-run -v <files>` and `ant apply <files>`.
