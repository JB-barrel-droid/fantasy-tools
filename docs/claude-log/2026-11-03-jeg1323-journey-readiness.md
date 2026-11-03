## 2026-11-03 - JEG-1323 journey boot readiness

Contract: diagnose the concrete CI failure on integrated head `68e4ffc5` and
correct the bounded harness race without weakening assertions or product logic.

### Verified (check named)

- V2 run `41579184397`, journey job `125730039939`, failed only
  `LeagueSiteTest.test_league_to_compare_journey` / `trade='unequal'`:
  no Details button for the `164,2807|3942,1483` package. The later reload and
  AI-panel steps were skipped after that failure; no complete gate was claimed.
- An instrumented normal run found that exact package visible at rank 5.
  An instrumented delayed-v2-boot run reproduced the same unequal-package
  failure with `ui.ready=false`, no result and no Details button, while both
  idle flags were false. Thus idle alone was not a completed boot/search.
  Logs: `/tmp/jeg1323-journey-diagnostic.log` and
  `/tmp/jeg1323-late-boot-before.log`.
- The new `test_league_to_compare_journey_waits_for_late_boot` reuses the
  existing delayed-engine control and the full original journey assertions.
  It failed before the readiness correction, on the same unequal subcase:
  `/tmp/jeg1323-late-regression-before.log` (1 failure in 24.588 seconds).
- `settle()` now requires `TradeValueLeague.ui.ready` as well as the existing
  idle flags. No timeout was increased, no assertion removed or relaxed,
  no candidate substituted, and no baseline registry exemption added.
- Exact affected CI command, with required rendering and destination identity:
  `python3 -m unittest -v tests.test_uso_site_journey_render
  tests.test_jeg1249_league_site_render` -- all 25 tests PASS in 267.659 seconds,
  no skips. Includes the real missing-get mutation guard, ordinary/unequal
  journeys, delayed boot, canonical basis, oversized override, saved workspace
  and paste/provenance checks. Log: `/tmp/jeg1323-journey-readiness-after.log`.
- Application/readout source, values and fixtures are unchanged. Local generated
  build output is excluded from this correction. `git diff --check` passes.

### Claimed, not confirmed

- Fresh exact-head CI and independent delta review remain required. The old
  failing run was not blindly retried; no job or process was cancelled.
- No broad local validation, merge, deploy, deletion, access change or Supabase
  action. Optional denied PR/Linear publication remains deferred.
