# JEG-323 — repo-side guard for `public.check_source_vintages()`

**Lane:** minimax (M3)
**Branch:** `minimax/jeg-323-healthstub-guard`
**Status:** ready-to-commit. Not pushed, not deployed.
**Scope:** repo guard + ops docs only. No live Supabase access, no
production change, no methodology/values/copy change.

## Why this ticket exists

Production Supabase exposes `public.check_source_vintages()`, a stub
which returns the hard-coded `{"changed": false, "note": "stub"}`.
There is no `CREATE FUNCTION` body for it in this repo — confirmed by
grep across `sql/migrations/` and `sql/contract/` and by the new
regression test below (the same scan that catches the stub class).
The stub is a false-green health surface: anyone reading the live
function gets "changed=false" no matter what the data says. JEG-323
tracks its revoke/removal. This branch adds the repo-side guard so
the same failure mode cannot sneak back in under a new name, and
updates the operating docs so nobody cites the stub as if it were
real.

## Test design

File: `tests/test_health_function_no_hardcoded_green.py`
Wired into: `Makefile` `test-unit` (which feeds `make validate`) —
slotted alphabetically between `test_espn_zeroed_staleness` and
`test_razzball_supabase`. `make validate` ordering is preserved; no
existing wiring was removed.

The test is a pure string/regex scan. No DB, no fixtures, no
network. It does three things:

1. **Synthetic-stub case** — inline-SQL function whose only body is
   `return jsonb_build_object('changed', false, 'note', 'stub');` with
   no FROM or JOIN. The classifier returns `fail-stub`. The test
   asserts that. (Proves the heuristic catches the JEG-323 class.)

2. **Synthetic-real case** — inline-SQL function whose body reads
   from `public.source_trade_values` and `public.pipeline_cron_state`
   via FROM. The classifier returns `pass`. The test asserts that.
   (Proves the heuristic does not over-trigger on real checks.)

3. **Synthetic name-only and comment-only cases** — a function whose
   only health marker is its name (`health_probe()`) and a function
   whose only health marker is its leading comment ("Returns the
   freshness stamp…"). Both have constant-return bodies. Both
   classify as `fail-stub`. (Proves both arms of the
   health-shaped-by-name-or-comment heuristic catch the same
   failure mode.)

4. **Repo scan** — walks `sql/migrations/*.sql` and
   `sql/contract/*.sql` for `CREATE [OR REPLACE] FUNCTION` bodies,
   classifies each via the same heuristic, and fails on any
   health-shaped function that reads no table and is not on the
   `ALLOWLIST` dict (currently empty). The empty ALLOWLIST keeps the
   bar high: a new stub lands → test goes red → reviewer must add
   the function to the allowlist with a written reason.

The classifier distinguishes three outcomes:
- `pass-nonscope` — function is not health-shaped; nothing to say.
- `pass` — health-shaped AND body references FROM or JOIN.
- `fail-stub` — health-shaped AND no relation read. This is the
  JEG-323 failure mode.

### Why the synthetic cases prove the guard catches the stub class

The whole point of the ticket is that "returns a constant" and "is
named like a health check" co-occurring is the failure mode. The four
synthetic inline-SQL strings exercise every entry path that would
classify a function as health-shaped (name match, comment match,
or both) crossed with every constant-return shape (language plpgsql
+ jsonb_build_object, language sql + string literal). Each of those
combinations MUST classify as `fail-stub`; the test asserts each
one. If a future refactor weakens the heuristic, one of the four
will go green-on-red and the test will fail loudly. The
synthetic-real case is the negative control: a function that DOES
read tables MUST classify as `pass`. If a future refactor
over-triggers, the real case will fail. Together the five
synthetics pin the heuristic from both sides.

The repo-scan test pins the actual repo state. Today `grep` finds
zero `CREATE FUNCTION` bodies in `sql/migrations/` or `sql/contract/`
(the only DDL is `CREATE TABLE`, `CREATE INDEX`, `CREATE SCHEMA`,
`CREATE VIEW`, and `CREATE EXTENSION`). The scan therefore sees zero
health-shaped functions and passes. The day someone lands a stub
under any name matching `health|freshness|vintage|check_`, the test
goes red with the exact file and qualified name. There is no silent
false-green.

## Ops docs updated

Three docs in `docs/audits/jeg285-phase2/` now distinguish the
three concerns and carry the JEG-323 stub warning:

- **`02-pgcron-job-specs.md`** — added a top-level
  "Three separate concerns — keep them separate" section naming:
    1. Source content freshness / health (`pipelines/verify_import_health.py`,
       `make import-health`, GHA `import-health.yml`).
    2. Source-vintage change detection (this JEG-285 Job 1,
       `public.check_source_vintages()`, `pipeline_cron_state`).
    3. Code-change detection (JEG-205 `pipelines/`-hash path,
       GitHub-side only — stays in `.github/source-vintage-check.yml`,
       NOT moved to pg_cron).
  The JEG-323 warning is restated at the Job 1 section (the spot
  where the spec first references `check_source_vintages()`).

- **`05-job1-shadow-spec.md`** — added a "Which concern this spec
  covers" subsection pointing readers back at the three-concern
  split in (1) above, and a "JEG-323 stub warning" subsection that
  pins the new function body to the regression test's bar.

- **`05-shadow-01-source-vintage-check.md`** — same "Which concern"
  pointer and same JEG-323 stub warning at the top, so reviewers
  who land on this spec see both points before they start.

The `lanes/inbox/minimax/JEG-322-phase1.md` file the original ticket
brief mentioned does not exist in the repo (the only JEG-322 trace
in the file tree is inside the `jeg285-phase2` audit docs above).
The three-concern distinction is therefore added where JEG-322
content actually lives. No `JEG-322-phase1.md` file was created;
adding one was out of scope and would have been speculative.

## Files changed

```
Makefile                                                |  1 +
docs/audits/jeg285-phase2/02-pgcron-job-specs.md        | 30 ++++
docs/audits/jeg285-phase2/05-job1-shadow-spec.md        | 16 ++-
docs/audits/jeg285-phase2/05-shadow-01-source-vintage-check.md | 18 ++++
lanes/inbox/minimax/JEG-323-guard.md                    | new
tests/test_health_function_no_hardcoded_green.py        | new
```

No SQL values, methodology, or user-facing copy changed. The new
test is hermetic (string scan only). No DB or network call is made.

## Open follow-ups (not this branch)

- The actual revoke of the live stub
  `public.check_source_vintages()` in production Supabase is the
  JEG-323 ticket body, owned by the lane that picks up that work.
- When the JEG-285 Job 1 implementation phase lands the real
  function body in `sql/migrations/`, the body MUST read at least
  one relation (FROM or JOIN); the new regression test will fail
  loudly if a stub slips in. The plan at
  `05-shadow-01-source-vintage-check.md` §3 already meets that bar
  (it reads from `public.source_trade_values`,
  `public.pipeline_cron_state`, etc.).