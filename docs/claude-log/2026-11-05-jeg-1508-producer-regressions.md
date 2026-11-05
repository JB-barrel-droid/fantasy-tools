## 2026-11-05 - Producer compatibility and roster grain (JEG-1508 / JEG-1416)

Contract: correct diagnostics against PR #1249 source
`2c7a915be6e39b043abec04243e97678669f5b0d` on the existing remote branch
`muse/JEG-1196-contract-1-1`. Own only producer/contract/tests and their fixtures;
this unique log is the required session receipt. No archive, renderer, board
implementation, shared integration, or Supabase edit. No broad suite rerun.

### Verified (check named)
- Fresh ticket/PR reads found no competing implementation owner or newer head.
  The old generated worktree is untouched; corrections use a clean isolated
  checkout. Correction child JEG-1508 was created on the same parent/branch/PR.
- New `tests.test_weekly_inputs_compatibility` against the original producer:
  9 tests, 8 failing assertions/subcases and 1 error. It reproduces the real
  board's unknown-source rejection and the frozen base reader's two `leg.id`
  errors, ambiguous team/kickoff selection, and missing/contradictory roster
  grain. Logs: `/tmp/jeg-1508-before-final-regressions.log`.
- `python3 -m unittest tests.test_weekly_inputs_contract
  tests.test_build_weekly_inputs tests.test_weekly_inputs_compatibility`:
  129 tests pass, exit 0 (`/tmp/jeg-1508-focused-final.log`).
- The compatibility fixture is a byte-for-byte copy of the actual 1.0 reader
  from `ad0cfc3a:pipelines/lib/weekly_inputs_contract.py`, blob
  `0a945477bcd28ec7df85df16d88308f03e7d9921`. It is not a simulated reader.
- Flag-free artifacts omit the optional roster/slate legs and now build through
  the actual board and validate with the actual base 1.0 reader. Supplying an
  empty optional input still declares an unavailable leg with null cells.
  The two changed old assertions assumed mandatory new legs; they now assert
  the intended optional-leg behavior. Existing stale/partial/zero cases remain.
- Roster file season/week are required; explicit row grain must agree with
  them. Rejected rows are counted, not relabeled current. Bare row lists cannot
  invent a file grain. Team disagreement produces one conflict, a null team and
  a null kickoff independent of row order. Agreed percentage zeros survive;
  conflicting percentage values remain null with reasons.
- Bounded existing board classes plus the focused modules: 208 tests,
  207 pass and one failure in `Determinism` (see below). No consumer assertion
  was edited or suppressed. Log: `/tmp/jeg-1508-consumers.log`.
- Actual board CLI succeeds. JSON comparison against its golden proves the
  only difference is `$.inputs.weekly_inputs.sha256`, from
  `b725cf300623a9fbe9b9b0c0779f710bf3fd42146400688521fd86bb6ca11655` to
  `81e682e289017a0a0661af19cbbc0c5a3b27738a49296ea12a318e422142b3a3`.
  `/tmp/jeg-1508-board-hash.patch` is an unapplied one-field patch for the
  consumer fixture owner. That shared fixture is outside this lane's scope.
- Scoped `git diff --check` passes. The producer golden changed only by removal
  of the two absent optional legs and their row cells.

### Claimed, not confirmed
- Full opt-in artifacts still use new roster/slate leg IDs; an unchanged 1.0
  reader cannot accept those IDs, and the existing board does not consume them.
  Flag-free compatibility is verified; blanket forward compatibility is not.
  A wire-format decision is pending: use extension fields for warning-only old
  reads, or retain the present leg format and require a 1.1 reader for opt-in
  data. No wire-format change is inferred from the diagnostics.
- The board golden hash update belongs to its owner. Until applied, the existing
  byte-for-byte consumer test remains red; this is not a green full-suite receipt.
- Exact-head full CI and independent review remain outstanding. Fixture paths
  retain the deterministic higher review-risk floor. Diagnostics are not review.
- Automatic approval review denied the detailed new claim comment on JEG-1416,
  citing disclosure of internal diagnostic/workflow details to Linear. It was
  not retried, copied to another destination, or worked around. The prior PR-body
  publication denial also remains in force; no PR body write was attempted.
