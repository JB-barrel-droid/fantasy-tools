# Supabase Writer Audit System

## Problem

Supabase writers (pipelines that insert/upsert into Supabase tables) currently lack:
- Writer identity (what code wrote the data)
- Run ID (unique identifier for the write operation)
- Operation/reason (why the write happened)
- Code revision (what version of the code wrote it)
- Start/completion/failure timestamps
- Durable audit trail in the database

This makes it impossible to:
- Trace data provenance
- Debug write failures
- Detect unauthorized writes
- Audit the pipeline for compliance

## Design

### Audit Table: `pipeline_write_audit`

Every Supabase write operation must create an audit record.

```sql
CREATE TABLE IF NOT EXISTS public.pipeline_write_audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id text NOT NULL,                    -- Unique ID for this write operation
    writer_identity text NOT NULL,           -- e.g., 'save_espn_cbs_references.py'
    code_revision text,                      -- Git commit SHA or version
    source text NOT NULL,                    -- Data source: 'espn', 'cbs', 'usatoday', etc.
    operation text NOT NULL,                 -- 'upsert', 'insert', 'delete'
    reason text,                             -- Human-readable reason for the write
    table_name text NOT NULL,                -- Target table
    row_count integer,                       -- Number of rows written
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    failed_at timestamptz,
    error_message text,
    metadata jsonb,                          -- Additional context (vintage, filters, etc.)
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pipeline_write_audit_run_id_idx
    ON public.pipeline_write_audit (run_id);
CREATE INDEX IF NOT EXISTS pipeline_write_audit_writer_idx
    ON public.pipeline_write_audit (writer_identity, started_at DESC);
CREATE INDEX IF NOT EXISTS pipeline_write_audit_table_idx
    ON public.pipeline_write_audit (table_name, started_at DESC);
```

### Writer Identity Helper

A shared Python module `pipelines/lib/writer_audit.py` provides:

```python
from pipelines.lib.writer_audit import WriterAudit

# At start of write operation
audit = WriterAudit(
    writer_identity="save_espn_cbs_references.py",
    source="espn",
    operation="upsert",
    reason="Weekly ESPN projection import",
    table_name="espn_season_projections",
)
audit.start()  # Creates audit record, returns run_id

try:
    # ... do the write ...
    audit.complete(row_count=150)
except Exception as e:
    audit.fail(str(e))
    raise
```

The helper automatically captures:
- `run_id`: UUID generated at start
- `code_revision`: Git commit SHA of the repo (or "unknown" if not a git repo)
- `started_at`: Timestamp when `start()` is called
- `completed_at` / `failed_at`: Timestamps when operation finishes

### Required Audit Fields on Data Tables

All pipeline-written tables must include these columns (added via migration):

```sql
-- Standard audit columns for pipeline-written tables
ALTER TABLE <table> ADD COLUMN IF NOT EXISTS _writer_identity text;
ALTER TABLE <table> ADD COLUMN IF NOT EXISTS _run_id text;
ALTER TABLE <table> ADD COLUMN IF NOT EXISTS _written_at timestamptz DEFAULT now();
```

These are prefixed with underscore to distinguish from domain columns.

### Enforcement

1. **Write wrapper**: All Supabase writes go through `writer_audit.py` which enforces audit record creation before allowing the write.

2. **Negative test**: `tests/test_writer_audit_enforcement.py` verifies that:
   - Writes without an audit record are rejected
   - Audit records with missing required fields are rejected
   - The audit trail is queryable

3. **CI gate**: `make validate` includes the audit enforcement tests.

## Implementation Steps

1. Create `pipelines/sql/create_pipeline_write_audit.sql`
2. Create `pipelines/lib/writer_audit.py`
3. Add audit columns to existing tables (migration)
4. Update writers:
   - `pipelines/save_espn_cbs_references.py`
   - `pipelines/save_usatoday_references.py`
   - `pipelines/import_supabase_references.py`
   - `pipelines/lib/preseason_ecr.py`
   - `pipelines/lib/canonical_players.py`
   - `pipelines/bake_players.py`
5. Create `tests/test_writer_audit_enforcement.py`
6. Run full test suite

## Tables Requiring Audit Columns

- `public.cbs_trade_values`
- `public.espn_season_projections` (check exact name)
- `public.source_trade_values`
- `public.players` (if written by pipeline)
- Any other pipeline-written tables

## Notes

- The audit table itself is append-only; records are never updated except to set `completed_at`/`failed_at`.
- `run_id` is a UUID string, unique per write operation (not per row).
- For batch writes, one audit record covers the entire batch.
- The `metadata` JSONB field stores operation-specific context (e.g., vintage dates, filters applied, source URLs).
