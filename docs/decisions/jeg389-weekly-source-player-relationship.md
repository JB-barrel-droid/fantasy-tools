# JEG-389 decision: weekly-source player relationship (2026-10-04)

## Inspection result

`weekly_source_snapshots` does **not** exist in this repo: no DDL in
`sql/migrations/`, no Python reader/writer, no live table in the
migration workstream's scope. It appears only as:

- a referenced table name in `sql/migrations/007_never_blend_trigger.sql`
  (the weekly Vegas/FDS scope), and
- a design artifact in the JEG-367 weekly-backend review
  (`lanes/inbox/chatgpt/JEG-367-review-result.md`: "Concrete schema
  moves: 003_weekly_source_snapshots.sql").

It belongs to the **weekly workstream** (JEG-367, ECR-vs-Vegas backend),
whose tables are not yet created. There is no weekly-source player
relationship to add *in this repo* today.

## Requirement for when the table is created

When the weekly workstream creates `weekly_source_snapshots`, its
player column MUST:

1. FK to the canonical player identity (`public.players.player_key`;
   player NAMES resolve through the canonical naming table per the
   standing rule — never a source spelling).
2. Be `NOT NULL` and fail closed on unresolvable identity (exclude the
   row with a loud warning, never guess).
3. Use `NEW.*` column references in any trigger (never payload JSONB) —
   the JEG-389 map's H4 finding.

## In-scope player relationship (this repo, verified)

The weekly cadence in *this* workstream is `consolidated_values`
(week-indexed). Its player relationship:

- `consolidated_values.player_key → public.players.player_key`
- Enforced fail-closed at **load time** by
  `pipelines/load_ddf_leg_to_supabase.py::verify_player_keys`
  (any unknown key aborts the load), and at **publish time** by gate 2
  (`player_joins`) in `api.run_publish_gate`, which fails the publish
  with sample orphan keys on miss.

No new FK DDL is added here: the relationship is already enforced at
both write boundaries, which is stronger than a bare FK for a table
whose DDL lives outside this repo's versioned migration set.
