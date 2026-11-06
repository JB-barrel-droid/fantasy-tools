# Learn data: number lineage snapshots

`lineage-week9.json` feeds Learn > How we get our numbers (`learn/numbers/numbers.js`).

## Capture (2026-11-05, content as_of 2026-11-06, week 9)
- Server: DDF MCP, Supabase project `iskiybsimubiujwuchsl`, function `mcp` (JSON-RPC `tools/call`).
- Settings on every call: `scoring half_ppr, teams 12, superflex false, slots [1,2,3,1,1,6]` (QB RB WR TE FLEX BENCH).
- `audit_values view=source limit=50` for cbs, usatoday, fantasypros, fantasycalc, once with `position all` (source order, overall rank) and once per QB/RB/WR/TE (to reach players outside a source's top 50).
- `get_values limit=200` (DDF Value, rank order), `get_player_value` (Stevenson, Love, Diggs, Rice, Gibbs cross-check), `explain` (methodology, sources, value_scale), `audit_values view=health`.
- Raw responses: `raw-week9/`. Build tag `tv-20261106-0341-62dfe5b` comes from `10-lineage/LINEAGE-MAP.md` (live bundle); the MCP responses do not carry it.

## Definition used
`explain methodology`: DDF Value is the average of the four published trade charts (CBS Sports, USA Today, FantasyPros, FantasyCalc), each adjusted to the league. Projection sources (ESPN, CBS rest of season, Razzball) are not in the average, even though `get_values` lists them under `sources_included`.

## Verification
- `players[]` holds the 124 players from the top 200 by DDF Value that appear in all four captured source views (all named players are included; nobody is padded with zero).
- For each player, mean of the four adjusted values vs the tool's DDF Value: 103 tie out exactly at 0.1; 21 differ (`verification.rounding_cases`), max gap 0.075 (Matthew Golden 32.825 vs 32.9, C.J. Stroud 2.925 vs 3.0; the rest are .x5 ties, 19 resolved down, 12 up across all ties). The tool returns adjusted values rounded to 0.1 and averages the unrounded ones, so the mean of rounded inputs can be off by up to 0.05 before display rounding. Every gap is inside that bound. The UI shows the tool's value and says so when the shown inputs do not round to it.
- `index_factor` is derived (indexed total / published total), not returned by the tool. Applied to every captured row it reproduces the indexed value within 0.051 (display rounding).
- Each chart's adjusted total is 2688.0 = the value pie (28 x 12 teams x 8 starting slots), matching the health check.

## Refresh
Re-run the same calls for the new week and regenerate with the capture script logic described above; bump `as_of`, `week`, `build`.
