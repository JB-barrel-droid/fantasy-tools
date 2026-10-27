## 2026-10-26 - Red main: bench-share readout test at the week 8 flip (JEG-1152)

Contract: get `tests.test_bench_share_readout_matches_reference` green again
(17 errors, `float - NoneType`), which blocked `make validate`, every PR
`preview` check and every pages.yml deploy on main. Values unchanged.

### Root cause

No code change caused it. pages.yml was green on 1edb9309 (22:55 UTC) and red
from 37644d91 (23:36 UTC), and the only change between them is chain-status
JSON. The test read two different clocks:

- the Python reference (`value_reference.Inputs.load`) uses the **UTC** date;
- the engine page (`product-data.js todayIsoDay`) uses the **America/New_York** date.

From 00:00 UTC Tuesday 2026-10-27 the reference said content week 8 and the
page still said week 7. All seven fixture sections are week 7, so the reference
excluded the four charts ("not yet published for week 8"). Since JEG-1073
(679fa54e, #919) the blended DDF Value has no projection fallback, so every
blended value, and with it the bench-share readout, was null. The engine
returned numbers, so the comparison raised `float - None`. The same test
would also fail once New York reaches Tuesday, when both sides are on week 8
against week-7 charts (null readout, then the plausibility band
`0.05 < None`).

### Fix

The test pins both sides to a day in the served data's content week:
`Inputs.load(..., today=...)` for the reference and `window.TRADE_VALUE_TODAY`
for the page, both using `tests.test_week_history._fixture_today` (the same
pin JEG-787/JEG-791 added to the other render tests). No assertion changed.

### Verified (check named)

- Before the fix, at 02:05 UTC 2026-10-27:
  `python -m unittest tests.test_bench_share_readout_matches_reference` gave
  `FAILED (errors=17)`. After the fix: `OK` (3 tests).
- In Python, `Setting('ppr', 12).result()` with the real clock: included =
  espn, cbsros, razzball; usatoday, fantasycalc, fantasypros and cbs were
  "not yet published for week 8"; blended DDF Value was non-null for 0 of 738 rows.
- `_fixture_today()` returns 2026-10-26 (week 7, the data's week).
- The diff touches only this test file and this log, so no pipeline or engine
  value can change.

### Claimed, not confirmed

- The live site loses all blended DDF Values from Tuesday 00:00 New York time
  until the week-8 charts land (no chart in I, no fallback since JEG-1073).
  That is product behaviour, not this test. Follow-up for the lead.
- The UTC/New York clock difference between the reference and the engine is a
  separate defect in `pipelines/value_reference.py`. It is left alone here to
  avoid a conflict with PR 957.
