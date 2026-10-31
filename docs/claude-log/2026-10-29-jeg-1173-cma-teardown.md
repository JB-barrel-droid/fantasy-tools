## 2026-10-29 - JEG-1173 tear down the retired Claude Managed Agent

Contract: record the retirement of `session:cma` in the repo, check what became
of its PRs, and make its scripts refuse to run. Pausing its two deployments is
Jeremy's step (it needs his Anthropic account).

### Verified (check named)
- PR #1001 and PR #1002 are merged (GitHub PR API: `merged: true`, both
  2026-10-27). Nothing to close.
- PR #1003 (`cma/JEG-1049`) is still open; PR #1011 (`cma/JEG-885`) merged
  2026-10-28 (GitHub PR API).
- Remote branches `cma/JEG-1049` and `cma/JEG-925` exist (`git ls-remote`).
- `bash managed-agents/scripts/create-deployments.sh` exits 1 with the
  retired message before touching `ant` or Keychain.
- `ddf-queue` fired hourly through 2026-10-29 15:00 UTC and stopped without
  work each time (running comment on JEG-1173, last edit 15:02 UTC).
- The deployments are not Claude Code routines: `list_triggers` on this account
  shows no `ddf-queue` or `ddf-weekly-usage`.

### Claimed, not confirmed
- The deployments are still enabled; this sandbox has no key for that
  Anthropic workspace, so their state was not read directly.
