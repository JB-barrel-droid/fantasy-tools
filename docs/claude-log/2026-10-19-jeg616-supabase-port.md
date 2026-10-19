# JEG-616: Supabase edge function wiring (follow-up to PR 644)

**Date:** 2026-10-19. **Branch:** `jeg-616-supabase-deploy-config`.
Decision (Jeremy, 2026-10-19): host on Supabase, not Cloudflare.

PR 644 had already merged the function and MCP server; this adds the wiring.

## Changed
- `supabase/config.toml`: `verify_jwt = false` for `get-values` (public, no keys).
- Function: site origin now `DDF_SITE_ORIGIN` secret, default the Pages URL,
  because `datadrivenfootball.com` did not resolve on 2026-10-19 (the merged
  code would have failed every request). Pages origin added to CORS. Fixed a
  `deno check` type error. Attribution link uses the configured origin.
- MCP server: no default to the non-existent `/api/values`; `DDF_API_URL` is
  required and errors clearly; site link configurable.
- `docs/values-endpoint.md`: config, deploy commands, limits.

## Verified
- `deno check` on the function: clean. `npx tsc --noEmit` in `mcp-server`: clean.
- Ran the function locally under `deno run` against the live Pages site:
  ppr/12 returned values (as_of 2026-10-19, Gibbs 71.8); `scoring=bad` gave 400.

## Not verified
- `tests/test_endpoint_parity.py`: 1 passed (negative), 4 errored on Playwright
  (browser not installed here), so parity was not re-run. No value math changed.
- Not deployed; no secrets set. Cold-start latency and edge CPU/memory limits
  on Supabase are untested.
