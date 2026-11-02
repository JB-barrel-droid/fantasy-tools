## 2026-11-01 - JEG-1472 scoped release-window pause

Contract: let the merge gate pause only the frequent bot writers on main for at
most 2 hours through one reviewed switch workflow, so daily snapshots keep
publishing and each release window needs no PR toggle (option A of the
release-pause proposal). Nothing is live: the PR is a draft, the control file
still ships `paused:false`, and the switch workflow was not dispatched.

### Verified (check named)
- Guard scoping: `tests/test_main_write_switch.py::ScopeDecisionTest` and
  `ScopedGuardCliTest` pass. A daily writer is not paused by a scoped pause; a
  writer outside the scope publishes while the pause is on; an expired scoped
  pause restores publication (decision function and the real guard script
  against a local bare remote).
- Existing guard behaviour: `tests/test_main_write_guard.py` still passes with no
  assertion changed. One exemption was added to its "every git commit is
  guarded" scan, naming `main-write-pause-switch`, because the switch must run
  during a pause.
- Switch validation: `SwitchBuildTest` shows 121 minutes, 0, an empty or
  multi-line reason and a daily or unknown writer in the scope are refused, with
  nothing written, and that 120 minutes is accepted.
- Switch workflow boundary: `SwitchWorkflowTest` (plain-text checks, and a PyYAML
  parse) shows the only `git add` is the control path, the push is an explicit
  `HEAD:${GITHUB_REF}` refspec, the push is preceded by a check that the diff
  against main is only the control path, validation runs before the token is
  minted, and the only secrets named are the two existing App secrets.
- Fail-before: with `pipelines/main_write_guard.py` restored to origin/main
  (dd26deff), 17 of the 21 tests in `tests/test_main_write_switch.py` fail (3
  assertion failures, including the daily-writer and outside-scope guard-script
  tests, and 14 errors where the old guard has no `writer` argument, scope
  allowlist or switch module). The 4 that pass: the three workflow-file tests
  (they fail on origin/main only because the workflow file does not exist there)
  and `test_expired_scoped_pause_restores_a_frequent_writer`, which passes on the
  old guard too (an expired pause already restored publication) and is kept as a
  regression pin; the function-level expiry test does fail before.

### Claimed, not confirmed
- The workflow has not run on GitHub. `actionlint` is not installed in this
  environment; the file was only parsed with PyYAML. CI's pinned actionlint step
  covers it.
- The pushed control reaching a real writer run on main with the pause on is
  untested. The smallest real test is a 15-minute pause at a quiet time, which
  needs Jeremy's yes.
- Whether the pause commit's own push triggers Pages and other workflows was not
  checked. Other App pushes to main already do.
- `espn-supabase-sync` and `espn-history-probe` are classed as daily on the
  ticket's word; their schedules were not re-checked.

## Mac integration, 2026-11-02 UTC

Jeremy requested completion for the Nov 2 6 AM CT window. Merged origin/main
951f95df0ad4059701b4b18574b1e4dfdba4a877 normally; no conflict, force push,
HANDOFF edit, value-math edit, production dispatch, pause or Supabase operation.

Verified: 86 focused tests passed (guard, switch, writer workflows and
credentials, draft CI, rebuild-chain). actionlint passed for both changed
workflow files with shellcheck/pyflakes disabled as in CI.

Not confirmed: full make validate stopped in sync because installed Playwright
cannot find chromium_headless_shell-1208. No automatic retry. Generated tracked
output restored; untracked build output remains local and is excluded.
CI must establish the full gate on the pushed head; independent review remains
required. No review of this work was performed by its author.
