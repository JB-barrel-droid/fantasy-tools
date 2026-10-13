## 2026-10-12 - JEG-620 Draft Sharks puller (part 1)

Contract: bring Draft Sharks into the pipeline per the source pattern, fail closed, without wiring it into published DDF Value.

### Verified (check named)
- Public, no login: `curl` of https://www.draftsharks.com/trade-value-chart returned HTTP 200, 12.8 MB, no redirect; the whole chart is embedded JSON (`"players":[...]`, 3100 rows), parsed with `pipelines/pull_draftsharks.py` against the live page (949 QB/RB/WR/TE priced rows; positive redraft half-PPR values: QB 24, RB 67, WR 60, TE 17).
- Values are 0-100 trade values per format (redraft/dynasty x no/half/one PPR/TE premium x superflex) with a market value beside each; 0 = unpriced (written null), negatives to about -135 are real below-replacement values and are kept (my first 0..100 range check tripped on them; widened to -200..100 after measuring).
- `tests/test_pull_draftsharks.py` (9 tests: nulls not zero, negative kept, IDP dropped, tiny body = SOURCE_BLOCKED, missing array/column = SOURCE_LAYOUT, missing position = SOURCE_TRUNCATED, scale change = VALUE_RANGE, CLI writes nothing on failure). Added to `make test-core` beside the FantasyCalc puller test.

### Claimed, not confirmed
- Identity: only a crude name check against the vendored 2026-09 identity snapshot (152 of 168 positive rows matched; the misses looked like nickname-expansion artifacts of my check). The real resolver (`lib/canonical_players.resolve_with_reason` against live `public.players`) was NOT run; the saver must do it.
- Not done, by design: saver, Supabase table, workflow, source_probe signal, bake leg, fidelity pulse. A new table is a production Supabase schema change Jeremy has not approved (CLAUDE.md), and DDF Value must not take the source until its pulse is green. JEG-620 stays In Progress.
- The page has no chart timestamp; vintage = run date, `fingerprint` decides change.
