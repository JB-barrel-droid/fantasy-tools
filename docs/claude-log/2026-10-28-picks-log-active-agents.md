## 2026-10-28 - Picks log copy and active agents in HANDOFF.md

Contract: Jeremy asked to copy the relevant decisions from the Claude-only
picks log into GitHub and to keep HANDOFF.md current with which agents and
automated sessions are active and how to stop or coordinate with them. Adds
`docs/picks-log.md` (indexed in `docs/README.md`) and two HANDOFF.md sections.
Docs only.

### Verified (check named)
- 12 picks copied verbatim from the main-chat log as relayed at 03:22 UTC.
- Open PRs and authors: GitHub REST `pulls?state=open` at 03:25 UTC.
- Running and queued workflows: GitHub REST `actions/runs?status=in_progress|queued`.
- pg_cron jobs and schedules: `select jobname, schedule, active from cron.job` (read-only) on the production project.
- Last successful Deploy dashboard run is `fde5b9e`: GitHub REST pages.yml runs, status=success.
- Managed agent schedules and pause command: `managed-agents/README.md`, `scripts/create-deployments.sh`.

### Claimed, not confirmed
- The overnight routine's times, limits and stop date, the lane list, and the disabled routines come from the coordinator session's view of Jeremy's app, not a check here.
- Whether Ba-Nana, Muse, the managed agent and the Cursor agent are running now is inferred from PR activity, not checked on their hosts.
