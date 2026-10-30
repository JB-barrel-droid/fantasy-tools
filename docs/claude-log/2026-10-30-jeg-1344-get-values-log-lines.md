## 2026-10-30 - JEG-1344 (part of JEG-1061): get-values log lines

Contract: add the log lines Jeremy asked for on Oct 25 ("log fresh custom-league computes and
rate-limited requests, revisit at launch") without changing the limiter, cache or policy. Stacked on
#1124 (JEG-1225), with a normal main merge that clears #1124's conflict with #1156.

### Verified (check named)
- Before the hook (tree `2027b305`, #1124 + main): `node --experimental-strip-types --no-warnings
  tests/node/jeg_1061_logging_contract.mjs dist` exits 1 with the 5 recorded violations. After: exit 0,
  all 5 scenarios pass.
- `jeg_1061_logging_contract.mjs --self-test`: correct log accepted, 21 mutations caught.
- `python3 -m unittest tests.test_jeg_1061_logging_contract tests.test_league_mapping
  tests.test_get_values_value_context`: OK, with `expected_failures_before_hook.json` set to `[]`.
- Node checks `get_values_rate_limit_check`, `get_values_value_context_check`,
  `get_values_handler_check`, `get_values_week_check`: ok.
- The main merge (`2027b305`): `tests.test_ddf_value_link`, `test_get_values_value_context`,
  `test_connector_analyses`, `test_build_v2_page`, `test_mcp_week` OK; `test_endpoint_parity` OK with its
  browser case skipped (no Chromium here).
- `make validate`: see the PR for its result on this head.

### Claimed, not confirmed
- The browser parity case and the render suites run only in CI.
- Live log lines: not checked. That needs a `get-values` deploy, which waits on Jeremy's named yes
  after #1124 and this PR merge.
