# get-values priced nobody after the week 8 flip

## What happened
From Oct 27 07:00Z, get-values answered with an empty players list (edge logs: 13 to 20 KB replies on
Oct 26, 266 to 271 bytes after). The calendar had moved to content week 8, but the published site still
had fantasycalc, usatoday, fantasypros and cbs on week 7.

## Cause
`supabase/functions/get-values/index.ts` dropped a weekly chart as "stale" whenever its week was older
than the calendar's content week, on top of the first-load rule (older than the newest published week).
On the flip every chart is behind the calendar, so all four were dropped and DDF Value came out null.
The site stopped doing this in JEG-1176/1177 (a week view judges "older" against the view's week), but
get-values was never changed.

## Fix
- get-values judges older-week only by the first-load rule: a weekly chart behind the newest published
  weekly week (capped at the calendar week, as before). The calendar alone never drops a chart.
- `tests/_edge_pipeline_runner.cjs` mirrors the same rule.
- `tests/node/get_values_handler_check.mjs` re-asks the default league with the clock pinned past the
  last content week: it must still price over 50 players at the same values. With the old rule it
  prices none.

## Checks
- On main today, the handler check fails (`players.length > 50`). With the fix it prints ok.
- `tests.test_league_mapping` needs Chromium to rebuild dist, so it was run here as the handler check
  against the committed dist. It runs in the nightly full suite (test-unit).
- Not deployed. The live get-values keeps the old rule until it is redeployed, which waits on Jeremy.
  It clears on its own once a week 8 bundle reaches Pages.
- PR #1024 (JEG-1179) moves this logic into `get-values/pipeline.ts`. Its fallback branch still has the
  calendar rule, so it needs the same change when it merges main in.
