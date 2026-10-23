## 2026-10-23 - JEG-949 fourth projection source (Sleeper weekly projections, RotoWire), id mapping and loader

Contract: add a fourth independent projection source with 2018-2026 history for source-weight evaluation (parent JEG-943). Evaluate RotoWire vs Sleeper, map ids to player_key, give research a loader. No shown value, DDF Value definition or published output may change. No Supabase write, no migration applied.

### Source choice
Sleeper's public projections endpoint (provider field `rotowire`) is the source. RotoWire direct: anonymous table shows 3 rows, the rest is subscription (docs/research/source-discovery-2026-10-15.md), so it is not retrievable without a login. The Sleeper history was already pulled in data/inputs/weekly_projections_sleeper.csv.gz by pipelines/pull_sleeper_projections.py (JEG-540); this ticket did not re-pull it.

### Verified (check named)
- Endpoint reachable without credentials: HTTP 200 on api.sleeper.app/projections/nfl/2024/5 (curl).
- Coverage: weeks 1-17 for 2018-2020, 1-18 for 2021-2026; 52,462 player-week rows, QB/RB/WR/TE/FB, std/half/ppr totals, weekly (not rest-of-season) (read of the csv, per-season week sets).
- Stability: live re-pull vs stored ppr values, 2018 wk5 (208 rows), 2022 wk9 (296), 2024 wk5 (298): 0 changed. 2026 wk6: 277 of 312 changed, max 8.7 (current season is rolling).
- Timing caveat: `updated_at` present from 2023, always Monday or Tuesday (2024 sample 5,643 Tue, 358 Mon); pre-kickoff status of old weeks is not proven. MAE vs nflverse actuals for rows projected 4+ ppr: 5.89, 5.79, 5.63, 5.77, 5.55, 5.45, 5.54, 5.30 for 2018-2025, i.e. no sign of a post-game projection.
- Sleeper's own gsis_id is missing for most current players (3,893 of 12,229; Herbert, Hurts, Gibbs have none) and wrong for two (Conklin 5133 and Izzo 5094 are swapped). Found by comparing layers.
- Mapping (pipelines/sleeper_projection_idmap.py, data/inputs/sleeper_projection_idmap.csv and _report.json): 1,275 projected players; 902 matched to player_key, 367 gsis known but not in public.players (all last projected before 2025), 2 conflict, 4 unmapped. gsis resolves for 99.6% of QB/RB/WR/TE rows; player_key for 81.8% of rows (890 of 1,251 players), 82.5% for players averaging 4+ ppr. Players snapshot is a SELECT on public.players (4,702 rows; 4,613 with gsis; no duplicate gsis).
- Loader (pipelines/sleeper_projection_loader.py): gsis route 2018-2025 pairs 39,394 of 45,269 rows (132 no identity, 5,743 no actuals row); player_key route 2024-2026 pairs 12,703 of 19,359 (99 no identity, 6,557 no actuals row). Missing actuals are dropped, never zero-filled.
- Tests: tests/test_sleeper_projection_idmap.py, 13 pass. Mutations each fail the suite (run by hand): no disagreement check (2 fail), no name check (1), suggestion used as key (2), loader reads csv gsis (2), zero-fill of missing actuals (1). One test also embeds a first-answer-wins resolver as the simulated broken state.
- No value change: `value_check.py compare --rerun-engine --strict` on origin/main vs this branch gives identical reports ignoring timestamps and paths; git tree ids of data/fixtures/current and app/trade-value-chart/assets are equal; the diff against origin/main adds files only (docs/risk-register.md gets one row).
- check_supabase_naming.py: OK.

### Claimed, not confirmed
- The 4 unmapped and 2 conflict players: Conklin/Izzo resolution (DynastyProcess, sportradar and espn agree on the gsis that does not match Sleeper's own) is left unmapped by design pending review, not confirmed against nflverse names.
- The migration (supabase/migrations/jeg949_sleeper_player_ids_20261023.sql) was not run anywhere, including a scratch DB; syntax checked by eye only.
- Independence: this is one company's (RotoWire) projections; independence from ESPN/CBS/Razzball was not tested.
- docs/selfhost-tables.md does not exist in this repo; the data placement follows data/inputs conventions and supabase-naming-conventions.md.
