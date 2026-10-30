## 2026-10-29 - JEG-1269 correct retired-agent pause evidence (PR #1107)

Contract: fix the two findings in review a36720e7 on #1107 @ cd88d47. Silence
is no longer treated as proof of a pause, and #1107 stops editing shared
protocol files. Docs, a static test and the Makefile only; nothing paused,
deleted, executed or deployed.

Correction to `2026-10-29-jeg-1173-cma-teardown.md`: its stopping test (no new
run comment after the next top of the hour) is withdrawn. Missing comments are
corroboration only.

### Verified (check named)
- `tests.test_managed_agents_retired` (static, executes no script): 3 tests
  pass on this branch. Against `origin/main`'s `managed-agents/` tree, 2 of 3
  fail (no lib.sh guard, README lacks the unverified-state text).
- `tests.test_doc_staleness` still passes.
- A `ddf-queue` run fired at 16:05 UTC on 2026-10-29 (running comment on
  JEG-1173), after Jeremy reported at about 15:20 UTC that his Console
  Deployments page was empty.
- `AGENTS.md` and `HANDOFF.md` are back to their merge-base content on this
  branch. The cma-retirement hunk for them was posted on JEG-1218 as a
  separate patch for Codex; it applies cleanly (`git apply --check -3`) on
  #1073's head `fef356ee`.

### Claimed, not confirmed
- Both deployments still exist and are unpaused in workspace
  `wrkspc_01A4qjuy7wHWubEvx73fHKym`. Nobody has run an authenticated read;
  the operational state is UNVERIFIED.
