## 2026-10-12 - JEG-605, JEG-599, JEG-600 docs consolidation

Contract: archive finished docs (JEG-605), rewrite the current-state architecture page (JEG-599), add the Supabase table map (JEG-600). Docs only.

### Verified (check named)
- pg_cron: read-only `select jobname, schedule, active from cron.job` on project iskiybsimubiujwuchsl returned 19 jobs, all active; the architecture page lists them.
- Table and view counts (94 and 30): read-only `pg_class` query on schema public.
- Files and jobs on the architecture page: read `pipelines/sync_dashboard_artifacts.py`, `rebuild-chain.yml`, `pages.yml`, `bake-players.yml` and `ls dist`; confirmed `pipelines/build_v2_page.py`, `build_week_history.py`, `export_consolidated_json.py` exist and `app/v2/v2.js` is the v2 source.
- Moved files: grep of tests, pipelines, tools, modules, app, sql, Makefile for the old paths found only code comments (gate.mjs, value_reference.py, twotier.py); no code reads the moved files. Code comments were left alone (docs only).
- `make validate` exit 0 on the branch.

### Claimed, not confirmed
- Writer and reader columns in `docs/supabase-tables.md` come from a text scan (see the page); not traced per write.
- The pg_cron to workflow mapping for source-probe and ingest workflows is inferred from workflow headers, not from a live run.
- `docs/architecture-target.md` still mentions retired pieces; not edited in this PR.
- JEG-600: the "nine switched off" jobs no longer exist in `cron.job`, so there is nothing to mark off; the list shows only the 19 active jobs.
