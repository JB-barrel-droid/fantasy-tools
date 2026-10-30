## 2026-10-30 - JEG-1061 shared get-values compute limit (off by default)

Contract: make the get-values 10/min fresh-compute limit hold across function instances, as a two-way door that
changes nothing live until Jeremy approves the migration, the deploy and the switch. Branch
`claude/JEG-1061-shared-limit`, PR #1224. Jeremy picked A (2026-10-30 20:19 UTC): merge on green, still switched off.

### Verified (check named)
- On main, two handler instances each count alone: `tests/node/get_values_shared_rate_limit_check.mjs` fails on main's
  `index.ts` with "11th compute from one key across two instances must be a 429" and passes on this branch.
- Shared on: one count across instances; a second key has its own budget; the bucket is an HMAC under the service key,
  not the IP or a plain SHA-256 (same node check, cases 1, 2, 6).
- Database failure, database up then down mid-minute, a 50 ms timeout: the in-memory count decides and a
  `get_values.rate_limit_fallback` line is logged with no IP (node check cases 3, 4, 6). The pre-review `rate-limit.ts`
  (9ec29cf) fails these cases.
- Secret off, or no URL or service key: no database call, behaviour as before (node check cases 5, 6).
- Migration on a local Postgres 16 with Supabase-style default grants and a bypassrls service_role: 10 hits pass, the
  11th fails, the window resets, anon and authenticated are denied on the function and the table (removing the table
  revoke makes that test fail), bad arguments refused, argument names match `rate-limit.ts`, rollback removes both,
  re-apply works (`tests.test_jeg1061_shared_rate_limit`, 8 OK).
- No regressions in `tests.test_league_mapping`, `tests.test_jeg_1061_logging_contract`,
  `tests.test_edge_functions_parse` on the tree merged with main at 374dc8f.
- Independent Claude review: REQUEST CHANGES at 858e162 (6 findings), delta PASS at 23e75ca; receipt on PR #1224. Its own
  check on a local Postgres: 60 parallel calls on one bucket gave exactly 10 allowed.

### Claimed, not confirmed
- The migration is NOT applied and get-values is NOT deployed with this code; nothing here ran against the live
  Supabase project. PostgREST returning the boolean bare and the service_role bypassing RLS are taken from Supabase
  behaviour, not checked live.
- Not turned on: the connector (`mcp`) calls get-values without a client address, so with the switch on every
  connector user would share one 10/min budget (JEG-1392 must land first).
- Turning it on needs Jeremy's yes to each of: apply `jeg1061_shared_rate_limit_20261030`, deploy get-values, set
  `DDF_SHARED_RATE_LIMIT=1`; then check the function logs for a 429 on the 11th compute from one key. Off: unset the
  secret (warm instances keep it until they recycle); rollback `supabase/rollbacks/jeg1061_shared_rate_limit_rollback_20261030.sql`.
