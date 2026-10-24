## 2026-10-24 - JEG-1034: unblock the rebuild chain (laptop-2)

### Finding

Every hourly rebuild since 2026-10-23 11:45 UTC ran green: all 7 sources
promoted, the rank guard held, and the engine agreed with the reference on
1,226,406 values. The post-rebuild `make validate` then failed closed on one
plausibility bound: `test_bench_share_readout_matches_reference`,
`0.05 < overall < 0.15`. Half-PPR/8 teams read 0.1538 on the fresh data
(run 40118692646), against 0.1456 on the 10-23 data. The live site stayed on
the 10-23 fixture.

`config/lineup_parameters.json` `content_week` (the last week with completed
games; the window starts the week after) was set to 6 on 2026-10-16 and
nothing advances it.

**Correction to the ticket:** for today's Week 7 data, 6 is correct. A "Week
N" chart is posted after week N-1's games, so the window 7-17 is right. It
would have gone stale on 2026-10-27, when Week 8 charts are served.

### Decision (Jeremy, 2026-10-24)

"A" (advance the content week automatically from the served data) "And B"
(widen the bound).

### Change

- `derive_lineup_parameters.advance_content_week()`: sets content_week to
  the newest served week minus one, never back. It recomputes
  `resolved_default` and writes in the config's own format.
- `make sync` (`sync_dashboard_artifacts.py`) builds the history index first,
  advances the week, then copies the config to the page.
- The chain commits `config/lineup_parameters.json`.
- The bench-share bound is now 5-18% (Jeremy's rule change).
- `tests/test_lineup_content_week_advance.py` is added to `make test-core`.

### Values

- Unchanged by this PR: the config stays at 6 for Week 7 data.
- From the first sync with Week 8 data: bench share drops about 0.3 points
  in every setting. The highest is 14.6% -> 14.3% at 8 teams (reference,
  committed data).

### Verified (named checks)

- `tests.test_lineup_content_week_advance`: the four behaviour tests error
  before the function exists and pass after.
- Committed-config guard: fails with a simulated stale config (content_week
  5 against Week 7 data, "5 not greater than or equal to 6").
- `tests.test_derive_lineup_parameters`: OK.

### Not run locally

- `make sync` (forbidden here) and the bench-share render test, which builds
  dist. The PR's preview CI runs make validate.
- `tests.test_validate_runner` / `tests.test_run_suite` fail identically on
  unchanged main on this Windows machine.
