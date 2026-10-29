## 2026-10-29 - JEG-1314: divergence weeks by served week, FantasyPros week 8 recorded, report refreshed

Contract: close the #1112 (JEG-1172) follow-ups: label each divergence
source-week by the week the source is served as, record FantasyPros week 8,
and find and fix why the committed report was stale.

### Verified (check named)
- On the e2c191c inputs (worktree; content_week 8, every chart served week 7)
  the new check labels FantasyPros week 7 and shows it `reviewed` under JEG-796,
  with "also warned in week 6"; main's code on the same inputs says
  `investigate`, "also warned in week 7" (the JEG-1172 alert). CBS rest of
  season moves the same way (week 7, reviewed under JEG-794).
- On current main inputs (all charts served week 8) every source's week,
  status and usual rate are unchanged by the code change
  (`check_source_divergence.py --out` before and after, compared).
- `python3 -m unittest tests.test_source_divergence`: 18 OK; the 7 new tests
  fail or error on main's code.
- `tests.test_open_divergence_issues`, `tests.test_jeg1172_fantasypros_w8_trace`,
  `tests.test_jeg1171_cbsros_w8_divergence_trace`, `tests.test_week_state`,
  `tests.test_value_check`: OK.
- Stale report cause: no workflow staged `dist/modules/source-divergence.json`;
  in the last 600 commits of main every change to it came from a person's
  commit or PR merge, none from a workflow (git log on the path; the oldest
  hit is only the shallow-clone boundary).
  `rebuild-chain.yml` now adds it in the success branch.
- `dist/modules/source-divergence.json` regenerated with sync's own arguments
  (generated 2026-10-29T20:28Z, fixture built 2026-10-29T16:16Z).

### Claimed, not confirmed
- `tests.test_published_surfaces` fails the same way on main (needs a built
  `dist/` with consolidated-values.json); not caused by this change.
- After merge, divergence-issues.yml will read the refreshed report and open
  a sub-issue for FantasyCalc week 8 (investigate on current data); CBS rest
  of season week 8 should dedupe against JEG-1171. Not run.
