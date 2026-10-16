## 2026-10-15 - JEG-620 / JEG-621 Sharks saver, table, pulse reader

Contract: Jeremy approved (2026-10-15) one new table per source in production Supabase, create only. Neither source is wired into published DDF Value.

### Done
- Migrations `sql/migrations/008_draftsharks_trade_values.sql` and `009_fantasysharks_projections.sql`, applied through the Supabase MCP to project iskiybsimubiujwuchsl (names `jeg620_draftsharks_trade_values`, `jeg621_fantasysharks_projections`). Create table, two indexes, RLS enabled with no policies (service role only, same as `razzball_projections`). No drops, alters of existing tables, or deletes.
- Savers `pipelines/save_draftsharks_references.py`, `save_fantasysharks_references.py`: reuse the Razzball saver's canonical resolver and Supabase hooks; unmatched names go to the review report; nulls stay null; whole-save verification fails closed.
- Pulse readers `pipelines/fidelity_sources/draftsharks.py` (redraft no/half/one PPR trade values) and `fantasysharks.py` (ROS totals), registered in `fidelity_pulse.PROJECTIONS` and `LABEL`.
- Fantasy Sharks bake leg NOT built: total / team games remaining is points per team game, not per game played (JEG-676 basis); no defensible conversion. GAP-FANTASYSHARKS-ROS-TOTAL updated.
- Draft Sharks bake leg NOT built either (not asked beyond saver/table/pulse; a trade-value leg needs the value_reference/bake lanes other agents own). Both stay held: the pulse chart stage reads "not in the live chart file" (red).

### Verified (check named)
- `tests/test_sharks_savers.py` (4): saver columns subset of migration columns, upsert key is a unique index, migrations only create and enable RLS, nulls stay null, unmatched to review, empty/undated snapshot fails closed.
- `tests/test_fidelity_sharks.py` (8): readers parse each scoring, skip unpriced/non-skill, fail loudly on bot wall / missing array / missing columns / non-CSV / HTTP error; both sources registered; chart stage is red for a source absent from the chart file.
- Existing fidelity suites (pulse, hold, razzball, sentinels, followups, check/build source fidelity, espn) still pass (206 tests).
- Live pulls with the existing pullers returned 949 (Draft Sharks) and 480 (Fantasy Sharks) rows.

### Claimed, not confirmed
- No real save ran: this machine's `sbclient` is stale (bad magic number) and holds no service key, so the tables are empty. Identity match rates against live `public.players` are unmeasured.
- No scheduled save workflow, source_probe signal, or bake leg exists for either source; the pulse therefore has nothing stored to read until a save runs.
- `get_advisors` not run. `make validate` and the full sweep not run (value lanes in flux, per instruction).
