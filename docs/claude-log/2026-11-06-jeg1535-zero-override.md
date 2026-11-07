## 2026-11-06 - JEG-1535 follow-up: an override of 0 is a real override

Contract: PR #1339's review reported that a numeric 0 override is treated as absent by the Values editor.
Reproduce on the live page and locally, fix at the root, and add regression tests.

Root cause: `app/next/values-overrides.js` read the stored entry by truthiness (`if(!curEntry)`, `curEntry?...`), so a
saved 0 showed as "= DDF", the button read "Set override", Reset was disabled and the field reopened at DDF Value.
The store (`ddf-v2-value-overrides` held `{"2227":0}`), the adapter (`DDF.engine.overrides.get` returns null only
when absent), the engine (`normalizeOverride(0)` is an absolute 0; the row priced at 0) and the old v2 Overrides tab
(explicit `!== undefined` checks) were already correct. Fix: one explicit `hasEntry = entry !== null && entry !==
undefined` used at every read in the editor.

### Verified (check named)
- Live reproduction before the fix (Playwright on https://datadrivenfootball.github.io/fantasy-tools/values.html,
  build tv-20261106-2104-77f7236): after setting 0, store `{"2227":0}`, engine DDF 0, v2 tab `DDFOverrides.all()`
  `{"2227":0}`, but the editor showed "= DDF", "Set override", Reset disabled, and reopened at 75.68.
- `tests.test_values_zero_override`: the round-trip test (set 0, reopen, Chart row marked, update to 12.5, back to
  0, reset; store, engine row and page record checked at each step) fails on the pre-fix file ('= DDF' != '0.0')
  and passes with the fix; the v2 cross-page test passes on both (the old tab was already right).

### Claimed, not confirmed
- CI on the PR head and live behaviour after deploy: see the PR and the ticket.
