## 2026-11-02 - JEG-1458 ingest harness correction

Contract: repair the additional ingest harness failures exposed by Preview
shard 3 on `95fd8fa0`, preserving the real workflow's dry/write behavior.

### Verified (check named)
- CI job `125062132905` failed `test_real_workflow` and
  `test_dropping_the_dry_run_flag_is_caught`: the harness omitted step env
  bindings and still mutated the pre-array dry-run string.
- The harness now renders the real step environment with no secret values,
  mutates the current Bash array expression, and records argument boundaries.
  A literal URL containing spaces, `&` and shell syntax remains one argument
  for each of the three sources under the fake Python executable.
- `python3 -m unittest tests.test_trade_chart_ingest_ci
  tests.test_supabase_bytes_rollup
  tests.test_rebuild_chain_consolidation_nonblocking`: 48 tests pass.
- Checking related offline workflow contracts also exposed Razzball's harness
  omitting the same step environment. It now reads the declared environment;
  dry/write expectations and failure mutations are unchanged. The ESPN weekly,
  CBS ROS and Sunday projection contracts passed in that check.

### Claimed, not confirmed
- Fresh final-head CI and independent review remain for the ticket handoff.
  No workflow behavior changed in this correction.
