## 2026-10-16 - JEG-676: history index normalization for DDF composite tests

Contract: fix the remaining 5 DDF composite value test failures in the
rebuild chain so Week 6 can publish.

### Root cause

PR #623's `normalize_chart_weeks` bumped fixture sections to the current
content week but did not touch the history index
(`dist/assets/history/index.json`).  The JS determines each source's
served week from the history index (via content fingerprinting at build
time), not from the fixture's `week_designated`.  In CI, the chain
promotes most sources to Week 6 while CBS stays held at Week 5; after
`normalize_chart_weeks` bumps CBS's fixture to "Week 6", the history
index still maps it to week 5.  The JS saw CBS as "serves Week 5, not
Week 6" and excluded it.  The same mismatch affected projections
(ESPN, CBS ROS, Razzball) which stay at their original served week in
the history but need to match charts for the prior-week pairing.

### Change (PR #631)

- Added `normalize_served_weeks()`: bumps every source in the history
  index to `content_week()` after `normalize_chart_weeks` runs.
- Updated `run()` to normalize the history index after the fixture,
  folding `history_edit` into the same index load.
- Fixed `test_chart_without_saved_prior_inputs_is_left_out_of_both_weeks`
  to use `content_week() - 1` instead of the stale on-disk
  `served_week("cbs") - 1`.

### Verified (check named)

- 15/15 DDF composite value tests pass locally (including the 5 that
  failed in chain run 38852779680)
- 34/34 view invariants + week history + rescaled-copy tests pass locally
- PR #631 merged to main

### Claimed, not confirmed

- Chain run 38855740401 (dispatched after merge) will pass `make validate`
  and publish Week 6.

### Earlier fixes this session

- PR #628 (merged): fixed stale rescaled-copy test anchor and banned
  tooltip labels from JEG-490.
- PR #623 (merged, earlier session): added `normalize_chart_weeks` but
  missed the history index -- this PR (#631) completes that fix.
