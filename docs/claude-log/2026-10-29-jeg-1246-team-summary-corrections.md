# JEG-1246: PR #964 team value summary corrections (2026-10-29)

Correction child of JEG-890, from Codex's independent review at `7d84cdb9`. Same branch
(`fe/JEG-890-team-summary`), no second implementation, no value math change.

## Main integration

`origin/main` merged normally. One conflict, in `app/v2/finder.js`'s exported `api` object: main's list
(finder hash, bench backups, saved-team choices and the rest) was taken whole, plus this branch's `teamSummary`
and `SUMMARY_ROWS`. Nothing else conflicted; no main hunk was changed.

## Finding 1: unavailable-chart crash

`tsTable` read `s.cells[name]` for the Trade chart average before `tsCell` checked `available === false`, so a week
with 0, 1 or 2 usable charts (below `MIN_CHARTS`) threw. `tsCell(series, name)` now returns "n/a" before any cell is
read. The market note now shows whenever the average is absent, with the usable count. Per-chart columns are exactly
the usable charts, the others are named "not compared", and with none "No trade chart is compared this week."

## Finding 2: incomplete partitions

`pickStarters` puts a player with no DDF Value in `unvalued`, never in starters or bench, so a chart total of 40 read
against starters 10 + bench 0 with nothing marked. `teamSummary` now carries that set as an `unplaced` row (label
"No DDF Value"), listed only when someone is in it, so Starters + Bench + No DDF Value = Total in every series. The
DDF cell there has no number (never 0) and is incomplete. Starters and Bench carry the names as `unplaced` and render
a "*" with the names as a tip; a note names each team's players. No starter slot is guessed for him.

## Tests

- `tests/test_v2_finder_teams.py` (node): Codex's 10 / 0 / 40 example, the mixed roster (R5 no DDF Value, T2 no
  FantasyPros value) reconciling in every series, and a complete-data positive control (no row, no flags, every total
  complete). Three new mutations (partition dropped, row never listed, Starters/Bench never flagged) each fail.
  Against `7d84cdb9` the new checks fail (no `unplaced` cell; starters 10 + bench 0 vs total 40 marked complete).
- `tests/test_v2_finder_teams_render.py` (Chromium, 1366 and 390): 0 / 1 / 2 usable charts and a listed starter with no
  DDF Value; mutations restoring the crash ordering and dropping the partition each fail.
- The finder search signature (`tests/fixtures/finder_search_signature.js`) is byte-identical to main's.
- `test_v2_finder_groups` and `test_v2_finder_search_unchanged` fail identically on current main; not this change.

Render tests need Chromium, which this cloud session cannot download (Playwright download host blocked); they run in
the `v2-render` CI with `RENDER_TESTS_REQUIRED=1`. Neither team-summary module was in any PR check before (only the
nightly full suite), so both are now a step in `.github/workflows/v2-render-test.yml`.

## Iteration 2: phone clipping of the partial-Total warning (Codex Mac review 8e0720c5)

In "Show each chart" at 390 / 375 px a partial Total ("182.0 incomplete") overflowed its column by about 41–44 px:
`td.num` and `.v2-find-ts-inc` are `nowrap` in a fixed-layout table. Display only, in `app/v2/v2.css`:

- a partial cell's wrapper (`.v2-find-ts-incomplete` inside `td.num`) is an inline flex row that wraps, so the warning
  drops under the number; the warning word itself may break mid-word only in a column too narrow for it (four charts
  on a 375 px phone). Nothing is hidden or truncated;
- under 480 px, cell padding 3px 4px and the row label column 30% (was 38%) to give the numbers room.

No markup, math or missing-value change. Main `430791c4` merged in normally first (no conflicts).

Regression (`tests/test_v2_finder_teams_render.py`, Chromium at 390 and 375): one of their players loses his
FantasyPros value, Show each chart is opened, and every summary cell must have no inner overflow, every incomplete
warning must sit inside its cell, no per-chart table or the page may scroll sideways, and their FantasyPros Total must
read as a partial number marked incomplete. Repeated with all four charts as columns. A guard serves the `1e1bbb5`
stylesheet block (both rules removed, the phone media query restored) and requires the check to fail at 390.
