# Values endpoint (Supabase edge function `get-values`) and MCP server

Ticket JEG-616. Hosting decision: Supabase edge function (Jeremy, 2026-10-19).

- Function: `supabase/functions/get-values/index.ts`. Reads the published site
  (`value-model.js`, `lineup-parameters.json`, the comparison bundle, the
  `players-data` island on the home page, and the week history under
  `assets/history/`), runs `runValuePipeline`, returns blended values. No
  database access, no schema change, no service-role key. The engine input
  (source eligibility, the week view) is built in `get-values/pipeline.ts`,
  which the parity runner (`tests/_edge_pipeline_runner.cjs`) imports too.
- Public: `verify_jwt = false` in `supabase/config.toml`; per-IP rate limit
  (30/min, in memory per instance); CORS allow-list in the function.
- Parity with the page is pinned by `tests/test_endpoint_parity.py` (including
  each week of a week transition, JEG-1179).
- MCP server, local: `mcp-server/` (stdio), set `DDF_API_URL` to the function URL.
- MCP server, remote (JEG-1012): `supabase/functions/mcp/` (Streamable HTTP, stateless, JSON responses). See "Remote MCP" below.

## Request

`GET|POST /functions/v1/get-values` with `scoring` (standard|half_ppr|ppr),
`teams` (8|10|12|14), `superflex` (0|1), and optionally `league` (JEG-1031): the
normalized DDF league section (`roster`, `shares`, `bso`, `inj`, `conf`, `weeks`;
a JSON object in a POST body, a JSON string in a GET query). The top-level
`scoring`, `teams` and `superflex` win over the same fields inside `league`.
The response lists the settings that differ from the site defaults in
`league_custom`. Optional `include=charts` adds per-chart Adjusted values
(`chart_values`), per-chart Indexed values (`chart_indexed`) and DDF
sub-versions (`ddf_value_charts`, `ddf_value_projections`) to each player
record (used internally by the MCP `find_trades` tools). The trade finder
judges the other team on the mean of `chart_indexed`, the market: the mean of
`chart_values` is DDF Value itself, and `ddf_value_charts` equals DDF Value
since JEG-1073 (JEG-1129).

### Week (JEG-1179)

Sources publish week N+1 at different times. Each answer is priced on one week,
with the site's own rule and data:

- **Default week**: `ValueModel.weekState` from the published `value-model.js`
  (the code the page runs, not a copy) over the DDF Value sources at the
  requested setting, each with the week it serves in
  `assets/history/index.json`. N+1 only when more than half of those sources
  serve it; exactly half stays on N (Jeremy, 2026-10-27, JEG-1176).
- **`week`** (optional, GET query or POST body): N or N+1 during a transition,
  the one week otherwise. Not a whole number from 1 to 22: 400 `invalid week`.
  A week with no published sources: 400 with `code: "week_unavailable"`,
  `weeks` and `default_week`, and an `error` that names them, for example
  `Week 9 has no published sources at this setting. Weeks available: 8, 7 (default 8).`
  Never an empty list.
- **No carry-forward**: a source still on week N is left out of week N+1 (named in
  `missing_sources`); a source already on N+1 is priced on its saved copy of
  week N (`assets/history/week-<N>.json`), or named missing when none is saved.
- Without a history index for the served build (or a `value-model.js` without
  `weekState`), the calendar fallback applies: the week is the newest week any
  weekly chart serves (capped at the calendar's week), and a weekly chart counts
  as older only when it is behind that week, never just because the calendar has
  moved on (#1028). That is the only week that can be asked for then.
- This fixes JEG-1157: from the Tuesday flip until the charts land, the
  calendar says N+1 while the charts serve N, and the endpoint used to price
  almost nothing. The default now stays on N.

Response fields: `week` (the week priced), `default_week`, `weeks` (the weeks
that can be asked for), `sources_included`, `missing_sources` (DDF Value sources
at this setting that have not published this week). Tests:
`tests/node/get_values_week_check.mjs` (the handler on the built `dist/`,
synthetic transitions), `tests/test_endpoint_parity.py test_week_parity` (page
parity per week).

### Value basis and player overrides from a share link (JEG-1225)

Jeremy, 2026-10-28 (JEG-1224 D1: "B"): a chat given a link with the sender's own
basis or overrides prices its answer under them. get-values takes them in the
text the link carries, optional, GET query or POST body:

- **`basis`**: `fantasycalc` (one source) or `blend:espn.60_razzball.40` (whole
  percents), as `basis=` in a share link. Absent: our methodology.
- **`ov`**: `2227:58` (an absolute DDF Value), `2227:+5` (an adjustment), comma
  separated, or the packed `z:`/`z2:` form, as `ov=` in a share link.

The text is read by the site's own `app/v2/ddf-value-link.js` (the one reader of
the link format, loaded from `<site>/v2/` at cold start like `value-model.js`).
`get-values/value-context.ts` sends the basis to `runValuePipeline` as
`basisConfig` in the form the page's engine does (`curve-widget.js`
`canonicalBasis`) and applies each override with `ValueModel.applyDdfOverride`,
as the page does. No new value math. An override replaces DDF Value only: the
tier, the charts' values and the projections version are the pipeline's, as on
the page.

