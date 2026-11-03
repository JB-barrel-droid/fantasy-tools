## 2026-11-03 - JEG-1323 functional main integration

Contract: integrate functional main after PR #1255 merged; preserve the trade
readout, existing fixtures and generated main work. Parent owns release.

### Verified (check named)

- Live PR #1174 and remote ref remained at `39cb858451ac240cd8d80f75e69bdbaf329fc47b`;
  no newer ticket writer claim appeared. Resumed the existing isolated worktree.
- Normally merged pinned main `832a18d90704ffa547ad5aae22e179e28843f3f1`,
  including #1255 / `4c60f8fd0e631f3fb961174f9be8f9f77ab67796`, JEG-1176
  weekly-transition test corrections, a recorded pipeline hash and operational
  artifacts. Automatic merge was conflict-free; no resolution or feature edit.
- Readout/finder code, both JEG-1323 golden/sentinel fixtures and the shared
  front-door identity fix are unchanged. `git diff --cached --check` passes.
- Focused integration command: 132 tests PASS in baseline attribution,
  weekly-input building/contracts, DST deadlines, render/validate shard guards,
  readout rows and first-half parity. Changed-workflow guards also pass:
  `tests.test_draft_ci_workflows`, `tests.test_preview_workflow_matches_pages`
  and `tests.test_ci_speedup_workflows`. Logs are
  `/tmp/jeg1323-nov03-focused.log` and `/tmp/jeg1323-nov03-workflow.log`.
- No full local validation job was started, repeated or cancelled. Prior local
  validation processes had already completed naturally before this integration.

### Claimed, not confirmed

- Fresh exact-head CI and independent delta review remain required. Prior-head
  check marks and reviews do not clear this integration.
- No merge, deploy, production change, deletion, access change or Supabase action.
  Previously denied optional PR/Linear publication was not retried.
