## 2026-10-22 - JEG-882 Research post 7: does the market gap predict anything

Contract: backtest the Trade targets Buy / Sell gap against the saved weekly
chart history (weeks 2 to 7) and realised points, write the post, the script
and its outputs, and put the product decisions to Jeremy as choices.

Branch `docs/research-post7-gap` (worktree from origin/main cc576e7). Files:
`tools/research/gap_backtest.py`, `docs/research/data/gap_backtest.{json,csv,md}`,
`docs/research/posts/07-does-the-gap-predict.md`, README row.

### Verified (check named)
- `python3 tools/research/gap_backtest.py` runs in about 37 s on the system
  python3 (3.9.6) with numpy 2.0.2, no network, and writes the three outputs.
- Self-test inside the script: week 7 re-priced from `data/history/week-7.json`
  with the Python reference (`pipelines/value_reference.py`,
  value-reference-002/2) matches the reference's live run for 2026-10-22 on
  3,670 values with max abs diff 0.0000, once the held FantasyCalc section is
  read from the served version (the chain held FantasyCalc red that day; the raw
  week-7 snapshot differs from the served section on 192 of 198 values and gives
  a DDF Value max diff of 0.32).
- Signal rebuilt from `app/v2/targets.js` (marketConsensus lines 95-117,
  rankEquivalents 64-84, buildTargets 131-193) and spot-checked by reading the
  code; no engine-vs-script parity test of the lists exists (see Claimed).
- Headline figures (Full PPR, 12 teams, DDF Value blend, weeks 2-6 predicting
  3-7, 1,023 player-weeks, 239 players): Spearman gap vs next-week consensus
  change -0.15 [-0.22, -0.09]; vs our value +0.01; placebo (consensus own prior
  move) +0.18; Sell listed 65% fell (base 55%, n=142); Buy listed 66% rose (base
  45%, n=47); actuals vs projection -0.01 [-0.09, +0.07] (n=883). All 12
  settings: -0.10 to -0.17, intervals excluding zero. Projections-only DDF
  Value: -0.22 on consensus, +0.21 on our value (both converge).
- Live build tag read from https://jb-barrel-droid.github.io/fantasy-tools/ on
  2026-10-22: `tv-20261022-1627-fee76c6`. `gh pr view 814 --json state`: OPEN
  (DDF Value still the blend).
- `python3 -m unittest tests.test_doc_staleness`: passes (README Maintained
  rows unchanged).
- numpy 2.0.2 on this Mac raises spurious "divide by zero in matmul" warnings
  for `@` on plain float arrays; `np.dot` does not. The script uses `np.dot`.

### Claimed, not confirmed
- The browser engine's Trade targets lists equal the script's rebuilt lists
  for week 7. The reference matches the engine's values (value_check), and the
  script follows targets.js line by line, but no headless run of
  `buildTargets` was diffed against the script (DISK IS TIGHT; no dist history
  built). A parity harness would promote this.
- Interpretation that the placebo's positive sign is charts updating at
  different speeds (momentum across charts) rather than something else.
- The sweep's intervals use 200 bootstrap draws (the default setting uses
  1,000), so the sweep CIs are coarser.
