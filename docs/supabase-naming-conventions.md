# Supabase Naming Conventions

## Convention

Every Supabase **table, view, materialized view, and function** declared in
`sql/migrations/*.sql` follows:

> `<subproject>_<entity>`

Both halves are snake_case (lowercase letters, digits, underscores), must
start with a letter, and must contain at least one underscore separator.

- `<subproject>` names the owner of the data — either a publisher or source
  (`cbs`, `espn`, `razzball`, `usatoday`, `fantasypros`, `fantasycalc`, ...)
  or a pipeline-internal scope (`pipeline`, `source`, ...).
- `<entity>` names what the table/view/function holds
  (`trade_values`, `ros_projections`, `season_projections`, `write_audit`,
  `value_adjustments`, ...). The entity half may itself contain underscores.

Examples already in the schema (whether declared in `sql/migrations/*.sql` or
in older DDL retained in the live database):

| Name | subproject | entity | Where it lives |
|------|------------|--------|----------------|
| `cbs_trade_values` | cbs | trade_values | `pipelines/sql/create_espn_cbs_reference_tables.sql` |
| `cbs_ros_projections` | cbs | ros_projections | `sql/migrations/002_cbs_ros_projections.sql` |
| `espn_season_projections` | espn | season_projections | `pipelines/sql/create_espn_cbs_reference_tables.sql` |
| `source_trade_values` | source | trade_values | (existing pre-migrations table) |
| `source_value_adjustments` | source | value_adjustments | (fit artifact, sibling of `source_trade_values`) |
| `pipeline_write_audit` | pipeline | write_audit | `pipelines/sql/create_pipeline_write_audit.sql` (and repaired by `sql/migrations/001_pipeline_write_audit_repair.sql`) |
| `razzball_projections` | razzball | projections | `sql/migrations/003_razzball_projections.sql` |

The convention is enforced at validation time by
`pipelines/check_supabase_naming.py`, which parses `sql/migrations/*.sql`
directly (no DB connection). A name is **either conventional, on the
exception list, or a failure**. There is no silent-allow path.

## Exception list

Tables that are genuinely shared and cannot carry a subproject prefix appear
on a documented exception list. Every exception needs a one-line
justification; adding one requires a same-touch edit to
`pipelines/check_supabase_naming.py` AND this doc. An exception without a
matching doc row is itself a regression in this doc.

