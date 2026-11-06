## 2026-10-31 - Weekly-inputs contract 1.1: roster and slate legs (JEG-1416, child of JEG-1196)

Contract: one bounded slice on branch `muse/JEG-1196-contract-1-1` (base
origin/main 51557a5), local commits only. Schema `weekly-inputs` 1.1.0,
additive: a `roster` leg (ESPN rostered % and adds trend) and a `slate` leg
(kickoff time per team for the game week), with validator, producer, fixtures
and contract doc updated. No value math, no waiver-board builder changes (the
builder source flip belongs with/after PR #1239), no push, no PR.

### Verified (check named)
- Tests first: commit `aec60921a` adds the cases; run before implementing,
  every new behavior case failed (contract: `leg.id` on the new legs and the
  1.0.0 version constant; producer: argparse refused `--espn-roster` /
  `--slate`). The 1.0-compatibility case passed before and after, as a guard.
- `python3 -m unittest tests.test_weekly_inputs_contract
  tests.test_build_weekly_inputs`: 115 tests, 1 failure — the pre-existing
  `test_freshness_rule_matches_check_reference_freshness`, red on the base
  before this slice (that file no longer contains the `one_week_behind`
  literal). The 3 producer golden failures also present on the base are gone:
  the regenerated golden differs from the old one only in schema version, the
  roster/slate legs and reports, and the alias-file hash (the committed
  golden's hash was stale against the committed alias file).
- One assertion in the tests-first commit was itself wrong and is corrected
  in the implementation commit: the slate-conflict case adds a second game
  for team AAA against EEE, not DDD (a DDD game would conflict DDD too, so
  the count is 1 only with a fresh opponent).
- Contract CLI on the new fixtures: `tests/fixtures/weekly_inputs/valid/
  roster_slate_*.json` validate through `tests.test_weekly_inputs_contract`
  fixture cases (complete, partial, stale, unavailable).

### Claimed, not confirmed
- The stored ESPN roster shape ({season, week, captured_at, rows}) is new —
  no stored shape existed in the producer — and no real ESPN roster pull has
  been run against it. `adds_trend` is the stored change in rostered
  percentage points over the source's reporting window; nothing computes it.
