# JEG-1242: projection-history backfill tests survive new weeks (2026-10-29)

Scope: `tests/test_projection_captures.py` (BackfillTests, new BackfillFixtureTests)
and new `tests/fixtures/projection_history_backfill/`. No production writer,
live history, guard test (JEG-1238), Supabase, workflow or data change.

## Failing before (main `ca51f2fd`, network blocked)

```
FAIL: test_real_history_counts (tests.test_projection_captures.BackfillTests.test_real_history_counts)
    self.assertEqual({w for s, w in pairs if s == "espn"}, {2, 3, 4, 5, 6, 7})
AssertionError: Items in the first set but not the second:
8
Ran 29 tests ... FAILED (failures=1)
```

`data/history/week-8.json` is already on main, so this reproduced as-is.

## What changed

- `test_real_history_counts` is now a live-tree smoke: each source keeps its
  frozen floor (espn 2-7, razzball 3-7, cbs 4-7), must be contiguous through the
  latest week the tree holds, rows are ROS/backfill only with ppg and no
  points/games, every source-week has 500+ rows, and per-source-week counts
  equal a count taken straight from the raw JSON (independent source mapping).
- `BackfillFixtureTests`: a three-week hand-written fixture with 18 literal
  expected rows (source, week, capture_at, player_key, format, ppg); a new-week
  case (week 5 adds 9 literal rows, weeks 2-4 unchanged); a synthetic tree
  proving the live check needs no edit for a new week and fails on a dropped
  latest week; and source-text mutants of `rows_from_history`.

## Mutation diagnostics (network blocked)

```
live latest week: 8
- omit razzball
    fixture: killed (AssertionError: Items in the second set but not the first:)
    live: killed (AssertionError: False is not true : razzball: historical weeks missing, have [])
- weekly cbs instead of cbsros
    fixture: killed (AssertionError: Items in the first set but not the second:)
    live: killed (AssertionError: False is not true : cbs: historical weeks missing, have [])
- weekly horizon
    fixture: killed (AssertionError: Tuples differ: ('backfill', 'week', 3) != ('backfill', 'ros', 0))
    live: killed (AssertionError: Tuples differ: ('backfill', 'week', 3) != ('backfill', 'ros', 0))
- drop a format
    fixture: killed (AssertionError: Items in the second set but not the first:)
    live: killed (AssertionError: {('espn', 2): 700, ('espn', 3): 848, ('razzball', 3): 1[293 chars] 732} != {('espn', 2): 1050, ('espn', 3): 1272, ('razzball', 3):[301)
- empty output
    fixture: killed (AssertionError: [] is not true : backfill yielded no rows)
    live: killed (AssertionError: [] is not true : backfill yielded no rows)
- skip latest week
    fixture: killed (AssertionError: Items in the second set but not the first:)
    live: killed (AssertionError: Items in the second set but not the first:)
- missing ppg written as 0
    fixture: killed (AssertionError: Items in the first set but not the second:)
    live: n/a (value mutant)
- per-format shift
    fixture: killed (ValueError: a capture row needs points or ppg)
    live: n/a (value mutant)
- wrong capture_at
    fixture: killed (AssertionError: Items in the first set but not the second:)
    live: n/a (value mutant)
live smoke on weeks 2-7 only: PASS
live smoke on weeks 2-8: PASS
```

## Focused run

`python3 -m unittest tests.test_projection_captures` with sockets blocked:
36 tests OK, no skips, `git status` clean apart from this change (no data writes).
`tests.test_player_identity_guard` has one failure
(`pipelines/lib/projection_capture.py` resolve without canonical_players) that
is identical on main without this change; it is JEG-1238 / #1103 scope and untouched here.
