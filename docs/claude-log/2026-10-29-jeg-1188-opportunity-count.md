## 2026-10-29 - Why league-wide opportunities went 89 -> 34 (JEG-1188, Claude lane)

Contract: explain why league-wide Trade opportunities on the 20-team fixture league (team 0 = you) fell from 89 to 34
between the 2026-10-26 and 2026-10-27 real-page reads, with fixed inputs; say whether it is intended filtering or a
regression; leave a deterministic check. Diagnostic only: no search, fit, value or default change.

### Answer
- There is no single 89 -> 34 change. The fixture count moved four times, each reproduced on the built page at that
  revision with that revision's own code and data:

  | Revision | When (UTC) | Page count (Natural / Market / Force) | What changed it |
  |---|---|---|---|
  | `bb61662592` (#945 branch) | 10-26 11:59 | 89 (60 / 0 / 29) | JEG-1108 your-side rule; the 10-26 log's 89 |
  | `8b5c4f04ba` (#945 branch) | 10-26 13:36 | 66 (38 / 0 / 28) | bench-only throw-ins (Jeremy accepted the rule, 10-26) and the 10-26 12:26 data rebuild merged in |
  | `e696bf25` / `9d7fa48e` (main) | 10-26 21:33 to 10-27 10:46 | 100 (57 / 0 / 43) | the 10-26 14:34 and 16:16 data rebuilds; no code |
  | `47fd50ca` (main, #957) | 10-27 10:53 | 34 (7 / 0 / 27) | #957, JEG-1121 bench seats (VORP bench allocation in `value-model.js`) |
  | `33e138e5` (main) | 10-27 17:36 | 34 (7 / 0 / 27) | the JEG-1096 log's 34; nothing since #957 moved it |
  | `ff35152` (main today) | 10-29 | 59 (9 / 18 / 32) | later data; #1072 shows all qualified trades (53 -> 59); JEG-1187 relabels Force as Market supported |

- The step to 34 is #957 and it is the engine's values, not the search. #957 changed no `app/v2` code (only
  `value-model.js` and the pipelines), so the search code is the same on both sides; with that code and the
  before-957 context, swapping in the after-957 engine rows moves pass gates 389 -> 112 and qualified 151 -> 34.
  (`finder.js` reads only the rows, the charts and the lineup shape; the bench allocation and weights do not enter the
  gates.) Of the 389 packages that passed the gates before #957, 77 still pass, 311 fail only the DDF Value edge (you
  no longer win on DDF Value), 1 fails both, 0 fail the chart gate alone. These are at #957's own code (modules dir
  pointed at that day's `app/v2`). In the full page dump (738 rows; the fixtures keep only the 248 rostered ones)
  #957 moved DDF Value for 185 rows (by position, mean change: WR -2.5, RB +2.2, TE +2.3, QB +1.2) and the compared
  charts' values for 98. Team 0 holds 4 WRs (-10.5 together) and 5 RBs (+8.6).
- So the drop is the intended consequence of an approved value change (JEG-1121, Jeremy's approval cited in
  `docs/claude-log/2026-10-26-jeg1121-vorp-bench.md`), not a regression in candidate enumeration, fit, viability or the
  lineup boxes. Whether DDF Value after JEG-1121 prices WRs right is a value question and is not answered here.
- Stage counts with main's modules at `ff35152` (2026-10-29) on each frozen context (`node tests/node/jeg1188_opportunity_stages.cjs`):

  | Context | Page | Pass gates | Lineup boxes drop | Qualified | Top 10 per opponent | Shown | Nat | Mkt | Force |
  |---|---|---|---|---|---|---|---|---|---|
  | oct26-a-fit-rewrite | 89 | 273 | 192 | 124 | 77 | 124 | 79 | 13 | 32 |
  | oct26-b-throw-ins | 66 | 263 | 209 | 97 | 66 | 97 | 58 | 10 | 29 |
  | oct27-c-before-957 | 100 | 389 | 296 | 151 | 100 | 151 | 81 | 31 | 39 |
  | oct27-d-after-957 | 34 | 112 | 101 | 34 | 34 | 34 | 7 | 6 | 21 |
  | oct29-e-main | 59 | 158 | 135 | 59 | 53 | 59 | 9 | 18 | 32 |

  The historical 89 / 66 / 100 were capped at 10 per opponent (the bug #1072 fixed); today's code shows all qualified.
  "Lineup boxes drop" counts packages before throw-in variants fold into one row, so it can exceed pass gates minus
  qualified. The fixtures' `teams` is the engine state's 12, not the league's 20; it feeds only the bench depth,
  which the gates never read.

### Update 2026-10-31: after JEG-1125's even band
- #1033 (JEG-1125, Jeremy's option A) changed `finder.js`: a net is even when it is under max(1 point, 3% of the
  average side), for the DDF Value edge and each chart's rival check, not under 0.05 as before. The check's
  independent judge now applies the band of the modules it replays (`EVEN_FLOOR` / `EVEN_SHARE` from their
  `trade.js`; 0.05 for a checkout older than #1033). No search, fit, value or default change here.
- Stage counts with main at `168aba93` (2026-10-30, merged into this branch):

  | Context | Page | Pass gates | Lineup boxes drop | Qualified | Top 10 per opponent | Shown | Nat | Mkt | Force |
  |---|---|---|---|---|---|---|---|---|---|
  | oct26-a-fit-rewrite | 89 | 251 | 232 | 78 | 50 | 78 | 0 | 26 | 52 |
  | oct26-b-throw-ins | 66 | 274 | 273 | 68 | 52 | 68 | 0 | 18 | 50 |
  | oct27-c-before-957 | 100 | 400 | 325 | 151 | 89 | 151 | 0 | 106 | 45 |
  | oct27-d-after-957 | 34 | 117 | 123 | 28 | 28 | 28 | 0 | 0 | 28 |
  | oct29-e-main | 59 | 161 | 147 | 62 | 53 | 62 | 2 | 3 | 57 |

- Re-judged with today's band, the #957 step still is the DDF Value edge: of 400 packages, 64 still pass, 329 fail
  only the edge, 6 fail both, 1 fails the chart gate alone. The check now asserts that at least 95% of the lost
  packages fail the edge (all of them at #957's own code), instead of none failing the chart gate alone.
- The old bench-swap equality assertions are dropped: they could not fail, since the gates never read the bench
  numbers. The #957 cross is now rows swapped under the same code.
- The fixtures' revisions `bb61662592` and `8b5c4f04ba` are commits on #945's branch (`fe/JEG-1108-fit`), which
  merged into main on 2026-10-26 at 21:33 UTC; they may not survive that branch's deletion.

### Verified (check named)
- `tools/jeg1188/dump_context.py` (new; built dist served as the render tests serve it, CBS held, page clock pinned to
  the data week, fixture-20team seeded, page driven by `tools/jeg1188/page_driver.cjs` under jsdom 24.1.3) reproduced
  every page count above at its revision: 89 / 66 / 100 / 34 / 59, and 34 at `33e138e5` (not kept as a fixture).
- Replaying each frozen context with its own revision's `app/v2` gives the page's exact row ids
  (`node tests/node/jeg1188_opportunity_stages.cjs <that worktree>/app/v2 --json`, `matchesPage` true for all five).
- 2x2 crosses (rows x code) at the two data steps: `bb61662592` rows with `8b5c4f04ba` code 77, the reverse 76;
  `8b5c4f04ba` rows with `e696bf25` code 66, `e696bf25` rows with `8b5c4f04ba` code 100 (data only).
- `node tests/node/jeg1188_opportunity_stages.cjs --assert` on this branch: assertions pass (2026-10-31, with main
  merged in; also with `ff35152`'s `app/v2`). With `--mutant cap-per-opponent` or `no-lineup-boxes` it fails on
  shown vs qualified; with `weaker-chart-gate` the independent judge finds shown rows that fail the gates.
- `python3 -m unittest tests.test_jeg1188_opportunity_count`: 7 tests pass (wired into `test-unit-modules`).
- The league fixture (`tests/fixtures/league/fixture-20team.json`) is byte-identical at every revision above.

### Claimed, not confirmed
- Only team 0 of the 20-team fixture was replayed; teams 3 and 7 and the 4-team fixture (JEG-1096's other rows) were not.
- jsdom is not Chromium. It matched every historical page count and every row id, but no layout-dependent behavior
  was exercised. Playwright's Chromium download is blocked in this sandbox, so `tools/fit_distribution_page.py` was not run.
- Main's page pin today is 2026-10-29 (from `tests.test_week_history._fixture_today`), 2026-10-26 at the other revisions.
- The fixtures keep rostered players only and drop `ddfByVersion`; the replay matches the page with them, so the
  dropped fields are not read by `finder.js` / `opportunities.js` today.
