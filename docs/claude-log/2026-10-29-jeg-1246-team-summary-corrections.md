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
