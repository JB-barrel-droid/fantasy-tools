## 2026-10-30 - JEG-1240 follow-up: the get= guard compares runs by package, not by team id

Follow-up to #1110 (merged as 84c5e17). The Mac's browser runs on JEG-1304 (03:05 and 12:48 UTC) showed
`test_guard_fails_on_a_link_without_get` failing on its own harness. The baseline and mutant journeys reached the same
14 stages, read the same way, but each run saves the league afresh, so every pick's row id
(`<opponent team id>|<give>|<get>`) carries a different team id. `mutant.stages == baseline.stages` failed on that id.
`mutant.codes() - baseline.codes()` had the same problem, so the known page-side reds (for example `basis-changed` at
`Compare elsewhere`) would also have counted as new codes the mutant lost.

- `same_stage` and `run_shape` take each pick's team id out of stage names. The guard compares stages and codes on that
  shape. The package stays in the name, so a different package is still a different stage.
- Test-only, in `tests/test_uso_site_journey_render.py`. No page, value, Makefile or workflow change.

### Verified (check named)

- `RunShapeTest` (3 tests, no browser). On 84c5e17's comparison, two runs of the same journey that differ only by
  team id compare unequal, and the mutant's new codes are `basis-changed` and `package-changed`. On this head the runs
  compare equal and the new codes are `package-changed` alone. A different package still compares as a different
  stage.
- `python3 -m unittest tests.test_uso_site_journey_render`: 18 run, 14 pass, 4 browser tests skipped (no Chromium).

### Claimed, not confirmed

- The browser guard hasn't run on this head. With the id fixed, it should pass only if the mutant's new codes stay
  within `PACKAGE_LOSS` (the Mac saw `package-changed` and `value-missing`). The other two browser failures are
  page-side (Compare elsewhere does not carry rosters or basis) and are not touched here.
