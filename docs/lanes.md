# PR lane attribution

Every PR, including docs-only PRs, identifies its builder, model and coordinator.
Owner: JEG-1453. Last verified: 2026-10-31.

Use exactly one visible, standalone line (outside comments and code fences):

```text
Lane: built by Codex (gpt-6.1-sol); coordinated by Claude Duet; review pending.
```

Replace the model, coordinator and review status with the actual participants.
The builder is who produced the change, regardless of the GitHub login or coordinator.

| Builder | Required branch prefix |
| --- | --- |
| Claude | `claude/` |
| Codex | `codex/` |
| OpenCode | `opencode/` |
| Pi | `pi/` |
| Muse | `muse/` |
| Console worker | `console/` |

The PR lane workflow validates the body and head branch on opening, body edits,
new commits, reopening and readiness changes. No path filters exempt docs.
It runs trusted base code, without checking out PR code or using API quota.

`.github/lane-check.json` enables `warn_only` during the seven-day rollout,
ending **2026-11-07 at 16:30 UTC** (10:30 AM Central). At that instant the
same check automatically returns failure for invalid attribution, even while
`warn_only` remains true. Setting the flag false enforces immediately. Existing
PRs need the line and a matching branch before their next check after that date.
If rollout lands later than October 31, the coordinator should move the deadline
to preserve seven days of warnings. No scheduled job retroactively reruns PRs.

`lanes.pr_attribution.parse_lane` returns builder, model and coordinator;
`check_prefix` validates the head branch. The retired `lanes/protocol.py` only
accepts MiniMax outbox adapters, so its lane set is not reused or expanded.

JEG-1429's cost/throughput ledger is absent from the checked origin/main.
When it lands, use `parse_lane(pr_body)` for lane counts (and report missing or
invalid historical attribution as unknown); do not infer the builder from login.

AGENTS.md's prefix rule follows after PR #1250 merges; this change deliberately
leaves that file to its current owner.
