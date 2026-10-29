# 2026-10-28: why the board stayed on week 7 (JEG-1194)

Jeremy asked why the board isn't updating from each source and to fix the process.

## What happened

- Supabase had week 7, and from Oct 27 to 28 week 8, for every source. The site
  was built Oct 26 15:42Z and still says "data through Week 7".
- The rebuild chain failed every run from Oct 26 15:42Z, about 44 hours. Its
  `make validate` gate is all or nothing, so one source's failure kept all
  seven on week 7. The failing check changed four times:
  1. value-check-compare (razzball review hold with no prior section);
  2. test_week_history DeltaRecompute;
  3. test_rank_guard on lagging charts (fixed by #1016 and #1020);
  4. from Oct 28 03:00Z, test_superflex `test_live_page_superflex_control`:
     "superflex cbs: listed players not plotted".
- Cause of 4: CBS's week 8 save had 0 TE rows (parser, fixed by #1019). The
  fidelity pulse turned that into a red hold on CBS. The hold applied to the
  live week 7 CBS chart, so the good chart was grayed out, and the render test
  then failed for CBS. The JEG-799 match only skips a hold for a candidate
  *newer* than the one measured; here the bad data was the newer save and the
  live chart was the older one, so the match pointed the wrong way.
- Nothing alerted: the failure went to comparison-chain-status.json and the
  monitoring table only.

## Fixed (be/jeg-1194-board-publish)

- `fidelity_pulse.red_scope`: a red whose stages only judge a stored save
  newer than the live chart (publisher_vs_stored, or stored-side count drops)
  is stamped `scope: stored_newer_than_site`.
- `fidelity_hold.apply_fidelity_holds`: a scoped hold holds a build from the
  newer save and leaves the live chart's own section unheld (and removes an
  older fidelity hold on it).
- `pipelines/chain_stuck_alert.py` + a rebuild-chain step: when the chain fails
  and the fixture is 6 hours old, open one `chain-stuck` GitHub issue naming the
  failing check, held sources and each source's served week; close it when the
  chain publishes.
- Review follow-up: a scoped hold carries `judged_save` (the bad bake's
  pulled_at, the same value as a section's snapshot_fetched_at, or a
  projection's snapshot). The chain skips it only for a build from a clearly
  later save, so the fixed CBS re-ingest (12:23Z) is not held on an older
  pulse, and anything unclear (USA Today's midnight pulled_at) stays held. A
  first version compared saved_at within 300 s and let a USA Today build
  through; the second review caught it. The alert finds its issue by title
  too and never fails the job on malformed input.
- Jeremy said yes (12:22Z) to reloading CBS week 8 and merging #1027 and this:
  the reload wrote bake cbswk8_2026-10-28t1223_v1 (35 TE, 452 rows); the 12:40Z
  pulse then showed CBS amber, not red.
- #1027 (board lane) makes the three render tests accept a red-held lagging
  chart; reviewed PASS by an independent agent.

## Verified (check named)

- tests.test_fidelity_hold (73), test_fidelity_pulse, test_seeded_hold_build,
  test_rebuild_chain_per_source_hold and the other fidelity suites pass.
- The new StoredSaveNewerThanTheLiveChart class fails on the old code (1
  failure, 4 errors) and passes with the fix.
- tests.test_chain_stuck_alert (13) passes; its workflow test fails without the
  workflow step.
- Every test that reads rebuild-chain.yml passes except
  WeekTransitionSentinelTest's engine test, which needs Playwright (same on main).
- Dry run against the committed status prints the issue text with the 44 hours.

## Claimed, not confirmed

- That the next chain run publishes week 8 once #1027 and this land: depends on
  the 12:07Z CBS ingest reloading TE rows and on the browser render tests in CI.
- That GitHub emails Jeremy for the issue: default for a repo owner who watches
  the repo; not checked.
