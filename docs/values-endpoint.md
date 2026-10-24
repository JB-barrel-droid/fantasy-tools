# Values endpoint (Supabase edge function `get-values`) and MCP server

Ticket JEG-616. Hosting decision: Supabase edge function (Jeremy, 2026-10-19).

- Function: `supabase/functions/get-values/index.ts`. Reads the published site
  (`value-model.js`, `lineup-parameters.json`, the comparison bundle, and the
  `players-data` island on the home page), runs `runValuePipeline`, returns
  blended values. No database access, no schema change, no service-role key.
- Public: `verify_jwt = false` in `supabase/config.toml`; per-IP rate limit
  (30/min, in memory per instance); CORS allow-list in the function.
- Parity with the page is pinned by `tests/test_endpoint_parity.py`.
- MCP server, local: `mcp-server/` (stdio), set `DDF_API_URL` to the function URL.
- MCP server, remote (JEG-1012): `supabase/functions/mcp/` (Streamable HTTP, stateless, JSON responses). See "Remote MCP" below.

## Request

`GET|POST /functions/v1/get-values` with `scoring` (standard|half_ppr|ppr),
`teams` (8|10|12|14), `superflex` (0|1).

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
- Cold start fetches about 3.7 MB; first call is slow, results cached 5 minutes.

## Remote MCP (JEG-1012)

For Claude.ai custom connectors, ChatGPT apps/developer mode and any MCP client
that needs a URL instead of a local process.

- Function: `supabase/functions/mcp/` (`index.ts` serves, `rpc.ts` is the
  JSON-RPC dispatch, `tools.ts` is the tool logic). Public (`verify_jwt = false`),
  POST only, no sessions, no SSE, 60 requests/min per IP per instance.
- It calls `get-values` (`DDF_API_URL` secret overrides the URL; default is
  `$SUPABASE_URL/functions/v1/get-values`), so tool numbers match the site.
- Tools: `get_values`, `get_player_value`, `trade_targets`, `compare_trade`,
  `explain`. Name lookup and trade math run server-side; each result also
  carries `structuredContent`. `risers_fallers` is not offered: the endpoint
  has no prior-week data.
- Tests: `tests/test_mcp_remote.py` (node, stub values, no network) in
  `make test-unit`.

Deploy: `supabase functions deploy mcp --project-ref <PROJECT_REF>`.
Connector URL: `https://<PROJECT_REF>.supabase.co/functions/v1/mcp`.

Not yet verified (2026-10-24): the deployed function against a real client,
and `deno check` on `index.ts` (no Deno in the build sandbox).

### Shared state with the site (JEG-1027)

Spec: `design/llm-site-state.md`. Every tool takes an optional `state` (a pasted `ddf-state` block, JSON or site link) that supplies the league; explicit arguments win. Every result ends with a link to the same view on the site (`/#compare-trade?...`, `/#trade-targets?...`, `/#find-trade?...`) and returns the state in `structuredContent.state`. `read_state` resolves a pasted state to players and prices them; `make_state` turns names from the chat into a block and link for the site.

- The function loads the codec `app/v2/ddf-state.js` from `<site>/v2/ddf-state.js` at cold start (published by the v2 build). If that fails, tools answer from their plain arguments and say the pasted state was not read.
- **Pricing limit:** `get-values` prices only scoring, teams and superflex. A pasted league with a roster shape, position shares, season weeks or advanced settings is priced with the site's default lineup, and the result says so (JEG-1029 tracks pricing the full league).
- **Site side:** compare links open today (`give`, `get`, `scoring`, `roster`...). `teams`, `mine`, `theirs` and `target` are read by the site in JEG-1026; until then those links open the right tab with the league settings the site already understands.