- The response adds `value_context`: `basis` (null = our methodology),
  `basis_applied`, `basis_members`, `basis_fell_back_to_default` (none of the
  basis' sources is usable this week), `overrides`, `overrides_applied`, and
  `overrides_not_priced` (keys with no pipeline row: named, not added). An
  overridden player also carries `override` and `pipeline_value`.
- A part that is sent but cannot be read: 400 with
  `code: "value_context_unreadable"` and `unread` (`basis`, `ov`). Never a silent
  fall back to our methodology.
- A site that does not publish `v2/ddf-value-link.js` yet: requests without a
  basis or overrides answer as before; with one, 503
  `code: "value_context_unavailable"`.
- The answer cache key and the compute rate limit include the context.
- Tests: `tests/node/get_values_value_context_check.mjs` (the handler on the
  built `dist/` against the parity runner, errors, cache, the site's share link
  read back, the basis form against `curve-widget.js`),
  `tests/test_endpoint_parity.py test_value_context_parity` (page parity in
  Standard, Half PPR and PPR).
- Not yet: the MCP tools passing a pasted link's context through (JEG-1225
  slice 4c), and `docs/get-values.openapi.yaml`, which ships with Pages and so
  should list `basis` and `ov` only once this function is deployed.

### Custom leagues: computed on demand, stored nowhere (JEG-1031)

Jeremy, 2026-10-24: "Compute on demand, store nothing." `league.ts` maps the
league onto the engine's `setting` and `resolveLineupParameters` arguments with
the page's own clamps (a value the page would reject falls back to the
default). Nothing is written to Supabase; the settings space cannot grow the
warehouse. Cost is bounded instead: answers are kept in memory only (6 entries,
5-minute TTL, keyed by the mapped league), a fresh custom-league run is limited
to 10 per minute per IP, and the response holds only the player list, so its
size does not grow with the settings. `tests/test_endpoint_parity.py` compares
custom leagues against the page, and `tests/test_league_mapping.py` pins the
mapping and clamps. Deploy `get-values` before `mcp`; an `mcp` that sends
`league` to an older `get-values` would silently get default-lineup values.

## Configuration

| Name | Where | Default |
|---|---|---|
| `DDF_SITE_ORIGIN` | function secret (optional) | `https://jb-barrel-droid.github.io/fantasy-tools` |
| `DDF_API_URL` | MCP server env (required) | none |
| `DDF_SITE_URL` | MCP server env (optional) | the Pages URL |

`datadrivenfootball.com` did not resolve on 2026-10-19, so the Pages URL is the
default origin. Once the domain is live, set `DDF_SITE_ORIGIN` (no redeploy of
code needed, only the secret) and add the origin to `ALLOWED_ORIGINS` if it
differs.

## Deploy

`get-values` was found deployed on 2026-10-24 (project `iskiybsimubiujwuchsl`, version 2, `verify_jwt` false). Commands for a fresh project:

    supabase login
    supabase link --project-ref <PROJECT_REF>
    supabase functions deploy get-values --project-ref <PROJECT_REF>
    # optional, only after the custom domain is live:
    supabase secrets set DDF_SITE_ORIGIN=https://datadrivenfootball.com --project-ref <PROJECT_REF>

No other secrets are needed. URL: `https://<PROJECT_REF>.supabase.co/functions/v1/get-values`.

## Known limits

- The function evals the site's own `value-model.js` at cold start (loaded
  from the published origin, so the endpoint always matches the page).
- Rate limit is per instance, not global.
- Cold start fetches about 3.7 MB plus the history index (about 13 KB); a week
  document (about 70 KB) is fetched only when the week priced needs a saved
  copy. First call is slow, results cached 5 minutes per league and week.

