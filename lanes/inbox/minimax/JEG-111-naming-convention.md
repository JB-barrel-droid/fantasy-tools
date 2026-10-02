# JEG-111-naming-convention — dispatcher evidence bundle

Issue: JEG-111 (Supabase naming convention doc + validator). Convention + plan
only; actual renames out of scope (separate tickets).
Branch: `minimax/jeg-111-naming-convention` (off origin/main `5df093c`)
Worktree: `~/workspace/worktrees/wt-jeg111-naming-convention`
  (NOT /tmp — /tmp is a 512M tmpfs at 99%; checkouts fail there.)

## What happened

The M3 worker (`mmcode exec`, runId exec_turn_mures24y_1x9ixg) wrote all three
deliverables, then FAILED at the end with:

    429 Token Plan usage limit reached: Upgrade your Token Plan or purchase
    Credits for more usage. (2056)

The worker never committed and never wrote this inbox report. The dispatcher
(me) ran the brief's acceptance commands outside the sandbox, repaired 3
defects, and committed. No retry of the MiniMax call was made (429 = hard stop).

## Files changed (all new)

- `docs/supabase-naming-conventions.md` (165 lines) — the `<subproject>_<entity>`
  convention, exception list (`players`, justified), sequenced migration plan,
  and the recorded current-schema verdict (GREEN, exit 0, 2026-10-02).
- `pipelines/check_supabase_naming.py` (176 lines) — parses
  `sql/migrations/*.sql` directly for CREATE TABLE/VIEW/MATERIALIZED
  VIEW/FUNCTION (handles OR REPLACE, IF NOT EXISTS, schema-qualified and
  double-quoted identifiers, comment stripping); exit 1 lists every violation
  with file/line/kind/name. Read-only: no DB connection, no writes.
- `tests/test_supabase_naming.py` (260 lines, unittest) — 17 tests: violation
  fixtures (single-word, uppercase, leading-digit-quoted, view, function,
  multiple), exception-list fixtures, clean-schema fixture.

## Commands run + outputs (dispatcher-verified)

```
$ python3 -m py_compile pipelines/check_supabase_naming.py tests/test_supabase_naming.py
PY_COMPILE OK

$ python3 pipelines/check_supabase_naming.py
OK: every CREATE in .../sql/migrations follows <subproject>_<entity> or is on
the documented exception list.
(checker exit: 0)

$ python3 -m unittest tests.test_supabase_naming -v
Ran 17 tests in 1.220s
OK
```

## VERIFIED (dispatcher executed, outputs pasted above)

- All 17 unit tests pass.
- The checker exits 0 on the real `sql/migrations/` directory.
- py_compile clean on both Python files.

## UNVERIFIED

- `make validate` was NOT run (out of scope for this subtask's file boundaries;
  the checker is not yet wired into the validate target — see open questions).
- No live-DB comparison was made: the checker reads `sql/migrations/*.sql`
  only, so tables created by older DDL outside migrations/ are not checked.
  The doc acknowledges this (examples table cites pre-migrations tables).

## Dispatcher repairs (3 defects found by running the worker's own tests)

1. Quoted identifiers: the worker's regex could not parse
   `CREATE TABLE public."2day_count_runs"` — it reported `'public'` instead of
   the name. Fixed: name branch now accepts `"[^"]+"` (quotes stripped before
   the convention check) plus digit-leading unquoted names, so nothing slips
   past the parser.
2. Wrong fixture: `test_multiple_violations_all_listed` used `another_bad` as
   the second violation, but `another_bad` IS conventional per
   `<subproject>_<entity>`. Fixed the fixture to `anotherbad` (genuinely
   violating) with a comment explaining why.
3. Message mismatch: the test asserted `"NOT on exception list"` (uppercase)
   but the implementation prints lowercase. Fixed the test to case-insensitive
   match.

## Convention verdict on the current schema

GREEN — `python3 pipelines/check_supabase_naming.py` exits 0 on
`sql/migrations/*.sql` at `5df093c`. Recorded in the doc §"Current verdict".

## Open questions

1. Wiring into validation: the original JEG-111 acceptance asks for the naming
   check "wired into validation", but the brief's file boundaries limited the
   worker to the 3 new files, so `make validate` does not invoke the checker.
   Recommend a follow-up: add `python3 pipelines/check_supabase_naming.py` to
   the validate target (Makefile change, one line).
2. The checker covers `sql/migrations/*.sql` only. Older tables created by DDL
   in `pipelines/sql/` or `waiver_wire/pipeline/sql/` are not checked. The
   JEG-111-schema-inventory subtask (running in parallel) covers the full
   picture; reconcile before wiring into CI.
3. Exception list currently has one entry: `players` (canonical identity map,
   cannot carry a subproject prefix — justified in the doc).
