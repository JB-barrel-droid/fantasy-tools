## 2026-10-29 - JEG-1047 waiver line pinned to one player (research)

Contract: confirm that one fringe player's projection sets each position's
waiver line on the projection legs, measure it on the 12-combo grid for ESPN,
CBS ROS and Razzball, and compare candidate line rules for Jeremy. Research
only: no value math, default, ranking or feed changed.

### Verified (check named)
- Mechanism: `pipelines/value_reference.py` `_source_lines` sets
  `w = work[n_rost][1]`; `app/trade-value-chart/assets/value-model.js` sets
  `waiver = work[N].native` (read in code).
- All 144 projection lines (3 scorings x 4 team counts x 3 sources x 4
  positions) are `roster_determined` at this build
  (`tools/research/jeg1047_waiver_anchor.py`, no skipped cells).
- 1 PPG change to the waiver-line player only: median 18 other players move,
  worst 3.2 points, 19% of cases move someone > 1.0 point; top-player control
  worst 1.3 (same script, readout `docs/research/data/jeg1047_waiver_anchor.md`).
- Median band equals the current rule on every case (same script; follows
  from the median of a sorted centred window being its centre).
- Average band (7 players) passes a 1.0 point tolerance on all 288 +/-1 PPG
  cases; switching at 12-team PPR moves 24 of 739 DDF Projections values
  (max 0.26) and 23 DDF Value values (max 0.24) (scratch run of the same
  harness, current vs avg_band_3).
- Production files untouched: `git diff --stat origin/main` lists only the new
  research script, docs and this log.

### Claimed, not confirmed
- The JS engine moves the same way as the reference (parity tests hold them
  together, but the harness ran only the reference).
- CBS ROS and Razzball were held (publisher_vs_stored) at run time; their
  figures use the stored projections.