## Remote MCP (JEG-1012)

For Claude.ai custom connectors, ChatGPT apps/developer mode and any MCP client
that needs a URL instead of a local process.

- Function: `supabase/functions/mcp/` (`index.ts` serves, `rpc.ts` is the
  JSON-RPC dispatch, `tools.ts` is the tool logic). Public (`verify_jwt = false`),
  POST only, no sessions, no SSE, 60 requests/min per IP per instance.
- It calls `get-values` (`DDF_API_URL` secret overrides the URL; default is
  `$SUPABASE_URL/functions/v1/get-values`), so tool numbers match the site.
- Tools: `get_values`, `get_player_value`, `trade_targets`, `compare_trade`,
  `read_state`, `make_state`, `find_trades`, `find_trades_league`, `explain`.
  Name lookup and trade math run server-side; each result also carries
  `structuredContent`. `risers_fallers` is not offered: the endpoint has no
  prior-week data.
- `find_trades`: takes two rosters (comma-separated names), finds trade packages
  where you gain DDF Value and at least 3 of 4 trade charts say the other team
  breaks even or wins. Each trade is scored on the 9 viability checks (see
  "Viability scoring" below) and labelled High/Med-High/Medium when viable.
  Optional: `max_per_side` (1-4, default 2), `min_rival_edge`, `limit`,
  `viable_only`, viability threshold overrides. Loads `finder.js` from the site
  (like the codec) and calls `get-values?include=charts` for per-chart values, passing the pasted `league` too (JEG-1070), so the finder prices the same league as `get_values`.
  The pure function `findTradesForPair` is in `mcp/find-trades.ts`.
- `find_trades_league`: takes your roster plus up to 15 opponents (each with a
  name and roster). Runs `find_trades` for each pair, scores all candidates on
  the 9 viability checks, ranks viable-first, and selects the best package
  (non-conflicting viable offers: no player sent twice, each opponent at most
  once). Returns ranked trades with labels/failure reasons/temporary-gap flags,
  the recommended package, and your projected lineup after. Optional:
  `max_per_side`, `min_rival_edge`, `limit`, `viable_only`, viability threshold
  overrides.
