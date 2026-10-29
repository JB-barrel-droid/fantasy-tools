## 2026-10-28 - League candidate completeness

Contract: Jeremy asked why JSN never appeared as a trade-away and clarified,
“That’s an enhancement, but he still should have showed up.” Preserve every
qualified candidate through fit/ranking/filtering; paginate only afterward.
No numerical value-basis, fairness, or enumeration-rule changes. Separate from #1069.

### Verified (check named)

- Production `/v2/finder.js` and `/v2/opportunities.js` fetched during diagnosis
  matched main `e20fa24e` except local trailing newline. `computePairing` requested
  ten results before fit evaluation/global ranking/filtering; Show all could not
  recover discarded candidates. Fix branch started at `e55ea518`.
- `test_opportunities_preserve_qualified_candidates`: synthetic coherent
  four-chart means, default maxSize 2: 52 qualified, 22 sending synthetic JSN.
  Old first 10 contain no JSN; fixed league path preserves all 52/all 22.
- `node tests/league_harness.cjs app/v2 tests/fixtures/league`: final 52 checks
  passed, including natural fit beyond old cap, exact lazy-vs-direct full fit,
  filter preservation, cancellation before caching partial work, and cache budget.
- Independent reviewer passed final source review for draft publication and reran
  all 52 Node checks with zero failures; this is not merge/live approval.
- `tests.test_v2_league_units` mutation suite passed before the final additional
  cache/full-fit assertions; final-head rerun recorded in PR when complete.
- Existing direct-finder oracle now requests all results; single-core fixture
  check selects that core explicitly, since other cores are no longer discarded.
  Assertions retain the original numerical and folding guarantees.
- Cooperative fit batches check cancellation after yielding. Existing league UI
  rejects cancelled/outdated run IDs. Partial pairings are not cached. Sync
  enumeration and final sorting remain synchronous. Large result append uses a
  loop rather than spread arguments to avoid the JS argument-count limit.
- Full fit details are recomputed by the identical `tradeFit` function only when
  opened. Compact ranking/filter columns and per-pair shared input context remain.
  Cache eviction is capped at 150,000 retained rows/400 pairings; active candidates
  are never truncated by this optimization. Oversized pairings are not cached.

### Performance evidence

Deterministic synthetic 12 teams × 15 players, standard shape, DDF equals the
four adjusted-chart mean. Not Jeremy's league and not a browser/device benchmark.
Run `node --expose-gc tools/benchmark_league_candidates.cjs 2`, repeat for 3/4;
optional `capped` simulates the original admission truncation.

| Package | Qualified rows | Original capped sync | Naive complete sync | Mitigated async cold / warm |
| --- | ---: | ---: | ---: | ---: |
| 2 | 504 |69ms|123ms|122ms /1.6ms|
| 3 |10,544|374ms|1,586ms|1,692ms /15.9ms|
| 4 |102,692|3,215ms|14,671ms|17,400ms /250ms|

Original cap retained 110 rows regardless of package size. Complete counts and
warm ordered IDs/edges/labels match; 11/11 pairings reused. Size 4 peak RSS fell
859→454MiB (post-GC retained heap 208 MiB). Fit yields: size 2 max 17.6 ms;
size 3 max 67.8 ms/p95 39.2 ms; size 4 max 431.8 ms/p95 13.6 ms, 1,059 yields.
Optional 4 remains expensive and can briefly block during unchanged enumeration.
No arbitrary replacement candidate cap introduced.

### Claimed, not confirmed

- No exact current user-league replay. Need complete league export/share state,
  selected team, scoring/lineup/week/source availability, basis/overrides and filters.
- DDF default is chart-based; projection-only 9.1 is not candidate admission.
  Correcting completeness does not promise projection-only sell-high deals qualify.
- Browser gates pending authorized CI: make sync first lacked bundled Chromium;
  system Chromium then failed local Unix socket permission. Escalated test runner
  failed before execution with read-only runtime sessions path. No bypass/retry.
  Initial render attempt also exposed a preexisting stale mutation anchor in the
  oppanel test; it was not altered to obtain a pass.
- Full aggregate gates and live publication not completed. Generated build output
  left uncommitted; only explicitly scoped source/test/docs/benchmark files staged.
- Linear creation/assignment rejected by auto-review; no ticket created and no
  retry through another route. Parent handles specific authorization/metadata.
