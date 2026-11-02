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
| Mac Claude | `mac-claude/` |
| cloud Claude | `claude/` |
| Codex | `codex/` |
| OpenCode | `opencode/` |
| Pi | `pi/` |
| Muse | `muse/` |
| Console worker | `console/` |

The PR lane workflow validates the body and head branch on opening, body edits,
new commits, reopening and readiness changes. No path filters exempt docs.
It runs trusted base code, without checking out PR code or using API quota on PR events.

`.github/lane-check.json` enforces attribution for new PRs. PRs opened before
**2026-11-02 03:56:10 UTC** (the start of the Mac update) permanently pass with
an annotation warning if attribution is invalid. This keeps existing open PRs
safe throughout tonight's window and later edits. Missing or malformed opening
times do not qualify for grandfathering. The cutoff does not move with the clock.

The read-only manual workflow rechecks all open PRs and reports in its own run;
it does not write PR check statuses. Making the check required remains Jeremy's
repository-settings decision.

`lanes.pr_attribution.parse_lane` returns builder, model and coordinator;
`check_prefix` validates the head branch. The retired `lanes/protocol.py` only
accepts MiniMax outbox adapters, so its lane set is not reused or expanded.

JEG-1429's cost/throughput ledger is absent from the checked origin/main.
When it lands, use `parse_lane(pr_body)` for lane counts (and report missing or
invalid historical attribution as unknown); do not infer the builder from login.

AGENTS.md's prefix rule follows after PR #1250 merges; this change deliberately
leaves that file to its current owner.