| Name | Justification |
|------|---------------|
| `players` | Canonical identity map. The naming authority — every other table joins to it on `player_key`. Every pipeline reads it; it cannot carry a subproject prefix. (Adding a prefix would also break the `public.players` reference baked into Supabase's row-level security and RLS-disabled PostgREST contract; the table is identity infrastructure, not pipeline output.) |

If a future table meets the same criteria (read by every pipeline, identity
or audit trail role, no subproject owner), add it here in the same change
that edits the validator.

## Validator

`pipelines/check_supabase_naming.py` runs as part of `make validate`. It:

1. Reads every `*.sql` in `sql/migrations/` (override via `--sql-dir`).
2. Strips SQL comments (`-- ...` and `/* ... */`) so commented-out
   `CREATE` lines cannot become false positives.
3. Matches `CREATE [OR REPLACE] [MATERIALIZED] (TABLE|VIEW|FUNCTION)
   [IF NOT EXISTS] [<schema>.]<name>` and captures `<name>`. The name
   anchor is **before** the function parameter list / `AS` clause, so
   `CREATE FUNCTION foo(...) ...` captures `foo`.
5. For every captured name, the name is either conventional or on the
   exception list. If neither, the validator fails closed.

Verdict:

- **Exit 0** — every CREATE in the directory is conventional or on the
  exception list.
- **Exit 1** — one or more violations. Stderr lists every offender with
  the file, line, kind, and the offending name.

The validator is read-only and never connects to Supabase. It runs in CI
because it depends only on the in-tree SQL files.

### Current verdict

Running `python3 pipelines/check_supabase_naming.py` against the current
`sql/migrations/*.sql` declares two `CREATE TABLE` objects:

- `public.cbs_ros_projections` — `cbs` + `ros_projections`. Conventional.
- `public.razzball_projections` — `razzball` + `projections`. Conventional.

The remaining schema objects are referenced (not created) in the migrations
via `ALTER TABLE` / `DROP INDEX` and are ignored by the validator by
design — rename history lives in the migration files themselves, not in
the validator's output.

**Verdict: GREEN (exit 0).** Recorded 2026-10-02 by JEG-111.

## Migration plan (sequenced)

Renames are **out of scope** for this ticket (one JEG per table). This
section is the sequence a future rename PR must follow — no rename ships
without its readers and writers updated in the same change.

### Per-rename sequence

For a table T to be renamed from `old_name` to `<subproject>_<entity>`:

1. **Inventory readers and writers.**
     `grep -rn "old_name" pipelines/ tests/ app/ ops/ docs/` to enumerate
     every PostgREST path (`sbclient.post('/rest/v1/<old_name>', ...)`),
     every importer (`SOURCE_TABLES['<old_name>']`), every fixture
     reference, every watcher script, and every doc that names the table.
     Attach the exhaustive list to the JEG ticket before any code lands.

2. **Add the new name as a `CREATE TABLE IF NOT EXISTS …` migration** in
     `sql/migrations/<n>_<new_table>.sql`. Do NOT drop the old table in
     this migration. The new migration's DDL must mirror the old table's
     columns, constraints, indexes, and audit columns (`_writer_identity`,
     `_run_id`, `_written_at`); see `pipelines/sql/create_espn_cbs_reference_tables.sql`
     for the current shape and `docs/SUPABASE_WRITER_AUDIT.md` for the
     audit-column contract. Backfill columns with NULL on existing rows
     (per the standing rule in `docs/methodology.md`: never invent sentinel
     values for missing provenance).

3. **Dual-write.** Every writer POST/PATCHes both old and new for one full
     bake cycle (or until the next import-health pass is green on both
     tables). Document the chosen window on the JEG ticket. The
     `pipeline_write_audit` table records the dual-run for verification;
     if both rows are missing on the new name, the dual-write step failed.

4. **Reader cutover.** Switch every reader to the new name. Run
     `make validate` and `make import-health NFL_WEEK=<n>`; the new name
     must produce identical values to the old name before any cutover
     proceeds. Re-run `pipelines/check_supabase_naming.py` -- if the
     intermediate dual-write name is not conventional, the validator goes
     red and the migration is blocked. (Use a conventional temporary name
     on the exception list if absolutely necessary, with the same
     one-line justification rule.)

5. **Stop writing the old name.** After the cutover window closes, drop
     the dual-write path in every writer; old writers now write only to
     the new table. The `pipeline_write_audit` table records each writer's
     last old-name row -- that row's `started_at` is the cutover timestamp.

6. **Drop the old table.** `DROP TABLE IF EXISTS public.old_name` in a
     fresh migration (`sql/migrations/<n+1>_drop_<old_name>.sql`); verify
     no `grep` reference remains; verify `pipeline_write_audit` no longer
     has rows for `<old_name>` past the cutover timestamp.

A rename PR that does any of steps 1-6 without also doing steps 1-5 in the
same change is a fail-closed regression and is blocked at review.

### Cross-cutting constraints

- Renames cannot ship across deploy boundaries. Every migration must be
  backward-compatible with the readers and writers that exist at the time
  it lands. (PostgREST serves `app/`, the Pages deploy runs from `main`,
  and `pipelines/check_supabase_naming.py` runs in CI on every push.)
- The validator must stay green through every intermediate state. If the
  rename introduces an intermediate name that is not conventional or on
  the exception list, the validator goes red and the migration is blocked.
- Per the standing rules in `docs/methodology.md`: never delete audit
  columns (`_writer_identity`, `_run_id`, `_written_at`) on rename. New
  tables carry the same columns; backfill them with NULL on existing
  rows. The writer-audit enforcement tests
  (`tests/test_writer_audit_enforcement.py`) gate this.
- The `players` table is on the exception list and stays on it for the
  lifetime of the project. There is no migration plan for renaming it; if
  a future schema proposes moving identity off `public.players`, that
  decision belongs in a dedicated JEG ticket and the exception-list
  removal is part of that ticket.