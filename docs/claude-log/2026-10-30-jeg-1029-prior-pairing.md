## 2026-10-30 - JEG-1029: prior-week pairing when an included source has no Week N-1 (PR #1156 review finding)

Contract: fix the Codex P2 finding at `supabase/functions/get-values/analysis.ts` priorBlock. When an
included source had no Week N-1 snapshot, the prior run dropped it but `current_values` still came from
get-values' full run, so risers_fallers reported a change of source membership as a change of value.
Port VP-1.2 as the page does it (curve-widget.js computePipeline: this week is run on I, the sources
with a prior-week snapshot; weekPipeline: the prior week on I with that run's pie).

### Verified (check named)
- New test `tests.test_connector_analyses.ConnectorAnalysesParity.test_unpaired_source_prior_pairs_on_included_set`
  (FantasyCalc's Week 7 entry left out of the history, through the runner's new `--drop-entry 7:fantasycalc`
  and the same deletion on value_reference's History) fails on 8e17e8d0 (`current ddf_value ...: edge ...,
  reference ...` mismatches) and passes after the fix.
- Reference parity in that scenario: every DDF version's prior values and current_values, and every
  available source series' prior values and current_values, match `value_reference` (prior_result() and
  rows(), which run on I) to 1e-6; risers_fallers' answer equals movers.js on the reference's pair
  (same test).
- Josh Allen, ppr 12 teams, FantasyCalc's Week 7 dropped: DDF Value Δ was 31.16 - 26.54 = +4.62 on the
  old code (the full run's value against a prior on I); now 26.12 - 26.54 = -0.42, the reference's pair
  (scratch run of the edge runner and value_reference).
- When every included source has a Week N-1 entry the answer is byte-identical to 8e17e8d0: the runner's
  `--include series,prior,audit` output for ppr 12/0, half_ppr 10/1, standard 14/0 compared with `cmp`.
- `python3 -m unittest tests.test_connector_analyses tests.test_connector_inventory` OK (inventory's one
  expected failure is the existing open-routes marker); `tests.test_mcp_week tests.test_endpoint_parity` OK.
  The Makefile runs no deno check for get-values; none run.

### Claimed, not confirmed
- The deployed function behaves as the runner does (it imports the same analysis.ts); not deployed or
  checked live.
- Out of scope and unchanged: in the same scenario get-values' own values (the `values` answer, the
  series and audit blocks) are still the full run, because buildPipelineInput does not apply the VP-1.2
  pairing the page applies to its current run (195 players' DDF Value differ from the reference's rows at
  ppr 12/0 with FantasyCalc's Week 7 dropped). Needs its own ticket if the page parity is to hold there.
