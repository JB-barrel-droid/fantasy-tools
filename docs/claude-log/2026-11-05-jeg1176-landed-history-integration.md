## 2026-11-05 - JEG-1176 landed-history integration

Contract: integrate the history loader with main
`96bcd199bb3802db7958e9874f387d039cf548fc`, including the landed #1310
capture-clock fix, without changing pricing or value methodology.

### Verified (check named)

- A normal merge applied without conflicts. The main delta from
  `e36c26429087ff97ba9828e904ca789c4c46c27a` contains the #1310 history
  capture helper, its regression and log, and the source-vintage hash record.
- The capture code and regression blobs match landed commit
  `12061ea81c972062f344586e43a827d8a7259588` exactly. The helper uses
  `parse_iso_timestamp` and the New York calendar; only `week_column_pull`
  accepts a label matching either UTC or New York. Other evidence rules and
  `week_of_day` remain unchanged.
- Pricing code, the Python reference, the `priced > 100` assertion and the
  original rail/footer source and test blobs remain unchanged.
  `git diff --check` passes for the integration delta.
- A main check snapshot at 05:02 UTC reported 13 successes, one skipped check
  and a failed `probe` in Source change probes, at `Dispatch full ingests`.
  This snapshot does not establish green main or fresh fixture/live recovery.

### Claimed, not confirmed

- The imported pull-clock regression and required-browser `make validate`
  must qualify the resulting exact head. The contract suite follows successful
  validation, sequentially through the baseline attribution wrapper.
- Prior-head results do not qualify this revision. Current-main green,
  exact-head remote CI, delta review and fresh chain/live acceptance remain
  separate gates.
