## 2026-10-23 - DDF Value: predictive aggregation research (JEG-943)

Branch: `research/ddf-predictive-aggregation`. PR pending.

### What was done

1. **Data inventory.** Catalogued all projection history, actuals, and identity
   data in the repo. Critical gap: no CBS ROS or Razzball week-ahead projections
   are stored. ESPN weekly exists (2026 wk 1-7). RotoWire/Sleeper weekly exists
   (2018-2026) but identity mapping to player_key is incomplete.

2. **Evaluation protocol.** Defined targets (week-ahead PPR ppg + ROS value
   above waivers), rolling-origin splitting, metrics (MAE, RMSE, rank
   correlation, calibration), baselines, and bootstrap CIs. Stratified by
   early/mid/late season per Jeremy's note on declining bench value.

3. **Candidate aggregators.** Documented 11 methods from equal-weight mean
   through stacking, with data requirements and overfit risk for each.

4. **Preliminary backtest.** Ran `tools/research/source_accuracy_backtest.py`
   on ROS projections vs 2026 week 2-6 actuals (PPR). 1,655 player-weeks.

5. **Decay section.** Added as a first-class deliverable: what decays, over
   what horizon, per position, and relation to the ROS target. Checked post 1
   revision (PR #846) for conflicts -- none found.

6. **Research article draft.** `docs/research/posts/10-how-ddf-value-should-be-built.md`.

7. **Internal plan.** `docs/research/ddf-predictive-plan.md`.

8. **Linear tickets.** JEG-943 (umbrella), JEG-944 (store snapshots),
   JEG-945 (backtest), JEG-946 (research post 10).

### Verified (check named)

- Backtest script: all numbers in post 10 and the plan doc come from one run of
  `source_accuracy_backtest.py` (output in `docs/research/data/source_accuracy_backtest.json`
  and `.md`). No manual numbers.
- Equal-weight mean MAE (4.609) vs inverse-error weighted MAE (4.612): difference
  is 0.003, within noise. Verified by reading the JSON output.
- Source availability per week: weeks 2-3 missing CBS ROS (week 2 also missing
  Razzball). Verified by reading `data/history/week-N.json` for N=2..7.
- Post 1 revision (PR #846, branch `research/post1-revision`): read the full
  revised post. It does not define a decay function; mentions "mid-season
  improvement not modeled" as a limitation. No conflict with post 10.

### Claimed, not confirmed

- That the 95% CI overlap between sources means the true ranking could reverse
  with more data. (Statistical truism, not testable on current data.)
- That CBS ROS and Razzball publish scrapeable week-ahead projections. (Not
  verified; if they do not, this is a risk.)
- That the Sleeper/RotoWire identity mapping covers enough players to be useful.
  (Coverage not measured; listed as a gap.)
