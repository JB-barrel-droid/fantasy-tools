## 2026-10-29 - JEG-1258 (part of JEG-1061): get-values logging contract tests

Contract: an offline, new-file harness that specifies and checks the fresh-compute and rate-limit log
events Jeremy asked for on JEG-1061, records the current handler's exact failing-before state, and
hands the get-values owner a narrow hook proposal. No runtime, limiter, workflow or HANDOFF change.

### Verified (check named)
- `--self-test` exits 0: a correct log is accepted (string and object forms) and 17 mutations are caught.
- Plain run on main b8630697 (clock pinned to 2026-10-29 15:00Z; same output with it at 2026-09-10, 2026-12-20 and 2027-02-10) with the committed dist and with a freshly synced dist exits 1 with exactly
  the 5 violations in `tests/fixtures/jeg_1061_logging/expected_failures_before_hook.json`; output md5
  identical over 3 runs; all statuses held (11th compute 429, 31st request 429, cache, other key, reset).
- `python3 -m unittest tests.test_jeg_1061_logging_contract -v`: 2 tests OK (about 5 s).
- Scratch copy of main + `hook-proposal.patch`: full contract passes (exit 0); with the recorded list it
  reports 5 UNEXPECTED PASS (exit 1); with `[]` it passes.
- PR #1024 head 179288b (JEG-1179, worktree in scratch): same 5 violations; + `hook-proposal-on-pr1024.patch`
  passes.
- Scratch mutations: compute limit 11 and general limit 31 give harness failure exit 2; hook logging
  default computes, cache hits, an `ip` field, or a compute 429 labeled general give exit 1 with named
  violations.

### Claimed, not confirmed
- Supabase edge logs show a `console.log` JSON string as a searchable event; not checked live (no
  Supabase or production access in this ticket).
- Nothing more. Note: `tests/test_jeg_1061_logging_contract.py` is not in any CI target yet, because
  `make test-unit-modules` lists modules explicitly and the Makefile is outside this ticket's paths;
  adding `python3 -m unittest tests.test_jeg_1061_logging_contract` there is left to the coordinator.