- **Week (JEG-1179):** every tool that prices players takes an optional `week`
  (passed to get-values; absent = the site's default week). `read_state` reads
  `wk=N` from a pasted site link; an explicit `week` wins. Every result carries
  `week`, `default_week`, `weeks`, `sources_included` and `missing_sources` in
  `structuredContent`, a "Week:" line after the settings line, and, when a
  week was asked for, `wk=N` on the site link. A week with no published sources
  comes back as a tool error with get-values' message. Tests:
  `tests/node/mcp_week_check.mjs` (`tests/test_mcp_week.py`).
- Both finder tools default to at most 10 candidates. Text lists up to five;
  structured candidates keep complete fit reasons. A reply may return a shorter
  ranked prefix to fit its UTF-8 budget (pair: 6,700 bytes for limits up to 10,
  17,000 above; league: 8,000 / 11,500). `shown` and the text report the actual
  count. The selected league package, its total edge and projected lineup stay
  intact. If even one candidate plus the complete envelope cannot fit, the tool
  returns a concise error asking for fewer opponents or shorter names.
- Opponent display names may repeat. League candidates, package offers and
  `perOpponent` entries include `opponent_index`, the zero-based index in the
  supplied `opponents` array. Identity follows this index through scoring and
  package selection, so equal names never share a roster.
- Tests: `tests/test_mcp_remote.py` (node, stub values, no network) in
  `make test-unit`.

Deploy: `supabase functions deploy mcp --project-ref <PROJECT_REF>`.
Connector URL: `https://<PROJECT_REF>.supabase.co/functions/v1/mcp`.

Not yet verified (2026-10-24): the deployed function against a real client,
and `deno check` on `index.ts` (no Deno in the build sandbox).

### Shared state with the site (JEG-1027)

Spec: `design/llm-site-state.md`. Every tool takes an optional `state` (a pasted `ddf-state` block, JSON or site link) that supplies the league; explicit arguments win. Every result ends with a link to the same view on the site (`/#compare-trade?...`, `/#trade-targets?...`, `/#find-trade?...`) and returns the state in `structuredContent.state`. `read_state` resolves a pasted state to players and prices them; `make_state` turns names from the chat into a block and link for the site.

- The function loads the codec `app/v2/ddf-state.js` from `<site>/v2/ddf-state.js` at cold start (published by the v2 build). If that fails, tools answer from their plain arguments and say the pasted state was not read.
- **Custom leagues (JEG-1031):** `get-values` prices the whole pasted league (roster shape, position shares, season weeks, advanced settings), so the tools no longer add a "default lineup" note.
- **Site side:** compare links open today (`give`, `get`, `scoring`, `roster`...). `teams`, `mine`, `theirs` and `target` are read by the site in JEG-1026; until then those links open the right tab with the league settings the site already understands.

### Viability scoring (JEG-1038)

`mcp/viability.ts` — pure module, no I/O. Scores and ranks trade offers by
viability. Used by `find_trades` (single pair) and the batch league tool.
The site's `finder.js` can load the same logic later.

**Per-offer output (`ScoredOffer`):**

| Field | Type | Description |
|---|---|---|
| `team` | string | Opponent team name |
| `userGives` / `userGets` | `[{player_key, name, pos, ddfValue}]` | Players traded |
| `ddfEdge` | number | DDF Value gain (receive − give) for the user |
| `userLineupDelta` | number | User's starting lineup value change on DDF |
| `theirMarketNet` | number | Other team's market-value net (what they get − give) |
| `theirLineupDelta` | number | Other team's lineup change on market value |
| `theirPositionsBefore` / `After` | `{pos: {starters, value}}` | Their starters at each position, before/after |
| `userProtectedAfter` | `{pos: {starters, value}}` | User's starters at guardrail positions, after |
| `viable` | boolean | All 9 checks passed |
| `label` | `"High" \| "Med-High" \| "Medium" \| null` | Acceptance likelihood (null when non-viable) |
| `failedChecks` | `string[]` | Human-readable failure reasons |
| `temporaryGap` | boolean | Either team cannot fill a starting slot while injured players are out |
| `checks` | `CheckResult[]` | All 9 checks with name, passed, detail |

**Viability checks (all run on every offer):**

1. **Arbitrage**: user receives more DDF value than sent.
2. **Perceived fairness**: other team receives >= what it sends on market value.
3. **User lineup improves**: user's starting lineup strictly improves on DDF value (> 0, not break-even). (Jeremy 2026-10-24.)
4. **Their lineup improves**: other team's starting lineup strictly improves on market value (> 0). (Jeremy 2026-10-24.)
5. **Position protection**: other team's resulting starting lineup total market value must not decrease. Empty slots filled at replacement level (0), so a real hole shows as a value loss. Per-position before/after starters are display-only, not pass/fail. (Jeremy 2026-10-24: dropped per-position 15% weaker test.)
6. **Depth**: neither team lacks healthy relevant players for starting slots plus backups at RB/WR.
7. **Roster space**: a team taking more players than it sends must have dead weight to drop.
8. **QB kept**: both teams keep a QB.
9. **User guardrails**: user-defined position protections are satisfied.

**Ordering:** viable first (by DDF edge, then user lineup improvement, then
perceived fairness). Non-viable follow (fewest failed checks, then DDF edge).
Deduplicated by received players.

**Labels:** High = a position they give up actually gets better and their lineup
clearly improves; Med-High = their lineup or perceived value clearly improves;
Medium = fair swap with small gain for them.

**Package (`selectPackage`):** across all added teams, the best combination of
viable offers that never sends the same player twice and uses each team at most
once. Output includes the user's lineup after the package.

**Configurable defaults (awaiting Jeremy's review):**

| Parameter | Default | Description |
|---|---|---|
| `minDdfEdge` | 0 | Minimum DDF value gain for the user |
| `minMarketNet` | 0 | Minimum market-value gain for the other team |
| `minUserLineupGain` | 0 | Minimum user lineup improvement |
| `minTheirLineupGain` | 0 | Minimum their lineup improvement |
| `positionWeakerThreshold` | 0.15 | _(Unused, kept for compat. Per-position test removed 2026-10-24.)_ |
| `depthPlayerCutoff` | 0.5 | Minimum DDF value for a player to count as depth _(pending Jeremy's answer)_ |
| `deadWeightCutoff` | 0.5 | Maximum DDF value for a player to be considered droppable _(pending Jeremy's answer)_ |
| `minRbBackups` | 1 | Minimum healthy RB backups beyond starters |
| `minWrBackups` | 0 | Minimum healthy WR backups beyond starters (Jeremy 2026-10-28: lowered from 1, JEG-1129) |
| `guardrails` | `[]` | User-defined position protections |
